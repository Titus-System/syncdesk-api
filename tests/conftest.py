import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
import pytest_asyncio
from beanie import init_beanie
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.mongo.dependencies import get_mongo_session
from app.db.postgres.base import Base
from app.db.postgres.dependencies import get_postgres_session
from app.domains.live_chat.entities import Conversation
from app.main import create_app


# Beanie initialization fixture
@pytest_asyncio.fixture(autouse=True)
async def init_beanie_for_tests(mongo_db_conn: AsyncIOMotorDatabase[dict[str,Any]]):
    await init_beanie(database=mongo_db_conn, document_models=[Conversation])
    yield
    # No teardown needed for Beanie

settings = get_settings()


@pytest.fixture(scope="session", autouse=True)
def _create_tables() -> Generator[None, Any, None]:
    """Create all tables once before the test session, drop after."""

    async def _setup() -> None:
        engine = create_async_engine(settings.test_database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await engine.dispose()

    async def _teardown() -> None:
        engine = create_async_engine(settings.test_database_url)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
        await engine.dispose()

    asyncio.run(_setup())
    yield
    asyncio.run(_teardown())


@pytest.fixture
def async_engine() -> AsyncEngine:
    engine = create_async_engine(
        settings.test_database_url,
        echo=False,
    )
    return engine


@pytest.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncSession | Any:
    async with async_engine.connect() as conn:
        trans = await conn.begin()

        async_session = async_sessionmaker(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )

        async with async_session() as session:
            yield session

        await trans.rollback()


@pytest.fixture
def mongo_client() -> AsyncIOMotorClient[dict[str,Any]]:
    client: AsyncIOMotorClient[dict[str,Any]] = AsyncIOMotorClient(settings.test_mongo_bd_url)
    return client


@pytest.fixture
async def mongo_db_conn(
    mongo_client: AsyncIOMotorClient[dict[str,Any]]
) -> AsyncGenerator[AsyncIOMotorDatabase[dict[str,Any]], None]:
    db: AsyncIOMotorDatabase[dict[str,Any]] = mongo_client.get_default_database()
    yield db
    mongo_client.close()


@pytest.fixture(scope="module")
def app() -> FastAPI:
    app = create_app()
    return app


@pytest.fixture
async def client(
    app: FastAPI,
    db_session: AsyncSession,
    mongo_db_conn: AsyncGenerator[AsyncIOMotorDatabase[dict[str,Any]], None]
) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTPX AsyncClient connected to the FastAPI test app."""

    async def _override_postgres() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_mongo() -> AsyncGenerator[AsyncIOMotorDatabase[dict[str,Any]], None]:
        yield mongo_db_conn

    app.dependency_overrides[get_postgres_session] = _override_postgres
    app.dependency_overrides[get_mongo_session] = _override_mongo
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
