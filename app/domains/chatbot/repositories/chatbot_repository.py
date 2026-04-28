from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from bson.errors import InvalidId
from pymongo import DESCENDING
from app.domains.chatbot.schemas import AttendanceSearchFiltersDTO, CreateAttendanceDTO

class ChatbotRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        # Nomes das coleções mantidos como no banco de dados para evitar perda de referência
        self.attendances_collection = db["atendimentos"]
        self.tickets_collection = db["tickets"]

    async def create_attendance(self, dto: CreateAttendanceDTO, triage_id: str) -> dict[str, Any]:
        document = dto.model_dump(mode="json")

        query_id: ObjectId | str
        if ObjectId.is_valid(triage_id):
            query_id = ObjectId(triage_id)
        else:
            query_id = triage_id

        document["_id"] = query_id
        document["triage"] = []

        await self.attendances_collection.insert_one(document)

        return {
            "triage_id": str(query_id),
            "status": document.get("status"),
            "start_date": document.get("start_date"),
            "client": document.get("client"),
            "triage": document.get("triage"),
        }

    async def find_attendance(self, attendance_id: str) -> dict[str, Any] | None:
        try:
            query_id = ObjectId(attendance_id)
        except InvalidId:
            query_id = attendance_id
        return await self.attendances_collection.find_one({"_id": query_id})

    async def save_attendance(self, attendance_id: str, full_attendance: dict[str, Any]) -> None:
        try:
            query_id = ObjectId(attendance_id)
        except InvalidId:
            query_id = attendance_id

        full_attendance["_id"] = query_id

        await self.attendances_collection.replace_one(
            {"_id": query_id},
            full_attendance,
            upsert=True
        )

    async def list_attendances(
        self, filters: AttendanceSearchFiltersDTO
    ) -> list[dict[str, Any]]:
        query: dict[str, Any] = {}

        if filters.client_id is not None:
            query["client.id"] = str(filters.client_id)

        if filters.client_name is not None:
            query["client.name"] = {"$regex": filters.client_name, "$options": "i"}

        if filters.status is not None:
            query["status"] = filters.status.value

        if filters.result_type is not None:
            query["result.type"] = filters.result_type

        if filters.start_date_from is not None or filters.start_date_to is not None:
            date_query: dict[str, Any] = {}
            if filters.start_date_from is not None:
                date_query["$gte"] = filters.start_date_from.isoformat()
            if filters.start_date_to is not None:
                date_query["$lte"] = filters.start_date_to.isoformat()
            query["start_date"] = date_query

        if filters.has_evaluation is True:
            query["evaluation"] = {"$ne": None}
        elif filters.has_evaluation is False:
            query["evaluation"] = None

        if filters.rating is not None:
            query["evaluation.rating"] = filters.rating

        cursor = self.attendances_collection.find(query).sort("start_date", DESCENDING)
        return await cursor.to_list(length=None)
