import re
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from beanie import PydanticObjectId
from beanie.odm.queries.aggregation import AggregationQuery
from bson import Binary
from motor.motor_asyncio import AsyncIOMotorCommandCursor, AsyncIOMotorDatabase
from pymongo.errors import (
    ConnectionFailure,
    DuplicateKeyError,
    ServerSelectionTimeoutError,
    WriteError,
)

from app.core.decorators import require_dto
from app.core.logger import get_logger
from app.db.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.domains.live_chat.exceptions import ParentConversationNotFoundError

from ..entities import ChatMessage, ChatParticipants, Conversation
from ..schemas import ActiveConversationSummary, CreateConversationDTO, PaginatedMessages


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
                ticket_id=dto.ticket_id,
                agent_id=dto.agent_id,
                client_id=dto.client_id,
                sequential_index=dto.sequential_index or 0,
                parent_id=dto.parent_id,
            )
            return await c.insert()

        except DuplicateKeyError as err:
            details = err.details or {}
            get_logger("app.live_chat.repository").warning(
                "Duplicate conversation key error: keyPattern=%s keyValue=%s ticket_id=%s sequential_index=%s",
                details.get("keyPattern"),
                details.get("keyValue"),
                dto.ticket_id,
                dto.sequential_index,
            )
            raise ResourceAlreadyExistsError("Chat", "index") from err

    async def get_by_id(self, id: PydanticObjectId) -> Conversation | None:
        return await Conversation.get(id)

    async def get_chat_participants(self, id: PydanticObjectId) -> ChatParticipants | None:
        return await Conversation.find_one(Conversation.id == id, projection_model=ChatParticipants)

    async def get_by_client_id(self, client_id: UUID) -> list[Conversation]:
        query: AggregationQuery[Conversation] = Conversation.aggregate(
            [
                {"$match": {"client_id": Binary(client_id.bytes, subtype=4)}},
                {"$sort": {"sequential_index": 1}},
            ],
            projection_model=Conversation,
        )
        return await query.to_list()

    async def get_by_ticket_id(
        self, ticket_id: PydanticObjectId
    ) -> list[Conversation]:
        query: AggregationQuery[Conversation] = Conversation.aggregate(
            [
                {"$match": {"ticket_id": ticket_id}},
                {"$addFields": {"_sort": {"$ifNull": ["$finished_at", datetime(9999, 12, 31)]}}},
                {"$sort": {"_sort": 1}},
                {"$unset": "_sort"},
            ],
            projection_model=Conversation,
        )
        return await query.to_list()

    # async def get_paginated_messages(
    #     self, ticket_id: PydanticObjectId, page: int, limit: int
    # ) -> PaginatedMessages:
    #     query: AggregationQuery[Conversation] = Conversation.aggregate(
    #         [
    #             {"$match": {"ticket_id": ticket_id}},
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
        self, ticket_id: PydanticObjectId, page: int, limit: int
    ) -> PaginatedMessages:
        skip = (page - 1) * limit

        pipeline: list[dict[str, Any]] = [
            {"$match": {"ticket_id": ticket_id}},
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

    async def get_current_ticket_participants(
        self, ticket_id: PydanticObjectId
    ) -> tuple[UUID, ...] | None:
        doc = await self.db["conversations"].find_one(
            {"ticket_id": ticket_id},
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
        logger = get_logger("app.live_chat.repository")
        try:
            await conversation.update({"$push": {"messages": message.model_dump()}})
        except (ConnectionFailure, ServerSelectionTimeoutError) as e:
            logger.error("MongoDB connection error on add_message", extra={"conversation_id": str(id)}, exc_info=e)
            raise RuntimeError("Connection error when saving the message") from e
        except WriteError as e:
            logger.error("MongoDB write error on add_message", extra={"conversation_id": str(id)}, exc_info=e)
            raise RuntimeError("Error persisting message") from e

    async def attribute_agent(self, conversation_id: PydanticObjectId, agent_id: UUID) -> None:
        conversation = await Conversation.get(conversation_id)
        if not conversation:
            raise ResourceNotFoundError("Conversation", str(conversation_id))
        await conversation.update({"$set": {"agent_id": agent_id}})

    async def get_latest_open_by_ticket_id(
        self, ticket_id: PydanticObjectId
    ) -> Conversation | None:
        query: AggregationQuery[Conversation] = Conversation.aggregate(
            [
                {"$match": {"ticket_id": ticket_id, "finished_at": None}},
                {"$sort": {"sequential_index": -1}},
                {"$limit": 1},
            ],
            projection_model=Conversation,
        )
        results = await query.to_list()
        return results[0] if results else None

    async def get_active_conversations(
        self, user_id: UUID, is_admin: bool, search: str | None = None
    ) -> list[ActiveConversationSummary]:
        match_stage: dict[str, Any] = {"finished_at": None}

        if not is_admin:
            match_stage["$or"] = [
                {"agent_id": Binary(user_id.bytes, subtype=4)},
                {"agent_id": str(user_id)},
                {"agent_id": None},
            ]

        pipeline: list[dict[str, Any]] = [
            {"$match": match_stage},
            {
                "$lookup": {
                    "from": "tickets",
                    "localField": "ticket_id",
                    "foreignField": "_id",
                    "as": "ticket",
                }
            },
            {"$unwind": {"path": "$ticket", "preserveNullAndEmptyArrays": True}},
            {
                "$addFields": {
                    "last_message_obj": {"$arrayElemAt": [{"$ifNull": ["$messages", []]}, -1]},
                    "message_count": {"$size": {"$ifNull": ["$messages", []]}},
                    "client_name": {"$ifNull": ["$ticket.client.name", "Usuário"]},
                    "client_email": "$ticket.client.email",
                    "description": "$ticket.description",
                    "product": "$ticket.product",
                    "triage_id": {"$toString": "$ticket.triage_id"},
                    "ticket_status": "$ticket.status",
                    "created_at": "$ticket.creation_date",
                    "notes": {
                        "$map": {
                            "input": {"$ifNull": ["$ticket.comments", []]},
                            "as": "comment",
                            "in": "$$comment.text",
                        }
                    },
                    "current_agent": {
                        "$arrayElemAt": [{"$ifNull": ["$ticket.agent_history", []]}, -1]
                    },
                }
            },
            {
                "$addFields": {
                    "assigned_agent_id": "$current_agent.agent_id",
                    "assigned_agent_name": "$current_agent.name",
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "chat_id": "$_id",
                    "ticket_id": "$ticket_id",
                    "client_id": "$client_id",
                    "client_name": "$client_name",
                    "client_email": "$client_email",
                    "agent_id": "$agent_id",
                    "started_at": "$started_at",
                    "finished_at": "$finished_at",
                    "last_message": "$last_message_obj.content",
                    "last_message_at": "$last_message_obj.timestamp",
                    "message_count": "$message_count",
                    "triage_id": "$triage_id",
                    "product": "$product",
                    "description": "$description",
                    "notes": "$notes",
                    "ticket_status": "$ticket_status",
                    "assigned_agent_id": "$assigned_agent_id",
                    "assigned_agent_name": "$assigned_agent_name",
                    "created_at": "$created_at",
                }
            },
        ]

        if search:
            regex = {"$regex": re.escape(search), "$options": "i"}
            pipeline.append(
                {
                    "$match": {
                        "$or": [
                            {"client_name": regex},
                            {"client_email": regex},
                            {"last_message": regex},
                            {"description": regex},
                            {"product": regex},
                            {"notes": {"$elemMatch": regex}},
                        ]
                    }
                }
            )

        pipeline.append({"$sort": {"last_message_at": -1, "created_at": -1, "started_at": -1}})

        cursor: AsyncIOMotorCommandCursor[dict[str, Any]] = (
            Conversation.get_motor_collection().aggregate(pipeline)
        )
        docs = await cursor.to_list(length=None)

        return [
            ActiveConversationSummary(
                chat_id=doc["chat_id"],
                ticket_id=doc["ticket_id"],
                client_id=self._normalize_uuid_value(doc["client_id"]),
                client_name=doc.get("client_name") or "Usuário",
                client_email=doc.get("client_email"),
                agent_id=self._normalize_uuid_value(doc.get("agent_id")),
                started_at=doc["started_at"],
                finished_at=doc.get("finished_at"),
                last_message=doc.get("last_message"),
                last_message_at=doc.get("last_message_at"),
                message_count=doc.get("message_count", 0),
                triage_id=doc.get("triage_id"),
                product=doc.get("product"),
                description=doc.get("description"),
                notes=doc.get("notes", []),
                ticket_status=doc.get("ticket_status"),
                assigned_agent_id=self._normalize_uuid_value(doc.get("assigned_agent_id")),
                assigned_agent_name=doc.get("assigned_agent_name"),
                created_at=doc.get("created_at"),
            )
            for doc in docs
        ]

    @staticmethod
    def _normalize_uuid_value(value: Any) -> UUID | None:
        if value is None:
            return None
        if isinstance(value, UUID):
            return value
        if isinstance(value, Binary):
            return UUID(bytes=bytes(value))
        if isinstance(value, (bytes, bytearray)):
            return UUID(bytes=bytes(value))
        return UUID(str(value))
