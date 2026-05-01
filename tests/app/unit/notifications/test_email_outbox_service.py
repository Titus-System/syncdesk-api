from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.core.config import get_settings
from app.core.event_dispatcher.schemas import (
    PasswordResetEventSchema,
    WelcomeInviteEventSchema,
)
from app.domains.notifications.entities import (
    PasswordResetPayload,
    WelcomeInvitePayload,
)
from app.domains.notifications.enums import EmailEventType
from app.domains.notifications.services.email_outbox_service import EmailOutboxService


def _make_outbox_row() -> MagicMock:
    row = MagicMock()
    row.id = uuid4()
    return row


def _welcome_schema(roles: list[str] | None = None) -> WelcomeInviteEventSchema:
    return WelcomeInviteEventSchema(
        user_id=uuid4(),
        user_name="Test User",
        user_email="user@example.com",
        roles=roles or ["user"],
        raw_token="raw-token",
        one_time_password="TempPass1!",
        max_attempts=5,
    )


def _reset_schema(
    roles: list[str] | None = None,
    user_email: str = "user@example.com",
    raw_token: str = "reset-tok",
) -> PasswordResetEventSchema:
    return PasswordResetEventSchema(
        user_id=uuid4(),
        user_email=user_email,
        roles=roles or ["user"],
        raw_token=raw_token,
        max_attempts=5,
    )


class TestEmailOutboxService:

    @pytest.fixture
    def repo(self) -> AsyncMock:
        mock = AsyncMock()
        mock.enqueue = AsyncMock(return_value=_make_outbox_row())
        return mock

    @pytest.fixture
    def service(self, repo: AsyncMock) -> EmailOutboxService:
        return EmailOutboxService(repo=repo)


    @pytest.mark.asyncio
    async def test_enqueue_welcome_invite_calls_repo(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        await service.enqueue_welcome_invite(_welcome_schema(roles=["admin"]))
        repo.enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueue_welcome_invite_uses_web_url_for_admin(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        await service.enqueue_welcome_invite(_welcome_schema(roles=["admin"]))
        dto = repo.enqueue.call_args[0][0]
        assert isinstance(dto.payload, WelcomeInvitePayload)
        assert dto.payload.frontend_url == get_settings().WEB_FRONTEND_URL

    @pytest.mark.asyncio
    async def test_enqueue_welcome_invite_uses_mobile_url_for_client(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        await service.enqueue_welcome_invite(_welcome_schema(roles=["client"]))
        dto = repo.enqueue.call_args[0][0]
        assert isinstance(dto.payload, WelcomeInvitePayload)
        assert dto.payload.frontend_url == get_settings().MOBILE_FRONTEND_URL

    @pytest.mark.asyncio
    async def test_enqueue_welcome_invite_event_type(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        await service.enqueue_welcome_invite(_welcome_schema())
        dto = repo.enqueue.call_args[0][0]
        assert dto.event_type == EmailEventType.WELCOME_INVITE

    @pytest.mark.asyncio
    async def test_enqueue_welcome_invite_payload_contains_token(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        schema = WelcomeInviteEventSchema(
            user_id=uuid4(),
            user_name="Test User",
            user_email="user@example.com",
            roles=["user"],
            raw_token="my-secret-token",
            one_time_password="Pass!",
            max_attempts=5,
        )
        await service.enqueue_welcome_invite(schema)
        dto = repo.enqueue.call_args[0][0]
        assert isinstance(dto.payload, WelcomeInvitePayload)
        assert dto.payload.token == "my-secret-token"
        assert dto.payload.one_time_password == "Pass!"


    @pytest.mark.asyncio
    async def test_enqueue_password_reset_calls_repo(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        await service.enqueue_password_reset(_reset_schema(roles=["user"]))
        repo.enqueue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_enqueue_password_reset_event_type(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        await service.enqueue_password_reset(_reset_schema())
        dto = repo.enqueue.call_args[0][0]
        assert dto.event_type == EmailEventType.PASSWORD_RESET

    @pytest.mark.asyncio
    async def test_enqueue_password_reset_payload_contains_token(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        await service.enqueue_password_reset(_reset_schema(raw_token="reset-secret"))
        dto = repo.enqueue.call_args[0][0]
        assert isinstance(dto.payload, PasswordResetPayload)
        assert dto.payload.token == "reset-secret"
        assert not hasattr(dto.payload, "one_time_password")

    @pytest.mark.asyncio
    async def test_enqueue_password_reset_recipient_is_user_email(
        self, service: EmailOutboxService, repo: AsyncMock
    ) -> None:
        await service.enqueue_password_reset(_reset_schema(user_email="specific@example.com"))
        dto = repo.enqueue.call_args[0][0]
        assert dto.recipient == "specific@example.com"
