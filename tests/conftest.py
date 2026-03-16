import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.postgres.base import Base
from app.db.mongo.dependencies import get_mongo_session
from app.db.postgres.dependencies import get_postgres_session
from app.main import create_app

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


@pytest.fixture(scope="module")
def app() -> FastAPI:
    app = create_app()
    return app


@pytest.fixture
async def client(app: FastAPI, db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """Provide an HTTPX AsyncClient connected to the FastAPI test app."""

    class _FakeMongoAdmin:
        async def command(self, _command: str) -> dict[str, int]:
            return {"ok": 1}

    class _FakeMongoClient:
        def __init__(self) -> None:
            self.admin = _FakeMongoAdmin()

    class _FakeMongoDb:
        def __init__(self) -> None:
            self.client = _FakeMongoClient()

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    def _override_mongo_session() -> _FakeMongoDb:
        return _FakeMongoDb()

    app.dependency_overrides[get_postgres_session] = _override_session
    app.dependency_overrides[get_mongo_session] = _override_mongo_session
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as async_client:
        yield async_client
    app.dependency_overrides.clear()
