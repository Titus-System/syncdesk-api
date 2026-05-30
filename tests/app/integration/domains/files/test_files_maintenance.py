"""Integration tests for the files-domain maintenance jobs.

Three job families are covered:

- ``FileService.sweep_pending``: probes the storage backend to decide
  whether stale ``pending`` rows should be promoted to ``uploaded`` or
  marked ``failed``.
- ``FileService.expire_chat_files``: soft-deletes chat-message uploads
  past the retention window. Avatars must never be touched.
- ``FileService.purge_deleted``: removes the storage object for rows that
  have been soft-deleted longer than the grace period and stamps
  ``purged_at`` for idempotency.

Tests run against a real Postgres (``db_session`` fixture) and a real MinIO
backend when reachable; storage-touching tests skip otherwise. Timestamps
are forged with raw UPDATEs so we can exercise the time-window logic
without sleeping in the test.
"""

import contextlib
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.storage import ObjectStorage
from app.domains.auth.models import User as UserModel
from app.domains.files.enums import FileContext, FileStatus
from app.domains.files.models import FileObject
from app.domains.files.repositories import FileObjectRepository
from app.domains.files.services import FileService
from app.infra.storage.s3_object_storage import S3ObjectStorage

settings = get_settings()


# ────────────────────────────────────────────────────────
# Helpers
# ────────────────────────────────────────────────────────


async def _minio_is_reachable() -> bool:
    try:
        async with httpx.AsyncClient(timeout=2.0) as c:
            res = await c.get(f"{settings.S3_PUBLIC_ENDPOINT_URL}/minio/health/live")
            return res.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


@pytest_asyncio.fixture
async def real_storage() -> AsyncGenerator[S3ObjectStorage, None]:
    """Return a real ``S3ObjectStorage`` or skip the test.

    Concrete type (rather than the ``ObjectStorage`` ABC) is required by
    helpers that reach into ``_client``/``_bucket`` to put bytes directly
    into MinIO, bypassing the presign flow.
    """
    if not await _minio_is_reachable():
        pytest.skip(
            f"MinIO not reachable at {settings.S3_PUBLIC_ENDPOINT_URL}; "
            "start the docker-compose stack to run these tests."
        )
    yield S3ObjectStorage()


async def _put_object(storage: S3ObjectStorage, object_key: str, body: bytes) -> None:
    """Place raw bytes into MinIO without going through the presign flow."""
    async with storage._client(storage._internal_endpoint) as client:  # noqa: SLF001
        await client.put_object(
            Bucket=storage._bucket,  # noqa: SLF001
            Key=object_key,
            Body=body,
        )


async def _delete_object_quietly(storage: S3ObjectStorage, object_key: str) -> None:
    """Best-effort cleanup to avoid leaking test objects."""
    with contextlib.suppress(Exception):
        await storage.delete_object(object_key)


async def _create_user(db: AsyncSession) -> UUID:
    user = UserModel(
        email=f"maintenance-{uuid4().hex[:8]}@test.com",
        password_hash="hashed",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user.id


async def _create_file(
    db: AsyncSession,
    *,
    user_id: UUID,
    status: FileStatus,
    context: FileContext = FileContext.LIVE_CHAT_MESSAGE,
    object_key: str | None = None,
    size_bytes: int = 64,
    created_at: datetime | None = None,
    uploaded_at: datetime | None = None,
    deleted_at: datetime | None = None,
    purged_at: datetime | None = None,
) -> FileObject:
    """Create a FileObject row with explicit timestamps for time-window tests.

    The repository sets ``created_at`` via the server default and stamps
    ``uploaded_at``/``deleted_at`` to ``now()`` inside its transitions; to
    test "older than X" branches we backdate via raw UPDATE after insert.
    """
    file_obj = FileObject(
        id=uuid4(),
        bucket=settings.S3_BUCKET_DEFAULT,
        object_key=object_key or f"{context.value}/test/{uuid4()}.bin",
        original_filename="probe.bin",
        content_type="application/octet-stream",
        size_bytes=size_bytes,
        context=context,
        status=status,
        uploaded_by_user_id=user_id,
        uploaded_at=uploaded_at,
        deleted_at=deleted_at,
        purged_at=purged_at,
    )
    db.add(file_obj)
    await db.commit()
    await db.refresh(file_obj)

    if created_at is not None:
        await db.execute(
            text("UPDATE file_objects SET created_at = :ts WHERE id = :id"),
            {"ts": created_at, "id": file_obj.id},
        )
        await db.commit()
        await db.refresh(file_obj)
    return file_obj


def _build_service(db: AsyncSession, storage: ObjectStorage) -> FileService:
    return FileService(repo=FileObjectRepository(db), object_storage=storage)


# ────────────────────────────────────────────────────────
# sweep_pending — real DB + real MinIO
# ────────────────────────────────────────────────────────


class TestSweepPending:
    @pytest.mark.asyncio
    async def test_pending_with_object_in_storage_is_recovered_to_uploaded(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        object_key = f"live_chat/test/{uuid4()}-recover.bin"
        await _put_object(real_storage, object_key, b"recovered-bytes")
        try:
            file_obj = await _create_file(
                db_session,
                user_id=user_id,
                status=FileStatus.PENDING,
                object_key=object_key,
                size_bytes=15,
                created_at=datetime.now(UTC) - timedelta(hours=1),
            )

            service = _build_service(db_session, real_storage)
            outcomes = await service.sweep_pending(max_age_minutes=15, batch_size=10)

            assert outcomes["recovered"] == 1
            assert outcomes["failed"] == 0
            refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
            assert refreshed is not None
            assert refreshed.status == FileStatus.UPLOADED
            assert refreshed.uploaded_at is not None
        finally:
            await _delete_object_quietly(real_storage, object_key)

    @pytest.mark.asyncio
    async def test_pending_without_object_in_storage_is_marked_failed(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        # No put_object call — storage has nothing under this key.
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.PENDING,
            object_key=f"live_chat/test/{uuid4()}-missing.bin",
            created_at=datetime.now(UTC) - timedelta(hours=1),
        )

        service = _build_service(db_session, real_storage)
        outcomes = await service.sweep_pending(max_age_minutes=15, batch_size=10)

        assert outcomes["recovered"] == 0
        assert outcomes["failed"] == 1
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.FAILED

    @pytest.mark.asyncio
    async def test_pending_too_recent_is_untouched(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        """A pending row younger than ``max_age_minutes`` is still inside the
        presign window; the worker must leave it alone."""
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.PENDING,
            # created_at left to server default = now()
        )

        service = _build_service(db_session, real_storage)
        outcomes = await service.sweep_pending(max_age_minutes=15, batch_size=10)

        assert outcomes == {"recovered": 0, "failed": 0, "error": 0}
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.PENDING

    @pytest.mark.asyncio
    async def test_already_uploaded_is_untouched(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.UPLOADED,
            uploaded_at=datetime.now(UTC) - timedelta(hours=2),
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )

        service = _build_service(db_session, real_storage)
        outcomes = await service.sweep_pending(max_age_minutes=15, batch_size=10)

        assert outcomes == {"recovered": 0, "failed": 0, "error": 0}
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.UPLOADED

    @pytest.mark.asyncio
    async def test_already_failed_is_untouched(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.FAILED,
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )

        service = _build_service(db_session, real_storage)
        outcomes = await service.sweep_pending(max_age_minutes=15, batch_size=10)

        assert outcomes == {"recovered": 0, "failed": 0, "error": 0}
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.FAILED

    @pytest.mark.asyncio
    async def test_already_deleted_is_untouched(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.DELETED,
            deleted_at=datetime.now(UTC) - timedelta(hours=1),
            created_at=datetime.now(UTC) - timedelta(hours=2),
        )

        service = _build_service(db_session, real_storage)
        outcomes = await service.sweep_pending(max_age_minutes=15, batch_size=10)

        assert outcomes == {"recovered": 0, "failed": 0, "error": 0}
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.DELETED

    @pytest.mark.asyncio
    async def test_batch_size_caps_number_processed(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        """``batch_size`` must cap each tick so the worker never starves."""
        user_id = await _create_user(db_session)
        for _ in range(5):
            await _create_file(
                db_session,
                user_id=user_id,
                status=FileStatus.PENDING,
                object_key=f"live_chat/test/{uuid4()}-bulk.bin",
                created_at=datetime.now(UTC) - timedelta(hours=1),
            )

        service = _build_service(db_session, real_storage)
        outcomes = await service.sweep_pending(max_age_minutes=15, batch_size=2)

        # Each pending has no object in storage, so every processed row
        # transitions to failed; batch_size=2 means at most two transitions.
        assert outcomes["failed"] == 2
        assert outcomes["recovered"] == 0


# ────────────────────────────────────────────────────────
# expire_chat_files — real DB only
# ────────────────────────────────────────────────────────


class _NullStorage(ObjectStorage):
    """Storage stub for tests that exercise pure DB logic.

    ``expire_chat_files`` never touches the backend; using a stub keeps the
    test isolated from MinIO availability and makes failures here strictly
    about the DB query.
    """

    async def generate_presigned_upload(
        self,
        object_key: str,
        content_type: str,
        max_size_bytes: int,
        expires_in_seconds: int,
    ) -> Any:
        raise AssertionError("retention worker must not call storage")

    async def generate_presigned_download_url(
        self, object_key: str, expires_in_seconds: int
    ) -> str:
        raise AssertionError("retention worker must not call storage")

    async def object_exists(self, object_key: str) -> bool:
        raise AssertionError("retention worker must not call storage")

    async def get_object_size(self, object_key: str) -> int | None:
        raise AssertionError("retention worker must not call storage")

    async def delete_object(self, object_key: str) -> None:
        raise AssertionError("retention worker must not call storage")


class TestExpireChatFiles:
    @pytest.mark.asyncio
    async def test_old_chat_uploaded_is_soft_deleted(
        self,
        db_session: AsyncSession,
    ) -> None:
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.UPLOADED,
            context=FileContext.LIVE_CHAT_MESSAGE,
            uploaded_at=datetime.now(UTC) - timedelta(days=200),
        )

        service = _build_service(db_session, _NullStorage())
        count = await service.expire_chat_files(retention_days=180, batch_size=10)

        assert count == 1
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.DELETED
        assert refreshed.deleted_at is not None

    @pytest.mark.asyncio
    async def test_recent_chat_uploaded_is_untouched(
        self,
        db_session: AsyncSession,
    ) -> None:
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.UPLOADED,
            context=FileContext.LIVE_CHAT_MESSAGE,
            uploaded_at=datetime.now(UTC) - timedelta(days=30),
        )

        service = _build_service(db_session, _NullStorage())
        count = await service.expire_chat_files(retention_days=180, batch_size=10)

        assert count == 0
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.UPLOADED

    @pytest.mark.asyncio
    async def test_old_avatar_is_never_touched(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Critical regression: avatar files must not be expired by retention.

        The plan reserves the 180-day retention window for chat media only;
        avatars are kept indefinitely and only removed by explicit user
        action.
        """
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.UPLOADED,
            context=FileContext.USER_AVATAR,
            object_key=f"avatars/users/{user_id}.png",
            uploaded_at=datetime.now(UTC) - timedelta(days=400),
        )

        service = _build_service(db_session, _NullStorage())
        count = await service.expire_chat_files(retention_days=180, batch_size=10)

        assert count == 0
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.UPLOADED

    @pytest.mark.asyncio
    async def test_already_deleted_chat_is_untouched(
        self,
        db_session: AsyncSession,
    ) -> None:
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.DELETED,
            context=FileContext.LIVE_CHAT_MESSAGE,
            uploaded_at=datetime.now(UTC) - timedelta(days=200),
            deleted_at=datetime.now(UTC) - timedelta(days=10),
        )

        service = _build_service(db_session, _NullStorage())
        count = await service.expire_chat_files(retention_days=180, batch_size=10)

        assert count == 0
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.DELETED

    @pytest.mark.asyncio
    async def test_pending_chat_is_untouched(
        self,
        db_session: AsyncSession,
    ) -> None:
        """Retention only sweeps ``uploaded`` rows; pending rows belong to
        the cleanup worker."""
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.PENDING,
            context=FileContext.LIVE_CHAT_MESSAGE,
            created_at=datetime.now(UTC) - timedelta(days=200),
        )

        service = _build_service(db_session, _NullStorage())
        count = await service.expire_chat_files(retention_days=180, batch_size=10)

        assert count == 0
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.PENDING

    @pytest.mark.asyncio
    async def test_batch_size_caps_number_processed(
        self,
        db_session: AsyncSession,
    ) -> None:
        user_id = await _create_user(db_session)
        for _ in range(4):
            await _create_file(
                db_session,
                user_id=user_id,
                status=FileStatus.UPLOADED,
                context=FileContext.LIVE_CHAT_MESSAGE,
                uploaded_at=datetime.now(UTC) - timedelta(days=300),
            )

        service = _build_service(db_session, _NullStorage())
        count = await service.expire_chat_files(retention_days=180, batch_size=2)

        assert count == 2


# ────────────────────────────────────────────────────────
# purge_deleted — real DB + real MinIO
# ────────────────────────────────────────────────────────


class TestPurgeDeleted:
    @pytest.mark.asyncio
    async def test_deleted_past_grace_with_object_is_purged(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        object_key = f"live_chat/test/{uuid4()}-purge.bin"
        await _put_object(real_storage, object_key, b"to-be-purged")

        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.DELETED,
            object_key=object_key,
            uploaded_at=datetime.now(UTC) - timedelta(days=10),
            deleted_at=datetime.now(UTC) - timedelta(days=8),
        )

        service = _build_service(db_session, real_storage)
        outcomes = await service.purge_deleted(grace_days=7, batch_size=10)

        assert outcomes["ok"] == 1
        assert outcomes["error"] == 0

        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.status == FileStatus.DELETED
        assert refreshed.purged_at is not None

        # Storage object must be gone.
        assert await real_storage.get_object_size(object_key) is None

    @pytest.mark.asyncio
    async def test_deleted_within_grace_is_untouched(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        object_key = f"live_chat/test/{uuid4()}-keep.bin"
        await _put_object(real_storage, object_key, b"still-in-grace")
        try:
            file_obj = await _create_file(
                db_session,
                user_id=user_id,
                status=FileStatus.DELETED,
                object_key=object_key,
                deleted_at=datetime.now(UTC) - timedelta(days=3),
            )

            service = _build_service(db_session, real_storage)
            outcomes = await service.purge_deleted(grace_days=7, batch_size=10)

            assert outcomes == {"ok": 0, "error": 0}
            refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
            assert refreshed is not None
            assert refreshed.purged_at is None
            # Storage object must still be there.
            assert await real_storage.get_object_size(object_key) is not None
        finally:
            await _delete_object_quietly(real_storage, object_key)

    @pytest.mark.asyncio
    async def test_already_purged_is_untouched(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        already_purged_at = datetime.now(UTC) - timedelta(days=1)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.DELETED,
            object_key=f"live_chat/test/{uuid4()}-already.bin",
            deleted_at=datetime.now(UTC) - timedelta(days=10),
            purged_at=already_purged_at,
        )

        service = _build_service(db_session, real_storage)
        outcomes = await service.purge_deleted(grace_days=7, batch_size=10)

        assert outcomes == {"ok": 0, "error": 0}
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        # ``purged_at`` must not be moved by a subsequent pass.
        assert refreshed.purged_at is not None
        assert abs(
            (refreshed.purged_at - already_purged_at).total_seconds()
        ) < 1.0

    @pytest.mark.asyncio
    async def test_object_already_absent_is_still_marked_purged(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        """If the storage object was already removed out-of-band, ``delete_object``
        is a no-op and we should still stamp ``purged_at`` so the row is not
        scanned again on every future tick."""
        user_id = await _create_user(db_session)
        file_obj = await _create_file(
            db_session,
            user_id=user_id,
            status=FileStatus.DELETED,
            object_key=f"live_chat/test/{uuid4()}-ghost.bin",  # never uploaded
            deleted_at=datetime.now(UTC) - timedelta(days=10),
        )

        service = _build_service(db_session, real_storage)
        outcomes = await service.purge_deleted(grace_days=7, batch_size=10)

        assert outcomes["ok"] == 1
        refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
        assert refreshed is not None
        assert refreshed.purged_at is not None

    @pytest.mark.asyncio
    async def test_uploaded_status_is_never_purged_even_if_old(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        """Only ``deleted`` rows are eligible; an ``uploaded`` row is alive
        even if ``deleted_at`` happens to be ancient (shouldn't be set, but
        guard against accidental data drift)."""
        user_id = await _create_user(db_session)
        object_key = f"live_chat/test/{uuid4()}-live.bin"
        await _put_object(real_storage, object_key, b"still-live")
        try:
            file_obj = await _create_file(
                db_session,
                user_id=user_id,
                status=FileStatus.UPLOADED,
                object_key=object_key,
                uploaded_at=datetime.now(UTC) - timedelta(days=30),
            )

            service = _build_service(db_session, real_storage)
            outcomes = await service.purge_deleted(grace_days=7, batch_size=10)

            assert outcomes == {"ok": 0, "error": 0}
            refreshed = await FileObjectRepository(db_session).get_by_id(file_obj.id)
            assert refreshed is not None
            assert refreshed.status == FileStatus.UPLOADED
            assert refreshed.purged_at is None
            assert await real_storage.get_object_size(object_key) is not None
        finally:
            await _delete_object_quietly(real_storage, object_key)

    @pytest.mark.asyncio
    async def test_batch_size_caps_number_processed(
        self,
        db_session: AsyncSession,
        real_storage: S3ObjectStorage,
    ) -> None:
        user_id = await _create_user(db_session)
        for _ in range(4):
            await _create_file(
                db_session,
                user_id=user_id,
                status=FileStatus.DELETED,
                object_key=f"live_chat/test/{uuid4()}-bulk-purge.bin",
                deleted_at=datetime.now(UTC) - timedelta(days=10),
            )

        service = _build_service(db_session, real_storage)
        outcomes = await service.purge_deleted(grace_days=7, batch_size=2)

        assert outcomes["ok"] == 2
        assert outcomes["error"] == 0
