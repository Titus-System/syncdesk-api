from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.domains.notifications.entities import EmailOutbox
from app.domains.notifications.enums import EmailEventType, EmailOutboxStatus
from app.domains.notifications.schemas import PasswordResetPayload, WelcomeInvitePayload
from app.domains.notifications.worker import _backoff_seconds, _process_single, _render_html


def test_backoff_increases_with_attempts() -> None:
    b1 = _backoff_seconds(1, 900)
    b2 = _backoff_seconds(2, 900)
    b3 = _backoff_seconds(3, 900)
    assert b1 < b2 < b3


def test_backoff_caps_at_max() -> None:
    b = _backoff_seconds(20, 900)
    assert b <= 900 * 1.1  # allow for jitter


def _welcome_payload() -> WelcomeInvitePayload:
    return WelcomeInvitePayload(
        user_id=uuid4(),
        user_name="Alice",
        user_email="alice@example.com",
        one_time_password="Tmp1!",
        frontend_url="http://localhost:3000",
        token="tok123",
    )


def _reset_payload() -> PasswordResetPayload:
    return PasswordResetPayload(
        user_id=uuid4(),
        user_email="bob@example.com",
        frontend_url="http://localhost:3000",
        token="reset-tok",
    )


def _make_entry(
    payload: WelcomeInvitePayload | PasswordResetPayload,
    event_type: EmailEventType,
    attempts: int = 0,
    max_attempts: int = 5,
) -> EmailOutbox:
    entry = MagicMock(spec=EmailOutbox)
    entry.id = uuid4()
    entry.event_type = event_type
    entry.recipient = "test@example.com"
    entry.payload = payload
    entry.status = EmailOutboxStatus.PENDING
    entry.attempts = attempts
    entry.max_attempts = max_attempts
    entry.last_error = None
    entry.next_attempt_at = datetime.now(UTC)
    entry.created_at = datetime.now(UTC)
    entry.sent_at = None
    entry.locked_at = None
    entry.lock_owner = None
    return entry


def test_render_html_welcome_invite() -> None:
    entry = _make_entry(_welcome_payload(), EmailEventType.WELCOME_INVITE)
    subject, html = _render_html(entry)
    assert "Welcome" in subject
    assert "Alice" in html or "localhost" in html


def test_render_html_password_reset() -> None:
    entry = _make_entry(_reset_payload(), EmailEventType.PASSWORD_RESET)
    subject, html = _render_html(entry)
    assert "Reset" in subject
    assert "reset-tok" in html or "localhost" in html


@pytest.mark.asyncio
async def test_process_single_success_marks_sent() -> None:
    entry = _make_entry(_welcome_payload(), EmailEventType.WELCOME_INVITE)
    email_strategy = MagicMock()
    email_strategy._send = AsyncMock()

    mock_repo = AsyncMock()
    mock_repo.mark_sent = AsyncMock()

    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)

    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)

    mock_session = MagicMock()
    mock_session.begin.return_value = begin_cm

    session_maker = MagicMock()
    session_maker.return_value = session_cm
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)

    with patch(
        "app.domains.notifications.worker.EmailOutboxRepository",
        return_value=mock_repo,
    ):
        await _process_single(session_maker, email_strategy, entry, "worker-1")

    email_strategy._send.assert_awaited_once()
    mock_repo.mark_sent.assert_awaited_once()


@pytest.mark.asyncio
async def test_process_single_failure_marks_retry() -> None:
    entry = _make_entry(
        _welcome_payload(), EmailEventType.WELCOME_INVITE, attempts=0, max_attempts=5
    )
    email_strategy = MagicMock()
    email_strategy._send = AsyncMock(side_effect=Exception("SMTP down"))

    mock_repo = AsyncMock()
    mock_repo.mark_retry = AsyncMock()
    mock_repo.mark_dead = AsyncMock()

    session_cm = MagicMock()
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.begin.return_value = begin_cm
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session_maker = MagicMock(return_value=session_cm)

    with patch(
        "app.domains.notifications.worker.EmailOutboxRepository",
        return_value=mock_repo,
    ):
        await _process_single(session_maker, email_strategy, entry, "worker-1")

    mock_repo.mark_retry.assert_awaited_once()
    mock_repo.mark_dead.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_single_failure_marks_dead_when_max_attempts_reached() -> None:
    entry = _make_entry(
        _welcome_payload(), EmailEventType.WELCOME_INVITE, attempts=4, max_attempts=5
    )
    email_strategy = MagicMock()
    email_strategy._send = AsyncMock(side_effect=Exception("persistent failure"))

    mock_repo = AsyncMock()
    mock_repo.mark_retry = AsyncMock()
    mock_repo.mark_dead = AsyncMock()

    session_cm = MagicMock()
    begin_cm = MagicMock()
    begin_cm.__aenter__ = AsyncMock(return_value=None)
    begin_cm.__aexit__ = AsyncMock(return_value=False)
    mock_session = MagicMock()
    mock_session.begin.return_value = begin_cm
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session_maker = MagicMock(return_value=session_cm)

    with patch(
        "app.domains.notifications.worker.EmailOutboxRepository",
        return_value=mock_repo,
    ):
        await _process_single(session_maker, email_strategy, entry, "worker-1")

    mock_repo.mark_dead.assert_awaited_once()
    mock_repo.mark_retry.assert_not_awaited()
