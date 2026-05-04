from typing import Annotated
from uuid import uuid4

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, WebSocketException
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketState
from pydantic import ValidationError

from app.core.dependencies import WSResponseFactoryDep
from app.core.logger import get_logger
from app.domains.auth import CurrentUserSessionWsDep, require_permission_ws
from app.domains.auth.entities import UserWithRoles
from app.domains.live_chat.entities import Conversation

from ..chat_manager import ChatConnection, get_chat_manager
from ..dependencies import ConversationServiceDep
from ..exceptions import ChatRoomNotFoundError, InvalidMessageError

logger = get_logger("app.live_chat.router")


def ensure_ws_request_id(ws: WebSocket) -> None:
    if not hasattr(ws.state, "request_id"):
        ws.state.request_id = ws.headers.get("x-request-id") or str(uuid4())


def get_role_names(user: UserWithRoles) -> set[str]:
    return {str(role).strip().lower() for role in user.roles_names()}


def is_admin(user: UserWithRoles) -> bool:
    return "admin" in get_role_names(user)


def can_user_join_conversation(user: UserWithRoles, conversation: Conversation) -> bool:
    if is_admin(user):
        return True

    return user.id in conversation.participants()


def get_accepted_subprotocol(ws: WebSocket) -> str | None:
    requested = ws.headers.get("sec-websocket-protocol")

    if not requested:
        return None

    parts = [part.strip() for part in requested.split(",")]

    if "access_token" in parts:
        return "access_token"

    return None


chat_manager = get_chat_manager()
chat_router = APIRouter()


@chat_router.websocket("/room/{chat_id}", dependencies=[require_permission_ws("chat:add_message")])
async def connect_to_conversation(
    chat_id: PydanticObjectId,
    ws: WebSocket,
    _: Annotated[None, Depends(ensure_ws_request_id)],
    auth: CurrentUserSessionWsDep,
    service: ConversationServiceDep,
    response: WSResponseFactoryDep,
) -> None:
    user = auth[0]
    log_ctx = {"chat_id": str(chat_id), "user_id": str(user.id)}

    logger.info("WS connect attempt", extra=log_ctx)

    chat = await service.get_by_id(chat_id)

    if chat is None:
        logger.warning("WS denied: chat does not exist", extra=log_ctx)
        await ws.send_denial_response(
            JSONResponse(
                status_code=403,
                content={"detail": "Chat does not exist."},
            )
        )
        return

    if not chat.is_opened():
        logger.warning("WS denied: chat already closed", extra=log_ctx)
        await ws.send_denial_response(
            JSONResponse(
                status_code=403,
                content={"detail": "Chat is already closed."},
            )
        )
        return

    if not can_user_join_conversation(user, chat):
        logger.warning("WS denied: user not allowed in chat", extra=log_ctx)
        await ws.send_denial_response(
            JSONResponse(
                status_code=403,
                content={"detail": "User is not allowed to join this chat."},
            )
        )
        return

    subprotocol = get_accepted_subprotocol(ws)
    logger.debug(
        "WS accepting handshake",
        extra={**log_ctx, "subprotocol": subprotocol},
    )
    await ws.accept(subprotocol=subprotocol)
    logger.info("WS handshake accepted", extra=log_ctx)

    conn = ChatConnection(ws, response, user)
    joined = False

    try:
        await chat_manager.join_room(chat_id, conn)
        joined = True
        logger.info("WS joined room", extra=log_ctx)

        while ws.client_state == WebSocketState.CONNECTED:
            try:
                payload = await conn.receive_payload()
                logger.debug("WS payload received", extra=log_ctx)

                message = service.handle_message(chat_id, user.id, payload)

                await service.add_message_to_conversation(chat_id, message)
                logger.debug(
                    "WS message persisted",
                    extra={**log_ctx, "message_id": str(message.id)},
                )

                await chat_manager.broadcast(chat_id, message)
                logger.debug(
                    "WS message broadcast",
                    extra={**log_ctx, "message_id": str(message.id)},
                )

            except WebSocketDisconnect as e:
                logger.info(
                    "WS client disconnected",
                    extra={**log_ctx, "code": e.code, "reason": e.reason},
                )
                break
            except (InvalidMessageError, ValidationError) as e:
                logger.warning(
                    "WS invalid message",
                    extra={**log_ctx, "error": str(e)},
                )
                await conn.send_error(
                    WebSocketException(code=1003, reason=str(e) or "")
                )
            except ValueError as e:
                logger.warning(
                    "WS policy violation",
                    extra={**log_ctx, "error": str(e)},
                )
                await conn.send_error(
                    WebSocketException(code=1008, reason=str(e))
                )
            except RuntimeError as e:
                logger.error(
                    "WS runtime error",
                    extra={**log_ctx, "error": str(e)},
                )
                await conn.send_error(
                    WebSocketException(code=1011, reason=str(e))
                )

    except ChatRoomNotFoundError as e:
        logger.warning(
            "Chat room not found during connection",
            extra={**log_ctx, "error": str(e)},
        )
        await conn.send_error(WebSocketException(code=1011, reason=str(e)))
        await conn.close(code=1011, reason="Chat room unavailable")

    except Exception:
        logger.exception("WS unexpected error", extra=log_ctx)
        raise

    finally:
        if joined:
            logger.info("WS leaving room", extra=log_ctx)
            await chat_manager.leave_room(chat_id, conn)
        else:
            logger.info("WS connection ended without joining", extra=log_ctx)


@chat_router.websocket("/test/room/{conversation_id}")
async def connect_to_conversation_test(
    conversation_id: PydanticObjectId,
    ws: WebSocket,
    _: Annotated[None, Depends(ensure_ws_request_id)],
    service: ConversationServiceDep,
    response: WSResponseFactoryDep,
) -> None:
    await ws.accept()

    conn = ChatConnection(ws, response)
    user_id = uuid4()

    await chat_manager.join_room(conversation_id, conn)

    try:
        while ws.client_state == WebSocketState.CONNECTED:
            try:
                payload = await conn.receive_payload()
                message = service.handle_message(conversation_id, user_id, payload)

                await chat_manager.broadcast(conversation_id, message)

            except WebSocketDisconnect:
                break
            except InvalidMessageError as e:
                await conn.send_error(
                    WebSocketException(
                        code=1003,
                        reason=str(e) or "",
                    )
                )

    finally:
        await chat_manager.leave_room(conversation_id, conn)