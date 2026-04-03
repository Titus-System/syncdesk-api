from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from app.core.email.schemas import ResetPasswordEmailParams, WelcomeEmailParams
from app.infra.email import resend_service
from app.infra.email.resend_service import ResendEmailService


class FakeResendError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"resend error {status_code}")
        self.status_code = status_code


@pytest.mark.asyncio
async def test_send_reset_email_delegates_to_send(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ResendEmailService()
    send_mock = AsyncMock()
    render_mock = MagicMock(return_value="<html>reset</html>")
    monkeypatch.setattr(service, "_send", send_mock)
    monkeypatch.setattr(resend_service, "render_password_reset_email", render_mock)

    params = ResetPasswordEmailParams(
        user_email="user@example.com",
        reset_url="https://syncdesk.pro/reset?token=test-token",
    )

    await service.send_reset_email("user@example.com", params)

    render_mock.assert_called_once_with(params)

    send_mock.assert_awaited_once_with(
        "user@example.com",
        "Reset Your Password",
        "<html>reset</html>",
    )


@pytest.mark.asyncio
async def test_send_welcome_email_delegates_to_send(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ResendEmailService()
    send_mock = AsyncMock()
    render_mock = MagicMock(return_value="<html>welcome</html>")
    monkeypatch.setattr(service, "_send", send_mock)
    monkeypatch.setattr(resend_service, "render_welcome_email", render_mock)

    params = WelcomeEmailParams(
        user_name="Pedro",
        user_email="user@example.com",
        one_time_password="A1B2C3",
        login_url="https://syncdesk.pro/login",
    )

    await service.send_welcome_email("user@example.com", params)

    render_mock.assert_called_once_with(params)

    send_mock.assert_awaited_once_with(
        "user@example.com",
        "Welcome to SyncDesk!",
        "<html>welcome</html>",
    )


@pytest.mark.asyncio
async def test_send_retries_on_timeout_then_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    service = ResendEmailService()
    service.logger = MagicMock()

    send_async_mock = AsyncMock(
        side_effect=[
            httpx.TimeoutException("timeout"),
            httpx.TimeoutException("timeout"),
            None,
        ]
    )
    sleep_mock = AsyncMock()

    monkeypatch.setattr(resend_service.resend.Emails, "send_async", send_async_mock)
    monkeypatch.setattr(resend_service.asyncio, "sleep", sleep_mock)

    await service._send("user@example.com", "Subject", "<html>body</html>")

    assert send_async_mock.await_count == 3
    sleep_mock.assert_any_await(2)
    sleep_mock.assert_any_await(4)
    assert sleep_mock.await_count == 2
    assert service.logger.warning.call_count == 2
    service.logger.error.assert_not_called()


@pytest.mark.asyncio
async def test_send_raises_non_retryable_resend_error_without_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ResendEmailService()
    service.logger = MagicMock()

    send_async_mock = AsyncMock(side_effect=FakeResendError(400))

    monkeypatch.setattr(resend_service, "ResendError", FakeResendError)
    monkeypatch.setattr(resend_service.resend.Emails, "send_async", send_async_mock)

    with pytest.raises(FakeResendError):
        await service._send("user@example.com", "Subject", "<html>body</html>")

    assert send_async_mock.await_count == 1
    service.logger.warning.assert_not_called()
    service.logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_send_raises_after_max_retries_for_retryable_resend_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = ResendEmailService()
    service.logger = MagicMock()

    send_async_mock = AsyncMock(side_effect=FakeResendError(503))
    sleep_mock = AsyncMock()

    monkeypatch.setattr(resend_service, "ResendError", FakeResendError)
    monkeypatch.setattr(resend_service.resend.Emails, "send_async", send_async_mock)
    monkeypatch.setattr(resend_service.asyncio, "sleep", sleep_mock)

    with pytest.raises(FakeResendError):
        await service._send("user@example.com", "Subject", "<html>body</html>")

    assert send_async_mock.await_count == resend_service.MAX_RETRIES
    assert sleep_mock.await_count == resend_service.MAX_RETRIES - 1
    assert service.logger.warning.call_count == resend_service.MAX_RETRIES - 1
    service.logger.error.assert_called_once()
