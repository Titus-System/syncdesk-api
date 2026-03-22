from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, WebSocket, WebSocketException
from fastapi.websockets import WebSocketState

from app.core.dependencies import WSResponseFactoryDep

from .chat_manager import ChatConnection, get_chat_manager
from .dependencies import ChatServiceDep
from .exceptions import InvalidMessageError


def ensure_ws_request_id(ws: WebSocket) -> None:
    if not hasattr(ws.state, "request_id"):
        ws.state.request_id = ws.headers.get("x-request-id") or str(uuid4())


chat_manager = get_chat_manager()
live_chat_router = APIRouter()


@live_chat_router.get("/conversations/{id}", tags=["Conversations"])
async def get_conversation(id: UUID) -> None:
    # Load conversation history
    ...


@live_chat_router.websocket("/room/{conversation_id}")
async def connect_to_conversation(
    conversation_id: UUID,
    ws: WebSocket,
    _: Annotated[None, Depends(ensure_ws_request_id)],
    service: ChatServiceDep,
    response: WSResponseFactoryDep,
) -> None:
    await ws.accept()
    conn = ChatConnection(ws, response)
    user_id = uuid4()
    await service.join_chat_room(conversation_id, conn)

    try:
        while ws.client_state == WebSocketState.CONNECTED:
            try:
                payload = await conn.receive_payload()
                message = await service.handle_message(conversation_id, user_id, payload)

                await chat_manager.broadcast(conversation_id, message)

            except InvalidMessageError as e:
                await conn.send_error(
                    WebSocketException(
                        code=1003,
                        reason=str(e) or "",
                    )
                )

    finally:
        await chat_manager.leave_room(conversation_id, conn)
