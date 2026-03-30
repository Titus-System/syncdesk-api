from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase


class TicketRepository:
    def __init__(self, db: AsyncIOMotorDatabase[dict[str, Any]]):
        self.db = db
