from datetime import datetime
from uuid import UUID

from pydantic import BaseModel

from ..enums import TokenPurpose


class CreatePasswordResetTokenDTO(BaseModel):
    user_id: UUID
    token_hash: str
    purpose: TokenPurpose
    expires_at: datetime
