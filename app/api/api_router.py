from typing import Any

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.dependencies import ResponseFactoryDep
from app.domains.auth import auth_router, permission_router, role_router, user_router
from app.domains.live_chat import live_chat_router
from app.schemas.response import ErrorContent, GenericSuccessContent

api_router = APIRouter()


class V1RootData(BaseModel):
    status: str
    environment: str


v1_responses: dict[int | str, dict[str, Any]] = {
    status.HTTP_200_OK: {
        "model": GenericSuccessContent[V1RootData],
        "description": "API v1 status.",
    },
    status.HTTP_500_INTERNAL_SERVER_ERROR: {
        "model": ErrorContent,
        "description": "Internal Server Error.",
    },
}


@api_router.get("", tags=["api"], responses=v1_responses)
async def root(response_factory: ResponseFactoryDep, request: Request) -> JSONResponse:
    return response_factory.success(
        data={"status": "API - version 1", "environment": get_settings().ENVIRONMENT},
        status_code=status.HTTP_200_OK,
    )


api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(role_router, prefix="/roles", tags=["Roles"])
api_router.include_router(permission_router, prefix="/permissions", tags=["Permissions"])
api_router.include_router(user_router, prefix="/users", tags=["Users"])

api_router.include_router(live_chat_router, prefix="/live_chat", tags=["Live Chat"])
