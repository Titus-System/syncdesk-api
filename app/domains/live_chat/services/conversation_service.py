from typing import Any
from uuid import UUID

from beanie import PydanticObjectId

from app.domains.live_chat.entities import ChatMessage, ChatParticipants, Conversation
from app.domains.live_chat.schemas import CreateConversationDTO, IncomingMessage

from ..repositories import ConversationRepository


class ConversationService:
    def __init__(self, repository: ConversationRepository) -> None:
        self.repo = repository

    def handle_message(
        self, room_id: PydanticObjectId, user_id: UUID, payload: dict[Any, Any]
    ) -> ChatMessage:
        data = IncomingMessage(**payload)
        return ChatMessage.create(
            conversation_id=room_id,
            sender_id=user_id,
            type=data.type,
            content=data.content,
            mime_type=data.mime_type,
            filename=data.filename,
            responding_to=data.responding_to,
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
