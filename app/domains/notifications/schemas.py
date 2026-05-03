from uuid import UUID

from pydantic import BaseModel

from app.core.schemas import BaseDTO
from app.domains.notifications.enums import EmailEventType


class WelcomeInvitePayload(BaseModel):
    user_id: UUID
    user_name: str
    user_email: str
    one_time_password: str
    frontend_url: str
    token: str


class PasswordResetPayload(BaseModel):
    user_id: UUID
    user_email: str
    frontend_url: str
    token: str


EmailOutboxPayload = WelcomeInvitePayload | PasswordResetPayload


class EnqueueEmailOutboxDTO(BaseDTO):
    event_type: EmailEventType
    recipient: str
    payload: WelcomeInvitePayload | PasswordResetPayload
    max_attempts: int = 5
