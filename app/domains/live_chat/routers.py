from uuid import UUID, uuid4

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketState

from app.core.dependencies import ResponseFactoryDep
from app.domains.live_chat.entities import ChatMessage

from .chat_manager import get_chat_manager

live_chat_router = APIRouter()


@live_chat_router.post("/open_room")
def open_room(response: ResponseFactoryDep) -> JSONResponse:
    room_id = uuid4()
    get_chat_manager().open_room(room_id)
    return response.success({"room_id": str(room_id)})


@live_chat_router.get("/conversations/{id}")
async def get_conversation(id: UUID) -> None:
    # Load conversation history
    ...


@live_chat_router.websocket("/{conversation_id}")
async def connect_to_conversation(conversation_id: UUID) -> None:
    # Connects to room or create if necessary
    ...


@live_chat_router.websocket("/room/{room_id}")
async def chat_room(room_id: UUID, ws: WebSocket) -> None:
    await ws.accept()
    chat_manager = get_chat_manager()
    await chat_manager.join_room(room_id, ws)

    try:
        while ws.client_state == WebSocketState.CONNECTED:
            payload = await ws.receive_json()
            message = ChatMessage.create(
                conversation_id=room_id,
                sender_id=room_id,
                type="text",
                content=payload["content"],
            )
            await chat_manager.broadcast(room_id, message)
    except WebSocketDisconnect:
        ...
    finally:
        await chat_manager.leave_room(room_id, ws)
