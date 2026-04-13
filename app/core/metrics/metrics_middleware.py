import time
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import Response
from starlette.routing import Match

from .global_metrics import error_count, request_count, request_latency


def _get_route_template(request: Request) -> str:
    """Resolve the matched route template (e.g. /api/tickets/{id}) instead of
    the raw path, to avoid high-cardinality labels in Prometheus."""
    app = request.app
    for route in app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            return getattr(route, "path", request.url.path)
    return request.url.path


def add_metrics_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def http_metrics_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        endpoint = _get_route_template(request)
        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        except Exception as e:
            error_count.labels(endpoint=endpoint, exception_type=type(e).__name__).inc()
            raise
        finally:
            elapsed = time.perf_counter() - start_time
            request_latency.labels(method=request.method, endpoint=endpoint).observe(elapsed)
            request_count.labels(
                method=request.method, endpoint=endpoint, status=status_code
            ).inc()
