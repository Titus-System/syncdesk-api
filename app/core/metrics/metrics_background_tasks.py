import asyncio

import psutil
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from .decorators import track_background_job
from .global_metrics import (
    db_pool_checked_out,
    db_pool_overflow,
    db_pool_size,
    system_cpu_count,
    system_cpu_usage,
    system_memory_bytes,
    system_memory_usage,
)


@track_background_job("update_system_metrics")
async def update_system_metrics(pg_engine: AsyncEngine) -> None:
    while True:
        mem = psutil.virtual_memory()
        system_memory_usage.labels(type="used").set(mem.used / mem.total * 100)
        system_memory_usage.labels(type="free").set(mem.free / mem.total * 100)
        system_memory_bytes.labels(type="total").set(mem.total)
        system_memory_bytes.labels(type="used").set(mem.used)
        system_memory_bytes.labels(type="free").set(mem.free)

        cpu_percent = psutil.cpu_percent(interval=None)
        system_cpu_usage.set(cpu_percent)
        system_cpu_count.set(psutil.cpu_count())

        pool: QueuePool = pg_engine.pool  # type: ignore[assignment]
        db_pool_size.set(pool.size())
        db_pool_checked_out.set(pool.checkedout())
        db_pool_overflow.set(pool.overflow())

        await asyncio.sleep(5)
