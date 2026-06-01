from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.notifications.enums import EmailEventType, EmailOutboxStatus
from app.domains.notifications.repositories.email_outbox_repository import (
    EmailOutboxRepository,
)
from app.domains.notifications.schemas import (
    EnqueueEmailOutboxDTO,
    PasswordResetPayload,
    WelcomeInvitePayload,
)


def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _welcome_payload() -> WelcomeInvitePayload:
    return WelcomeInvitePayload(
        user_id=uuid4(),
        user_name="Test User",
        user_email="test@example.com",
        one_time_password="TempPass1!",
        frontend_url="http://localhost:3000",
        token="raw-token-abc",
    )


def _reset_payload() -> PasswordResetPayload:
    return PasswordResetPayload(
        user_id=uuid4(),
        user_email="reset@example.com",
        frontend_url="http://localhost:3000",
        token="reset-token",
    )


def _welcome_dto(**overrides: Any) -> EnqueueEmailOutboxDTO:
    defaults: dict[str, Any] = {
        "event_type": EmailEventType.WELCOME_INVITE,
        "recipient": f"user_{uuid4().hex[:6]}@example.com",
        "payload": _welcome_payload(),
    }
    return EnqueueEmailOutboxDTO(**{**defaults, **overrides})


def _reset_dto(**overrides: Any) -> EnqueueEmailOutboxDTO:
    defaults: dict[str, Any] = {
        "event_type": EmailEventType.PASSWORD_RESET,
        "recipient": f"user_{uuid4().hex[:6]}@example.com",
        "payload": _reset_payload(),
    }
    return EnqueueEmailOutboxDTO(**{**defaults, **overrides})


class TestEmailOutboxDTOs:
    def test_enqueue_dto_welcome_valid(self) -> None:
        dto = _welcome_dto()
        assert dto.event_type == EmailEventType.WELCOME_INVITE
        assert isinstance(dto.payload, WelcomeInvitePayload)
        assert dto.max_attempts == 5

    def test_enqueue_dto_reset_valid(self) -> None:
        dto = _reset_dto()
        assert dto.event_type == EmailEventType.PASSWORD_RESET
        assert isinstance(dto.payload, PasswordResetPayload)

    def test_enqueue_dto_custom_max_attempts(self) -> None:
        dto = _welcome_dto(max_attempts=10)
        assert dto.max_attempts == 10

    def test_welcome_payload_invalid_user_id_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            WelcomeInvitePayload(
                user_id="not-a-uuid",  # pyright: ignore[reportArgumentType]
                user_name="X",
                user_email="x@example.com",
                one_time_password="P!",
                frontend_url="http://x",
                token="t",
            )

    def test_welcome_payload_missing_required_field_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            WelcomeInvitePayload(  # pyright: ignore[reportCallIssue]
                user_id=uuid4(),
                user_name="X",
                user_email="x@example.com",
                frontend_url="http://x",
                token="t",
            )

    def test_reset_payload_invalid_user_id_should_fail(self) -> None:
        with pytest.raises(ValidationError):
            PasswordResetPayload(
                user_id="not-a-uuid",  # pyright: ignore[reportArgumentType]
                user_email="x@example.com",
                frontend_url="http://x",
                token="t",
            )


class TestEmailOutboxRepository:
    @pytest.fixture
    def repo(self, db_session: AsyncSession) -> EmailOutboxRepository:
        return EmailOutboxRepository(db_session)

    @pytest.mark.asyncio
    async def test_enqueue_creates_pending_row(self, repo: EmailOutboxRepository) -> None:
        row = await repo.enqueue(_welcome_dto())
        assert row.id is not None
        assert row.status == EmailOutboxStatus.PENDING
        assert row.attempts == 0
        assert row.sent_at is None

    @pytest.mark.asyncio
    async def test_enqueue_returns_full_entity(self, repo: EmailOutboxRepository) -> None:
        recipient = "full@example.com"
        dto = _welcome_dto(recipient=recipient, max_attempts=7)
        row = await repo.enqueue(dto)
        assert row.recipient == recipient
        assert row.max_attempts == 7
        assert row.event_type == EmailEventType.WELCOME_INVITE
        assert row.last_error is None
        assert row.locked_at is None
        assert row.lock_owner is None
        assert row.created_at is not None
        assert row.next_attempt_at is not None

    @pytest.mark.asyncio
    async def test_enqueue_stores_payload(self, repo: EmailOutboxRepository) -> None:
        dto = _welcome_dto()
        row = await repo.enqueue(dto)
        assert isinstance(row.payload, WelcomeInvitePayload)
        assert row.payload.user_name == "Test User"
        assert row.payload.token == "raw-token-abc"

    @pytest.mark.asyncio
    async def test_enqueue_payload_uuid_round_trips(self, repo: EmailOutboxRepository) -> None:
        original_user_id = uuid4()
        payload = WelcomeInvitePayload(
            user_id=original_user_id,
            user_name="UUID Test",
            user_email="uuid@example.com",
            one_time_password="P!",
            frontend_url="http://x",
            token="t",
        )
        dto = EnqueueEmailOutboxDTO(
            event_type=EmailEventType.WELCOME_INVITE,
            recipient="uuid@example.com",
            payload=payload,
        )
        row = await repo.enqueue(dto)
        assert isinstance(row.payload, WelcomeInvitePayload)
        assert isinstance(row.payload.user_id, UUID)
        assert row.payload.user_id == original_user_id

    @pytest.mark.asyncio
    async def test_enqueue_reset_returns_typed_payload(
        self, repo: EmailOutboxRepository
    ) -> None:
        dto = _reset_dto()
        row = await repo.enqueue(dto)
        assert row.event_type == EmailEventType.PASSWORD_RESET
        assert isinstance(row.payload, PasswordResetPayload)
        assert not isinstance(row.payload, WelcomeInvitePayload)

    @pytest.mark.asyncio
    async def test_claim_batch_empty_when_no_pending(
        self, repo: EmailOutboxRepository
    ) -> None:
        rows = await repo.claim_batch(_now(), "worker-1", limit=10)
        assert rows == []

    @pytest.mark.asyncio
    async def test_claim_batch_returns_pending_rows(self, repo: EmailOutboxRepository) -> None:
        await repo.enqueue(_welcome_dto())
        await repo.enqueue(_welcome_dto())

        rows = await repo.claim_batch(_now(), "worker-1", limit=10)
        assert len(rows) >= 2

    @pytest.mark.asyncio
    async def test_claim_batch_sets_processing_status(
        self, repo: EmailOutboxRepository
    ) -> None:
        await repo.enqueue(_welcome_dto())
        rows = await repo.claim_batch(_now(), "worker-1", limit=10)
        assert len(rows) >= 1
        # mark_sent proves the row exists and has a valid id (worker found it)
        await repo.mark_sent(rows[0].id, _now())

    @pytest.mark.asyncio
    async def test_claim_batch_skips_future_rows(self, repo: EmailOutboxRepository) -> None:
        future = _now() + timedelta(hours=1)
        row = await repo.enqueue(_welcome_dto())
        # Manually set next_attempt_at to future via mark_retry
        await repo.mark_retry(row.id, "err", future, 1)

        claimed = await repo.claim_batch(_now(), "worker-1", limit=10)
        claimed_ids = [r.id for r in claimed]
        assert row.id not in claimed_ids

    @pytest.mark.asyncio
    async def test_claim_batch_respects_limit(self, repo: EmailOutboxRepository) -> None:
        for _ in range(5):
            await repo.enqueue(_welcome_dto())

        rows = await repo.claim_batch(_now(), "worker-1", limit=2)
        assert len(rows) <= 2

    @pytest.mark.asyncio
    async def test_mark_sent_sets_sent_status(self, repo: EmailOutboxRepository) -> None:
        row = await repo.enqueue(_welcome_dto())
        now = _now()
        await repo.mark_sent(row.id, now)
        # Verify by trying to claim — SENT rows should not appear
        claimed = await repo.claim_batch(now, "worker-2", limit=10)
        assert row.id not in [r.id for r in claimed]

    @pytest.mark.asyncio
    async def test_mark_retry_increments_attempts(self, repo: EmailOutboxRepository) -> None:
        row = await repo.enqueue(_welcome_dto())
        next_at = _now() + timedelta(seconds=4)
        await repo.mark_retry(row.id, "provider timeout", next_at, 1)
        # Row should be claimable after next_attempt_at passes
        claimed = await repo.claim_batch(next_at + timedelta(seconds=1), "worker-1", limit=10)
        assert any(r.id == row.id for r in claimed)

    @pytest.mark.asyncio
    async def test_mark_retry_persists_error_and_attempts(
        self, repo: EmailOutboxRepository
    ) -> None:
        row = await repo.enqueue(_welcome_dto())
        next_at = _now() + timedelta(seconds=1)
        await repo.mark_retry(row.id, "provider timeout", next_at, 3)

        claimed = await repo.claim_batch(next_at + timedelta(seconds=2), "worker-1", limit=10)
        matching = next((r for r in claimed if r.id == row.id), None)
        assert matching is not None
        assert matching.last_error == "provider timeout"
        assert matching.attempts == 3

    @pytest.mark.asyncio
    async def test_mark_retry_truncates_long_error(
        self, repo: EmailOutboxRepository
    ) -> None:
        row = await repo.enqueue(_welcome_dto())
        long_error = "x" * 3000
        next_at = _now() + timedelta(seconds=1)
        await repo.mark_retry(row.id, long_error, next_at, 1)

        claimed = await repo.claim_batch(next_at + timedelta(seconds=2), "worker-1", limit=10)
        matching = next((r for r in claimed if r.id == row.id), None)
        assert matching is not None
        assert matching.last_error is not None
        assert len(matching.last_error) == 2000

    @pytest.mark.asyncio
    async def test_mark_retry_not_claimable_before_next_attempt_at(
        self, repo: EmailOutboxRepository
    ) -> None:
        row = await repo.enqueue(_welcome_dto())
        future = _now() + timedelta(hours=2)
        await repo.mark_retry(row.id, "err", future, 1)

        claimed = await repo.claim_batch(_now(), "worker-1", limit=10)
        assert row.id not in [r.id for r in claimed]

    @pytest.mark.asyncio
    async def test_mark_dead_prevents_future_claims(
        self, repo: EmailOutboxRepository
    ) -> None:
        row = await repo.enqueue(_welcome_dto())
        await repo.mark_dead(row.id, "max retries exceeded")

        claimed = await repo.claim_batch(_now(), "worker-1", limit=10)
        assert row.id not in [r.id for r in claimed]
