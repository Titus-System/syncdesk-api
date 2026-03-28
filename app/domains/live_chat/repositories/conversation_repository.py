from datetime import datetime
from typing import Any, cast
from uuid import UUID

from beanie import PydanticObjectId
from beanie.odm.queries.aggregation import AggregationQuery
from motor.motor_asyncio import AsyncIOMotorCommandCursor, AsyncIOMotorDatabase
from pymongo.errors import (
    ConnectionFailure,
    DuplicateKeyError,
    ServerSelectionTimeoutError,
    WriteError,
)

from app.core.decorators import require_dto
from app.db.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.domains.live_chat.exceptions import ParentConversationNotFoundError

from ..entities import ChatMessage, ChatParticipants, Conversation
from ..schemas import CreateConversationDTO, PaginatedMessages


class ConversationRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        self.db = db

    @require_dto(CreateConversationDTO)
    async def create(self, dto: CreateConversationDTO) -> Conversation:
        try:
            if dto.parent_id is not None:
                parent = await self.conversation_exists(dto.parent_id)
                if not parent:
                    raise ParentConversationNotFoundError(f"Invalid parent_id {dto.parent_id}.")

            c = Conversation(
                service_session_id=dto.service_session_id,
                agent_id=dto.agent_id,
                client_id=dto.client_id,
                sequential_index=dto.sequential_index or 0,
                parent_id=dto.parent_id,
            )
            return await c.insert()

        except DuplicateKeyError as err:
            raise ResourceAlreadyExistsError("Chat", "index") from err

    async def get_by_id(self, id: PydanticObjectId) -> Conversation | None:
        return await Conversation.get(id)

    async def get_chat_participants(self, id: PydanticObjectId) -> ChatParticipants | None:
        return await Conversation.find_one(Conversation.id == id, projection_model=ChatParticipants)

    async def get_by_service_session_id(
        self, service_session_id: PydanticObjectId
    ) -> list[Conversation]:
        query: AggregationQuery[Conversation] = Conversation.aggregate(
            [
                {"$match": {"service_session_id": service_session_id}},
                {"$addFields": {"_sort": {"$ifNull": ["$finished_at", datetime(9999, 12, 31)]}}},
                {"$sort": {"_sort": 1}},
                {"$unset": "_sort"},
            ],
            projection_model=Conversation,
        )
        return await query.to_list()

    # async def get_paginated_messages(
    #     self, service_session_id: PydanticObjectId, page: int, limit: int
    # ) -> PaginatedMessages:
    #     query: AggregationQuery[Conversation] = Conversation.aggregate(
    #         [
    #             {"$match": {"service_session_id": service_session_id}},
    #             {"$sort": {"sequential_index": 1}},
    #         ],
    #         projection_model=Conversation,
    #     )
    #     conversations = await query.to_list()
    #     messages: list[ChatMessage] = []
    #     for c in conversations:
    #         messages.extend(c.messages)
    #     total = len(messages)
    #     ceiling = max(len(messages) - (page - 1) * limit, 0)
    #     floor = max(ceiling - limit, 0)
    #     messages = messages[floor:ceiling]

    #     return PaginatedMessages(
    #         messages=messages, total=total, page=page, limit=limit, has_next=floor > 0
    #     )

    async def get_paginated_messages(
        self, service_session_id: PydanticObjectId, page: int, limit: int
    ) -> PaginatedMessages:
        skip = (page - 1) * limit

        pipeline: list[dict[str, Any]] = [
            {"$match": {"service_session_id": service_session_id}},
            {"$sort": {"sequential_index": 1}},
            {"$unwind": "$messages"},
            {"$replaceRoot": {"newRoot": "$messages"}},
            {
                "$facet": {
                    "total": [{"$count": "count"}],
                    "messages": [
                        {"$sort": {"timestamp": 1}},
                        {
                            "$group": {
                                "_id": None,
                                "all": {"$push": "$$ROOT"},
                                "count": {"$sum": 1},
                            }
                        },
                        {
                            "$project": {
                                "sliced": {
                                    "$slice": [
                                        "$all",
                                        {"$max": [{"$subtract": ["$count", skip + limit]}, 0]},
                                        {
                                            "$subtract": [
                                                {"$max": [{"$subtract": ["$count", skip]}, 0]},
                                                {"$max": [
                                                        {"$subtract": ["$count", skip + limit]},
                                                        0,
                                                    ]
                                                },
                                            ]
                                        },
                                    ]
                                }
                            }
                        },
                        {"$unwind": "$sliced"},
                        {"$replaceRoot": {"newRoot": "$sliced"}},
                    ],
                }
            },
        ]

        cursor: AsyncIOMotorCommandCursor[dict[str, Any]] = (
            Conversation.get_motor_collection().aggregate(pipeline)
        )
        result: list[dict[str, Any]] = await cursor.to_list(length=1)
        facet: dict[str, list[dict[str, Any]]] = (
            result[0] if result else {"total": [], "messages": []}
        )

        total: int = facet["total"][0]["count"] if facet["total"] else 0
        ceiling: int = max(total - skip, 0)
        floor: int = max(ceiling - limit, 0)

        messages: list[ChatMessage] = [ChatMessage(**doc) for doc in facet["messages"]]

        return PaginatedMessages(
            messages=messages, total=total, page=page, limit=limit, has_next=floor > 0
        )

    async def get_current_service_session_participants(
        self, service_session_id: PydanticObjectId
    ) -> tuple[UUID, ...] | None:
        doc = await self.db["conversations"].find_one(
            {"service_session_id": service_session_id},
            {"client_id": 1, "agent_id": 1},
            sort=[("sequential_index", -1)],
        )
        if doc is None:
            return None
        participants: list[UUID] = [
            UUID(bytes=doc["client_id"])
            if isinstance(doc["client_id"], bytes)
            else UUID(doc["client_id"])
        ]
        agent_raw = doc.get("agent_id")
        if agent_raw is not None:
            participants.append(
                UUID(bytes=agent_raw) if isinstance(agent_raw, bytes) else UUID(agent_raw)
            )
        return tuple(participants)

    async def conversation_exists(self, id: PydanticObjectId) -> bool:
        doc = await self.db["conversations"].find_one({"_id": id}, {"_id": 1})
        return doc is not None

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
