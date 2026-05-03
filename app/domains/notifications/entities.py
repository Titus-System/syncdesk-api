from datetime import datetime
from uuid import UUID

from pydantic.dataclasses import dataclass

from app.domains.notifications.enums import EmailEventType
from app.domains.notifications.models import EmailOutboxStatus
from app.domains.notifications.schemas import PasswordResetPayload, WelcomeInvitePayload


@dataclass
class EmailOutbox:
    id: UUID
    event_type: EmailEventType
    recipient: str
    payload: WelcomeInvitePayload | PasswordResetPayload
    status: EmailOutboxStatus
    attempts: int
    max_attempts: int
    last_error: str | None
    next_attempt_at: datetime
    created_at: datetime
    sent_at: datetime | None
    locked_at: datetime | None
    lock_owner: str | None
