"""Background workers for the files domain.

Three independent ``asyncio`` loops mirror the ``EmailOutbox`` pattern in
``app/domains/notifications/worker.py``:

- ``run_pending_cleanup_worker``: reconciles abandoned ``pending`` uploads.
- ``run_chat_retention_worker``: soft-deletes chat-message files past the
  retention window. Avatars are never touched (filtered by ``context``).
- ``run_physical_purge_worker``: removes the storage object for rows that
  have been soft-deleted longer than the grace period.

Each loop owns its session maker, swallows exceptions to keep ticking, and
respects ``asyncio.CancelledError`` cleanly. A global
``FILE_MAINTENANCE_ENABLED`` flag mutes all three at startup if needed.
"""

import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.storage import ObjectStorage

from .repositories import FileObjectRepository
from .services import FileService

logger = get_logger("app.files.worker")


def _session_maker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


def _build_service(session: AsyncSession, storage: ObjectStorage) -> FileService:
    return FileService(repo=FileObjectRepository(session), object_storage=storage)


async def run_pending_cleanup_worker(
    engine: AsyncEngine, storage: ObjectStorage
) -> None:
    settings = get_settings()
    if not settings.FILE_MAINTENANCE_ENABLED:
        logger.info("Pending cleanup worker disabled via FILE_MAINTENANCE_ENABLED=False")
        return

    maker = _session_maker(engine)
    interval = settings.FILE_CLEANUP_PENDING_INTERVAL_SECONDS
    max_age = settings.FILE_CLEANUP_PENDING_MAX_AGE_MINUTES
    batch_size = settings.FILE_CLEANUP_PENDING_BATCH_SIZE
    logger.info(
        "Pending cleanup worker started",
        extra={
            "interval_seconds": interval,
            "max_age_minutes": max_age,
            "batch_size": batch_size,
        },
    )

    while True:
        try:
            async with maker() as session:
                service = _build_service(session, storage)
                outcomes = await service.sweep_pending(
                    max_age_minutes=max_age, batch_size=batch_size
                )
            if any(outcomes.values()):
                logger.info("Pending sweep tick complete", extra=outcomes)
        except asyncio.CancelledError:
            logger.info("Pending cleanup worker cancelled")
            raise
        except Exception:
            logger.exception("Pending cleanup worker error")
        await asyncio.sleep(interval)


async def run_chat_retention_worker(
    engine: AsyncEngine, storage: ObjectStorage
) -> None:
    settings = get_settings()
    if not settings.FILE_MAINTENANCE_ENABLED:
        logger.info("Chat retention worker disabled via FILE_MAINTENANCE_ENABLED=False")
        return

    maker = _session_maker(engine)
    interval = settings.FILE_RETENTION_INTERVAL_SECONDS
    retention_days = settings.LIVE_CHAT_FILE_RETENTION_DAYS
    batch_size = settings.FILE_RETENTION_BATCH_SIZE
    logger.info(
        "Chat retention worker started",
        extra={
            "interval_seconds": interval,
            "retention_days": retention_days,
            "batch_size": batch_size,
        },
    )

    while True:
        try:
            async with maker() as session:
                service = _build_service(session, storage)
                count = await service.expire_chat_files(
                    retention_days=retention_days, batch_size=batch_size
                )
            if count:
                logger.info("Chat retention tick complete", extra={"expired": count})
        except asyncio.CancelledError:
            logger.info("Chat retention worker cancelled")
            raise
        except Exception:
            logger.exception("Chat retention worker error")
        await asyncio.sleep(interval)


async def run_physical_purge_worker(
    engine: AsyncEngine, storage: ObjectStorage
) -> None:
    settings = get_settings()
    if not settings.FILE_MAINTENANCE_ENABLED:
        logger.info("Physical purge worker disabled via FILE_MAINTENANCE_ENABLED=False")
        return

    maker = _session_maker(engine)
    interval = settings.FILE_PURGE_INTERVAL_SECONDS
    grace_days = settings.FILE_RETENTION_GRACE_DAYS
    batch_size = settings.FILE_PURGE_BATCH_SIZE
    logger.info(
        "Physical purge worker started",
        extra={
            "interval_seconds": interval,
            "grace_days": grace_days,
            "batch_size": batch_size,
        },
    )

    while True:
        try:
            async with maker() as session:
                service = _build_service(session, storage)
                outcomes = await service.purge_deleted(
                    grace_days=grace_days, batch_size=batch_size
                )
            if any(outcomes.values()):
                logger.info("Physical purge tick complete", extra=outcomes)
        except asyncio.CancelledError:
            logger.info("Physical purge worker cancelled")
            raise
        except Exception:
            logger.exception("Physical purge worker error")
        await asyncio.sleep(interval)
