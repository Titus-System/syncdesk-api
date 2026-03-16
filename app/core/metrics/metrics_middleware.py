import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import Response

from .global_metrics import error_count, request_count, request_latency


def add_metrics_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def http_metrics_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        start_time = time.time()
        try:
            response = await call_next(request)
        except Exception as e:
            error_count.labels(endpoint=request.url.path, exception_type=type(e).__name__).inc()
            raise

        resp_time = time.time() - start_time
        request_latency.labels(request.method, request.url.path).observe(resp_time)
        request_count.labels(request.method, request.url.path, response.status_code).inc()
        return response
