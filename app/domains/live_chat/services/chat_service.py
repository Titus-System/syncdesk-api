from typing import Any
from uuid import UUID

from app.domains.live_chat.entities import ChatMessage
from app.domains.live_chat.exceptions import InvalidMessageError

from ..repositories import ChatRepository


class ChatService:
    def __init__(self, repository: ChatRepository) -> None:
        self.repo = repository

    async def handle_message(
        self, room_id: UUID, user_id: UUID, payload: dict[Any, Any]
    ) -> ChatMessage:
        if "type" not in payload or "content" not in payload:
            raise InvalidMessageError("Payload missing required fields: type, content")

        return ChatMessage.create(
            room_id,
            user_id,
            payload["type"],
            payload["content"],
            payload.get("mime_type"),
            payload.get("filename"),
            payload.get("responding_to"),
        )
