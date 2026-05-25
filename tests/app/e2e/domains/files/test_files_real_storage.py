"""End-to-end test that exercises the full client -> API -> MinIO -> client path.

Unlike ``test_files_routes.py`` which substitutes ``FakeObjectStorage``, this
module keeps the production ``S3ObjectStorage`` wired in. It validates that:

1. The backend issues a presigned POST URL the browser can actually use.
2. The bytes uploaded via that URL reach the storage backend.
3. The confirm endpoint head-checks the real object.
4. The download URL retrieves the original bytes.
5. Delete soft-removes the row.

Skips automatically when MinIO is not reachable.
"""

from collections.abc import AsyncGenerator
from typing import Any

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
    """Same as the default ``app`` fixture but without overriding ``get_object_storage``.

    The real ``S3ObjectStorage`` is used, so requests through this app hit MinIO.
    """
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


class TestFullUploadFlowAgainstMinIO:
    @pytest.mark.asyncio
    async def test_avatar_roundtrip_through_api(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """Full client journey: presign -> POST MinIO -> confirm -> download."""
        payload = b"real-bytes-from-e2e-test-against-minio"
        tokens = await real_auth.register_and_login(
            email="rs_avatar@test.com", username="rs_avatar"
        )
        headers = real_auth.auth_headers(tokens["access_token"])

        # 1. Ask the API for a presigned upload URL.
        presign = await real_storage_client.post(
            "/api/files/presign-upload",
            json={
                "filename": "real.png",
                "content_type": "image/png",
                "size_bytes": len(payload),
                "context": "user_avatar",
            },
            headers=headers,
        )
        assert presign.status_code == 201, presign.text
        body = presign.json()["data"]
        file_id = body["file_id"]
        upload_url = body["upload_url"]
        fields = body["fields"]

        # 2. Upload the bytes directly to MinIO using the presigned POST.
        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.post(
                upload_url,
                data=fields,
                files={"file": ("real.png", payload, "image/png")},
            )
        assert res.status_code in (200, 201, 204), res.text

        # 3. Confirm. The API must head-check the real object and transition it.
        confirm = await real_storage_client.post(
            f"/api/files/{file_id}/confirm", headers=headers
        )
        assert confirm.status_code == 200, confirm.text
        assert confirm.json()["data"]["status"] == "uploaded"

        # 4. Request a download URL and fetch the bytes back.
        dl_req = await real_storage_client.get(
            f"/api/files/{file_id}/download-url", headers=headers
        )
        assert dl_req.status_code == 200, dl_req.text
        download_url = dl_req.json()["data"]["url"]

        async with httpx.AsyncClient(timeout=10.0) as http:
            dl = await http.get(download_url)
        assert dl.status_code == 200
        assert dl.content == payload

        # 5. Cleanup: soft-delete via API.
        delete = await real_storage_client.delete(
            f"/api/files/{file_id}", headers=headers
        )
        assert delete.status_code == 200
        assert delete.json()["data"]["status"] == "deleted"

    @pytest.mark.asyncio
    async def test_confirm_without_real_upload_returns_409(
        self,
        real_storage_client: AsyncClient,
        real_auth: AuthActions,
    ) -> None:
        """When the client never PUTs to MinIO, head_object misses and confirm 409s."""
        tokens = await real_auth.register_and_login(
            email="rs_noput@test.com", username="rs_noput"
        )
        headers = real_auth.auth_headers(tokens["access_token"])

        presign = await real_storage_client.post(
            "/api/files/presign-upload",
            json={
                "filename": "ghost.png",
                "content_type": "image/png",
                "size_bytes": 32,
                "context": "user_avatar",
            },
            headers=headers,
        )
        file_id = presign.json()["data"]["file_id"]

        # No POST to MinIO here. Confirm must return 409.
        confirm = await real_storage_client.post(
            f"/api/files/{file_id}/confirm", headers=headers
        )
        assert confirm.status_code == 409, confirm.text
