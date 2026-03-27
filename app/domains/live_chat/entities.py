from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from beanie import Document, PydanticObjectId
from pydantic import BaseModel, Field, ValidationError
from pymongo import IndexModel

from .exceptions import InvalidMessageError


class ChatMessage(BaseModel):
    id: UUID
    conversation_id: PydanticObjectId
    sender_id: UUID | Literal["System"]
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    type: Literal["text", "file"]
    content: str
    mime_type: str | None = None
    filename: str | None = None
    responding_to: UUID | None = None

    @classmethod
    def create(
        cls,
        conversation_id: PydanticObjectId,
        sender_id: UUID | Literal["System"],
        type: Literal["text", "file"],
        content: str,
        mime_type: str | None = None,
        filename: str | None = None,
        responding_to: UUID | None = None,
    ) -> "ChatMessage":
        try:
            return cls(
                id=uuid4(),
                conversation_id=conversation_id,
                sender_id=sender_id,
                type=type,
                content=content,
                mime_type=mime_type,
                filename=filename,
                responding_to=responding_to,
            )
        except ValidationError as e:
            raise InvalidMessageError(str(e)) from e

    def to_payload(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)


class Conversation(Document):
    service_session_id: PydanticObjectId
    agent_id: UUID | None
    client_id: UUID
    sequential_index: int = 0
    parent_id: PydanticObjectId | None = None
    children_ids: list[PydanticObjectId] = Field(default_factory=list[PydanticObjectId])
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    messages: list[ChatMessage] = Field(default_factory=list[ChatMessage])

    class Settings:
        name = "conversations"
        indexes = [IndexModel([("service_session_id", 1), ("sequential_index", 1)], unique=True)]

    def is_opened(self) -> bool:
        return self.finished_at is None

    def participants(self) -> tuple[UUID, ...]:
        if self.agent_id is None:
            return (self.client_id,)
        return (self.client_id, self.agent_id)


class ChatParticipants(BaseModel):
    id: PydanticObjectId = Field(alias="_id")
    client_id: UUID
    agent_id: UUID | None
