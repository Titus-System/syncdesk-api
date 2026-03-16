from datetime import UTC, datetime
from typing import Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    id: UUID
    conversation_id: UUID
    sender_id: UUID
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    type: Literal["text", "file"]
    content: str
    mime_type: str | None = None
    filename: str | None = None
    responding_to: UUID | None = None

    @classmethod
    def create(
        cls,
        conversation_id: UUID,
        sender_id: UUID,
        type: Literal["text", "file"],
        content: str,
        mime_type: str | None = None,
        filename: str | None = None,
        responding_to: UUID | None = None,
    ) -> "ChatMessage":
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


class Conversation(BaseModel):
    id: UUID
    atendimento_id: UUID
    participants: list[UUID]
    created_at: datetime
    sequential_index: int = 0
    parent_id: UUID | None = None
    children_ids: list[UUID] | None = None
    closed_at: datetime | None = None
    messages: list[ChatMessage]

    @classmethod
    def create(
        cls,
        atendimento_id: UUID,
        participants: list[UUID],
        sequential_index: int = 0,
        parent_id: UUID | None = None,
    ) -> "Conversation":
        return cls(
            id=uuid4(),
            atendimento_id=atendimento_id,
            participants=participants,
            created_at=datetime.now(UTC),
            sequential_index=sequential_index,
            parent_id=parent_id,
            children_ids=[],
            messages=[],
        )

    def add_message(self, message: ChatMessage) -> None:
        self.messages.append(message)

    def get_message(self, message_id: UUID) -> ChatMessage | None:
        for m in self.messages:
            if m.id == message_id:
                return m
        return None

    def close(self) -> None:
        self.closed_at = datetime.now(UTC)

    def is_closed(self) -> bool:
        return self.closed_at is not None
