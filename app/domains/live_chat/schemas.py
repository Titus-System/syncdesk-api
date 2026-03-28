from typing import Any, Literal
from uuid import UUID

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, model_validator

from app.core.config import get_settings
from app.domains.live_chat.entities import ChatMessage
from app.domains.live_chat.exceptions import InvalidMessageError


class CreateConversationDTO(BaseModel):
    ticket_id: PydanticObjectId
    agent_id: UUID | None = None
    client_id: UUID
    sequential_index: int = 0
    parent_id: PydanticObjectId | None = None


class IncomingMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    type: Literal["text", "file"]
    content: str
    mime_type: str | None = None
    filename: str | None = None
    responding_to: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def check_required_fields(cls, data: dict[str, Any]) -> dict[str, Any]:
        if "type" not in data or "content" not in data:
            raise ValueError("Payload missing required fields: type, content")
        return data

    @model_validator(mode="after")
    def validate_logic(self) -> "IncomingMessage":
        if self.type == "text" and (self.filename is not None or self.mime_type is not None):
            raise ValueError(
                "Invalid payload. mime_type and filename fields are not allowed for text messages."
            )

        if self.type == "file" and (self.mime_type is None or self.filename is None):
            raise ValueError("mime_type and filename fields are required when type='file'")

        return self

    @model_validator(mode="after")
    def validate_content_size(self) -> "IncomingMessage":
        lim = get_settings().MAX_CHAT_MESSAGE_CONTENT_SIZE
        if len(self.content) > lim:
            raise InvalidMessageError(f"Message content exceeds {lim} characters.")
        return self


class PaginatedMessages(BaseModel):
    messages: list[ChatMessage]
    total: int
    page: int
    limit: int
    has_next: bool
