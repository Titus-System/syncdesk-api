from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId

class ChatbotRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        # Nomes das coleções mantidos como no banco de dados para evitar perda de referência
        self.attendances_collection = db["atendimentos"]
        self.tickets_collection = db["chamados"]

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

    async def create_ticket(self, ticket_data: dict[str, Any]) -> str:
        result = await self.tickets_collection.insert_one(ticket_data)
        return str(result.inserted_id)