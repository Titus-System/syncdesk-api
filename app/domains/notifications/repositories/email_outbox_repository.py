from datetime import datetime
from uuid import UUID

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.domains.notifications.entities import EmailOutbox as EmailOutboxEntity
from app.domains.notifications.enums import EmailEventType, EmailOutboxStatus
from app.domains.notifications.models import EmailOutbox
from app.domains.notifications.schemas import (
    EnqueueEmailOutboxDTO,
    PasswordResetPayload,
    WelcomeInvitePayload,
)


class EmailOutboxRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    @staticmethod
    def _to_entity(model: EmailOutbox) -> EmailOutboxEntity:
        event_type = EmailEventType(model.event_type)
        payload: WelcomeInvitePayload | PasswordResetPayload
        if event_type == EmailEventType.WELCOME_INVITE:
            payload = WelcomeInvitePayload(**model.payload)
        elif event_type == EmailEventType.PASSWORD_RESET:
            payload = PasswordResetPayload(**model.payload)
        else:
            raise ValueError(f"Unknown event_type: {model.event_type}")

        return EmailOutboxEntity(
            id=model.id,
            event_type=event_type,
            recipient=model.recipient,
            payload=payload,
            status=EmailOutboxStatus(model.status),
            attempts=model.attempts,
            max_attempts=model.max_attempts,
            last_error=model.last_error,
            next_attempt_at=model.next_attempt_at,
            created_at=model.created_at,
            sent_at=model.sent_at,
            locked_at=model.locked_at,
            lock_owner=model.lock_owner,
        )

    async def enqueue(self, dto: EnqueueEmailOutboxDTO) -> EmailOutboxEntity:
        row = EmailOutbox(
            event_type=dto.event_type,
            recipient=dto.recipient,
            payload=dto.payload.model_dump(mode="json"),
            status=EmailOutboxStatus.PENDING,
            max_attempts=dto.max_attempts,
        )
        self.db.add(row)
        await self.db.flush()
        return self._to_entity(row)

    async def claim_batch(
        self, now: datetime, worker_id: str, limit: int
    ) -> list[EmailOutboxEntity]:
        stmt = (
            select(EmailOutbox)
            .where(
                EmailOutbox.status.in_(
                    [EmailOutboxStatus.PENDING, EmailOutboxStatus.RETRY]
                ),
                EmailOutbox.next_attempt_at <= now,
            )
            .order_by(EmailOutbox.next_attempt_at)
            .with_for_update(skip_locked=True)
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        rows = list(result.scalars().all())

        if rows:
            ids = [r.id for r in rows]
            await self.db.execute(
                update(EmailOutbox)
                .where(EmailOutbox.id.in_(ids))
                .values(
                    status=EmailOutboxStatus.PROCESSING,
                    locked_at=now,
                    lock_owner=worker_id,
                )
            )
            await self.db.flush()

        return [self._to_entity(r) for r in rows]

    async def mark_sent(self, id: UUID, now: datetime) -> None:
        await self.db.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id == id)
            .values(
                status=EmailOutboxStatus.SENT,
                sent_at=now,
                locked_at=None,
                lock_owner=None,
                last_error=None,
            )
        )

    async def mark_retry(
        self,
        id: UUID,
        last_error: str,
        next_attempt_at: datetime,
        attempts: int,
    ) -> None:
        await self.db.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id == id)
            .values(
                status=EmailOutboxStatus.RETRY,
                last_error=last_error[:2000],
                next_attempt_at=next_attempt_at,
                attempts=attempts,
                locked_at=None,
                lock_owner=None,
            )
        )

    async def mark_dead(self, id: UUID, last_error: str) -> None:
        await self.db.execute(
            update(EmailOutbox)
            .where(EmailOutbox.id == id)
            .values(
                status=EmailOutboxStatus.DEAD,
                last_error=last_error[:2000],
                locked_at=None,
                lock_owner=None,
            )
        )
