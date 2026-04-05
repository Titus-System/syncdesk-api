import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from httpx import AsyncClient
from starlette.types import ASGIApp

from app.domains.auth.entities import UserWithRoles
from app.domains.live_chat.entities import Conversation
from app.domains.live_chat.schemas import CreateConversationDTO
from app.domains.ticket.models import (
    Ticket,
    TicketClient,
    TicketCompany,
    TicketCriticality,
    TicketStatus,
    TicketType,
)
from tests.app.e2e.conftest import AuthActions


class WebSocketDeniedError(Exception):
    """Raised when the server denies the WebSocket upgrade."""

    def __init__(self, status: int, body: str) -> None:
        self.status = status
        self.body = body
        super().__init__(f"WebSocket denied with HTTP {status}: {body}")


class WebSocketClosedError(Exception):
    """Raised when the server sends a close frame."""

    def __init__(self, code: int, reason: str = "") -> None:
        self.code = code
        self.reason = reason
        super().__init__(f"WebSocket closed with code {code}: {reason}")


class AsyncWebSocket:
    """Lightweight async WebSocket client for in-process ASGI testing."""

    def __init__(
        self,
        app: ASGIApp,
        path: str,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._app = app
        self._path = path
        self._extra_headers = headers or {}
        self._to_server: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._to_client: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._task: asyncio.Task[None] | None = None

    async def _receive(self) -> dict[str, Any]:
        return await self._to_server.get()

    async def _send(self, message: dict[str, Any]) -> None:
        await self._to_client.put(message)

    async def send_json(self, data: Any) -> None:
        await self._to_server.put({"type": "websocket.receive", "text": json.dumps(data)})

    async def receive_json(self, timeout: float = 5.0) -> dict[str, Any]:
        msg = await asyncio.wait_for(self._to_client.get(), timeout=timeout)
        if msg["type"] == "websocket.close":
            raise WebSocketClosedError(msg.get("code", 1000), msg.get("reason", ""))
        text: str = msg.get("text", "{}")
        result: dict[str, Any] = json.loads(text)
        return result

    async def close(self) -> None:
        await self._to_server.put({"type": "websocket.disconnect", "code": 1000})
        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=2.0)
            except (TimeoutError, Exception):
                self._task.cancel()

    async def __aenter__(self) -> "AsyncWebSocket":
        parsed = urlparse(self._path)
        headers_bytes: list[tuple[bytes, bytes]] = [
            (b"host", b"testserver"),
            (b"connection", b"upgrade"),
            (b"upgrade", b"websocket"),
        ]
        for k, v in self._extra_headers.items():
            headers_bytes.append((k.lower().encode(), v.encode()))

        scope: dict[str, Any] = {
            "type": "websocket",
            "asgi": {"version": "3.0"},
            "http_version": "1.1",
            "scheme": "ws",
            "server": ("testserver", 80),
            "path": parsed.path,
            "query_string": (parsed.query or "").encode(),
            "root_path": "",
            "headers": headers_bytes,
            "subprotocols": [],
            "extensions": {"websocket.http.response": {}},
        }

        await self._to_server.put({"type": "websocket.connect"})
        self._task = asyncio.create_task(self._app(scope, self._receive, self._send))

        response = await asyncio.wait_for(self._to_client.get(), timeout=5.0)

        if response["type"] == "websocket.accept":
            return self

        if response["type"] == "websocket.close":
            raise WebSocketClosedError(response.get("code", 1000), response.get("reason", ""))

        if response["type"] == "websocket.http.response.start":
            body_msg = await asyncio.wait_for(self._to_client.get(), timeout=5.0)
            body = body_msg.get("body", b"")
            if isinstance(body, bytes):
                body = body.decode()
            raise WebSocketDeniedError(response.get("status", 0), body)

        raise RuntimeError(f"Unexpected ASGI message: {response['type']}")

    async def __aexit__(self, *args: Any) -> None:
        await self.close()


@pytest_asyncio.fixture(autouse=True)
async def cleanup_live_chat_collections():
    await Conversation.delete_all()
    await Ticket.delete_all()
    yield
    await Conversation.delete_all()
    await Ticket.delete_all()


class TestWebSocketChat:
    """E2E tests for the WebSocket live chat flow."""

    @staticmethod
    async def _register_client_user(auth: AuthActions) -> tuple[UserWithRoles, str]:
        tokens = await auth.register_and_login_admin(
            email="ws_client@test.com",
            username="wsclient",
        )
        user = await auth.me(tokens["access_token"])
        return user, tokens["access_token"]

    @staticmethod
    async def _register_agent_user(auth: AuthActions) -> tuple[UserWithRoles, str]:
        await auth.register_agent(email="ws_agent@test.com", username="wsagent")
        tokens = await auth.login(email="ws_agent@test.com")
        user = await auth.me(tokens["access_token"])
        return user, tokens["access_token"]

    @staticmethod
    async def _create_ticket(
        client_id: Any,
        status: TicketStatus = TicketStatus.OPEN,
    ) -> PydanticObjectId:
        ticket = Ticket(
            triage_id=PydanticObjectId(),
            type=TicketType.ISSUE,
            criticality=TicketCriticality.MEDIUM,
            product="WebSocket Test Product",
            status=status,
            creation_date=datetime.now(UTC),
            description="Ticket created for live chat websocket tests",
            chat_ids=[],
            agent_history=[],
            client=TicketClient(
                id=client_id,
                name="WS Client",
                email="ws_client@test.com",
                company=TicketCompany(
                    id=client_id,
                    name="Test Company",
                ),
            ),
            comments=[],
        )
        await ticket.insert()
        return ticket.id

    @classmethod
    async def _create_conversation(
        cls,
        client: AsyncClient,
        auth: AuthActions,
        token: str,
        client_id: Any,
        agent_id: Any | None = None,
        ticket_status: TicketStatus = TicketStatus.OPEN,
    ) -> str:
        ticket_id = await cls._create_ticket(client_id=client_id, status=ticket_status)

        dto = CreateConversationDTO(
            ticket_id=ticket_id,
            client_id=client_id,
            agent_id=agent_id,
        )
        r = await client.post(
            "/api/conversations/",
            json=dto.model_dump(mode="json"),
            headers=auth.auth_headers(token),
        )
        assert r.status_code == 201, f"Failed to create conversation: {r.text}"
        return r.json()["data"]["id"]

    async def test_user_can_connect_and_receive_join_confirmation(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        user, token = await self._register_client_user(auth)
        conv_id = await self._create_conversation(client, auth, token, user.id)

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            join_msg = await ws.receive_json()
            assert join_msg["meta"]["success"] is True
            assert join_msg["data"]["sender_id"] == "System"
            assert "Joined to chat room" in join_msg["data"]["content"]
            assert join_msg["data"]["conversation_id"] == conv_id

            broadcast_join = await ws.receive_json()
            assert broadcast_join["data"]["sender_id"] == "System"
            assert "Joined chat room" in broadcast_join["data"]["content"]

    async def test_two_users_can_exchange_messages(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        client_user, client_token = await self._register_client_user(auth)
        agent_user, agent_token = await self._register_agent_user(auth)

        conv_id = await self._create_conversation(
            client,
            auth,
            client_token,
            client_user.id,
            agent_id=agent_user.id,
            ticket_status=TicketStatus.OPEN,
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {client_token}"},
        ) as ws_client:
            await ws_client.receive_json()
            await ws_client.receive_json()

            async with AsyncWebSocket(
                app,
                f"/api/live_chat/room/{conv_id}",
                headers={"Authorization": f"Bearer {agent_token}"},
            ) as ws_agent:
                await ws_agent.receive_json()
                await ws_agent.receive_json()
                await ws_client.receive_json()

                await ws_client.send_json({"type": "text", "content": "Hello from client!"})

                msg_client = await ws_client.receive_json()
                msg_agent = await ws_agent.receive_json()

                for msg in (msg_client, msg_agent):
                    assert msg["meta"]["success"] is True
                    assert msg["data"]["content"] == "Hello from client!"
                    assert msg["data"]["sender_id"] == str(client_user.id)
                    assert msg["data"]["type"] == "text"
                    assert msg["data"]["conversation_id"] == conv_id

                await ws_agent.send_json({"type": "text", "content": "Hello from agent!"})

                reply_client = await ws_client.receive_json()
                reply_agent = await ws_agent.receive_json()

                for msg in (reply_client, reply_agent):
                    assert msg["meta"]["success"] is True
                    assert msg["data"]["content"] == "Hello from agent!"
                    assert msg["data"]["sender_id"] == str(agent_user.id)

    async def test_message_persisted_in_conversation(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        user, token = await self._register_client_user(auth)
        conv_id = await self._create_conversation(
            client,
            auth,
            token,
            user.id,
            ticket_status=TicketStatus.OPEN,
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json({"type": "text", "content": "Persisted message"})
            await ws.receive_json()

        conv = await Conversation.get(PydanticObjectId(conv_id))
        assert conv is not None
        text_messages = [m for m in conv.messages if m.content == "Persisted message"]
        assert len(text_messages) == 1
        assert text_messages[0].sender_id == user.id
        assert text_messages[0].type == "text"

    async def test_invalid_payload_returns_error_and_keeps_connection(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        user, token = await self._register_client_user(auth)
        conv_id = await self._create_conversation(
            client,
            auth,
            token,
            user.id,
            ticket_status=TicketStatus.OPEN,
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json({"wrong_field": "oops"})
            error_msg = await ws.receive_json()

            assert error_msg["meta"]["success"] is False
            assert error_msg["status"] == 1003
            assert "Payload missing required fields" in error_msg["detail"]

            await ws.send_json({"type": "text", "content": "Still connected!"})
            valid_msg = await ws.receive_json()
            assert valid_msg["meta"]["success"] is True
            assert valid_msg["data"]["content"] == "Still connected!"

            await ws.send_json(
                {
                    "type": "text",
                    "content": "sending file",
                    "filename": "file.pdf",
                    "mime_type": "application/pdf",
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "mime_type and filename fields are not allowed" in error_msg["detail"]

            await ws.send_json(
                {"type": "file", "content": "ADFGER234TWERGW234", "filename": "file.pdf"}
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "mime_type and filename fields are required when type='file'" in error_msg["detail"]

    async def test_cannot_send_message_when_ticket_is_finished(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        user, token = await self._register_client_user(auth)
        conv_id = await self._create_conversation(
            client,
            auth,
            token,
            user.id,
            ticket_status=TicketStatus.FINISHED,
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json({"type": "text", "content": "Should be blocked"})
            error_msg = await ws.receive_json()

            assert error_msg["meta"]["success"] is False
            assert error_msg["status"] == 1008
            assert "finished" in error_msg["detail"].lower()

        conv = await Conversation.get(PydanticObjectId(conv_id))
        assert conv is not None
        blocked_messages = [m for m in conv.messages if m.content == "Should be blocked"]
        assert blocked_messages == []

    async def test_non_participant_cannot_connect(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        creator, creator_token = await self._register_client_user(auth)
        conv_id = await self._create_conversation(client, auth, creator_token, creator.id)

        outsider_tokens = await auth.register_and_login_admin(
            email="outsider@test.com",
            username="outsider",
        )

        with pytest.raises(WebSocketDeniedError) as exc_info:
            async with AsyncWebSocket(
                app,
                f"/api/live_chat/room/{conv_id}",
                headers={"Authorization": f"Bearer {outsider_tokens['access_token']}"},
            ):
                pass

        assert exc_info.value.status == 403
        assert "not a participant" in exc_info.value.body