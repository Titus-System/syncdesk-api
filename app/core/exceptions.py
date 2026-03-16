from collections.abc import Sequence
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logger import get_logger
from .response import ResponseFactory


class AppHTTPException(HTTPException):
    def __init__(
        self,
        status_code: int,
        detail: str | None = None,
        title: str | None = None,  # Adicionei 'title' para consistência
        errors: Sequence[Any] | dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        meta_extensions: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)

        self.type = f"https://httpstatuses.io/{status_code}"
        self.title = title or "Application Error"
        self.errors = errors
        self.meta_extensions = meta_extensions


def register_exception_handlers(app: FastAPI) -> None:
    logger = get_logger()

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        app_http_exc = AppHTTPException(
            status_code=exc.status_code,
            detail=exc.detail,
            title="HTTP Error",
        )
        response_factory = ResponseFactory(request)
        return response_factory.error(app_http_exc)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        sanitized_errors: list[dict[Any, Any]] = []
        for err in exc.errors():
            clean = {k: v for k, v in err.items() if k != "ctx"}
            if "ctx" in err and isinstance(err["ctx"], dict):
                clean["ctx"] = {
                    k: str(v) if not isinstance(v, (str, int, float, bool, type(None))) else v
                    for k, v in err["ctx"].items()
                }
            sanitized_errors.append(clean)

        app_http_exc = AppHTTPException(
            status_code=422,
            detail="Request validation failed",
            title="Validation Error",
            errors=sanitized_errors,
        )
        response_factory = ResponseFactory(request)
        return response_factory.error(app_http_exc)

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.error(f"Unhandled exception: {exc}", extra={"path": str(request.url)})

        app_http_exc = AppHTTPException(
            status_code=500,
            title="Internal Server Error",
            detail="An unexpected error occurred when processing your request.",
        )
        response_factory = ResponseFactory(request)
        return response_factory.error(app_http_exc)
