import asyncio
import re
from collections.abc import AsyncGenerator, Generator
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
)

from app.core.config import get_settings
from app.core.dependencies import get_email_service
from app.core.email.schemas import ResetPasswordEmailParams, WelcomeEmailParams
from app.core.email.strategy import EmailStrategy
from app.core.event_dispatcher import AppEvent, event_handler, get_event_dispatcher
from app.core.event_dispatcher.schemas import PasswordResetEventSchema, WelcomeInviteEventSchema
from app.db.mongo.dependencies import get_mongo_session
from app.db.postgres.base import Base

import app.domains.auth.models  # noqa: F401 — register models with Base.metadata
import app.domains.companies.models  # noqa: F401 — register models with Base.metadata
import app.domains.notifications.models  # noqa: F401 — register models with Base.metadata
import app.domains.products.models  # noqa: F401 — register models with Base.metadata
from app.db.postgres.dependencies import get_postgres_session
from app.domains.auth.entities import UserWithRoles
from app.main import create_app
from app.seed.seed import seed_permissions, seed_role_permissions, seed_roles

settings = get_settings()

ADMIN_ROLE_ID = 1
AGENT_ROLE_ID = 3

# ────────────────────────────────────────────────────────
# Fake Email Strategy (captures emails instead of sending)
# ────────────────────────────────────────────────────────


@dataclass
class SentEmail:
    to: str
    kind: str  # "welcome" or "reset"
    params: WelcomeEmailParams | ResetPasswordEmailParams


class FakeEmailStrategy(EmailStrategy):
    """In-memory email stub that records every call."""

    def __init__(self) -> None:
        self.sent: list[SentEmail] = []

    async def send_welcome_email(self, to: str, email_params: WelcomeEmailParams) -> None:
        self.sent.append(SentEmail(to=to, kind="welcome", params=email_params))

    async def send_reset_email(self, to: str, email_params: ResetPasswordEmailParams) -> None:
        self.sent.append(SentEmail(to=to, kind="reset", params=email_params))

    # ── helpers for test assertions ──

    def last_welcome(self) -> SentEmail | None:
        return next((e for e in reversed(self.sent) if e.kind == "welcome"), None)

    def last_reset(self) -> SentEmail | None:
        return next((e for e in reversed(self.sent) if e.kind == "reset"), None)

    @staticmethod
    def extract_token_from_url(url: str) -> str:
        """Pull the `token=…` query-param value out of a URL."""
        match = re.search(r"[?&]token=([^&]+)", url)
        assert match, f"No token found in URL: {url}"
        return match.group(1)


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


@pytest.fixture
def fake_email() -> FakeEmailStrategy:
    """Provide a fresh FakeEmailStrategy for each test."""
    return FakeEmailStrategy()


@pytest.fixture
def app(fake_email: FakeEmailStrategy) -> FastAPI:
    # Fresh dispatcher per test so handlers don't bleed across tests
    get_event_dispatcher.cache_clear()
    application = create_app()
    application.dependency_overrides[get_email_service] = lambda: fake_email
    return application


@pytest.fixture
async def client(
    app: FastAPI,
    fake_email: FakeEmailStrategy,
    db_session: AsyncSession,
    mongo_db_conn: AsyncGenerator[AsyncIOMotorDatabase[dict[str,Any]], None]
    ) -> AsyncGenerator[AsyncClient, None]:
    """AsyncClient wired to the test DB session via dependency override."""

    async def _override_session() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_mongo() -> AsyncGenerator[AsyncIOMotorDatabase[dict[str,Any]], None]:
        yield mongo_db_conn

    app.dependency_overrides[get_postgres_session] = _override_session
    app.dependency_overrides[get_mongo_session] = _override_mongo
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        # Lifespan has run; subscribe test capture handlers on the fresh dispatcher
        _register_email_capture(get_event_dispatcher(), fake_email)
        yield ac

    app.dependency_overrides.clear()


def _register_email_capture(dispatcher: Any, fake_email: FakeEmailStrategy) -> None:
    """Subscribe lightweight handlers that feed event data into FakeEmailStrategy."""

    @event_handler(WelcomeInviteEventSchema)
    async def _capture_welcome(schema: WelcomeInviteEventSchema) -> None:
        cfg = get_settings()
        base_url = (
            cfg.WEB_FRONTEND_URL
            if ("agent" in schema.roles or "admin" in schema.roles)
            else cfg.MOBILE_FRONTEND_URL
        )
        params = WelcomeEmailParams(
            user_name=schema.user_name,
            user_email=schema.user_email,
            one_time_password=schema.one_time_password,
            login_url=f"{base_url}/login?token={schema.raw_token}",
        )
        await fake_email.send_welcome_email(schema.user_email, params)

    @event_handler(PasswordResetEventSchema)
    async def _capture_reset(schema: PasswordResetEventSchema) -> None:
        cfg = get_settings()
        base_url = (
            cfg.WEB_FRONTEND_URL
            if ("agent" in schema.roles or "admin" in schema.roles)
            else cfg.MOBILE_FRONTEND_URL
        )
        params = ResetPasswordEmailParams(
            user_email=schema.user_email,
            reset_url=f"{base_url}/reset-password?token={schema.raw_token}",
        )
        await fake_email.send_reset_email(schema.user_email, params)

    dispatcher.subscribe(AppEvent.USER_WELCOME_INVITE, _capture_welcome)
    dispatcher.subscribe(AppEvent.USER_PASSWORD_RESET, _capture_reset)


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

    async def login_raw(
        self,
        email: str = "e2e@test.com",
        password: str = "Secure123!",
    ) -> Any:
        """Return the raw httpx Response (no assertions)."""
        return await self.client.post(
            "/api/auth/login",
            json={"email": email, "password": password},
        )

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

    async def register_agent(
        self,
        email: str = "agent@test.com",
        username: str = "agentuser",
        password: str = "Secure123!",
    ) -> dict[str, Any]:
        data = await self.register(email, username, password)
        user_id = data["id"]
        await self.db_session.execute(
            text(
                "INSERT INTO user_roles (user_id, role_id)"
                " VALUES (:uid, :rid) ON CONFLICT DO NOTHING"
            ),
            {"uid": user_id, "rid": AGENT_ROLE_ID},
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

    async def me(self, access_token: str) -> UserWithRoles:
        r = await self.client.get(
            "/api/auth/me",
            headers = self.auth_headers(access_token)
        )

        assert r.status_code == 200
        res = r.json()["data"]
        res["id"] = UUID(res["id"])
        return UserWithRoles(**res)


@pytest.fixture
def auth(client: AsyncClient, db_session: AsyncSession, _seed_auth_data: None) -> AuthActions:
    return AuthActions(client, db_session)
