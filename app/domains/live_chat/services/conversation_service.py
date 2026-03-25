from typing import Any
from uuid import UUID

from beanie import PydanticObjectId

from app.domains.live_chat.entities import ChatMessage, ChatParticipants, Conversation
from app.domains.live_chat.exceptions import InvalidMessageError
from app.domains.live_chat.schemas import CreateConversationDTO

from ..repositories import ConversationRepository


class ConversationService:
    def __init__(self, repository: ConversationRepository) -> None:
        self.repo = repository

    async def handle_message(
        self, room_id: PydanticObjectId, user_id: UUID, payload: dict[Any, Any]
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

    async def create(self, dto: CreateConversationDTO) -> Conversation:
        return await self.repo.create(dto)

    async def get_by_id(self, chat_id: PydanticObjectId) -> Conversation | None:
        return await self.repo.get_by_id(chat_id)

    async def get_participants(self, chat_id: PydanticObjectId) -> ChatParticipants | None:
        return await self.repo.get_chat_participants(chat_id)

    async def attribute_agent(self, chat_id: PydanticObjectId, agent_id: UUID) -> None:
        return await self.repo.attribute_agent(chat_id, agent_id)

    async def get_chats_from_service_session(
        self, service_session_id: PydanticObjectId
    ) -> list[Conversation]:
        return await self.repo.get_by_service_session_id(service_session_id)

    async def add_message_to_conversation(
        self, chat_id: PydanticObjectId, message: ChatMessage
    ) -> None:
        await self.repo.add_message(chat_id, message)
