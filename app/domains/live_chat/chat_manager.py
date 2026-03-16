from functools import lru_cache
from uuid import UUID, uuid4

from fastapi import WebSocket

from .entities import ChatMessage


class ChatRoom:
    def __init__(self, id: UUID):
        self.id = id
        self.connections: list[WebSocket] = []

    @classmethod
    def create(cls, id: UUID | None = None) -> "ChatRoom":
        return cls(id=uuid4() if id is None else id)

    async def join(self, ws: WebSocket) -> None:
        self.connections.append(ws)
        await ws.send_text(f"Connected to room {self.id}")

    async def leave(self, ws: WebSocket) -> None:
        self.connections.remove(ws)

    def is_empty(self) -> bool:
        return len(self.connections) <= 0

    async def broadcast(self, message: ChatMessage) -> None:
        json_payload = message.model_dump(mode="json", exclude_none=True)
        dead: list[WebSocket] = []
        for ws in self.connections:
            try:
                await ws.send_json(json_payload)
            except Exception:
                dead.append(ws)

        for ws in dead:
            self.connections.remove(ws)


class ChatManager:
    def __init__(self) -> None:
        self.rooms: dict[UUID, ChatRoom] = {}

    def open_room(self, id: UUID) -> UUID:
        room = ChatRoom.create(id)
        self.rooms[room.id] = room
        return room.id

    async def close_room(self, room_id: UUID) -> None:
        for ws in self.rooms[room_id].connections:
            await ws.close()
        del self.rooms[room_id]

    async def join_room(self, room_id: UUID, ws: WebSocket) -> None:
        await self.rooms[room_id].join(ws)

    async def leave_room(self, room_id: UUID, ws: WebSocket) -> None:
        await self.rooms[room_id].leave(ws)
        await ws.close()

    async def broadcast(self, room_id: UUID, message: ChatMessage) -> None:
        await self.rooms[room_id].broadcast(message)


@lru_cache
def get_chat_manager() -> ChatManager:
    return ChatManager()
