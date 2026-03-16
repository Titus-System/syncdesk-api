from typing import Any

from fastapi import Depends, FastAPI, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.api import api_router
from app.core import (
    ResponseFactory,
    get_response_factory,
    get_settings,
)
from app.core.config import Settings
from app.core.metrics import metrics_router
from app.domains.health import health_router
from app.schemas.response import ErrorContent, GenericSuccessContent

settings: Settings = get_settings()


class RootData(BaseModel):
    name: str = settings.PROJECT_NAME
    status: str = "ok"
    environment: str = settings.ENVIRONMENT


root_responses: dict[int | str, dict[str, Any]] = {
    status.HTTP_200_OK: {"model": GenericSuccessContent[RootData], "description": "API v1 status."},
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorContent,
        "description": "Internal Server Error.",
    },
}


def initiate_routers(app: FastAPI) -> None:
    inject_response_factory = Depends(get_response_factory)

    app.include_router(metrics_router)
    app.include_router(health_router)
    app.include_router(api_router, prefix="/api")

    @app.get("/", tags=["Health Check"], responses=root_responses)
    async def read_root(
        response_factory: ResponseFactory = inject_response_factory,
    ) -> JSONResponse:
        """root endpoint to verify the API's heakth status."""

        data = {"name": app.title, "status": "ok", "environment": settings.ENVIRONMENT}

        return response_factory.success(
            data=data,
            status_code=status.HTTP_200_OK,
        )
