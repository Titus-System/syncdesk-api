"""End-to-end avatar flow against real MinIO, real Postgres, real ASGI.

PR4 wires PUT /users/me/avatar and DELETE /users/me/avatar so a user
can pin a confirmed FileObject (context=user_avatar) onto their
profile and rotate or clear it later.

Happy paths drive the production upload pipeline (presign → POST
MinIO → confirm → PUT avatar → GET download URL → byte-compare) so a
regression in any layer (validation, storage adapter, FK, soft-delete)
surfaces here. Error branches live with direct FileObject inserts so
the slow MinIO round-trip is reserved for paths that actually depend
on it.
"""

from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.dependencies import get_email_service
from app.core.event_dispatcher import get_event_dispatcher
from app.db.mongo.dependencies import get_mongo_session
from app.db.postgres.dependencies import get_postgres_session
from app.domains.files.enums import FileContext, FileStatus
from app.domains.files.models import FileObject
from app.domains.files.repositories import FileObjectRepository
from app.main import create_app
from tests.app.e2e.conftest import AuthActions, FakeEmailStrategy

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


# ── Helpers ──────────────────────────────────────────────────────────


async def _upload_avatar_via_api(
    client: AsyncClient,
    token: str,
    payload: bytes = b"\x89PNG\r\n\x1a\nrealbytes",
    *,
    filename: str = "avatar.png",
    content_type: str = "image/png",
) -> str:
    """Drive the full presign → POST MinIO → confirm flow for an avatar."""
    headers = {"Authorization": f"Bearer {token}"}
    presign = await client.post(
        "/api/files/presign-upload",
        json={
            "filename": filename,
            "content_type": content_type,
            "size_bytes": len(payload),
            "context": "user_avatar",
            "context_ref": {},
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


async def _insert_file_directly(
    db_session: AsyncSession,
    uploader_id: UUID,
    *,
    context: FileContext = FileContext.USER_AVATAR,
    status: FileStatus = FileStatus.UPLOADED,
    object_key: str | None = None,
) -> UUID:
    """Insert a FileObject row bypassing the API. Used for error-branch
    setups that don't require an actual blob in MinIO."""
    repo = FileObjectRepository(db_session)
    file_id = uuid4()
    if object_key is None:
        if context == FileContext.USER_AVATAR:
            object_key = f"avatars/users/{uploader_id}-{file_id}.bin"
        else:
            object_key = f"live_chat/{uuid4()}/{file_id}-probe.bin"
    await repo.create(
        FileObject(
            id=file_id,
            bucket="syncdesk-files",
            object_key=object_key,
            original_filename="probe.bin",
            content_type="image/png",
            size_bytes=4,
            context=context,
            status=status,
            uploaded_by_user_id=uploader_id,
        )
    )
    return file_id


# ── Tests ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
class TestUserAvatarHappyPathsRealMinIO:
    async def test_set_avatar_makes_it_visible_on_me_and_downloadable_intact(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Full flow: presign + upload + confirm + PUT /users/me/avatar.

        Asserts that:
        - the response carries avatar_file_id
        - GET /auth/me also returns the new avatar_file_id
        - the bytes are downloadable via the file download URL and match
          exactly what was uploaded.
        """
        payload = b"avatar-real-bytes-for-roundtrip-verification"
        tokens = await real_auth.register_and_login_admin(
            email="avatar_ok@test.com", username="avatar_ok"
        )
        token = tokens["access_token"]

        file_id = await _upload_avatar_via_api(
            real_storage_client, token, payload
        )

        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": file_id},
            headers=real_auth.auth_headers(token),
        )
        assert put.status_code == 200, put.text
        body = put.json()["data"]
        assert body["avatar_file_id"] == file_id

        me = await real_storage_client.get(
            "/api/auth/me", headers=real_auth.auth_headers(token)
        )
        assert me.status_code == 200, me.text
        assert me.json()["data"]["avatar_file_id"] == file_id

        dl = await real_storage_client.get(
            f"/api/files/{file_id}/download-url",
            headers=real_auth.auth_headers(token),
        )
        assert dl.status_code == 200
        download_url = dl.json()["data"]["url"]

        async with httpx.AsyncClient(timeout=10.0) as http:
            blob = await http.get(download_url)
        assert blob.status_code == 200
        assert blob.content == payload

    async def test_rotate_avatar_swaps_bytes_and_soft_deletes_previous(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Full byte-level verification of avatar rotation.

        After uploading a first image, setting it, uploading a different
        second image, and rotating to it: the new avatar's download must
        return the *second* image bytes (not the first), proving the
        rotation actually swapped content end-to-end and not just the
        metadata pointer. The previous file must be inaccessible.
        """
        payload_first = b"FIRST-avatar-image-bytes-alpha-version"
        payload_second = b"SECOND-different-avatar-bytes-beta-rev"
        assert payload_first != payload_second  # sanity: distinct inputs

        tokens = await real_auth.register_and_login_admin(
            email="avatar_rot@test.com", username="avatar_rot"
        )
        token = tokens["access_token"]
        headers = real_auth.auth_headers(token)

        # First avatar.
        first_id = await _upload_avatar_via_api(
            real_storage_client, token, payload_first
        )
        first_put = await real_storage_client.put(
            "/api/users/me/avatar", json={"file_id": first_id}, headers=headers
        )
        assert first_put.status_code == 200

        # Confirm the first avatar serves its original bytes before the rotation.
        first_dl = await real_storage_client.get(
            f"/api/files/{first_id}/download-url", headers=headers
        )
        assert first_dl.status_code == 200
        async with httpx.AsyncClient(timeout=10.0) as http:
            first_blob = await http.get(first_dl.json()["data"]["url"])
        assert first_blob.status_code == 200
        assert first_blob.content == payload_first

        # Rotate to the second avatar.
        second_id = await _upload_avatar_via_api(
            real_storage_client, token, payload_second
        )
        second_put = await real_storage_client.put(
            "/api/users/me/avatar", json={"file_id": second_id}, headers=headers
        )
        assert second_put.status_code == 200, second_put.text
        assert second_put.json()["data"]["avatar_file_id"] == second_id

        # The previous file is gone (soft-deleted).
        old_dl = await real_storage_client.get(
            f"/api/files/{first_id}/download-url", headers=headers
        )
        assert old_dl.status_code == 404

        # The new file is downloadable AND returns the second image's
        # bytes — proves rotation actually swapped content, not just the
        # file_id pointer.
        new_dl = await real_storage_client.get(
            f"/api/files/{second_id}/download-url", headers=headers
        )
        assert new_dl.status_code == 200
        async with httpx.AsyncClient(timeout=10.0) as http:
            second_blob = await http.get(new_dl.json()["data"]["url"])
        assert second_blob.status_code == 200
        assert second_blob.content == payload_second
        assert second_blob.content != payload_first

        # And the consolidated read endpoint reports the second avatar
        # consistently — the dedicated GET should agree with the rotation.
        get_me = await real_storage_client.get(
            "/api/users/me/avatar", headers=headers
        )
        assert get_me.status_code == 200
        assert get_me.json()["data"]["file_id"] == second_id
        async with httpx.AsyncClient(timeout=10.0) as http:
            me_blob = await http.get(get_me.json()["data"]["download_url"])
        assert me_blob.status_code == 200
        assert me_blob.content == payload_second

    async def test_delete_avatar_clears_field_and_soft_deletes_previous(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        tokens = await real_auth.register_and_login_admin(
            email="avatar_del@test.com", username="avatar_del"
        )
        token = tokens["access_token"]
        headers = real_auth.auth_headers(token)

        file_id = await _upload_avatar_via_api(real_storage_client, token)
        await real_storage_client.put(
            "/api/users/me/avatar", json={"file_id": file_id}, headers=headers
        )

        delete = await real_storage_client.delete(
            "/api/users/me/avatar", headers=headers
        )
        assert delete.status_code == 200, delete.text
        assert delete.json()["data"]["avatar_file_id"] is None

        # File is gone (soft-delete).
        dl = await real_storage_client.get(
            f"/api/files/{file_id}/download-url", headers=headers
        )
        assert dl.status_code == 404

    async def test_delete_avatar_is_idempotent_when_user_had_none(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """A user without any avatar should still get 200 from DELETE."""
        tokens = await real_auth.register_and_login_admin(
            email="avatar_none@test.com", username="avatar_none"
        )
        token = tokens["access_token"]
        headers = real_auth.auth_headers(token)

        delete = await real_storage_client.delete(
            "/api/users/me/avatar", headers=headers
        )
        assert delete.status_code == 200
        assert delete.json()["data"]["avatar_file_id"] is None

    async def test_put_with_same_file_id_is_idempotent_and_does_not_soft_delete(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Setting the same file_id twice must not soft-delete the file.

        The router guards against this with ``previous_file_id !=
        dto.file_id`` before calling ``file_service.delete``. If that
        guard is ever removed, the second PUT would delete the file
        right after pointing the user at it — exactly the bug this
        test catches.
        """
        tokens = await real_auth.register_and_login_admin(
            email="avatar_idem@test.com", username="avatar_idem"
        )
        token = tokens["access_token"]
        headers = real_auth.auth_headers(token)

        file_id = await _upload_avatar_via_api(real_storage_client, token)

        first = await real_storage_client.put(
            "/api/users/me/avatar", json={"file_id": file_id}, headers=headers
        )
        assert first.status_code == 200, first.text

        second = await real_storage_client.put(
            "/api/users/me/avatar", json={"file_id": file_id}, headers=headers
        )
        assert second.status_code == 200, second.text
        assert second.json()["data"]["avatar_file_id"] == file_id

        # The file MUST still be downloadable — i.e., its status is
        # still 'uploaded', not 'deleted' from a self-inflicted delete.
        dl = await real_storage_client.get(
            f"/api/files/{file_id}/download-url", headers=headers
        )
        assert dl.status_code == 200, (
            "Idempotent PUT soft-deleted the file it just claimed — "
            "the previous_file_id != dto.file_id guard is broken"
        )

    async def test_auth_me_returns_avatar_file_id_null_before_any_set(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Read-side contract: ``GET /auth/me`` returns avatar_file_id=null
        for a freshly registered user who never set an avatar."""
        tokens = await real_auth.register_and_login_admin(
            email="avatar_me_null@test.com", username="avatar_me_null"
        )
        token = tokens["access_token"]

        me = await real_storage_client.get(
            "/api/auth/me", headers=real_auth.auth_headers(token)
        )
        assert me.status_code == 200
        body = me.json()["data"]
        assert "avatar_file_id" in body
        assert body["avatar_file_id"] is None

    async def test_auth_me_returns_null_avatar_after_delete(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """After DELETE the field must read back as null on /auth/me."""
        tokens = await real_auth.register_and_login_admin(
            email="avatar_me_del@test.com", username="avatar_me_del"
        )
        token = tokens["access_token"]
        headers = real_auth.auth_headers(token)

        file_id = await _upload_avatar_via_api(real_storage_client, token)
        await real_storage_client.put(
            "/api/users/me/avatar", json={"file_id": file_id}, headers=headers
        )
        await real_storage_client.delete(
            "/api/users/me/avatar", headers=headers
        )

        me = await real_storage_client.get("/api/auth/me", headers=headers)
        assert me.status_code == 200
        assert me.json()["data"]["avatar_file_id"] is None

    async def test_get_my_avatar_returns_all_nulls_when_user_has_no_avatar(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """``GET /users/me/avatar`` on a user without avatar returns all
        nullable fields as ``None`` so the frontend can branch on a single
        check."""
        tokens = await real_auth.register_and_login_admin(
            email="avatar_get_empty@test.com", username="avatar_get_empty"
        )
        token = tokens["access_token"]

        r = await real_storage_client.get(
            "/api/users/me/avatar", headers=real_auth.auth_headers(token)
        )
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body == {
            "file_id": None,
            "download_url": None,
            "expires_at": None,
        }

    async def test_get_my_avatar_returns_file_id_and_working_download_url(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """One-shot read of the avatar: file_id + presigned URL that
        actually downloads the original bytes."""
        payload = b"avatar-via-get-endpoint-bytes"
        tokens = await real_auth.register_and_login_admin(
            email="avatar_get@test.com", username="avatar_get"
        )
        token = tokens["access_token"]
        headers = real_auth.auth_headers(token)

        file_id = await _upload_avatar_via_api(
            real_storage_client, token, payload
        )
        put = await real_storage_client.put(
            "/api/users/me/avatar", json={"file_id": file_id}, headers=headers
        )
        assert put.status_code == 200, put.text

        r = await real_storage_client.get(
            "/api/users/me/avatar", headers=headers
        )
        assert r.status_code == 200, r.text
        body = r.json()["data"]
        assert body["file_id"] == file_id
        assert body["download_url"] is not None
        assert body["expires_at"] is not None

        async with httpx.AsyncClient(timeout=10.0) as http:
            blob = await http.get(body["download_url"])
        assert blob.status_code == 200
        assert blob.content == payload


@pytest.mark.asyncio
class TestUserAvatarErrorBranches:
    """All paths the set-avatar validator can reject. Real Postgres,
    direct FileObject inserts — these exercise pure cross-domain
    validation rules that never touch MinIO."""

    async def test_set_avatar_with_unknown_file_id_returns_404(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        tokens = await real_auth.register_and_login_admin(
            email="avatar_unk@test.com", username="avatar_unk"
        )
        token = tokens["access_token"]
        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": str(uuid4())},
            headers=real_auth.auth_headers(token),
        )
        assert put.status_code == 404
        assert "does not reference a known file" in put.json()["detail"]

    async def test_set_avatar_with_file_from_another_user_returns_403(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        sender_tokens = await real_auth.register_and_login_admin(
            email="avatar_me@test.com", username="avatar_me"
        )
        other_tokens = await real_auth.register_and_login_admin(
            email="avatar_other@test.com", username="avatar_other"
        )
        other = await real_auth.me(other_tokens["access_token"])

        foreign_file_id = await _insert_file_directly(db_session, other.id)

        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": str(foreign_file_id)},
            headers=real_auth.auth_headers(sender_tokens["access_token"]),
        )
        assert put.status_code == 403
        assert "not uploaded by the current user" in put.json()["detail"]

    async def test_set_avatar_with_chat_context_file_returns_400(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        tokens = await real_auth.register_and_login_admin(
            email="avatar_ctx@test.com", username="avatar_ctx"
        )
        user = await real_auth.me(tokens["access_token"])
        wrong_ctx_id = await _insert_file_directly(
            db_session, user.id, context=FileContext.LIVE_CHAT_MESSAGE
        )

        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": str(wrong_ctx_id)},
            headers=real_auth.auth_headers(tokens["access_token"]),
        )
        assert put.status_code == 400
        assert "context 'live_chat_message'" in put.json()["detail"]

    async def test_set_avatar_with_pending_file_returns_409(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        tokens = await real_auth.register_and_login_admin(
            email="avatar_pend@test.com", username="avatar_pend"
        )
        user = await real_auth.me(tokens["access_token"])
        pending_id = await _insert_file_directly(
            db_session, user.id, status=FileStatus.PENDING
        )

        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": str(pending_id)},
            headers=real_auth.auth_headers(tokens["access_token"]),
        )
        assert put.status_code == 409
        assert "status 'pending'" in put.json()["detail"]

    async def test_set_avatar_with_deleted_file_returns_409(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        tokens = await real_auth.register_and_login_admin(
            email="avatar_del2@test.com", username="avatar_del2"
        )
        user = await real_auth.me(tokens["access_token"])
        deleted_id = await _insert_file_directly(
            db_session, user.id, status=FileStatus.DELETED
        )

        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": str(deleted_id)},
            headers=real_auth.auth_headers(tokens["access_token"]),
        )
        assert put.status_code == 409
        assert "status 'deleted'" in put.json()["detail"]

    async def test_set_avatar_with_failed_file_returns_409(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
        db_session: AsyncSession,
    ) -> None:
        tokens = await real_auth.register_and_login_admin(
            email="avatar_fail@test.com", username="avatar_fail"
        )
        user = await real_auth.me(tokens["access_token"])
        failed_id = await _insert_file_directly(
            db_session, user.id, status=FileStatus.FAILED
        )

        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": str(failed_id)},
            headers=real_auth.auth_headers(tokens["access_token"]),
        )
        assert put.status_code == 409
        assert "status 'failed'" in put.json()["detail"]

    async def test_set_avatar_without_auth_returns_403(
        self,
        real_storage_client: AsyncClient,
    ) -> None:
        """FastAPI HTTPBearer returns 403 when the token is missing."""
        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": str(uuid4())},
        )
        assert put.status_code == 403

    async def test_set_avatar_with_missing_file_id_returns_422(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Pydantic-level guard: file_id is required by SetUserAvatarDTO."""
        tokens = await real_auth.register_and_login_admin(
            email="avatar_no_field@test.com", username="avatar_no_field"
        )
        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={},
            headers=real_auth.auth_headers(tokens["access_token"]),
        )
        assert put.status_code == 422

    async def test_set_avatar_with_malformed_uuid_returns_422(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Pydantic rejects non-UUID values for file_id before the route runs."""
        tokens = await real_auth.register_and_login_admin(
            email="avatar_bad_uuid@test.com", username="avatar_bad_uuid"
        )
        put = await real_storage_client.put(
            "/api/users/me/avatar",
            json={"file_id": "not-a-uuid"},
            headers=real_auth.auth_headers(tokens["access_token"]),
        )
        assert put.status_code == 422
