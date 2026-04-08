import asyncio

from sqlalchemy.ext.asyncio import AsyncEngine

from .metrics import update_system_metrics


def global_background_tasks(pg_engine: AsyncEngine) -> list[asyncio.Task[None]]:
    tasks: list[asyncio.Task[None]] = [asyncio.create_task(update_system_metrics(pg_engine))]
    return tasks
