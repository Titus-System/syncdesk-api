"""End-to-end live-chat file attachments against real MinIO.

This module exercises the full PR3 flow without mocking storage:

1. Client asks the API for a presigned upload URL.
2. The bytes are POSTed straight into MinIO via the presigned policy.
3. The API ``confirm`` endpoint head-checks the object.
4. A WebSocket message of ``type="file"`` carrying the new ``file_id`` is
   sent over the live_chat channel and broadcast back.
5. The download URL endpoint returns a presigned GET whose bytes match
   the original upload exactly.

Unlike ``test_live_chat_routes.py`` (which inserts ``FileObject`` rows
directly to focus on validator branches), this file keeps the real
``S3ObjectStorage`` wired so we get integration evidence that an
attached file is uploadable, persistable and downloadable through the
same conversation it was attached to. Tests skip automatically when
MinIO is not reachable.

The helper ``AsyncWebSocket`` lives in the sibling test module so we
can share the in-process ASGI transport without re-implementing the
WebSocket framing.
"""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_email_service
from app.core.event_dispatcher import get_event_dispatcher
from app.db.mongo.dependencies import get_mongo_session
from app.db.postgres.dependencies import get_postgres_session
from app.domains.live_chat.entities import Conversation
from app.domains.live_chat.schemas import CreateConversationDTO
from app.main import create_app
from tests.app.e2e.conftest import AuthActions, FakeEmailStrategy
from tests.app.e2e.domains.live_chat.test_live_chat_routes import AsyncWebSocket

settings = get_settings()


async def _minio_is_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            res = await c.get(f"{settings.S3_PUBLIC_ENDPOINT_URL}/minio/health/live")
            return res.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


@pytest_asyncio.fixture(autouse=True)
async def _require_minio() -> AsyncGenerator[None, None]:
    if not await _minio_is_reachable():
        pytest.skip(
            f"MinIO not reachable at {settings.S3_PUBLIC_ENDPOINT_URL}; "
            "start the docker-compose stack to run these tests."
        )
    yield


@pytest.fixture
def real_storage_app(fake_email: FakeEmailStrategy) -> FastAPI:
    """Same as the default ``app`` fixture but without overriding storage."""
    get_event_dispatcher.cache_clear()
    application = create_app()
    application.dependency_overrides[get_email_service] = lambda: fake_email
    return application


@pytest.fixture
async def real_storage_client(
    real_storage_app: FastAPI,
    db_session: AsyncSession,
    mongo_db_conn: AsyncGenerator[AsyncIOMotorDatabase[dict[str, Any]], None],
) -> AsyncGenerator[AsyncClient, None]:
    async def _override_postgres() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    async def _override_mongo() -> AsyncGenerator[
        AsyncIOMotorDatabase[dict[str, Any]], None
    ]:
        yield mongo_db_conn

    real_storage_app.dependency_overrides[get_postgres_session] = _override_postgres
    real_storage_app.dependency_overrides[get_mongo_session] = _override_mongo
    transport = ASGITransport(app=real_storage_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    real_storage_app.dependency_overrides.clear()


@pytest.fixture
def real_auth(
    real_storage_client: AsyncClient,
    db_session: AsyncSession,
    _seed_auth_data: None,
) -> AuthActions:
    return AuthActions(real_storage_client, db_session)


async def _upload_chat_file_via_api(
    client: AsyncClient,
    token: str,
    conversation_id: str,
    payload: bytes,
    *,
    filename: str = "probe.bin",
    content_type: str = "application/pdf",
) -> str:
    """Drive the full presign → POST MinIO → confirm flow and return the file_id."""
    headers = {"Authorization": f"Bearer {token}"}

    presign = await client.post(
        "/api/files/presign-upload",
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(payload),
            "context": "live_chat_message",
            "context_ref": {"conversation_id": conversation_id},
        },
        headers=headers,
    )
    assert presign.status_code == 201, presign.text
    data = presign.json()["data"]
    file_id = data["file_id"]

    async with httpx.AsyncClient(timeout=10.0) as http:
        res = await http.post(
            data["upload_url"],
            data=data["fields"],
            files={"file": (filename, payload, content_type)},
        )
    assert res.status_code in (200, 201, 204), res.text

    confirm = await client.post(
        f"/api/files/{file_id}/confirm", headers=headers
    )
    assert confirm.status_code == 200, confirm.text
    assert confirm.json()["data"]["status"] == "uploaded"
    return file_id


async def _create_conversation(
    client: AsyncClient,
    auth: AuthActions,
    token: str,
    client_id: Any,
    agent_id: Any | None = None,
) -> str:
    dto = CreateConversationDTO(
        ticket_id=PydanticObjectId(), client_id=client_id, agent_id=agent_id
    )
    r = await client.post(
        "/api/conversations/",
        json=dto.model_dump(mode="json"),
        headers=auth.auth_headers(token),
    )
    assert r.status_code == 201, f"Failed to create conversation: {r.text}"
    return str(r.json()["data"]["id"])


@pytest.mark.asyncio
class TestChatFileAttachmentsRealMinIO:
    async def test_admin_uploads_and_attaches_file_intact_through_conversation(
        self,
        real_storage_app: FastAPI,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Full happy path with the admin role.

        Asserts that the bytes posted to MinIO survive the round-trip and
        come back identical via the download URL the same conversation
        participant would request.
        """
        tokens = await real_auth.register_and_login_admin(
            email="ws_admin_file@test.com", username="wsadminfile"
        )
        user = await real_auth.me(tokens["access_token"])
        token = tokens["access_token"]
        conv_id = await _create_conversation(
            real_storage_client, real_auth, token, user.id
        )

        payload = b"real-bytes-from-live-chat-e2e-against-minio"
        file_id = await _upload_chat_file_via_api(
            real_storage_client, token, conv_id, payload
        )

        async with AsyncWebSocket(
            real_storage_app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()  # personal join confirmation
            await ws.receive_json()  # broadcast join

            await ws.send_json(
                {
                    "type": "file",
                    "content": "here is the file",
                    "filename": "probe.bin",
                    "mime_type": "application/pdf",
                    "file_id": file_id,
                }
            )
            broadcast = await ws.receive_json()
            assert broadcast["meta"]["success"] is True
            assert broadcast["data"]["type"] == "file"
            assert broadcast["data"]["file_id"] == file_id
            assert broadcast["data"]["conversation_id"] == conv_id

        # Download via presigned GET and verify bytes match exactly.
        dl_req = await real_storage_client.get(
            f"/api/files/{file_id}/download-url",
            headers=real_auth.auth_headers(token),
        )
        assert dl_req.status_code == 200, dl_req.text
        download_url = dl_req.json()["data"]["url"]

        async with httpx.AsyncClient(timeout=10.0) as http:
            dl = await http.get(download_url)
        assert dl.status_code == 200
        assert dl.content == payload, "Downloaded bytes do not match uploaded payload"

    async def test_agent_can_attach_file_in_their_conversation(
        self,
        real_storage_app: FastAPI,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        """Non-admin role: an agent uploads and shares a file in their chat.

        Exercises the same flow with the agent role to confirm that the
        validator is role-agnostic — only ownership, context, status and
        conversation membership matter.
        """
        # Client of the conversation, registered as admin so we can hand
        # them the conversation creation endpoint.
        client_tokens = await real_auth.register_and_login_admin(
            email="ws_client_role@test.com", username="wsclientrole"
        )
        client_user = await real_auth.me(client_tokens["access_token"])

        # Agent who will upload and attach the file.
        await real_auth.register_agent(
            email="ws_agent_role@test.com", username="wsagentrole"
        )
        agent_tokens = await real_auth.login(email="ws_agent_role@test.com")
        agent_user = await real_auth.me(agent_tokens["access_token"])
        agent_token = agent_tokens["access_token"]

        conv_id = await _create_conversation(
            real_storage_client,
            real_auth,
            client_tokens["access_token"],
            client_user.id,
            agent_id=agent_user.id,
        )

        payload = b"agent-attaches-file-bytes"
        file_id = await _upload_chat_file_via_api(
            real_storage_client, agent_token, conv_id, payload
        )

        async with AsyncWebSocket(
            real_storage_app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {agent_token}"},
        ) as ws:
            await ws.receive_json()
            await ws.receive_json()

            await ws.send_json(
                {
                    "type": "file",
                    "content": "from the agent",
                    "filename": "probe.bin",
                    "mime_type": "application/pdf",
                    "file_id": file_id,
                }
            )
            broadcast = await ws.receive_json()
            assert broadcast["meta"]["success"] is True
            assert broadcast["data"]["type"] == "file"
            assert broadcast["data"]["file_id"] == file_id
            assert broadcast["data"]["sender_id"] == str(agent_user.id)

    async def test_two_participants_exchange_file_in_real_time(
        self,
        real_storage_app: FastAPI,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Real-time delivery: a file uploaded by the client reaches the
        agent over their open WebSocket and the agent can fetch the bytes
        through their own download URL.

        This is the contract the chat UI relies on: when one participant
        attaches a file, the other side already in the room must see the
        message immediately and be able to retrieve the binary intact.
        """
        # Client connects first.
        client_tokens = await real_auth.register_and_login_admin(
            email="ws_rt_client@test.com", username="wsrtclient"
        )
        client_user = await real_auth.me(client_tokens["access_token"])
        client_token = client_tokens["access_token"]

        # Agent will be the recipient of the broadcast.
        await real_auth.register_agent(
            email="ws_rt_agent@test.com", username="wsrtagent"
        )
        agent_tokens = await real_auth.login(email="ws_rt_agent@test.com")
        agent_user = await real_auth.me(agent_tokens["access_token"])
        agent_token = agent_tokens["access_token"]

        conv_id = await _create_conversation(
            real_storage_client,
            real_auth,
            client_token,
            client_user.id,
            agent_id=agent_user.id,
        )

        payload = b"real-time-delivery-payload-bytes-into-minio"
        file_id = await _upload_chat_file_via_api(
            real_storage_client, client_token, conv_id, payload
        )

        async with AsyncWebSocket(
            real_storage_app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {client_token}"},
        ) as ws_client:
            await ws_client.receive_json()  # personal join confirmation
            await ws_client.receive_json()  # broadcast join

            async with AsyncWebSocket(
                real_storage_app,
                f"/api/live_chat/room/{conv_id}",
                headers={"Authorization": f"Bearer {agent_token}"},
            ) as ws_agent:
                await ws_agent.receive_json()  # personal join confirmation
                await ws_agent.receive_json()  # broadcast join

                # Client also gets the agent's join broadcast.
                await ws_client.receive_json()

                # Client sends the file message.
                await ws_client.send_json(
                    {
                        "type": "file",
                        "content": "shared file",
                        "filename": "probe.bin",
                        "mime_type": "application/pdf",
                        "file_id": file_id,
                    }
                )

                # Both sides must receive the broadcast in real time.
                msg_for_client = await ws_client.receive_json()
                msg_for_agent = await ws_agent.receive_json()

                for msg in (msg_for_client, msg_for_agent):
                    assert msg["meta"]["success"] is True
                    assert msg["data"]["type"] == "file"
                    assert msg["data"]["file_id"] == file_id
                    assert msg["data"]["sender_id"] == str(client_user.id)
                    assert msg["data"]["conversation_id"] == conv_id

                # The agent, who received the broadcast, requests the
                # download URL using their own token and pulls the bytes.
                dl_req = await real_storage_client.get(
                    f"/api/files/{file_id}/download-url",
                    headers=real_auth.auth_headers(agent_token),
                )
                assert dl_req.status_code == 200, dl_req.text
                download_url = dl_req.json()["data"]["url"]

                async with httpx.AsyncClient(timeout=10.0) as http:
                    dl = await http.get(download_url)
                assert dl.status_code == 200
                assert dl.content == payload, (
                    "Agent received the broadcast but the downloaded bytes "
                    "do not match what the client uploaded"
                )

    async def test_admin_observes_and_downloads_chat_file_without_being_a_participant(
        self,
        real_storage_app: FastAPI,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Admin oversight: a user with admin role who is NOT a participant
        of the conversation must still be able to (a) join the WebSocket
        room and receive the file-message broadcast in real time and
        (b) download the bytes through the file download URL.

        Both bypasses are implemented in the routers:
        - WS: ``can_user_join_conversation`` returns True for admins
          (``chat_router.py``)
        - Download: ``_ensure_user_can_read_chat_file`` early-returns for
          admins (``files/routers.py``)

        This test pins both paths against real MinIO so a regression in
        either authorization branch surfaces here.
        """
        # The chat participant is an agent so we can keep them clearly
        # separate from the observing admin role.
        await real_auth.register_agent(
            email="ws_oversight_agent@test.com", username="wsovagent"
        )
        agent_tokens = await real_auth.login(email="ws_oversight_agent@test.com")
        agent_user = await real_auth.me(agent_tokens["access_token"])
        agent_token = agent_tokens["access_token"]

        # Admin observer — has admin role, distinct identity, not a
        # participant of the conversation.
        admin_tokens = await real_auth.register_and_login_admin(
            email="ws_oversight_admin@test.com", username="wsovadmin"
        )
        admin_user = await real_auth.me(admin_tokens["access_token"])
        admin_token = admin_tokens["access_token"]

        # Conversation created by the admin so we have a token with the
        # POST /conversations permission, but the participants are the
        # agent and another (fictitious) client id. Crucially, the admin
        # is NOT in the participants list.
        conv_id = await _create_conversation(
            real_storage_client,
            real_auth,
            admin_token,
            client_id=str(uuid4()),
            agent_id=agent_user.id,
        )

        payload = b"admin-must-see-this-file-content"
        file_id = await _upload_chat_file_via_api(
            real_storage_client, agent_token, conv_id, payload
        )

        async with AsyncWebSocket(
            real_storage_app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {admin_token}"},
        ) as ws_admin:
            await ws_admin.receive_json()  # personal join confirmation
            await ws_admin.receive_json()  # broadcast join

            async with AsyncWebSocket(
                real_storage_app,
                f"/api/live_chat/room/{conv_id}",
                headers={"Authorization": f"Bearer {agent_token}"},
            ) as ws_agent:
                await ws_agent.receive_json()  # personal join confirmation
                await ws_agent.receive_json()  # broadcast join

                # Admin sees the agent's join broadcast.
                await ws_admin.receive_json()

                # Agent (the participant) sends the file message.
                await ws_agent.send_json(
                    {
                        "type": "file",
                        "content": "shared with the admin too",
                        "filename": "probe.bin",
                        "mime_type": "application/pdf",
                        "file_id": file_id,
                    }
                )

                # Both sockets receive the broadcast — admin observes
                # in real time even without being a participant.
                broadcast_agent = await ws_agent.receive_json()
                broadcast_admin = await ws_admin.receive_json()

                for msg in (broadcast_agent, broadcast_admin):
                    assert msg["meta"]["success"] is True
                    assert msg["data"]["type"] == "file"
                    assert msg["data"]["file_id"] == file_id
                    assert msg["data"]["sender_id"] == str(agent_user.id)

                # Admin requests the download URL using their own token
                # and pulls the file. The router's admin bypass kicks in.
                assert admin_user.id != agent_user.id  # sanity: distinct
                dl_req = await real_storage_client.get(
                    f"/api/files/{file_id}/download-url",
                    headers=real_auth.auth_headers(admin_token),
                )
                assert dl_req.status_code == 200, dl_req.text
                download_url = dl_req.json()["data"]["url"]

                async with httpx.AsyncClient(timeout=10.0) as http:
                    dl = await http.get(download_url)
                assert dl.status_code == 200
                assert dl.content == payload, (
                    "Admin received the broadcast but the downloaded "
                    "bytes do not match the original payload"
                )

    async def test_outsider_cannot_download_chat_file_from_other_conversation(
        self,
        real_storage_app: FastAPI,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Negative guard for the previous test: a user who is neither
        participant nor admin must get 403 when trying to download a chat
        file, even if they somehow learned the file_id.

        Pins the access control surface around real-time file sharing.
        """
        client_tokens = await real_auth.register_and_login_admin(
            email="ws_rt_owner@test.com", username="wsrtowner"
        )
        client_user = await real_auth.me(client_tokens["access_token"])
        client_token = client_tokens["access_token"]

        # Outsider has no relationship to the conversation.
        await real_auth.register_agent(
            email="ws_rt_outsider@test.com", username="wsrtoutsider"
        )
        outsider_tokens = await real_auth.login(email="ws_rt_outsider@test.com")
        outsider_token = outsider_tokens["access_token"]

        conv_id = await _create_conversation(
            real_storage_client, real_auth, client_token, client_user.id
        )

        payload = b"private-bytes"
        file_id = await _upload_chat_file_via_api(
            real_storage_client, client_token, conv_id, payload
        )

        dl_req = await real_storage_client.get(
            f"/api/files/{file_id}/download-url",
            headers=real_auth.auth_headers(outsider_token),
        )
        assert dl_req.status_code == 403, dl_req.text

    async def test_file_message_is_persisted_in_mongo_and_listed_via_history(
        self,
        real_storage_app: FastAPI,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
        mongo_db_conn: AsyncGenerator[
            AsyncIOMotorDatabase[dict[str, Any]], None
        ],
    ) -> None:
        """The file_id reaches Mongo and survives a REST history fetch.

        The broadcast asserting file_id in earlier tests only proves the
        WS payload, not the durable side. This test closes that loop:

        1. Upload a real file via the API.
        2. Send a ``type='file'`` message over the WS.
        3. Read the Conversation document directly from Mongo and verify
           the embedded ChatMessage has the correct ``file_id``.
        4. Hit ``GET /api/conversations/ticket/{ticket_id}/messages`` —
           the REST surface used by the frontend to render old chats —
           and verify the JSON response carries the same ``file_id``.

        Without this test a regression where ``add_message_to_conversation``
        drops the new field, or where the messages route serializes
        without it, would slip through.
        """
        tokens = await real_auth.register_and_login_admin(
            email="ws_persist_history@test.com", username="wspersisthistory"
        )
        user = await real_auth.me(tokens["access_token"])
        token = tokens["access_token"]

        # Explicit ticket_id so we can query the history endpoint later.
        ticket_id = PydanticObjectId()
        dto = CreateConversationDTO(
            ticket_id=ticket_id, client_id=user.id, agent_id=None
        )
        create_resp = await real_storage_client.post(
            "/api/conversations/",
            json=dto.model_dump(mode="json"),
            headers=real_auth.auth_headers(token),
        )
        assert create_resp.status_code == 201, create_resp.text
        conv_id = create_resp.json()["data"]["id"]

        payload = b"persisted-and-served-by-history-endpoint"
        file_id = await _upload_chat_file_via_api(
            real_storage_client, token, conv_id, payload
        )

        async with AsyncWebSocket(
            real_storage_app,
            f"/api/live_chat/room/{conv_id}",
            headers={"Authorization": f"Bearer {token}"},
        ) as ws:
            await ws.receive_json()  # personal join confirmation
            await ws.receive_json()  # broadcast join

            await ws.send_json(
                {
                    "type": "file",
                    "content": "must be persisted",
                    "filename": "probe.bin",
                    "mime_type": "application/pdf",
                    "file_id": file_id,
                }
            )
            broadcast = await ws.receive_json()
            assert broadcast["data"]["file_id"] == file_id

        # 1) Mongo persistence: the embedded ChatMessage has file_id set.
        conv = await Conversation.get(PydanticObjectId(conv_id))
        assert conv is not None
        file_messages = [m for m in conv.messages if m.type == "file"]
        assert len(file_messages) == 1
        assert file_messages[0].file_id == UUID(file_id)
        assert file_messages[0].sender_id == user.id

        # 2) REST history endpoint: serialized payload carries file_id.
        history = await real_storage_client.get(
            f"/api/conversations/ticket/{ticket_id}/messages",
            params={"page": 1, "limit": 50},
            headers=real_auth.auth_headers(token),
        )
        assert history.status_code == 200, history.text
        data = history.json()["data"]
        history_file_msgs = [m for m in data["messages"] if m["type"] == "file"]
        assert len(history_file_msgs) == 1
        assert history_file_msgs[0]["file_id"] == file_id
        assert history_file_msgs[0]["content"] == "must be persisted"
