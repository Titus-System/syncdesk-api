from typing import Any, cast
from uuid import UUID

from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import (
    ConnectionFailure,
    DuplicateKeyError,
    ServerSelectionTimeoutError,
    WriteError,
)

from app.core.decorators import require_dto
from app.db.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError

from ..entities import ChatMessage, ChatParticipants, Conversation
from ..schemas import CreateConversationDTO


class ConversationRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        self.db = db

    @require_dto(CreateConversationDTO)
    async def create(self, dto: CreateConversationDTO) -> Conversation:
        try:
            c = Conversation(
                service_session_id=dto.service_session_id,
                agent_id=dto.agent_id,
                client_id=dto.client_id,
                sequential_index=dto.sequential_index or 0,
                parent_id=dto.parent_id,
            )
            return cast(Conversation, await c.insert())

        except DuplicateKeyError as err:
            raise ResourceAlreadyExistsError("Chat", "index") from err

    async def get_by_id(self, id: PydanticObjectId) -> Conversation | None:
        return await Conversation.get(id)

    async def get_chat_participants(self, id: PydanticObjectId) -> ChatParticipants | None:
        return await Conversation.find_one(Conversation.id == id, projection_model=ChatParticipants)

    async def get_by_service_session_id(
        self, service_session_id: PydanticObjectId
    ) -> list[Conversation]:
        return await Conversation.find(
            Conversation.service_session_id == service_session_id
        ).to_list()

    async def update(self, conversation: Conversation) -> Conversation | None:
        return cast(Conversation | None, await conversation.save())

    async def delete(self, id: PydanticObjectId) -> Conversation | None:
        c = await Conversation.get(id)
        if c:
            await c.delete()
        return c

    async def add_message(self, id: PydanticObjectId, message: ChatMessage) -> None:
        conversation = await Conversation.get(id)
        if not conversation:
            raise ValueError(f"Conversation {id} not found")
        try:
            await conversation.update({"$push": {"messages": message.model_dump()}})
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            raise RuntimeError("Connection error when saving the message") from e
        except WriteError as e:
            raise RuntimeError("Error persisting message") from e

    async def attribute_agent(self, conversation_id: PydanticObjectId, agent_id: UUID) -> None:
        conversation = await Conversation.get(conversation_id)
        if not conversation:
            raise ResourceNotFoundError("Conversation", str(conversation_id))
        await conversation.update({"$set": {"agent_id": agent_id}})
