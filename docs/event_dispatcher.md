# Event Dispatcher — Inter-domain communication via internal events

## Problem

The project architecture separates features into independent domains (`auth`, `ticket`, `live_chat`, `chatbot`). This works well while each domain operates in isolation, but some business actions trigger consequences in other domains:

- Finishing a triage needs to create a ticket and open a conversation.
- Closing a ticket needs to end the conversation and request an attendance evaluation.
- Deactivating a user might need to terminate active sessions and revoke tokens.

The most intuitive approach — injecting services from other domains — creates problems as the system grows:

- **Growing coupling**: each new side effect requires changing the signature and body of the originating service.
- **Circular dependencies**: the day two domains need to react to each other's actions, the import graph breaks.
- **Responsibility violation**: the service that performs the action ends up knowing details of all affected domains.

## When to use events vs. direct injection

Not every cross-domain interaction should be an event. The distinction is simple:

| Scenario | Mechanism | Example |
|---|---|---|
| The caller **needs the result** to proceed | Service injection | Chatbot queries `UserService` to validate user existence before opening triage |
| The caller **just notifies something happened** and does not depend on the consequence | Event | Finished triage triggers ticket and conversation creation |

**Guiding questions:**

- "Do X **and then** Y with the result" → direct injection.
- "When X happens, **react**" → event.
- "Adding a new behavior requires changing the originating service?" → if yes, it should be an event.

## Solution: In-process EventDispatcher

An async lightweight dispatcher implemented in `app/core/event_dispatcher/`. No external infrastructure (Kafka, Redis, RabbitMQ) — just in-process coordination with `asyncio`.

### Structure

```
app/core/event_dispatcher/
├── __init__.py          # Re-exports: EventDispatcher, get_event_dispatcher, EventDispatcherDep
├── enums.py             # AppEvent enum (event catalog)
├── schemas.py           # DispatcherSchema base, typed payloads, EVENT_PAYLOAD_MAP
├── exceptions.py        # EventSchemaError, InvalidHandlerError
├── decorators.py        # @event_handler decorator
├── metrics.py           # Prometheus counters and histograms
└── event_dispatcher.py  # EventDispatcher (subscribe, publish), get_event_dispatcher
```

## Event catalog

| Event | Enum | Emitter | Payload | Listeners |
|---|---|---|---|---|
| `triage.finished` | `TRIAGE_FINISHED` | `ChatbotService` | `TriageFinishedEventSchema` | `TicketListener` — creates ticket, publishes `ticket.created` |
| `ticket.created` | `TICKET_CREATED` | `TicketListener` | `TicketCreatedEventSchema` | `ConversationListener` — opens first support conversation |
| `ticket.assignee_updated` | `TICKET_ASSIGNEE_UPDATED` | `TicketService` | `TicketAssigneeUpdatedEventSchema` | `ConversationListener` — updates participants in active conversation |
| `ticket.status_updated` | `TICKET_STATUS_UPDATED` | `TicketService` | `TicketStatusUpdatedEventSchema` | `ConversationListener` — updates message history with system message; `ChatbotService` — updates attendance status |
| `ticket.escalated` | `TICKET_ESCALATED` | `TicketService` | `TicketEscalatedEventSchema` | `ConversationListener` — opens new conversation linked to ticket |
| `ticket.closed` | `TICKET_CLOSED` | `TicketService` | `TicketClosedEventSchema` | `ConversationListener` — closes active conversation; `ChatbotListener` — closes attendance and requests evaluation |

## Event payloads

### `triage.finished`

| Field | Type | Description |
|---|---|---|
| `client_id` | `UUID` | Client ID in the auth domain |
| `client_email` | `str` | Client email |
| `client_name` | `str` | Client name |
| `company_id` | `UUID \| None` | Company ID (optional) |
| `company_name` | `str \| None` | Company name (optional) |
| `attendance_id` | `PydanticObjectId` | Attendance/triage ID |
| `ticket_type` | `TicketType` | Ticket type (`issue`, `access`, `new_feature`) |
| `ticket_criticality` | `TicketCriticality` | Criticality (`high`, `medium`, `low`) |
| `product_name` | `str` | Product name |
| `ticket_description` | `str` | Problem description |

### `ticket.created`

| Field | Type | Description |
|---|---|---|
| `ticket_id` | `PydanticObjectId` | Newly created ticket ID |
| `client_id` | `UUID` | Client ID |
| `agent_id` | `UUID \| None` | Assigned agent (None if awaiting assignment) |

### `ticket.assignee_updated`

| Field | Type | Description |
|---|---|---|
| `ticket_id` | `PydanticObjectId` | Ticket ID |
| `new_agent_id` | `UUID` | New responsible agent |
| `reason` | `str \| None` | Reassignment reason |

### `ticket.status_updated`

| Field | Type | Description |
|---|---|---|
| `ticket_id` | `PydanticObjectId` | Ticket ID |
| `new_status` | `TicketStatus` | New ticket status |

### `ticket.escalated`

| Field | Type | Description |
|---|---|---|
| `ticket_id` | `PydanticObjectId` | Ticket ID |
| `new_agent_id` | `UUID \| None` | Agent at the new level (None if pending) |
| `new_agent_name` | `str \| None` | New agent name |
| `new_level` | `str` | Target support level |
| `transfer_reason` | `str \| None` | Escalation reason |

### `ticket.closed`

| Field | Type | Description |
|---|---|---|
| `ticket_id` | `PydanticObjectId` | Ticket ID |
| `triage_id` | `PydanticObjectId` | Original triage ID |
| `client_id` | `UUID` | Client ID |

## Chained event flow

```
triage.finished
  └─ TicketListener creates ticket
       └─ publishes ticket.created
            ├─ ConversationListener creates conversation
            └─ (future) NotificationListener notifies agent
```

The conversation depends on `ticket_id`, which only exists after ticket creation. Therefore `ConversationListener` reacts to `ticket.created`, not `triage.finished`.

## Rules

- Services never import models or repositories from other domains.
- The dispatcher is fire-and-forget: `publish` schedules each handler as an `asyncio.Task` and returns immediately.
- All handlers must use the `@event_handler` decorator. `subscribe` rejects undecorated handlers with `InvalidHandlerError`.
- Handler subscription is idempotent — subscribing the same handler to the same event twice has no effect.
- The `@event_handler` decorator catches and logs exceptions automatically. An unhandled exception does not affect the emitter or other handlers.
- Listeners live in `listeners.py` inside each domain.
- Event names follow the pattern `{domain}.{past_action}`.
- Every event payload must be documented in this file when created.

## Adding a new event

1. Add the member to the `AppEvent` enum in `enums.py`.
2. Create the corresponding schema (inherits from `DispatcherSchema`) in `schemas.py`.
3. Add the entry to `EVENT_PAYLOAD_MAP`.
4. Document the event in this file (catalog table + payload fields).
5. Create the handler in the `listeners.py` of the reacting domain.
6. Register the handler in the domain's `register_*_listener`.
