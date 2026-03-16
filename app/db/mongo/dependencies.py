from typing import Annotated, Any

from fastapi import Depends
from motor.motor_asyncio import AsyncIOMotorDatabase

from .db import mongo_db


def get_mongo_session() -> AsyncIOMotorDatabase[dict[str, Any]]:
    return mongo_db.get_db()


MongoSessionDep = Annotated[AsyncIOMotorDatabase[dict[str, Any]], Depends(get_mongo_session)]
