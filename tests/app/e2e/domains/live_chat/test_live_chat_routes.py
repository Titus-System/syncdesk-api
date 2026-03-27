import asyncio
import json
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
from tests.app.e2e.conftest import AuthActions

# ── Async WebSocket test helper ─────────────────────────
# Starlette's ``TestClient`` runs WebSocket connections in a
# **separate thread / event-loop**, which prevents it from
# sharing the savepoint-isolated Postgres ``AsyncSession``
# provided by the test fixtures.
#
# ``AsyncWebSocket`` talks to the ASGI app directly inside the
# **same** event-loop so all dependency overrides (DB sessions,
# Mongo connections) work transparently.


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

    # -- ASGI callbacks (called by the app) -------------------

    async def _receive(self) -> dict[str, Any]:
        return await self._to_server.get()

    async def _send(self, message: dict[str, Any]) -> None:
        await self._to_client.put(message)

    # -- public API -------------------------------------------

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

    # -- context manager --------------------------------------

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
            # Needed so Starlette's send_denial_response sends an HTTP
            # body instead of a bare close frame.
            "extensions": {"websocket.http.response": {}},
        }

        # Queue the initial connect event *before* starting the app task
        # Wait for the server to accept, reject, or deny the connection.
        # so the app's first ``receive()`` returns immediately.
        await self._to_server.put({"type": "websocket.connect"})

        self._task = asyncio.create_task(self._app(scope, self._receive, self._send))

        # Wait for the server to accept, reject, or deny the connection.
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
async def cleanup_conversation_collection():
    await Conversation.delete_all()
    yield
    await Conversation.delete_all()


class TestWebSocketChat:
    """E2E tests for the WebSocket live chat flow."""

    @staticmethod
    async def _register_client_user(auth: AuthActions) -> tuple[UserWithRoles, str]:
        """Register a user with the admin role (has chat:add_message) and return (user, token)."""
        tokens = await auth.register_and_login_admin(
            email="ws_client@test.com", username="wsclient"
        )
        user = await auth.me(tokens["access_token"])
        return user, tokens["access_token"]

    @staticmethod
    async def _register_agent_user(auth: AuthActions) -> tuple[UserWithRoles, str]:
        """Register a user with the agent role and return (user, token)."""
        await auth.register_agent(email="ws_agent@test.com", username="wsagent")
        tokens = await auth.login(email="ws_agent@test.com")
        user = await auth.me(tokens["access_token"])
        return user, tokens["access_token"]

    @staticmethod
    async def _create_conversation(
        client: AsyncClient,
        auth: AuthActions,
        token: str,
        client_id: Any,
        agent_id: Any | None = None,
    ) -> str:
        """Create a conversation via REST and return its id."""
        dto = CreateConversationDTO(
            service_session_id=PydanticObjectId(),
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
            # First message: personal join confirmation
            join_msg = await ws.receive_json()
            assert join_msg["meta"]["success"] is True
            assert join_msg["data"]["sender_id"] == "System"
            assert "Joined to chat room" in join_msg["data"]["content"]
            assert join_msg["data"]["conversation_id"] == conv_id

            # Second message: broadcast "<name> Joined chat room."
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
            client, auth, client_token, client_user.id, agent_id=agent_user.id
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {client_token}"},
        ) as ws_client:
            await ws_client.receive_json()  # personal join confirmation
            await ws_client.receive_json()  # broadcast join

            async with AsyncWebSocket(
                app,
                f"/api/live_chat/room/{conv_id}",
                headers={"Authorization": f"Bearer {agent_token}"},
            ) as ws_agent:
                # Drain agent's own join messages
                await ws_agent.receive_json()  # personal join confirmation
                await ws_agent.receive_json()  # broadcast join

                # Client also receives agent's join broadcast
                await ws_client.receive_json()  # agent join broadcast

                # ── Client sends a message ──
                await ws_client.send_json({"type": "text", "content": "Hello from client!"})

                # Both should receive the broadcasted message
                msg_client = await ws_client.receive_json()
                msg_agent = await ws_agent.receive_json()

                for msg in (msg_client, msg_agent):
                    assert msg["meta"]["success"] is True
                    assert msg["data"]["content"] == "Hello from client!"
                    assert msg["data"]["sender_id"] == str(client_user.id)
                    assert msg["data"]["type"] == "text"
                    assert msg["data"]["conversation_id"] == conv_id

                # ── Agent replies ──
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
        conv_id = await self._create_conversation(client, auth, token, user.id)

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()  # join confirmation
            await ws.receive_json()  # broadcast join

            await ws.send_json({"type": "text", "content": "Persisted message"})
            await ws.receive_json()  # broadcasted message

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
        conv_id = await self._create_conversation(client, auth, token, user.id)

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()  # join confirmation
            await ws.receive_json()  # broadcast join

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
            assert (
                "Invalid payload. filename field is not allowed for text messages"
                in error_msg["detail"]
            )

            await ws.send_json(
                {"type": "file", "content": "ADFGER234TWERGW234", "filename": "file.pdf"}
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "mime_type is required when type='file'" in error_msg["detail"]

    async def test_non_participant_cannot_connect(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        creator, creator_token = await self._register_client_user(auth)
        conv_id = await self._create_conversation(client, auth, creator_token, creator.id)

        outsider_tokens = await auth.register_and_login_admin(
            email="outsider@test.com", username="outsider"
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
