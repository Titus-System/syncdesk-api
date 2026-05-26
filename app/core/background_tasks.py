import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from .metrics import update_system_metrics


def global_background_tasks(pg_engine: AsyncEngine) -> list[asyncio.Task[None]]:
    from app.core.dependencies import get_email_service, get_object_storage
    from app.domains.files.worker import (
        run_chat_retention_worker,
        run_pending_cleanup_worker,
        run_physical_purge_worker,
    )
    from app.domains.notifications.worker import run_email_outbox_worker

    email_strategy = get_email_service()
    object_storage = get_object_storage()
    tasks: list[asyncio.Task[None]] = [
        asyncio.create_task(update_system_metrics(pg_engine)),
        asyncio.create_task(run_email_outbox_worker(pg_engine, email_strategy)),
        asyncio.create_task(run_pending_cleanup_worker(pg_engine, object_storage)),
        asyncio.create_task(run_chat_retention_worker(pg_engine, object_storage)),
        asyncio.create_task(run_physical_purge_worker(pg_engine, object_storage)),
    ]
    return tasks
