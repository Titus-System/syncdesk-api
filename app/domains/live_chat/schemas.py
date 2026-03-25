from typing import Any, Literal
from uuid import UUID

from beanie import PydanticObjectId
from pydantic import BaseModel, ConfigDict, model_validator


class CreateConversationDTO(BaseModel):
    service_session_id: PydanticObjectId
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
    def validate_logic(self) -> 'IncomingMessage':
        if self.type == 'text' and self.filename is not None:
            raise ValueError(
                "Invalid payload. filename field is not allowed for text messages"
            )

        if self.type == "file" and self.mime_type is None:
            raise ValueError(
                "mime_type is required when type='file'"
            )

        return self
