from datetime import datetime
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.chatbot.enums import AttendanceStatus
from app.domains.chatbot.schemas import AttendanceSearchFiltersDTO, CreateAttendanceDTO


class ChatbotRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]) -> None:
        self.db = db
        self.collection = db["atendimentos"]

    async def create_attendance(
        self,
        dto: CreateAttendanceDTO,
        triage_id: str,
    ) -> dict[str, Any]:
        object_id = ObjectId(triage_id)
        data = dto.model_dump(mode="json")
        data["_id"] = object_id
        await self.collection.insert_one(data)
        return data

    async def find_attendance(self, triage_id: str) -> dict[str, Any] | None:
        return await self.collection.find_one({"_id": ObjectId(triage_id)})

    async def save_attendance(
        self,
        triage_id: str,
        attendance: dict[str, Any],
    ) -> None:
        object_id = ObjectId(triage_id)
        attendance["_id"] = object_id
        await self.collection.replace_one(
            {"_id": object_id},
            attendance,
            upsert=True,
        )

    async def list_attendances(
        self,
        filters: AttendanceSearchFiltersDTO,
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}

        if filters.client_id is not None:
            query["client.id"] = str(filters.client_id)

        if filters.client_name is not None:
            query["client.name"] = {
                "$regex": filters.client_name,
                "$options": "i",
            }

        if filters.status is not None:
            query["status"] = filters.status.value

        if filters.result_type is not None:
            query["result.type"] = filters.result_type

        if filters.has_evaluation is not None:
            query["evaluation"] = {"$ne": None} if filters.has_evaluation else None

        if filters.rating is not None:
            query["evaluation.rating"] = filters.rating

        date_query: dict[str, Any] = {}

        if filters.start_date_from is not None:
            date_query["$gte"] = filters.start_date_from.isoformat()

        if filters.start_date_to is not None:
            date_query["$lte"] = filters.start_date_to.isoformat()

        if date_query:
            query["start_date"] = date_query

        cursor = self.collection.find(query).sort("start_date", -1)
        return await cursor.to_list(length=None)

    async def finish_attendance_pending_evaluation(
        self,
        triage_id: str,
        finished_at: str,
    ) -> bool:
        result = await self.collection.update_one(
            {
                "_id": ObjectId(triage_id),
                "status": {"$ne": AttendanceStatus.FINISHED.value},
            },
            {
                "$set": {
                    "status": AttendanceStatus.FINISHED.value,
                    "end_date": finished_at,
                }
            },
        )
        return result.modified_count > 0

    async def find_ticket_and_conversation_ids_by_triage_id(
        self,
        triage_id: str,
    ) -> tuple[str | None, str | None]:
        triage_object_id = ObjectId(triage_id)

        ticket = await self.db["tickets"].find_one(
            {"triage_id": triage_object_id},
            sort=[("_id", -1)],
        )

        if ticket is None:
            return None, None

        ticket_id = str(ticket["_id"])
        chat_id: str | None = None

        chat_ids = ticket.get("chat_ids") or []
        if chat_ids:
            chat_id = str(chat_ids[-1])

        if chat_id is None:
            conversation = await self.db["conversations"].find_one(
                {"ticket_id": ticket["_id"]},
                sort=[("sequential_index", -1)],
            )

            if conversation is not None:
                chat_id = str(conversation["_id"])

        return ticket_id, chat_id