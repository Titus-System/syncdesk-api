from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.schemas.response import ErrorContent, Meta, SuccessContent


class ResponseFactory:
    def __init__(self, request: Request) -> None:
        self.request = request
        self.request_id: str | None = getattr(request.state, "request_id", None)

    def success(
        self,
        data: Any,
        status_code: int = status.HTTP_200_OK,
        headers: Mapping[str, str] | None = None,
        meta_extensions: dict[str, Any] | None = None,
    ) -> JSONResponse:
        meta: dict[str, Any] = {"request_id": self.request_id}
        if meta_extensions:
            meta.update(meta_extensions)

        content = SuccessContent(data=data, meta=Meta(**meta))
        response = JSONResponse(
            status_code=status_code, content=content.model_dump(exclude_none=True), headers=headers
        )
        return response

    def error(self, exc: HTTPException) -> JSONResponse:
        type_url = getattr(exc, "type", f"https://httpstatuses.io/{exc.status_code}")
        title = getattr(exc, "title", "HTTP Error")
        errors = getattr(exc, "errors", None)
        headers = getattr(exc, "headers", None)
        meta_extensions = getattr(exc, "meta_extensions", None)

        meta: dict[str, Any] = {"request_id": self.request_id}
        if meta_extensions:
            meta.update(meta_extensions)

        meta["success"] = False

        content = ErrorContent(
            type=type_url,
            title=title,
            status=exc.status_code,
            detail=exc.detail or "HTTP error occurred",
            instance=str(self.request.url.path),
            errors=errors,
            meta=Meta(**meta),
        )
        response = JSONResponse(
            status_code=exc.status_code,
            content=content.model_dump(exclude_none=True),
            headers=headers,
        )
        return response


def get_response_factory(request: Request) -> ResponseFactory:
    return ResponseFactory(request)
