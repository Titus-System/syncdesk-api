# Notifications Domain

Transactional email outbox for SyncDesk.

This module owns the durable persistence and delivery of outgoing emails. Producers in other domains never call email APIs directly — they publish a typed event on the application `EventDispatcher`, and the notifications domain consumes that event, persists an outbox row, and a background worker handles delivery, retry, and dead-lettering.

## Purpose

- Decouple email producers (auth, etc.) from email infrastructure.
- Survive process crashes: emails are committed to the database before delivery is attempted.
- Bounded retry with exponential backoff and a terminal `DEAD` status for unrecoverable failures.

## Architecture

- `models.py`: SQLAlchemy ORM model `EmailOutbox` (JSONB payload column). Restricted to the repository layer.
- `entities.py`: `EmailOutbox` dataclass entity returned by the repository.
- `enums.py`: `EmailEventType`, `EmailOutboxStatus`.
- `schemas.py`: `EnqueueEmailOutboxDTO` and the typed payload models (`WelcomeInvitePayload`, `PasswordResetPayload`).
- `repositories/email_outbox_repository.py`: persistence operations (`enqueue`, `claim_batch`, `mark_sent`, `mark_retry`, `mark_dead`).
- `services/email_outbox_service.py`: builds typed payloads from event schemas and delegates to the repository.
- `listeners.py`: subscribes to `EventDispatcher` events and invokes the service. This is the single integration point with other domains.
- `worker.py`: long-running async loop that claims pending rows with `FOR UPDATE SKIP LOCKED`, renders the email, sends through `EmailStrategy`, and updates status.
- `metrics.py`: Prometheus counters/gauges for queue depth and per-event processing outcomes.

The boundary rule: cross-domain integration goes through `EventDispatcher`. No domain imports a service or repository from `notifications`. The auth domain (only current producer) publishes events; the notifications listener handles persistence.

## Public Interface (for other domains)

To trigger an email, publish a typed event on `EventDispatcher`. The relevant event schemas live in `app/core/event_dispatcher/schemas.py`:

```python
from app.core.event_dispatcher import AppEvent, EventDispatcher
from app.core.event_dispatcher.schemas import WelcomeInviteEventSchema

class MyService:
    def __init__(self, dispatcher: EventDispatcher) -> None:
        self.dispatcher = dispatcher

    async def some_flow(self, ...) -> None:
        await self.dispatcher.publish(
            AppEvent.USER_WELCOME_INVITE,
            WelcomeInviteEventSchema(
                user_id=user.id,
                user_name=user.name,
                user_email=user.email,
                roles=user.roles_names(),
                raw_token=token,
                one_time_password=password,
                max_attempts=settings.EMAIL_OUTBOX_MAX_ATTEMPTS,
            ),
        )
```

The dispatch is fire-and-forget. The notifications listener picks it up, opens its own DB session, writes the outbox row, and commits. Producers do not need to await delivery and must not assume success on return.

## Supported Events

| `AppEvent`              | Payload schema (`app.core.event_dispatcher.schemas`) | Outbox `event_type` |
| ----------------------- | ---------------------------------------------------- | ------------------- |
| `USER_WELCOME_INVITE`   | `WelcomeInviteEventSchema`                           | `WELCOME_INVITE`    |
| `USER_PASSWORD_RESET`   | `PasswordResetEventSchema`                           | `PASSWORD_RESET`    |

The internal payload stored in the outbox JSONB column is a separate, narrower type (`WelcomeInvitePayload` / `PasswordResetPayload`) — the listener resolves the frontend URL from the user's roles before persisting.

## Adding a New Email Type

1. Add a value to `EmailEventType` in `enums.py`.
2. Add a typed payload model in `schemas.py` (one Pydantic `BaseModel` per email type).
3. Add a value to `AppEvent` in `app/core/event_dispatcher/enums.py` and the matching event schema in `app/core/event_dispatcher/schemas.py`. Register the pair in `EVENT_PAYLOAD_MAP`.
4. Add an `enqueue_<...>` method to `EmailOutboxService` that converts the event schema into the typed payload.
5. Add a handler method to `EmailOutboxListener` decorated with `@event_handler(<NewEventSchema>)`, and subscribe it inside `register_email_outbox_listener`.
6. Extend `_render_html` in `worker.py` with an `isinstance` branch for the new payload type.
7. Add a render function in `app/core/email/renderer.py` and a params schema in `app/core/email/schemas.py`.
8. Extend the repository's `_to_entity` `if/elif` so the new event type maps back to the right typed payload on read.

## Operations

### Worker lifecycle

`run_email_outbox_worker` is started as a global background task during application startup and cancelled gracefully during shutdown. It does nothing if `EMAIL_OUTBOX_ENABLED=False`.

Each iteration:
1. Claims a batch of `PENDING`/`RETRY` rows whose `next_attempt_at <= now()` using `FOR UPDATE SKIP LOCKED`. This is what makes the worker safe to run as multiple replicas — concurrent workers will not pick up the same row.
2. Bulk-updates claimed rows to `PROCESSING` with the current worker id and `locked_at`.
3. Renders the email and dispatches via the configured `EmailStrategy`.
4. On success: `mark_sent` (status `SENT`, clears lock and last error).
5. On failure: increments `attempts`. If `attempts >= max_attempts`, `mark_dead`; otherwise `mark_retry` with exponential backoff (`2 ** attempts` seconds, capped at `EMAIL_OUTBOX_BACKOFF_MAX_SECONDS`, plus jitter).

### Status machine

```
PENDING ──claim──▶ PROCESSING ──ok──▶ SENT
                       │
                       └──fail──▶ RETRY ──claim──▶ PROCESSING ─...
                                    │
                                    └──attempts >= max──▶ DEAD
```

`SENT` and `DEAD` are terminal — they are never claimed again.

### Configuration

| Setting                              | Purpose                                                    |
| ------------------------------------ | ---------------------------------------------------------- |
| `EMAIL_OUTBOX_ENABLED`               | Master switch for the worker.                              |
| `EMAIL_OUTBOX_BATCH_SIZE`            | Max rows claimed per poll.                                 |
| `EMAIL_OUTBOX_POLL_SECONDS`          | Sleep interval between polls.                              |
| `EMAIL_OUTBOX_MAX_ATTEMPTS`          | Default delivery attempts before dead-lettering.           |
| `EMAIL_OUTBOX_BACKOFF_MAX_SECONDS`   | Cap for the exponential backoff.                           |
| `EMAIL_OUTBOX_WORKER_ID`             | Optional explicit worker id (defaults to `host-pid`).      |

### Metrics

Exposed via Prometheus from `metrics.py`:

- `email_outbox_depth{status}` (gauge): claimed batch size by status.
- `email_outbox_processed_total{status}` (counter): per-row outcomes — `sent`, `retry`, `dead`.

### Testing

- **Unit**: `tests/app/unit/notifications/` — service and worker pieces with mocked dependencies.
- **Integration**: `tests/app/integration/domains/notifications/test_email_outbox_repository.py` — exercises the repository against a real database with savepoint isolation. No mocks; integration tests of this domain only stub the email sender (the external boundary).
- **e2e**: `tests/app/e2e/conftest.py` registers a capture handler on the dispatcher to assert that the right events were published end-to-end.
