import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from .metrics import update_system_metrics


def global_background_tasks(pg_engine: AsyncEngine) -> list[asyncio.Task[None]]:
    from app.core.dependencies import get_email_service
    from app.domains.notifications.worker import run_email_outbox_worker

    email_strategy = get_email_service()
    tasks: list[asyncio.Task[None]] = [
        asyncio.create_task(update_system_metrics(pg_engine)),
        asyncio.create_task(run_email_outbox_worker(pg_engine, email_strategy)),
    ]
    return tasks
