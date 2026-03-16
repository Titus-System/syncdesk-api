import asyncio

import psutil

from .decorators import track_background_job
from .global_metrics import system_cpu_usage, system_memory_usage


@track_background_job("update_system_metrics")
async def update_system_metrics() -> None:
    while True:
        mem = psutil.virtual_memory()
        system_memory_usage.labels(type="used").set(mem.used / mem.total * 100)
        system_memory_usage.labels(type="free").set(mem.free / mem.total * 100)

        cpu_percent = psutil.cpu_percent(interval=None)
        system_cpu_usage.set(cpu_percent)

        await asyncio.sleep(5)
