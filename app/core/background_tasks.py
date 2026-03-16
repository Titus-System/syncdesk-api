import asyncio

from .metrics import update_system_metrics


def global_background_tasks() -> list[asyncio.Task[None]]:
    tasks: list[asyncio.Task[None]] = [asyncio.create_task(update_system_metrics())]
    return tasks
