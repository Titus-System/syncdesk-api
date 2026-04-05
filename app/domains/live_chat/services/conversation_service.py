from typing import Any
from uuid import UUID

from beanie import PydanticObjectId

from app.domains.live_chat.entities import ChatMessage, ChatParticipants, Conversation
from app.domains.live_chat.exceptions import (
    ParentConversationNotFoundError,
    TicketClosedForNewMessagesError,
)
from app.domains.live_chat.schemas import CreateConversationDTO, IncomingMessage, PaginatedMessages
from app.domains.ticket.models import TicketStatus
from app.domains.ticket.repositories import TicketRepository

from ..repositories import ConversationRepository


class ConversationService:
    def __init__(
        self,
        repository: ConversationRepository,
        ticket_repository: TicketRepository,
    ) -> None:
        self.repo = repository
        self.ticket_repo = ticket_repository

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
        if dto.parent_id is not None:
            parent_exists = await self.repo.conversation_exists(dto.parent_id)
            if not parent_exists:
                raise ParentConversationNotFoundError(
                    f"Conversation of id {dto.parent_id} was not found."
                )
        return await self.repo.create(dto)

    async def get_by_id(self, chat_id: PydanticObjectId) -> Conversation | None:
        return await self.repo.get_by_id(chat_id)

    async def get_from_client(self, client_id: UUID) -> list[Conversation]:
        return await self.repo.get_by_client_id(client_id)

    async def get_participants(self, chat_id: PydanticObjectId) -> ChatParticipants | None:
        return await self.repo.get_chat_participants(chat_id)

    async def attribute_agent(self, chat_id: PydanticObjectId, agent_id: UUID) -> None:
        return await self.repo.attribute_agent(chat_id, agent_id)

    async def get_chats_from_ticket(
        self, ticket_id: PydanticObjectId
    ) -> list[Conversation]:
        return await self.repo.get_by_ticket_id(ticket_id)

    async def get_paginated_messages(
        self, ticket_id: PydanticObjectId, page: int, limit: int
    ) -> PaginatedMessages:
        return await self.repo.get_paginated_messages(ticket_id, page, limit)

    async def get_current_ticket_participants(
        self, ticket_id: PydanticObjectId
    ) -> tuple[UUID, ...] | None:
        return await self.repo.get_current_ticket_participants(ticket_id)

    async def _ensure_ticket_accepts_new_messages(
        self, chat_id: PydanticObjectId
    ) -> Conversation:
        conversation = await self.repo.get_by_id(chat_id)
        if conversation is None:
            raise ValueError(f"Conversation {chat_id} not found")

        ticket = await self.ticket_repo.get_by_id(conversation.ticket_id)
        if ticket is None:
            raise ValueError(f"Ticket {conversation.ticket_id} not found")

        if ticket.status == TicketStatus.FINISHED:
            raise TicketClosedForNewMessagesError(
                f"Cannot send new messages because ticket {ticket.id} is finished."
            )

        return conversation

    async def add_message_to_conversation(
        self, chat_id: PydanticObjectId, message: ChatMessage
    ) -> None:
        await self._ensure_ticket_accepts_new_messages(chat_id)
        await self.repo.add_message(chat_id, message)