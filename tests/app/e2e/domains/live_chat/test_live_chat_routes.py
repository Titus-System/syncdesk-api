import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.types import ASGIApp

from app.domains.auth.entities import UserWithRoles
from app.domains.files.enums import FileContext, FileStatus
from app.domains.files.models import FileObject
from app.domains.files.repositories import FileObjectRepository
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
            ticket_id=PydanticObjectId(),
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
                "mime_type, filename and file_id are not allowed"
                in error_msg["detail"]
            )

            await ws.send_json(
                {"type": "file", "content": "ADFGER234TWERGW234", "filename": "file.pdf"}
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert (
                "mime_type, filename and file_id are required when type='file'"
                in error_msg["detail"]
            )

    async def test_non_participant_cannot_connect(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        creator, creator_token = await self._register_client_user(auth)
        conv_id = await self._create_conversation(client, auth, creator_token, creator.id)

        await auth.register_agent(email="outsider@test.com", username="outsider")
        outsider_tokens = await auth.login(email="outsider@test.com")

        with pytest.raises(WebSocketDeniedError) as exc_info:
            async with AsyncWebSocket(
                app,
                f"/api/live_chat/room/{conv_id}",
                headers={"Authorization": f"Bearer {outsider_tokens['access_token']}"},
            ):
                pass

        assert exc_info.value.status == 403
        assert "not allowed to join" in exc_info.value.body


@pytest.mark.asyncio
class TestChatFileAttachments:
    """Validation of file_id when sending type='file' messages.

    The chat router consults the files domain at the composition layer to
    verify ownership, context and status of the referenced FileObject
    before persisting the message. These tests exercise the success path
    and each rejection branch, plus a backward-compat check for legacy
    documents that predate the file_id field.
    """

    @staticmethod
    async def _register_admin(
        auth: AuthActions, email: str, username: str
    ) -> tuple[UserWithRoles, str]:
        tokens = await auth.register_and_login_admin(email=email, username=username)
        user = await auth.me(tokens["access_token"])
        return user, tokens["access_token"]

    @staticmethod
    async def _create_conv(
        client: AsyncClient,
        auth: AuthActions,
        token: str,
        client_id: Any,
    ) -> str:
        dto = CreateConversationDTO(ticket_id=PydanticObjectId(), client_id=client_id)
        r = await client.post(
            "/api/conversations/",
            json=dto.model_dump(mode="json"),
            headers=auth.auth_headers(token),
        )
        assert r.status_code == 201, f"Failed to create conversation: {r.text}"
        return r.json()["data"]["id"]

    @staticmethod
    async def _insert_file(
        db_session: AsyncSession,
        uploader_id: UUID,
        conversation_id: PydanticObjectId | None = None,
        context: FileContext = FileContext.LIVE_CHAT_MESSAGE,
        status: FileStatus = FileStatus.UPLOADED,
    ) -> UUID:
        """Insert a FileObject row directly, bypassing presign + upload.

        The chat router only inspects DB state (ownership, context, status
        and the conversation id embedded in the object key); no MinIO call
        happens during message validation, so for the error-path tests we
        do not need a real blob.

        The object key mirrors ``FileService._build_object_key`` so the
        validator's conversation-id parser sees the same layout as
        production.
        """
        repo = FileObjectRepository(db_session)
        file_id = uuid4()
        if context == FileContext.LIVE_CHAT_MESSAGE:
            conv = conversation_id if conversation_id is not None else PydanticObjectId()
            object_key = f"live_chat/{conv}/{file_id}-probe.bin"
        else:
            object_key = f"avatars/users/{uploader_id}.bin"
        await repo.create(
            FileObject(
                id=file_id,
                bucket="syncdesk-files",
                object_key=object_key,
                original_filename="probe.bin",
                content_type="application/pdf",
                size_bytes=4,
                context=context,
                status=status,
                uploaded_by_user_id=uploader_id,
            )
        )
        return file_id

    async def test_text_message_with_file_id_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        user, token = await self._register_admin(auth, "f_txt@test.com", "f_txt")
        conv_id = await self._create_conv(client, auth, token, user.id)

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {"type": "text", "content": "oops", "file_id": str(uuid4())}
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "not allowed for text messages" in error_msg["detail"]

    async def test_file_message_with_unknown_file_id_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        user, token = await self._register_admin(auth, "f_unk@test.com", "f_unk")
        conv_id = await self._create_conv(client, auth, token, user.id)

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "ghost",
                    "filename": "x.pdf",
                    "mime_type": "application/pdf",
                    "file_id": str(uuid4()),
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "does not reference a known file" in error_msg["detail"]

    async def test_file_message_with_another_users_file_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        sender, sender_token = await self._register_admin(auth, "f_me@test.com", "f_me")
        other_tokens = await auth.register_and_login_admin(
            email="f_other@test.com", username="f_other"
        )
        other = await auth.me(other_tokens["access_token"])

        conv_id = await self._create_conv(client, auth, sender_token, sender.id)
        # File belongs to ``other``, not to the sender.
        foreign_file_id = await self._insert_file(db_session, other.id)

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {sender_token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "stealing",
                    "filename": "x.pdf",
                    "mime_type": "application/pdf",
                    "file_id": str(foreign_file_id),
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "not uploaded by the sender" in error_msg["detail"]

    async def test_file_message_with_wrong_context_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        user, token = await self._register_admin(auth, "f_ctx@test.com", "f_ctx")
        conv_id = await self._create_conv(client, auth, token, user.id)
        # Same uploader, but the file was meant as an avatar.
        avatar_file_id = await self._insert_file(
            db_session, user.id, context=FileContext.USER_AVATAR
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "mismatched",
                    "filename": "x.png",
                    "mime_type": "image/png",
                    "file_id": str(avatar_file_id),
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "context 'user_avatar'" in error_msg["detail"]

    async def test_file_message_with_pending_file_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        user, token = await self._register_admin(auth, "f_pend@test.com", "f_pend")
        conv_id = await self._create_conv(client, auth, token, user.id)
        pending_file_id = await self._insert_file(
            db_session, user.id, status=FileStatus.PENDING
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "too soon",
                    "filename": "x.pdf",
                    "mime_type": "application/pdf",
                    "file_id": str(pending_file_id),
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "status 'pending'" in error_msg["detail"]

    async def test_file_message_with_deleted_file_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        """Soft-deleted files cannot be referenced even by their owner."""
        user, token = await self._register_admin(auth, "f_del@test.com", "f_del")
        conv_id = await self._create_conv(client, auth, token, user.id)
        deleted_file_id = await self._insert_file(
            db_session, user.id, status=FileStatus.DELETED
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "gone",
                    "filename": "x.pdf",
                    "mime_type": "application/pdf",
                    "file_id": str(deleted_file_id),
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "status 'deleted'" in error_msg["detail"]

    async def test_file_message_with_failed_file_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        """Files left in FAILED state are not usable as attachments."""
        user, token = await self._register_admin(auth, "f_fail@test.com", "f_fail")
        conv_id = await self._create_conv(client, auth, token, user.id)
        failed_file_id = await self._insert_file(
            db_session, user.id, status=FileStatus.FAILED
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "broken",
                    "filename": "x.pdf",
                    "mime_type": "application/pdf",
                    "file_id": str(failed_file_id),
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "status 'failed'" in error_msg["detail"]

    async def test_file_message_with_malformed_file_id_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        """Non-UUID values in file_id are caught before any DB lookup.

        IncomingMessage already declares file_id as ``UUID | None``, so
        Pydantic rejects strings that don't parse as UUIDs first. The
        router's defensive ``UUID(str(...))`` block only fires if a future
        schema change loosens the type; the test pins both behaviors.
        """
        user, token = await self._register_admin(auth, "f_bad@test.com", "f_bad")
        conv_id = await self._create_conv(client, auth, token, user.id)

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "garbled",
                    "filename": "x.pdf",
                    "mime_type": "application/pdf",
                    "file_id": "not-a-uuid",
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            # Either Pydantic's UUID parse error or the router's explicit
            # message — both indicate the same rejection class.
            assert (
                "valid UUID" in error_msg["detail"]
                or "uuid" in error_msg["detail"].lower()
            )

    async def test_file_message_from_different_conversation_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        """A file uploaded in conversation A cannot be reused in conversation B.

        The object key carries the original conversation id; recipients in
        conversation B would receive 403 trying to download the file (the
        files router authorizes downloads against the embedded conversation
        id, not the message's conversation), so we reject at send time to
        avoid the confusing UX.
        """
        user, token = await self._register_admin(auth, "f_xconv@test.com", "f_xconv")
        # Two conversations owned by the same user.
        conv_a_id = await self._create_conv(client, auth, token, user.id)
        conv_b_id = await self._create_conv(client, auth, token, user.id)

        # File belongs to conversation A.
        foreign_file_id = await self._insert_file(
            db_session, user.id, conversation_id=PydanticObjectId(conv_a_id)
        )

        # Try to send it from conversation B.
        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_b_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "smuggled",
                    "filename": "x.pdf",
                    "mime_type": "application/pdf",
                    "file_id": str(foreign_file_id),
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "different conversation" in error_msg["detail"]

    async def test_legacy_mongo_conversation_without_file_id_still_loads(
        self,
        mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    ) -> None:
        """Backward compat read-side: documents written before PR3 lack the
        ``file_id`` key on embedded messages. Beanie must deserialize them
        with ``file_id`` defaulting to ``None`` so historical conversations
        keep loading after the schema change.

        Writes the document via raw Motor (bypassing Beanie's writer, which
        would always include the field) and reads it back via the
        ``Conversation`` model with the new schema.
        """
        conv_object_id = PydanticObjectId()
        message_id = uuid4()
        sender_id = uuid4()

        legacy_document = {
            "_id": conv_object_id,
            "ticket_id": PydanticObjectId(),
            "agent_id": None,
            "client_id": str(uuid4()),
            "sequential_index": 0,
            "parent_id": None,
            "children_ids": [],
            "started_at": datetime.now(UTC),
            "finished_at": None,
            "messages": [
                {
                    "id": str(message_id),
                    "conversation_id": conv_object_id,
                    "sender_id": str(sender_id),
                    "timestamp": datetime.now(UTC),
                    "type": "text",
                    "content": "pre-PR3 message",
                    # Crucially, no ``file_id`` key — simulates the
                    # document shape from before the field existed.
                }
            ],
        }
        await mongo_db_conn["conversations"].insert_one(legacy_document)

        loaded = await Conversation.get(conv_object_id)
        assert loaded is not None
        assert len(loaded.messages) == 1
        msg = loaded.messages[0]
        assert msg.file_id is None
        assert msg.id == message_id
        assert msg.type == "text"
        assert msg.content == "pre-PR3 message"

        # Datetime round-trip sanity: the Motor client in this project is
        # constructed without ``tz_aware=True``, so BSON dates come back as
        # naive datetimes — Pydantic accepts that and keeps them as naive.
        # The test pins that contract so a future "set tz_aware globally"
        # change surfaces here intentionally.
        assert msg.timestamp is not None
        assert msg.timestamp.tzinfo is None
        assert loaded.started_at is not None
        assert loaded.started_at.tzinfo is None

    async def test_file_message_with_malformed_object_key_is_rejected(
        self,
        app: Any,
        client: AsyncClient,
        auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        """Defensive branch: a FileObject row whose object_key does not
        match the ``live_chat/{conv_id}/...`` shape can't be associated
        with a conversation, so the validator must reject the attachment
        instead of raising or silently accepting it.

        Inserts the row directly so the validator sees a corrupted key
        the production code would normally never produce.
        """
        user, token = await self._register_admin(auth, "f_mkey@test.com", "f_mkey")
        conv_id = await self._create_conv(client, auth, token, user.id)

        repo = FileObjectRepository(db_session)
        file_id = uuid4()
        await repo.create(
            FileObject(
                id=file_id,
                bucket="syncdesk-files",
                # Missing the second path segment that the parser reads as
                # conversation id; ``_conversation_id_from_object_key``
                # returns None and the validator rejects.
                object_key="malformed-no-slash-no-conv-id",
                original_filename="probe.bin",
                content_type="application/pdf",
                size_bytes=4,
                context=FileContext.LIVE_CHAT_MESSAGE,
                status=FileStatus.UPLOADED,
                uploaded_by_user_id=user.id,
            )
        )

        async with AsyncWebSocket(
            app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "corrupt key",
                    "filename": "probe.bin",
                    "mime_type": "application/pdf",
                    "file_id": str(file_id),
                }
            )
            error_msg = await ws.receive_json()
            assert error_msg["status"] == 1003
            assert "different conversation" in error_msg["detail"]
