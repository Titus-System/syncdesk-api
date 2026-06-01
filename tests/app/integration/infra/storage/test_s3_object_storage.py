"""Integration tests for ``S3ObjectStorage`` exercising a real MinIO backend.

These tests skip automatically when the MinIO endpoint is unreachable. When
the local docker-compose stack is up they run end-to-end: presign a POST URL,
upload bytes through it via plain HTTP, head/delete the object, etc.
"""

from collections.abc import AsyncGenerator
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from botocore.exceptions import ClientError

from app.core.config import get_settings
from app.infra.storage.s3_object_storage import S3ObjectStorage

settings = get_settings()


async def _minio_is_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{settings.S3_PUBLIC_ENDPOINT_URL}/minio/health/live")
            return res.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


@pytest_asyncio.fixture(scope="module", autouse=True)
async def _require_minio() -> AsyncGenerator[None, None]:
    if not await _minio_is_reachable():
        pytest.skip(
            f"MinIO not reachable at {settings.S3_PUBLIC_ENDPOINT_URL}; "
            "start the docker-compose stack to run these tests.",
            allow_module_level=True,
        )
    yield


@pytest.fixture
def storage() -> S3ObjectStorage:
    return S3ObjectStorage()


@pytest.fixture
def object_key() -> str:
    return f"__tests__/{uuid4()}.txt"


class TestS3ObjectStorage:
    @pytest.mark.asyncio
    async def test_generate_presigned_upload_returns_post_payload(
        self, storage: S3ObjectStorage, object_key: str
    ) -> None:
        presigned = await storage.generate_presigned_upload(
            object_key=object_key,
            content_type="text/plain",
            max_size_bytes=1024,
            expires_in_seconds=60,
        )
        assert presigned.method == "POST"
        assert presigned.url.startswith(settings.S3_PUBLIC_ENDPOINT_URL)
        # Required by S3 multipart POST policy
        assert presigned.fields.get("key") == object_key
        assert presigned.fields.get("Content-Type") == "text/plain"
        assert "policy" in presigned.fields
        assert "x-amz-signature" in presigned.fields

    @pytest.mark.asyncio
    async def test_object_exists_returns_false_for_missing(
        self, storage: S3ObjectStorage, object_key: str
    ) -> None:
        assert await storage.object_exists(object_key) is False

    @pytest.mark.asyncio
    async def test_get_object_size_returns_none_for_missing(
        self, storage: S3ObjectStorage, object_key: str
    ) -> None:
        assert await storage.get_object_size(object_key) is None

    @pytest.mark.asyncio
    async def test_delete_object_on_missing_is_noop(
        self, storage: S3ObjectStorage, object_key: str
    ) -> None:
        # MinIO returns 204 for delete of missing key — should not raise.
        await storage.delete_object(object_key)

    @pytest.mark.asyncio
    async def test_full_upload_download_roundtrip(
        self, storage: S3ObjectStorage, object_key: str
    ) -> None:
        payload = b"hello-from-integration-test"
        presigned = await storage.generate_presigned_upload(
            object_key=object_key,
            content_type="text/plain",
            max_size_bytes=len(payload) * 2,
            expires_in_seconds=120,
        )

        # 1. Upload through the presigned POST URL (real S3 multipart form).
        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.post(
                presigned.url,
                data=presigned.fields,
                files={"file": (object_key, payload, "text/plain")},
            )
        assert res.status_code in (200, 201, 204), res.text

        # 2. The object now exists and reports the correct size.
        assert await storage.object_exists(object_key) is True
        assert await storage.get_object_size(object_key) == len(payload)

        # 3. Presigned download URL retrieves the original bytes.
        download_url = await storage.generate_presigned_download_url(
            object_key=object_key, expires_in_seconds=60
        )
        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.get(download_url)
        assert res.status_code == 200
        assert res.content == payload

        # 4. Delete cleans up the object.
        await storage.delete_object(object_key)
        assert await storage.object_exists(object_key) is False

    @pytest.mark.asyncio
    async def test_presigned_upload_enforces_max_size(
        self, storage: S3ObjectStorage, object_key: str
    ) -> None:
        max_size = 16
        presigned = await storage.generate_presigned_upload(
            object_key=object_key,
            content_type="text/plain",
            max_size_bytes=max_size,
            expires_in_seconds=120,
        )

        oversize_payload = b"x" * (max_size + 100)
        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.post(
                presigned.url,
                data=presigned.fields,
                files={"file": (object_key, oversize_payload, "text/plain")},
            )
        # MinIO rejects with 400 EntityTooLarge when the policy is violated.
        assert res.status_code == 400, res.text
        assert await storage.object_exists(object_key) is False

    @pytest.mark.asyncio
    async def test_presigned_upload_enforces_content_type(
        self, storage: S3ObjectStorage, object_key: str
    ) -> None:
        presigned = await storage.generate_presigned_upload(
            object_key=object_key,
            content_type="image/png",
            max_size_bytes=1024,
            expires_in_seconds=120,
        )
        # Client tries to upload under a different content type → policy violation.
        tampered_fields = {**presigned.fields, "Content-Type": "text/plain"}
        async with httpx.AsyncClient(timeout=10.0) as http:
            res = await http.post(
                presigned.url,
                data=tampered_fields,
                files={"file": (object_key, b"abc", "text/plain")},
            )
        assert res.status_code == 403, res.text
        assert await storage.object_exists(object_key) is False

    @pytest.mark.asyncio
    async def test_object_exists_propagates_unexpected_client_error(
        self, storage: S3ObjectStorage
    ) -> None:
        """A NoSuchKey-class error is swallowed; other errors must bubble up."""
        # Bucket name containing uppercase letters is invalid → MinIO returns
        # an error code that is NOT in our 404-equivalent set.
        bad_storage = S3ObjectStorage()
        bad_storage._bucket = "INVALID_BUCKET_NAME"  # noqa: SLF001 — test-only override
        with pytest.raises(ClientError):
            await bad_storage.object_exists("anything")
