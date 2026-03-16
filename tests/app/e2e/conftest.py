import asyncio
from collections.abc import AsyncGenerator, Generator
from typing import Any

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.postgres.base import Base
from app.db.postgres.dependencies import get_postgres_session
from app.main import create_app
from app.seed.seed import seed_permissions, seed_role_permissions, seed_roles

settings = get_settings()

ADMIN_ROLE_ID = 1


# ────────────────────────────────────────────────────────
# Session-scoped DDL (sync fixture → asyncio.run)
# ────────────────────────────────────────────────────────


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


# ────────────────────────────────────────────────────────
# Per-test fixtures (all function-scoped → same event loop)
# ────────────────────────────────────────────────────────


@pytest.fixture
async def async_engine() -> AsyncGenerator[AsyncEngine, None]:
    engine = create_async_engine(
        settings.test_database_url, echo=False, pool_size=5, max_overflow=0
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(async_engine: AsyncEngine) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional DB session with savepoint-based isolation.

    The outer transaction is never committed. Each ``session.commit()``
    inside the app only releases a SAVEPOINT. At the end of the test the outer
    transaction is rolled back, leaving the database clean.
    """
    async with async_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(bind=conn, expire_on_commit=False)

        # Start the first SAVEPOINT
        await conn.begin_nested()

        @event.listens_for(session.sync_session, "after_transaction_end")
        def _restart_savepoint(sess: Any, transaction: Any) -> None:
            """Re-open a SAVEPOINT after every commit (savepoint release)."""
            if conn.closed or conn.invalidated:
                return
            if not conn.in_nested_transaction():
                conn.sync_connection.begin_nested()

        yield session

        await session.close()
        await trans.rollback()


@pytest.fixture
def app() -> FastAPI:
    return create_app()


@pytest.fixture
async def client(app: FastAPI, db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the test DB session via dependency override."""

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    app.dependency_overrides[get_postgres_session] = _override_session
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()


# ────────────────────────────────────────────────────────
# Seed permissions + admin role for permission-protected endpoints
# ────────────────────────────────────────────────────────


@pytest.fixture
async def _seed_auth_data(db_session: AsyncSession) -> None:
    """Seed roles, permissions, and role-permission associations."""
    await seed_roles(db_session)
    await seed_permissions(db_session)
    await seed_role_permissions(db_session)
    # Advance sequences past the explicitly-inserted IDs to avoid conflicts
    await db_session.execute(text("SELECT setval('roles_id_seq', (SELECT MAX(id) FROM roles))"))
    await db_session.execute(
        text("SELECT setval('permissions_id_seq', (SELECT MAX(id) FROM permissions))")
    )
    await db_session.flush()


# ────────────────────────────────────────────────────────
# Auth helpers reusable across e2e tests
# ────────────────────────────────────────────────────────
class AuthActions:
    """Convenience wrapper around the auth endpoints."""

    def __init__(self, client: AsyncClient, db_session: AsyncSession) -> None:
        self.client = client
        self.db_session = db_session

    async def register(
        self,
        email: str = "e2e@test.com",
        username: str = "e2euser",
        password: str = "Secure123!",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"email": email, "username": username, "password": password}
        r = await self.client.post(
            "/api/auth/register",
            json=payload,
        )
        assert r.status_code == 201, f"Register failed: {r.text}"
        res: dict[str, Any] = r.json()["data"]
        return res

    async def login(
        self,
        email: str = "e2e@test.com",
        password: str = "Secure123!",
    ) -> dict[str, Any]:
        r = await self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )
        assert r.status_code == 200, f"Login failed: {r.text}"
        res = r.json()["data"]
        return res

    async def register_and_login(
        self,
        email: str = "e2e@test.com",
        username: str = "e2euser",
        password: str = "Secure123!",
    ) -> dict[str, Any]:
        """Register a user and return login tokens."""
        await self.register(email, username, password)
        return await self.login(email, password)

    async def register_admin(
        self,
        email: str = "admin@test.com",
        username: str = "adminuser",
        password: str = "Secure123!",
    ) -> dict[str, Any]:
        """Register a user and bootstrap admin role via direct DB insert."""
        data = await self.register(email, username, password)
        user_id = data["id"]
        # Bootstrap: directly assign admin role via DB (chicken-and-egg problem)
        await self.db_session.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id)"
                " VALUES (:uid, :rid) ON CONFLICT DO NOTHING"
            ),
            {"uid": user_id, "rid": ADMIN_ROLE_ID},
        )
        await self.db_session.flush()
        return data

    async def register_and_login_admin(
        self,
        email: str = "admin@test.com",
        username: str = "adminuser",
        password: str = "Secure123!",
    ) -> dict[str, Any]:
        """Register a user with the admin role and return login tokens."""
        await self.register_admin(email, username, password)
        return await self.login(email, password)

    def auth_headers(self, access_token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {access_token}"}


@pytest.fixture
def auth(client: AsyncClient, db_session: AsyncSession, _seed_auth_data: None) -> AuthActions:
    return AuthActions(client, db_session)
