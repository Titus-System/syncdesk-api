from functools import lru_cache
from typing import Any, cast
from uuid import UUID, uuid4

from fastapi import WebSocket, WebSocketException

from app.core.response import WSResponseFactory
from app.domains.live_chat.exceptions import InvalidMessageError

from .entities import ChatMessage


class ChatConnection:
    def __init__(self, ws: WebSocket, response: WSResponseFactory) -> None:
        self.ws = ws
        self.response = response

    async def send(self, message: ChatMessage) -> None:
        await self.ws.send_json(self.response.success(message.to_payload()))

    async def send_error(self, exc: WebSocketException) -> None:
        await self.ws.send_json(self.response.error(exc))

    async def room_join_confirmation(self, conversation_id: UUID) -> None:
        await self.send(
            ChatMessage.create(
                conversation_id, "System", "text", f"Joined to chat room {conversation_id}"
            )
        )

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        await self.ws.close(code, reason or "Connection fulfilled it's purpose.")

    async def receive_payload(self) -> dict[str, Any]:
        try:
            payload = await self.ws.receive_json()
            if not isinstance(payload, dict):
                raise InvalidMessageError("Payload must be a JSON object.")
        except ValueError as err:
            raise InvalidMessageError("Payload must be valid JSON.") from err

        return cast(dict[str, Any], payload)


class ChatRoom:
    def __init__(self, id: UUID):
        self.id = id
        self.connections: list[ChatConnection] = []
        self.dead: list[ChatConnection] = []

    @classmethod
    def create(cls, id: UUID | None = None) -> "ChatRoom":
        return cls(id=uuid4() if id is None else id)

    async def join(self, conn: ChatConnection) -> None:
        self.connections.append(conn)
        await conn.room_join_confirmation(self.id)

    async def leave(self, conn: ChatConnection) -> None:
        self.connections.remove(conn)
        await conn.close()

    async def close(self) -> None:
        for c in self.connections:
            await c.close(1001, "Chat Room is being closed by the server.")

    def is_empty(self) -> bool:
        return len(self.connections) <= 0

    def _drop_dead_connections(self) -> None:
        for ws in self.dead:
            self.connections.remove(ws)
        self.dead = []

    async def broadcast(self, message: ChatMessage) -> None:
        for conn in self.connections:
            try:
                await conn.send(message)
            except Exception:
                self.dead.append(conn)
        self._drop_dead_connections()


class ChatManager:
    def __init__(self) -> None:
        self.rooms: dict[UUID, ChatRoom] = {}

    def open_room(self, id: UUID | None) -> UUID:
        if id is None:
            id = uuid4()
        room = ChatRoom.create(id)
        self.rooms[room.id] = room
        return room.id

    async def close_room(self, room_id: UUID) -> None:
        await self.rooms[room_id].close()
        del self.rooms[room_id]

    async def join_room(self, room_id: UUID, conn: ChatConnection) -> None:
        if room_id not in self.rooms:
            self.open_room(room_id)
        await self.rooms[room_id].join(conn)

    async def leave_room(self, room_id: UUID, conn: ChatConnection) -> None:
        await self.rooms[room_id].leave(conn)

    async def broadcast(self, room_id: UUID, message: ChatMessage) -> None:
        await self.rooms[room_id].broadcast(message)


@lru_cache
def get_chat_manager() -> ChatManager:
    return ChatManager()
