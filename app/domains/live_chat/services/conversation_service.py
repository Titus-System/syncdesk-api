from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from beanie import PydanticObjectId

from app.domains.auth.entities import UserWithRoles
from app.domains.live_chat.entities import ChatMessage, ChatParticipants, Conversation
from app.domains.live_chat.exceptions import ParentConversationNotFoundError
from app.domains.live_chat.schemas import (
    ActiveConversationSummary,
    CreateConversationDTO,
    IncomingMessage,
    PaginatedMessages,
)

from ..metrics import chat_messages_total
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

    async def ticket_has_conversation(self, ticket_id: PydanticObjectId) -> bool:
        return await self.repo.ticket_has_conversation(ticket_id)

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

    async def get_chats_from_ticket(self, ticket_id: PydanticObjectId) -> list[Conversation]:
        return await self.repo.get_by_ticket_id(ticket_id)

    async def get_paginated_messages(
        self, ticket_id: PydanticObjectId, page: int, limit: int
    ) -> PaginatedMessages:
        return await self.repo.get_paginated_messages(ticket_id, page, limit)

    async def get_current_ticket_participants(
        self, ticket_id: PydanticObjectId
    ) -> tuple[UUID, ...] | None:
        return await self.repo.get_current_ticket_participants(ticket_id)

    async def add_message_to_conversation(
        self, chat_id: PydanticObjectId, message: ChatMessage
    ) -> None:
        chat_messages_total.inc()
        await self.repo.add_message(chat_id, message)

    async def get_active_conversations(
        self, user: UserWithRoles, search: str | None = None
    ) -> list[ActiveConversationSummary]:
        is_admin = "admin" in user.roles_names()
        chats = await self.repo.get_active_conversations(user.id, is_admin, search)

        result: list[ActiveConversationSummary] = []
        for chat in chats:
            can_join_live = is_admin or chat.agent_id == user.id
            needs_assume = (not is_admin) and chat.agent_id is None

            result.append(
                chat.model_copy(
                    update={
                        "can_join_live": can_join_live,
                        "needs_assume": needs_assume,
                    }
                )
            )

        return result

    async def assume_conversation(
        self, chat_id: PydanticObjectId, user: UserWithRoles
    ) -> Conversation | None:
        chat = await self.repo.get_by_id(chat_id)
        if chat is None:
            return None

        if not chat.is_opened():
            raise ValueError("Conversation is already closed.")

        is_admin = "admin" in user.roles_names()

        if chat.agent_id is None:
            await self.repo.attribute_agent(chat_id, user.id)
            chat.agent_id = user.id
            return chat

        if chat.agent_id == user.id:
            return chat

        if is_admin:
            await self.repo.attribute_agent(chat_id, user.id)
            chat.agent_id = user.id
            return chat

        raise PermissionError("Conversation is already assigned to another agent.")

    async def get_latest_open_by_ticket_id(
        self, ticket_id: PydanticObjectId
    ) -> Conversation | None:
        return await self.repo.get_latest_open_by_ticket_id(ticket_id)

    async def get_last_conversation_from_ticket(
        self, ticket_id: PydanticObjectId
    ) -> Conversation | None:
        return await self.repo.get_last_by_ticket_id(ticket_id)

    async def end_conversation(
        self, chat_id: PydanticObjectId, end_datetime: datetime | None = None
    ) -> Conversation | None:
        c = await self.get_by_id(chat_id)
        if c is None:
            return None
        c.finished_at = end_datetime if end_datetime else datetime.now(UTC)
        c = await self.repo.update(c)
        return c

    async def close_active_ticket_conversation(
        self,
        ticket_id: PydanticObjectId,
        system_message: str,
        finished_at: datetime | None = None,
    ) -> Conversation | None:
        conversation = await self.get_latest_open_by_ticket_id(ticket_id)
        if conversation is None or conversation.id is None:
            return None

        await self.add_message_to_conversation(
            conversation.id,
            ChatMessage.create(
                conversation_id=conversation.id,
                sender_id="System",
                type="text",
                content=system_message,
            ),
        )
        return await self.end_conversation(conversation.id, finished_at)

    async def append_conversation_to_ticket(
        self,
        ticket_id: PydanticObjectId,
        client_id: UUID,
        agent_id: UUID | None = None,
        closing_message: str | None = None,
    ) -> Conversation:
        last_conv = await self.get_last_conversation_from_ticket(ticket_id)

        sequential_index = (last_conv.sequential_index + 1) if last_conv else 0
        parent_id = last_conv.id if last_conv else None

        new_conv = await self.create(
            CreateConversationDTO(
                ticket_id=ticket_id,
                agent_id=agent_id,
                client_id=client_id,
                sequential_index=sequential_index,
                parent_id=parent_id,
            )
        )

        if last_conv is not None and last_conv.id is not None:
            if closing_message:
                await self.add_message_to_conversation(
                    last_conv.id,
                    ChatMessage.create(
                        conversation_id=last_conv.id,
                        sender_id="System",
                        type="text",
                        content=closing_message,
                    ),
                )
            await self.end_conversation(last_conv.id)
            if new_conv.id is not None:
                await self.repo.add_child(last_conv.id, new_conv.id)

        return new_conv
    

    async def search_conversation_by_text(
        self, search_query: str, user: UserWithRoles
    ) -> list[Conversation]:
        roles = user.roles_names()
        if "admin" in roles:
            return await self.repo.search_conversation_by_text(search_query)

        if any(role.strip().upper() in {"AGENT", "N1", "N2", "N3"} for role in roles):
            return await self.repo.search_conversation_by_text(
                search_query, agent_id=user.id
            )

        return await self.repo.search_conversation_by_text(
            search_query, client_id=user.id
        )
