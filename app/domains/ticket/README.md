# Ticket Domain

Official API contract for the SyncDesk ticket domain.

This module defines the public HTTP contracts, Pydantic schemas, pagination rules, event payloads, and the minimum implemented behavior required for the current sprint. The focus is contract definition, not full operational business implementation.

## Scope

Implemented routes:
- `POST /api/tickets/`
- `GET /api/tickets/`
- `GET /api/tickets/{ticket_id}`
- `PATCH /api/tickets/{ticket_id}`

Contract stubs in this sprint:
- `GET /api/tickets/queue`
- `POST /api/tickets/{ticket_id}/assign`
- `POST /api/tickets/{ticket_id}/escalate`
- `POST /api/tickets/{ticket_id}/transfer`

Out of scope:
- listeners for `live_chat`
- listeners for `chatbot`
- event dispatcher wiring
- delete endpoint
- full queue, assignment, escalation, and transfer business logic

## Architecture

- `models.py`: persistent ticket document and enums
- `schemas.py`: request/response contracts and event payloads
- `routers.py`: HTTP contract surface
- `services.py`: implemented business logic kept intentionally small
- `repositories.py`: MongoDB access for the implemented flows
- `dependencies.py`: service composition

The domain follows the project standards based on:
- `CurrentUserSessionDep`
- `require_permission(...)`
- `ResponseFactoryDep`
- `GenericSuccessContent[...]`

## Enums

### `TicketType`

Values:
- `issue`
- `access`
- `new_feature`

### `TicketCriticality`

Values:
- `high`
- `medium`
- `low`

### `TicketStatus`

Values:
- `open`
- `awaiting_assignment`
- `in_progress`
- `waiting_for_provider`
- `waiting_for_validation`
- `finished`

`awaiting_assignment` is a real status of the official contract. It is used to represent tickets that were created successfully and are waiting for an active assignee.

## Official initial status

The official initial status of a newly created ticket is:
- `awaiting_assignment`

This decision is applied consistently in the service layer and documented as the default lifecycle entry point for ticket operations.

## Persistent model strategy

The persisted `Ticket` document remains intentionally conservative.

Persisted fields:
- `triage_id`
- `type`
- `criticality`
- `product`
- `status`
- `creation_date`
- `description`
- `chat_ids`
- `agent_history`
- `client`
- `comments`

Not added in this sprint:
- `department`
- `current_assignee`
- dedicated department or assignee embedded references

Queue and routing concerns are represented in API DTOs where needed, without inflating the persisted MongoDB document.

## Schemas

### Main request/response contracts

- `CreateTicketDTO`
- `CreateTicketResponseDTO`
- `TicketSearchFiltersDTO`
- `TicketResponse`
- `TicketListResponse`
- `UpdateTicketDTO`
- `AssignTicketRequest`
- `EscalateTicketRequest`
- `TransferTicketRequest`
- `TicketQueueFiltersDTO`
- `TicketQueueItemResponse`
- `TicketQueueListResponse`

### Event payload contracts

- `TicketEventPayload`
- `TicketClosedEventPayload`
- `TicketAssigneeUpdatedEventPayload`
- `TicketEscalatedEventPayload`
- `TriageFinishedEventPayload`

### Provisional integration fields

The following fields are intentionally typed as `str` in this sprint:
- `department_id`
- `target_department_id`
- `level`
- `target_level`

These fields are provisional because they depend on external domain contracts. They are part of the official API contract here, but their concrete cross-domain type alignment remains owned by the external integration boundary.

## Routes

### `POST /api/tickets/`

Status:
- implemented

Permission:
- `ticket:create`

Request body:
- `CreateTicketDTO`

Response:
- `GenericSuccessContent[CreateTicketResponseDTO]`

Example request:

```json
{
  "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
  "type": "issue",
  "criticality": "high",
  "product": "Sistema Financeiro",
  "description": "Erro ao emitir boleto",
  "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
  "client_id": "0f7d7c4f-7b5b-45cb-9d85-6f3c69f0b5d2"
}
```

Example response:

```json
{
  "data": {
    "id": "67f0ca60e4b0b1a2c3d4e601",
    "status": "awaiting_assignment",
    "creation_date": "2026-04-14T12:00:00Z"
  }
}
```

### `GET /api/tickets/`

Status:
- implemented

Permission:
- `ticket:read`

Official response format:
- `GenericSuccessContent[TicketListResponse]`

Pagination defaults:
- `page=1`
- `page_size=20`

Query params:
- `ticket_id`
- `client_id`
- `triage_id`
- `status`
- `criticality`
- `type`
- `product`
- `page`
- `page_size`

Response shape:

```json
{
  "data": {
    "items": [],
    "page": 1,
    "page_size": 20,
    "total": 0
  }
}
```

### `GET /api/tickets/{ticket_id}`

Status:
- implemented

Permission:
- `ticket:read`

Response:
- `GenericSuccessContent[TicketResponse]`

### `PATCH /api/tickets/{ticket_id}`

Status:
- implemented

Permission:
- `ticket:update`

Official purpose:
- partially update a ticket

Supported request fields:
- `status`
- `criticality`
- `product`
- `description`

Actions that do not belong to this PATCH:
- assignment
- transfer
- escalation

Response:
- `GenericSuccessContent[TicketResponse]`

Event behavior:
- when the resulting status becomes `finished`, this route represents the `ticket.closed` business event contract

Example request:

```json
{
  "status": "finished",
  "criticality": "medium",
  "description": "Chamado concluido e validado."
}
```

### `GET /api/tickets/queue`

Status:
- contract stub

Permission:
- `ticket:queue`

Query params:
- `status`
- `type`
- `department_id`
- `unassigned_only`
- `level`
- `assignee_id`
- `page`
- `page_size`

Response:
- `GenericSuccessContent[TicketQueueListResponse]`

Ordering contract:
- criticality first
- creation date second

Current behavior:
- returns `501 Not Implemented`

### `POST /api/tickets/{ticket_id}/assign`

Status:
- contract stub

Permission:
- `ticket:assign`

Request body:
- `AssignTicketRequest`

Response:
- `GenericSuccessContent[TicketResponse]`

Event contract:
- emits `ticket.assignee_updated`

Current behavior:
- returns `501 Not Implemented`

### `POST /api/tickets/{ticket_id}/escalate`

Status:
- contract stub

Permission:
- `ticket:escalate`

Request body:
- `EscalateTicketRequest`

Business rule contract:
- escalation moves the ticket upward in the support structure

Response:
- `GenericSuccessContent[TicketResponse]`

Event contract:
- emits `ticket.escalated`

Current behavior:
- returns `501 Not Implemented`

### `POST /api/tickets/{ticket_id}/transfer`

Status:
- contract stub

Permission:
- `ticket:transfer`

Request body:
- `TransferTicketRequest`

Business rule contract:
- transfer changes the assignee without changing level or department

Response:
- `GenericSuccessContent[TicketResponse]`

Event contract:
- emits `ticket.assignee_updated`

Current behavior:
- returns `501 Not Implemented`

### Delete policy

`DELETE /api/tickets/{ticket_id}` is not exposed in this sprint.

Reason:
- ticket lifecycle must remain auditable and traceable

## Status transitions

Validated transitions:

| Current status | Allowed next statuses |
| --- | --- |
| `open` | `awaiting_assignment`, `in_progress` |
| `awaiting_assignment` | `in_progress` |
| `in_progress` | `awaiting_assignment`, `waiting_for_provider`, `waiting_for_validation`, `finished` |
| `waiting_for_provider` | `in_progress` |
| `waiting_for_validation` | `in_progress`, `finished` |
| `finished` | none |

Operational note:
- the official creation flow enters at `awaiting_assignment`
- `open` remains part of the official enum and transition graph

## Events

The ticket domain is the producer of:
- `ticket.closed`
- `ticket.assignee_updated`
- `ticket.escalated`

The ticket domain also defines the payload it expects to receive from:
- `triage.finished`

### `ticket.closed`

Purpose:
- notify downstream domains that the ticket was closed

Payload:
- `TicketClosedEventPayload`

Expected external consumers:
- `live_chat`
- `chatbot`

### `ticket.assignee_updated`

Purpose:
- notify assignment or transfer updates

Payload:
- `TicketAssigneeUpdatedEventPayload`

### `ticket.escalated`

Purpose:
- notify upward movement in the support structure

Payload:
- `TicketEscalatedEventPayload`

### `triage.finished`

Purpose:
- define the upstream event payload that can create a ticket from triage completion

Payload:
- `TriageFinishedEventPayload`

Responsibility boundary:
- the event publisher belongs to another domain
- the ticket domain validates and consumes the payload it receives
- `client_id` must come from a trusted authenticated source

## Permissions

Ticket permissions used by this contract:
- `ticket:read`
- `ticket:create`
- `ticket:update`
- `ticket:queue`
- `ticket:assign`
- `ticket:transfer`
- `ticket:escalate`

## Implementation summary

Implemented now:
- ticket creation
- paginated ticket listing
- ticket retrieval by id
- partial ticket update

Prepared as contract stubs:
- queue
- assignment
- escalation
- transfer
- event payload contracts for internal and external integrations
