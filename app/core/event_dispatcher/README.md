# Event Dispatcher

Asynchronous in-process communication between domains via internal events.

## Problem

Some business actions trigger consequences in other domains. Direct service injection creates growing coupling, circular dependencies, and responsibility violations. The Event Dispatcher decouples the emitter from consumers: whoever publishes the event does not know (and does not need to know) who reacts.

## When to use events vs. direct injection

| Scenario | Mechanism | Example |
| --- | --- | --- |
| The caller **needs the result** to proceed | Service injection | Chatbot queries `UserService` to validate user existence |
| The caller **just notifies something happened** | Event | Finished triage triggers ticket creation |

## Structure

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

## Public API

### `EventDispatcher`

```python
from app.core.event_dispatcher import EventDispatcher, get_event_dispatcher

dispatcher = get_event_dispatcher()  # singleton via @lru_cache
```

For FastAPI route injection, use `EventDispatcherDep`:

```python
from app.core.event_dispatcher import EventDispatcherDep

@router.post("/tickets/{ticket_id}/close")
async def close_ticket(dispatcher: EventDispatcherDep):
    ...
```

#### `subscribe(event: AppEvent, handler: EventHandler) -> None`

Subscribes a handler to react to an event. Subscription is idempotent — subscribing the same handler twice has no effect.

Validates at registration time that:
1. The handler is decorated with `@event_handler` — raises `InvalidHandlerError` otherwise.
2. The handler's declared payload types are compatible with the event's expected schema — raises `InvalidHandlerError` on mismatch.

This ensures wiring errors are caught **at application startup**, not at runtime.

#### `publish(event: AppEvent, payload: DispatcherSchema) -> None`

Emits an event. Validates that the payload matches the expected type via `EVENT_PAYLOAD_MAP`. Each subscribed handler is fired as an independent `asyncio.Task` (fire-and-forget).

```python
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.schemas import TriageFinishedEventSchema

await dispatcher.publish(
    AppEvent.TRIAGE_FINISHED,
    TriageFinishedEventSchema(
        client_id=client_id,
        client_email="user@example.com",
        client_name="User",
        attendance_id=attendance_id,
        ticket_type="issue",
        ticket_criticality="high",
        product_name="Product A",
        ticket_description="Error generating invoice",
    ),
)
```

### `@event_handler` decorator

All handlers must be decorated with `@event_handler`. The decorator:
- Declares which payload types the handler accepts (used by `subscribe` for validation).
- Wraps the handler body in `try/except` with structured logging — handlers do not need manual error handling.
- Raises `EventSchemaError` at call time if the payload type does not match the declared types.

```python
from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.schemas import TriageFinishedEventSchema

@event_handler(TriageFinishedEventSchema)
async def on_triage_finished(self, payload: TriageFinishedEventSchema) -> None:
    ...
```

### Payload validation

`publish` validates that the payload is an instance of the expected schema for the event via `EVENT_PAYLOAD_MAP`. If the type does not match, it raises `EventSchemaError`:

```python
# This raises EventSchemaError:
await dispatcher.publish(AppEvent.TRIAGE_FINISHED, TicketClosedEventSchema(...))
```

Field validation is performed by Pydantic at schema construction time, before `publish` is called.

## Event catalog

### `triage.finished`

Emitter: `ChatbotService`

Payload: `TriageFinishedEventSchema`

| Field | Type | Description |
| --- | --- | --- |
| `client_id` | `UUID` | Client ID in the auth domain |
| `client_email` | `str` | Client email |
| `client_name` | `str` | Client name |
| `company_id` | `UUID \| None` | Company ID (optional) |
| `company_name` | `str \| None` | Company name (optional) |
| `attendance_id` | `PydanticObjectId` | Attendance/triage ID |
| `ticket_type` | `str` | Ticket type (`issue`, `access`, `new_feature`) |
| `ticket_criticality` | `str` | Criticality (`high`, `medium`, `low`) |
| `product_name` | `str` | Product name |
| `ticket_description` | `str` | Problem description |

Listeners:
- **TicketListener** — creates a ticket and publishes `ticket.created`

### `ticket.created`

Emitter: `TicketListener` (in reaction to `triage.finished`)

Payload: `TicketCreatedEventSchema`

| Field | Type | Description |
| --- | --- | --- |
| `ticket_id` | `PydanticObjectId` | Newly created ticket ID |
| `client_id` | `UUID` | Client ID |
| `agent_id` | `UUID \| None` | Assigned agent (None if awaiting assignment) |

Listeners:
- **ConversationListener** — opens the first support conversation

### `ticket.assignee_updated`

Emitter: `TicketService` (assign or transfer)

Payload: `TicketAssigneeUpdatedEventSchema`

| Field | Type | Description |
| --- | --- | --- |
| `ticket_id` | `PydanticObjectId` | Ticket ID |
| `client_id` | `UUID` | Client ID |
| `new_agent_id` | `UUID` | New responsible agent |
| `reason` | `str \| None` | Reassignment reason |

Listeners:
- **ConversationListener** — updates participants in the active conversation

### `ticket.escalated`

Emitter: `TicketService`

Payload: `TicketEscalatedEventSchema`

| Field | Type | Description |
| --- | --- | --- |
| `ticket_id` | `PydanticObjectId` | Ticket ID |
| `client_id` | `UUID` | Client ID |
| `new_agent_id` | `UUID \| None` | Agent at the new level (None if pending) |
| `new_agent_name` | `str \| None` | New agent name |
| `new_level` | `str` | Target support level |
| `transfer_reason` | `str \| None` | Escalation reason |

Listeners:
- **ConversationListener** — opens a new conversation linked to the ticket

### `ticket.status_updated`

Emitter: `TicketService`

Payload: `TicketStatusUpdatedEventSchema`

| Field | Type | Description |
| --- | --- | --- |
| `ticket_id` | `PydanticObjectId` | Ticket ID |
| `new_status` | `str` | New ticket status |

### `ticket.closed`

Emitter: `TicketService` (when status transitions to `finished`)

Payload: `TicketClosedEventSchema`

| Field | Type | Description |
| --- | --- | --- |
| `ticket_id` | `PydanticObjectId` | Ticket ID |
| `triage_id` | `PydanticObjectId` | Original triage ID |
| `client_id` | `UUID` | Client ID |

Listeners:
- **ConversationListener** — closes the active conversation
- **ChatbotListener** — closes the attendance and requests evaluation

## Chained event flow

```
triage.finished
  └─ TicketListener creates ticket
       └─ publishes ticket.created
            ├─ ConversationListener creates conversation
            └─ (future) NotificationListener notifies agent
```

The conversation depends on `ticket_id`, which only exists after ticket creation. Therefore `ConversationListener` reacts to `ticket.created`, not `triage.finished`.

## Listener registration

Listeners are registered during the application lifespan, after database initialization. Each domain exposes a `register_*_listener(dispatcher)` function that builds its own dependencies internally:

```python
# app/domains/live_chat/listeners.py
def register_conversation_listener(dispatcher: EventDispatcher) -> None:
    repo = ConversationRepository(mongo_db.get_db())
    service = ConversationService(repo)
    listener = ConversationListener(service)

    dispatcher.subscribe(AppEvent.TICKET_CREATED, listener.on_ticket_created)
    dispatcher.subscribe(AppEvent.TICKET_CLOSED, listener.on_ticket_closed)
```

`main.py` orchestrates registration calls via `register_app_events_listeners(dispatcher)`:

```python
# app/main.py
def register_app_events_listeners(dispatcher: EventDispatcher) -> None:
    register_conversation_listener(dispatcher)
    # future domains register here
```

## Listener example

A listener is a class that lives in the domain's `listeners.py`. It receives domain services via constructor injection and exposes async handler methods — one per event it reacts to. Each handler receives the typed payload as its only argument.

```python
# app/domains/ticket/listeners.py
from app.core.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.schemas import TriageFinishedEventSchema, TicketCreatedEventSchema

from .schemas import CreateTicketDTO
from .services import TicketService


class TicketListener:
    def __init__(self, ticket_service: TicketService, dispatcher: EventDispatcher) -> None:
        self.service = ticket_service
        self.dispatcher = dispatcher

    @event_handler(TriageFinishedEventSchema)
    async def on_triage_finished(self, payload: TriageFinishedEventSchema) -> None:
        dto = CreateTicketDTO(
            triage_id=payload.attendance_id,
            type=payload.ticket_type,
            criticality=payload.ticket_criticality,
            product=payload.product_name,
            description=payload.ticket_description,
            client_id=payload.client_id,
        )
        ticket = await self.service.create(dto)

        await self.dispatcher.publish(
            AppEvent.TICKET_CREATED,
            TicketCreatedEventSchema(
                ticket_id=ticket.id,
                client_id=payload.client_id,
            ),
        )
```

Key points:
- The `@event_handler` decorator validates the payload type and wraps the body in `try/except` with structured logging. Handlers do not need manual error handling.
- The listener receives the `dispatcher` to publish chained events (`ticket.created`).
- Payload field access is typed: `payload.attendance_id`, not `kwargs["attendance_id"]`.

## Metrics

The dispatcher exposes Prometheus metrics via `app/core/event_dispatcher/metrics.py`:

| Metric | Type | Labels | Description |
| --- | --- | --- | --- |
| `events_published_total` | Counter | `event` | Number of times each event was published |
| `event_handler_failures_total` | Counter | `handler` | Number of times each handler failed |
| `event_handler_duration_seconds` | Histogram | `handler` | Handler execution latency |

`events_published_total` is recorded in `publish`. Handler failures and duration are recorded by the `@event_handler` decorator.

## Rules

- Services never import models or repositories from other domains.
- The dispatcher is fire-and-forget: `publish` schedules each handler as an `asyncio.Task` and returns immediately.
- All handlers must use the `@event_handler` decorator. `subscribe` rejects undecorated handlers with `InvalidHandlerError`.
- Handler subscription is idempotent — subscribing the same handler to the same event twice has no effect.
- Each handler is responsible for handling its own exceptions. The `@event_handler` decorator catches and logs exceptions automatically. An unhandled exception does not affect the emitter or other handlers.
- Listeners live in `listeners.py` inside each domain.
- Event names follow the pattern `{domain}.{past_action}`.
- Every event payload must be documented in this file when created.

## Adding a new event

1. Add the member to the `AppEvent` enum in `enums.py`.
2. Create the corresponding schema (inherits from `DispatcherSchema`) in `schemas.py`.
3. Add the entry to `EVENT_PAYLOAD_MAP`.
4. Document the event in this README with emitter, payload, and listeners.
5. Create the handler in the `listeners.py` of the reacting domain.
6. Register the handler in the domain's `register_*_listener`.
