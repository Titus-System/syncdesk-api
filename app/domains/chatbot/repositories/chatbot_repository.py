from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
from app.domains.chatbot.schemas import CreateAttendanceDTO
from app.domains.ticket.models import Ticket

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
        except Exception:
            query_id = attendance_id
        return await self.attendances_collection.find_one({"_id": query_id})

    async def save_attendance(self, attendance_id: str, full_attendance: dict[str, Any]) -> None:
        try:
            query_id = ObjectId(attendance_id)
        except Exception:
            query_id = attendance_id
            
        full_attendance["_id"] = query_id

        await self.attendances_collection.replace_one(
            {"_id": query_id},
            full_attendance,
            upsert=True
        )

    async def create_ticket(self, ticket: Ticket) -> str:
        created_ticket = await ticket.insert()
        return str(created_ticket.id)
