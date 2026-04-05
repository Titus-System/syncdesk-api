from typing import Annotated
from uuid import uuid4

from beanie import PydanticObjectId
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect, WebSocketException
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketState
from pydantic import ValidationError

from app.core.dependencies import WSResponseFactoryDep
from app.domains.auth import CurrentUserSessionWsDep, require_permission_ws

from ..chat_manager import ChatConnection, get_chat_manager
from ..dependencies import ConversationServiceDep
from ..exceptions import (
    ChatRoomNotFoundError,
    InvalidMessageError,
    TicketClosedForNewMessagesError,
)


def ensure_ws_request_id(ws: WebSocket) -> None:
    if not hasattr(ws.state, "request_id"):
        ws.state.request_id = ws.headers.get("x-request-id") or str(uuid4())


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

    chat = await service.get_by_id(chat_id)

    if chat is None or not chat.is_opened() or user.id not in chat.participants():
        await ws.send_denial_response(
            JSONResponse(
                status_code=403,
                content={"detail": "Chat does not exist or user is not a participant."},
            )
        )
        return

    await ws.accept()
    conn = ChatConnection(ws, response, user)
    joined = False

    try:
        await chat_manager.join_room(chat_id, conn)
        joined = True

        while ws.client_state == WebSocketState.CONNECTED:
            try:
                payload = await conn.receive_payload()
                message = service.handle_message(chat_id, user.id, payload)

                await service.add_message_to_conversation(chat_id, message)

                await chat_manager.broadcast(chat_id, message)

            except WebSocketDisconnect:
                break
            except (InvalidMessageError, ValidationError) as e:
                await conn.send_error(WebSocketException(code=1003, reason=str(e) or ""))
            except TicketClosedForNewMessagesError as e:
                await conn.send_error(WebSocketException(code=1008, reason=str(e)))
            except ValueError as e:
                await conn.send_error(WebSocketException(code=1008, reason=str(e)))
            except RuntimeError as e:
                await conn.send_error(WebSocketException(code=1011, reason=str(e)))
    except ChatRoomNotFoundError as e:
        await conn.send_error(WebSocketException(code=1011, reason=str(e)))
        await conn.close(code=1011, reason="Chat room unavailable")
    finally:
        if joined:
            await chat_manager.leave_room(chat_id, conn)


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