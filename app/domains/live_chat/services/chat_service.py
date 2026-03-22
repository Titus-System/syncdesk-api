from typing import Any
from uuid import UUID

from app.domains.live_chat.entities import ChatMessage
from app.domains.live_chat.exceptions import InvalidMessageError

from ..chat_manager import ChatConnection, ChatManager
from ..repositories import ChatRepository


class ChatService:
    def __init__(self, repository: ChatRepository, manager: ChatManager) -> None:
        self.repo = repository
        self.chat_manager = manager

    def create_empty_chat_room(self, room_id: UUID | None = None) -> UUID:
        return self.chat_manager.open_room(room_id)

    async def join_chat_room(self, room_id: UUID, conn: ChatConnection) -> None:
        await self.chat_manager.join_room(room_id, conn)

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

    def route_message(self) -> None: ...
