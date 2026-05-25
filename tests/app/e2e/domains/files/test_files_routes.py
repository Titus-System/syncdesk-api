"""End-to-end tests for the /api/files/* endpoints."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest
from beanie import PydanticObjectId
from botocore.exceptions import ClientError
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.files.enums import FileStatus
from app.domains.files.models import FileObject
from app.domains.live_chat.entities import Conversation
from tests.app.e2e.conftest import AuthActions, FakeObjectStorage


# ────────────────────────────────────────────────────────
# helpers
# ────────────────────────────────────────────────────────


async def _create_conversation(client_id: Any, agent_id: Any | None) -> Conversation:
    conv = Conversation(
        ticket_id=PydanticObjectId(),
        client_id=client_id,
        agent_id=agent_id,
    )
    await conv.insert()
    return conv


def _avatar_request(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "filename": "avatar.png",
        "content_type": "image/png",
        "size_bytes": 1024,
        "context": "user_avatar",
    }
    payload.update(overrides)
    return payload


def _chat_request(conversation_id: PydanticObjectId, **overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "filename": "screenshot.png",
        "content_type": "image/png",
        "size_bytes": 2048,
        "context": "live_chat_message",
        "context_ref": {"conversation_id": str(conversation_id)},
    }
    payload.update(overrides)
    return payload


# ════════════════════════════════════════════════════════
# POST /api/files/presign-upload
# ════════════════════════════════════════════════════════


class TestPresignUpload:
    @pytest.mark.asyncio
    async def test_avatar_success_returns_presigned_post(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        tokens = await auth.register_and_login(email="avu@test.com", username="avu")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post("/api/files/presign-upload", json=_avatar_request(), headers=headers)
        assert r.status_code == 201, r.text

        body = r.json()["data"]
        assert body["method"] == "POST"
        assert body["upload_url"].startswith("http://fake-storage/")
        assert body["max_size_bytes"] == 2 * 1024 * 1024
        assert "Content-Type" in body["fields"]
        assert len(fake_storage.presigned_uploads) == 1

    @pytest.mark.asyncio
    async def test_requires_authentication(self, client: AsyncClient) -> None:
        # FastAPI's HTTPBearer returns 403 (not 401) when the header is missing.
        r = await client.post("/api/files/presign-upload", json=_avatar_request())
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_unsupported_content_type_returns_400(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="badmime@test.com", username="badmime")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/files/presign-upload",
            json=_avatar_request(content_type="application/x-msdownload"),
            headers=headers,
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_size_above_context_limit_returns_400(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="bigfile@test.com", username="bigfile")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/files/presign-upload",
            json=_avatar_request(size_bytes=10 * 1024 * 1024),  # 10 MiB > 2 MiB avatar limit
            headers=headers,
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_size_zero_rejected_by_schema_returns_422(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="zerofile@test.com", username="zerofile")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/files/presign-upload",
            json=_avatar_request(size_bytes=0),
            headers=headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_filename_with_path_traversal_returns_400(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="badname@test.com", username="badname")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/files/presign-upload",
            json=_avatar_request(filename="../etc/passwd"),
            headers=headers,
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_message_requires_conversation_id(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="chat1@test.com", username="chat1")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/files/presign-upload",
            json={
                "filename": "x.png",
                "content_type": "image/png",
                "size_bytes": 1024,
                "context": "live_chat_message",
                "context_ref": {},
            },
            headers=headers,
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_message_invalid_conversation_id_returns_400(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="chat2@test.com", username="chat2")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/files/presign-upload",
            json={
                "filename": "x.png",
                "content_type": "image/png",
                "size_bytes": 1024,
                "context": "live_chat_message",
                "context_ref": {"conversation_id": "not-a-mongo-id"},
            },
            headers=headers,
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_chat_message_rejects_non_participant(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="outsider@test.com", username="outsider")
        headers = auth.auth_headers(tokens["access_token"])

        conv = await _create_conversation(client_id=uuid4(), agent_id=uuid4())
        r = await client.post(
            "/api/files/presign-upload",
            json=_chat_request(conv.id),
            headers=headers,
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_chat_message_succeeds_for_participant(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="part@test.com", username="part")
        me = await auth.me(tokens["access_token"])
        headers = auth.auth_headers(tokens["access_token"])

        conv = await _create_conversation(client_id=me.id, agent_id=uuid4())
        r = await client.post(
            "/api/files/presign-upload",
            json=_chat_request(conv.id),
            headers=headers,
        )
        assert r.status_code == 201, r.text
        assert r.json()["data"]["max_size_bytes"] == 25 * 1024 * 1024

    @pytest.mark.asyncio
    async def test_chat_message_succeeds_for_assigned_agent(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        """Both `client_id` and `agent_id` are participants of a conversation."""
        tokens = await auth.register_and_login(email="agent_up@test.com", username="agent_up")
        me = await auth.me(tokens["access_token"])
        headers = auth.auth_headers(tokens["access_token"])

        conv = await _create_conversation(client_id=uuid4(), agent_id=me.id)
        r = await client.post(
            "/api/files/presign-upload",
            json=_chat_request(conv.id),
            headers=headers,
        )
        assert r.status_code == 201, r.text


# ════════════════════════════════════════════════════════
# POST /api/files/{id}/confirm
# ════════════════════════════════════════════════════════


class TestConfirmUpload:
    @pytest.mark.asyncio
    async def test_confirm_after_upload_returns_uploaded(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        tokens = await auth.register_and_login(email="cfm@test.com", username="cfm")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        assert presign.status_code == 201
        file_id = presign.json()["data"]["file_id"]
        object_key = fake_storage.last_presigned_upload_key()

        fake_storage.mark_uploaded(object_key, size=1024)

        r = await client.post(f"/api/files/{file_id}/confirm", headers=headers)
        assert r.status_code == 200, r.text
        assert r.json()["data"]["status"] == "uploaded"

    @pytest.mark.asyncio
    async def test_confirm_without_upload_returns_409(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="cfm2@test.com", username="cfm2")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]

        r = await client.post(f"/api/files/{file_id}/confirm", headers=headers)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_confirm_missing_file_returns_404(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="cfm3@test.com", username="cfm3")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(f"/api/files/{uuid4()}/confirm", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_confirm_by_non_uploader_returns_403(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        owner = await auth.register_and_login(email="owner@test.com", username="owner")
        owner_headers = auth.auth_headers(owner["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=owner_headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())

        intruder = await auth.register_and_login(email="intruder@test.com", username="intruder")
        intruder_headers = auth.auth_headers(intruder["access_token"])

        r = await client.post(f"/api/files/{file_id}/confirm", headers=intruder_headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_confirm_is_idempotent(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        tokens = await auth.register_and_login(email="idem@test.com", username="idem")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())

        first = await client.post(f"/api/files/{file_id}/confirm", headers=headers)
        second = await client.post(f"/api/files/{file_id}/confirm", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 200
        assert second.json()["data"]["status"] == "uploaded"


# ════════════════════════════════════════════════════════
# GET /api/files/{id}/download-url
# ════════════════════════════════════════════════════════


class TestDownloadUrl:
    @pytest.mark.asyncio
    async def test_avatar_download_for_any_user(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        owner = await auth.register_and_login(email="avo@test.com", username="avo")
        owner_headers = auth.auth_headers(owner["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=owner_headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=owner_headers)

        other = await auth.register_and_login(email="avo2@test.com", username="avo2")
        other_headers = auth.auth_headers(other["access_token"])

        r = await client.get(f"/api/files/{file_id}/download-url", headers=other_headers)
        assert r.status_code == 200
        assert "signed=1" in r.json()["data"]["url"]

    @pytest.mark.asyncio
    async def test_missing_file_returns_404(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="dlmiss@test.com", username="dlmiss")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.get(f"/api/files/{uuid4()}/download-url", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_pending_file_returns_404(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="dlpend@test.com", username="dlpend")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]

        r = await client.get(f"/api/files/{file_id}/download-url", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_message_rejects_non_participant(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        owner = await auth.register_and_login(email="ch_owner@test.com", username="ch_owner")
        owner_user = await auth.me(owner["access_token"])
        owner_headers = auth.auth_headers(owner["access_token"])

        conv = await _create_conversation(client_id=owner_user.id, agent_id=uuid4())
        presign = await client.post(
            "/api/files/presign-upload", json=_chat_request(conv.id), headers=owner_headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=owner_headers)

        intruder = await auth.register_and_login(email="ch_intr@test.com", username="ch_intr")
        intruder_headers = auth.auth_headers(intruder["access_token"])

        r = await client.get(f"/api/files/{file_id}/download-url", headers=intruder_headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_chat_message_agent_can_read(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        """The assigned agent is a participant and must be allowed to read."""
        client_tokens = await auth.register_and_login(email="ch_cli@test.com", username="ch_cli")
        client_user = await auth.me(client_tokens["access_token"])
        client_headers = auth.auth_headers(client_tokens["access_token"])

        agent_tokens = await auth.register_and_login(email="ch_agt@test.com", username="ch_agt")
        agent_user = await auth.me(agent_tokens["access_token"])
        agent_headers = auth.auth_headers(agent_tokens["access_token"])

        # Client uploads a file in a conversation where the other user is the agent.
        conv = await _create_conversation(client_id=client_user.id, agent_id=agent_user.id)
        presign = await client.post(
            "/api/files/presign-upload",
            json=_chat_request(conv.id),
            headers=client_headers,
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=client_headers)

        # Agent (without admin role) can fetch the download URL.
        r = await client.get(f"/api/files/{file_id}/download-url", headers=agent_headers)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_chat_message_admin_can_read_any(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        owner = await auth.register_and_login(email="ch_admowner@test.com", username="ch_admowner")
        owner_user = await auth.me(owner["access_token"])
        owner_headers = auth.auth_headers(owner["access_token"])

        conv = await _create_conversation(client_id=owner_user.id, agent_id=uuid4())
        presign = await client.post(
            "/api/files/presign-upload", json=_chat_request(conv.id), headers=owner_headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=owner_headers)

        admin = await auth.register_and_login_admin(email="admdl@test.com", username="admdl")
        admin_headers = auth.auth_headers(admin["access_token"])

        r = await client.get(f"/api/files/{file_id}/download-url", headers=admin_headers)
        assert r.status_code == 200


# ════════════════════════════════════════════════════════
# DELETE /api/files/{id}
# ════════════════════════════════════════════════════════


class TestDeleteFile:
    @pytest.mark.asyncio
    async def test_uploader_can_delete(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        tokens = await auth.register_and_login(email="del1@test.com", username="del1")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=headers)

        r = await client.delete(f"/api/files/{file_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_admin_can_delete_others_file(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        owner = await auth.register_and_login(email="del_own@test.com", username="del_own")
        owner_headers = auth.auth_headers(owner["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=owner_headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=owner_headers)

        admin = await auth.register_and_login_admin(email="admdel@test.com", username="admdel")
        admin_headers = auth.auth_headers(admin["access_token"])

        r = await client.delete(f"/api/files/{file_id}", headers=admin_headers)
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_non_uploader_non_admin_returns_403(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        owner = await auth.register_and_login(email="del_own2@test.com", username="del_own2")
        owner_headers = auth.auth_headers(owner["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=owner_headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=owner_headers)

        intruder = await auth.register_and_login(email="del_int@test.com", username="del_int")
        intruder_headers = auth.auth_headers(intruder["access_token"])

        r = await client.delete(f"/api/files/{file_id}", headers=intruder_headers)
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_missing_returns_404(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="delmiss@test.com", username="delmiss")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.delete(f"/api/files/{uuid4()}", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_twice_returns_404_on_second(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        tokens = await auth.register_and_login(email="del2x@test.com", username="del2x")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=headers)

        first = await client.delete(f"/api/files/{file_id}", headers=headers)
        second = await client.delete(f"/api/files/{file_id}", headers=headers)
        assert first.status_code == 200
        assert second.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_with_invalid_uuid_returns_422(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        tokens = await auth.register_and_login(email="badid@test.com", username="badid")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.delete("/api/files/not-a-uuid", headers=headers)
        assert r.status_code == 422


# ════════════════════════════════════════════════════════
# Error branches (storage failures + uncommon DB states)
# ════════════════════════════════════════════════════════


class TestStorageFailures:
    """Exercises the try/except branches added against ``ClientError``."""

    @pytest.mark.asyncio
    async def test_presign_propagates_storage_error(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        """Storage backend failures during presign must escape the service.

        The ``@app.exception_handler(Exception)`` registered in
        ``app/core/exceptions.py`` converts unhandled exceptions to 500 in
        production. Under httpx ASGITransport the BaseHTTPMiddleware re-raises
        before the handler's Response reaches the client, so the test asserts
        the ``ClientError`` propagation directly — the assertion that matters
        is that the service does not silently swallow storage failures.
        """
        tokens = await auth.register_and_login(email="pse@test.com", username="pse")
        headers = auth.auth_headers(tokens["access_token"])

        fake_storage.set_failure("generate_presigned_upload")

        with pytest.raises(ClientError):
            await client.post("/api/files/presign-upload", json=_avatar_request(), headers=headers)

    @pytest.mark.asyncio
    async def test_confirm_with_storage_error_returns_409(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        """``ClientError`` while heading the object should map to 409, not 500."""
        tokens = await auth.register_and_login(email="cse@test.com", username="cse")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]

        # Simulate the storage backend going down between presign and confirm.
        fake_storage.set_failure("get_object_size")

        r = await client.post(f"/api/files/{file_id}/confirm", headers=headers)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_download_url_storage_error_propagates(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
    ) -> None:
        """Same rationale as ``test_presign_propagates_storage_error``."""
        tokens = await auth.register_and_login(email="dse@test.com", username="dse")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=headers)

        fake_storage.set_failure("generate_presigned_download_url")
        with pytest.raises(ClientError):
            await client.get(f"/api/files/{file_id}/download-url", headers=headers)


class TestUncommonDBStates:
    """Manipulates ``file_objects`` directly to reach states no endpoint exposes."""

    @pytest.mark.asyncio
    async def test_confirm_on_deleted_file_returns_404(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
        db_session: AsyncSession,
    ) -> None:
        tokens = await auth.register_and_login(email="cdel@test.com", username="cdel")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]

        # Soft-delete directly in the DB to bypass the route's own checks.
        await db_session.execute(
            update(FileObject)
            .where(FileObject.id == file_id)
            .values(status=FileStatus.DELETED, deleted_at=datetime.now(UTC))
        )
        await db_session.commit()

        r = await client.post(f"/api/files/{file_id}/confirm", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_download_of_failed_file_returns_404(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
        db_session: AsyncSession,
    ) -> None:
        tokens = await auth.register_and_login(email="dlf@test.com", username="dlf")
        headers = auth.auth_headers(tokens["access_token"])

        presign = await client.post(
            "/api/files/presign-upload", json=_avatar_request(), headers=headers
        )
        file_id = presign.json()["data"]["file_id"]

        # Simulate the pending-cleanup job marking the row as FAILED.
        await db_session.execute(
            update(FileObject).where(FileObject.id == file_id).values(status=FileStatus.FAILED)
        )
        await db_session.commit()

        r = await client.get(f"/api/files/{file_id}/download-url", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_chat_download_with_malformed_object_key_returns_403(
        self,
        client: AsyncClient,
        auth: AuthActions,
        fake_storage: FakeObjectStorage,
        db_session: AsyncSession,
    ) -> None:
        """Exercises the defensive ``IndexError`` branch in the chat download path.

        A ``live_chat_message`` row whose ``object_key`` does not follow the
        ``live_chat/{conversation_id}/...`` convention cannot have its owning
        conversation recovered. The router must reject with 403 rather than
        crash, regardless of who is asking.
        """
        tokens = await auth.register_and_login(email="dlmkey@test.com", username="dlmkey")
        me = await auth.me(tokens["access_token"])
        headers = auth.auth_headers(tokens["access_token"])

        # Create a fully-uploaded chat-message file row with a corrupt key.
        conv = await _create_conversation(client_id=me.id, agent_id=uuid4())
        presign = await client.post(
            "/api/files/presign-upload",
            json=_chat_request(conv.id),
            headers=headers,
        )
        file_id = presign.json()["data"]["file_id"]
        fake_storage.mark_uploaded(fake_storage.last_presigned_upload_key())
        await client.post(f"/api/files/{file_id}/confirm", headers=headers)

        await db_session.execute(
            update(FileObject).where(FileObject.id == file_id).values(object_key="malformed")
        )
        await db_session.commit()

        r = await client.get(f"/api/files/{file_id}/download-url", headers=headers)
        assert r.status_code == 403
