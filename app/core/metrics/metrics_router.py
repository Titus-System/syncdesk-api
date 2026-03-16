from fastapi import APIRouter, Request, Response

from .prometheus import prometheus

metrics_router = APIRouter()


@metrics_router.get("/metrics", tags=["Metrics"])
async def get_metrics(request: Request) -> Response:
    return Response(prometheus.get_all(), media_type="text/plain; version=0.0.4")


@metrics_router.get("/metrics/{prefix}", tags=["Metrics"])
async def filter_metrics(request: Request, prefix: str) -> Response:
    return Response(prometheus.get_all_by_prefix(prefix), media_type="text/plain; version=0.0.4")
