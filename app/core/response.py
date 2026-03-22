from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, Request, WebSocket, WebSocketException, status
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


class WSResponseFactory:
    def __init__(self, request_id: str | None = None, instance: str | None = None) -> None:
        self.request_id = request_id
        self.instance = instance

    def success(self, data: Any, meta_extensions: dict[str, Any] | None = None) -> dict[str, Any]:
        meta: dict[str, Any] = {"request_id": self.request_id}
        if meta_extensions:
            meta.update(meta_extensions)

        content = SuccessContent(data=data, meta=Meta(**meta))
        return content.model_dump(mode="json", exclude_none=True)

    def error(self, exc: WebSocketException) -> dict[str, Any]:
        type_url = getattr(exc, "type", "https://websocket.org/reference/close-codes/")
        meta_extensions = getattr(exc, "meta_extensions", None)

        meta: dict[str, Any] = {"request_id": self.request_id}
        if meta_extensions:
            meta.update(meta_extensions)

        meta["success"] = False

        content = ErrorContent(
            type=type_url,
            title="Websocket Error",
            status=exc.code or 1011,
            detail=getattr(exc, "reason", None) or "Websocket connection closed",
            instance=str(self.instance) or None,
            errors=getattr(exc, "errors", None),
            meta=Meta(**meta),
        )
        return content.model_dump(exclude_none=True)


def get_ws_response_factory(ws: WebSocket) -> WSResponseFactory:
    return WSResponseFactory(getattr(ws.state, "request_id", None), ws.url.path or None)
