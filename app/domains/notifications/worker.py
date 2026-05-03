import asyncio
import os
import random
import socket
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.email.renderer import render_password_reset_email, render_welcome_email
from app.core.email.schemas import ResetPasswordEmailParams, WelcomeEmailParams
from app.core.email.strategy import EmailStrategy
from app.core.logger import get_logger
from app.domains.notifications.entities import (
    EmailOutbox,
    WelcomeInvitePayload,
)
from app.domains.notifications.metrics import email_outbox_depth, email_outbox_processed_total
from app.domains.notifications.models import EmailOutboxStatus
from app.domains.notifications.repositories.email_outbox_repository import (
    EmailOutboxRepository,
)

logger = get_logger("app.notifications.worker")


def _worker_id() -> str:
    settings = get_settings()
    if settings.EMAIL_OUTBOX_WORKER_ID:
        return settings.EMAIL_OUTBOX_WORKER_ID
    return f"{socket.gethostname()}-{os.getpid()}"


def _backoff_seconds(attempts: int, max_seconds: int) -> float:
    base = min(2**attempts, max_seconds)
    jitter = random.uniform(0, base * 0.1)
    return base + jitter


def _render_html(entry: EmailOutbox) -> tuple[str, str]:
    if isinstance(entry.payload, WelcomeInvitePayload):
        params = WelcomeEmailParams(
            user_name=entry.payload.user_name,
            user_email=entry.payload.user_email,
            one_time_password=entry.payload.one_time_password,
            login_url=f"{entry.payload.frontend_url}/login?token={entry.payload.token}",
        )
        return "Welcome to SyncDesk!", render_welcome_email(params)

    else:
        params = ResetPasswordEmailParams(
            user_email=entry.payload.user_email,
            reset_url=f"{entry.payload.frontend_url}/reset-password?token={entry.payload.token}",
        )
        return "Reset Your Password", render_password_reset_email(params)


async def _process_single(
    session_maker: async_sessionmaker[AsyncSession],
    email_strategy: EmailStrategy,
    entry: EmailOutbox,
    worker_id: str,
) -> None:
    settings = get_settings()
    now = datetime.now(UTC).replace(tzinfo=None)
    outbox_id = str(entry.id)

    try:
        subject, html = _render_html(entry)
        await email_strategy._send(entry.recipient, subject, html)  # type: ignore[attr-defined]

        async with session_maker() as session:
            async with session.begin():
                repo = EmailOutboxRepository(session)
                await repo.mark_sent(entry.id, now)

        email_outbox_processed_total.labels(status="sent").inc()
        logger.info(
            "Outbox email sent",
            extra={"outbox_id": outbox_id, "event_type": entry.event_type.value},
        )

    except Exception as exc:
        new_attempts = entry.attempts + 1
        error_msg = str(exc)[:2000]

        async with session_maker() as session:
            async with session.begin():
                repo = EmailOutboxRepository(session)
                if new_attempts >= entry.max_attempts:
                    await repo.mark_dead(entry.id, error_msg)
                    email_outbox_processed_total.labels(status="dead").inc()
                    logger.error(
                        "Outbox email dead-lettered",
                        extra={"outbox_id": outbox_id, "attempts": new_attempts},
                        exc_info=exc,
                    )
                else:
                    delay = _backoff_seconds(new_attempts, settings.EMAIL_OUTBOX_BACKOFF_MAX_SECONDS)
                    next_attempt_at = now + timedelta(seconds=delay)
                    await repo.mark_retry(entry.id, error_msg, next_attempt_at, new_attempts)
                    email_outbox_processed_total.labels(status="retry").inc()
                    logger.warning(
                        "Outbox email scheduled for retry",
                        extra={
                            "outbox_id": outbox_id,
                            "attempts": new_attempts,
                            "next_attempt_at": next_attempt_at.isoformat(),
                        },
                    )


async def _poll_and_process(
    session_maker: async_sessionmaker[AsyncSession],
    email_strategy: EmailStrategy,
    worker_id: str,
) -> None:
    settings = get_settings()
    now = datetime.now(UTC).replace(tzinfo=None)

    async with session_maker() as session:
        async with session.begin():
            repo = EmailOutboxRepository(session)
            entries = await repo.claim_batch(now, worker_id, settings.EMAIL_OUTBOX_BATCH_SIZE)

    if not entries:
        return

    email_outbox_depth.labels(status=EmailOutboxStatus.PROCESSING).set(len(entries))
    logger.debug("Claimed outbox batch", extra={"count": len(entries), "worker_id": worker_id})

    tasks = [
        _process_single(session_maker, email_strategy, entry, worker_id) for entry in entries
    ]
    await asyncio.gather(*tasks, return_exceptions=True)


async def run_email_outbox_worker(
    engine: AsyncEngine,
    email_strategy: EmailStrategy,
) -> None:
    settings = get_settings()
    if not settings.EMAIL_OUTBOX_ENABLED:
        logger.info("Email outbox worker disabled via EMAIL_OUTBOX_ENABLED=False")
        return

    worker_id = _worker_id()
    session_maker: async_sessionmaker[AsyncSession] = async_sessionmaker(
        engine, expire_on_commit=False
    )
    logger.info("Email outbox worker started", extra={"worker_id": worker_id})

    while True:
        try:
            await _poll_and_process(session_maker, email_strategy, worker_id)
        except asyncio.CancelledError:
            logger.info("Email outbox worker cancelled", extra={"worker_id": worker_id})
            raise
        except Exception:
            logger.exception("Email outbox worker error")

        await asyncio.sleep(settings.EMAIL_OUTBOX_POLL_SECONDS)
