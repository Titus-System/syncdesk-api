from typing import Any

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core import get_logger, get_settings


class MongoDb:
    client: AsyncIOMotorClient[dict[str, Any]] | None = None
    db: AsyncIOMotorDatabase[dict[str, Any]] | None = None

    async def connect(self) -> None:
        self.client = AsyncIOMotorClient(get_settings().mongo_database_url)
        self.db = self.client[get_settings().MONGO_DB]
        await self.client.admin.command("ping")
        get_logger().info(f"✓ MongoDB connected: {get_settings().MONGO_DB}")

    async def disconnect(self) -> None:
        if self.client:
            self.client.close()
        self.client, self.db = None, None

    def get_db(self) -> AsyncIOMotorDatabase[dict[str, Any]]:
        if self.db is None:
            raise RuntimeError("MongoDB is not connected")
        return self.db


mongo_db = MongoDb()
