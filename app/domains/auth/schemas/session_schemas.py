from datetime import datetime
from uuid import UUID

from pydantic import model_validator

from app.core.http.schemas import SessionDeviceInfo
from app.core.schemas import BaseDTO

from ..enums import SessionStatus


class CreateSessionDTO(BaseDTO):
    user_id: UUID
    role_names: list[str] = []
    refresh_token_hash: str | None = None
    status: SessionStatus | None = None
    expires_at: datetime
    device_info: SessionDeviceInfo | None = None
    last_used_at: datetime | None = None

    @model_validator(mode="after")
    def validate_expiration(self) -> "CreateSessionDTO":
        if self.expires_at <= datetime.now():
            raise ValueError("expires_at must be in the future")
        return self


class UpdateSessionDTO(BaseDTO):
    refresh_token_hash: str | None = None
    status: SessionStatus | None = None
    expires_at: datetime | None = None
    last_used_at: datetime | None = None
    device_info: SessionDeviceInfo | None = None


class RefreshSessionDTO(BaseDTO):
    refresh_token_hash: str
    expires_at: datetime
