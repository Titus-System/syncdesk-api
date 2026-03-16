import time
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, TypeVar

from .global_metrics import job_duration, job_failures, job_runs

T = TypeVar("T")


def track_background_job(
    job_name: str,
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """
    Decorator to track execution count, failures, and latency of a background job.

    Args:
        job_name: Unique name of the background job for metrics labels.

    Returns:
        Decorated coroutine function.
    """

    def decorator(
        func: Callable[..., Coroutine[Any, Any, T]],
    ) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:
            job_runs.labels(job_name=job_name).inc()
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            except Exception:
                job_failures.labels(job_name=job_name).inc()
                raise
            finally:
                elapsed = time.time() - start_time
                job_duration.labels(job_name=job_name).observe(elapsed)

        return wrapper

    return decorator
