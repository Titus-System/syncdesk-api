from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import ResponseFactoryDep
from app.db.mongo.dependencies import MongoSessionDep
from app.db.postgres.dependencies import PgSessionDep


class HealthService:
    def __init__(
        self, postgres_db: AsyncSession, mongo_db: AsyncIOMotorDatabase[dict[str, Any]]
    ) -> None:
        self.postgres_db = postgres_db
        self.mongo_db = mongo_db

    async def ping_postgres(self) -> bool:
        stmt = "SELECT 1"
        res = await self.postgres_db.execute(text(stmt))
        row = res.scalar_one_or_none()
        return row is not None

    async def ping_mongo(self) -> bool:
        ping = await self.mongo_db.client.admin.command("ping")
        return bool(ping)


def get_health_service(db: PgSessionDep, mongo_db: MongoSessionDep) -> HealthService:
    return HealthService(db, mongo_db)


HealthServiceDep = Annotated[HealthService, Depends(get_health_service)]


health_router = APIRouter()


@health_router.get("/ping", tags=["Health Check"])
def ping(response: ResponseFactoryDep) -> JSONResponse:
    return response.success(data={"message": "pong"})


@health_router.get("/health", tags=["Health Check"])
async def check_health(service: HealthServiceDep, response: ResponseFactoryDep) -> JSONResponse:
    data = {}
    data["postgres_status"] = "connected" if await service.ping_postgres() else "degraded"
    data["mongo_status"] = "connected" if await service.ping_mongo() else "degraded"
    return response.success(data=data, status_code=status.HTTP_200_OK)


@health_router.get("/ready", tags=["Health Check"])
async def check_ready(service: HealthServiceDep, response: ResponseFactoryDep) -> JSONResponse:
    return response.success({})
