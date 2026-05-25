"""Integration tests for ``FileObjectRepository`` against a real Postgres."""

from datetime import datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.auth.models import User as UserModel
from app.domains.files.enums import FileContext, FileStatus
from app.domains.files.models import FileObject
from app.domains.files.repositories import FileObjectRepository


def _make_file_object(
    user_id: UUID,
    *,
    object_key: str | None = None,
    context: FileContext = FileContext.LIVE_CHAT_MESSAGE,
    status: FileStatus = FileStatus.PENDING,
) -> FileObject:
    return FileObject(
        id=uuid4(),
        bucket="syncdesk-files",
        object_key=object_key or f"live_chat/test/{uuid4()}-probe.txt",
        original_filename="probe.txt",
        content_type="text/plain",
        size_bytes=128,
        context=context,
        status=status,
        uploaded_by_user_id=user_id,
    )


class TestFileObjectRepository:
    @pytest.fixture
    def repo(self, db_session: AsyncSession) -> FileObjectRepository:
        return FileObjectRepository(db_session)

    @pytest.fixture
    async def user_id(self, db_session: AsyncSession) -> UUID:
        user = UserModel(
            email=f"file-{uuid4().hex[:8]}@test.com",
            password_hash="hashed",
        )
        db_session.add(user)
        await db_session.commit()
        await db_session.refresh(user)
        return user.id

    @pytest.mark.asyncio
    async def test_create_persists_with_defaults(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        file_obj = _make_file_object(user_id)
        created = await repo.create(file_obj)

        assert created.id == file_obj.id
        assert created.status == FileStatus.PENDING
        assert created.context == FileContext.LIVE_CHAT_MESSAGE
        assert created.uploaded_at is None
        assert created.deleted_at is None
        assert isinstance(created.created_at, datetime)

    @pytest.mark.asyncio
    async def test_get_by_id_returns_existing(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        fetched = await repo.get_by_id(created.id)
        assert fetched is not None
        assert fetched.id == created.id

    @pytest.mark.asyncio
    async def test_get_by_id_missing_returns_none(
        self,
        repo: FileObjectRepository,
    ) -> None:
        assert await repo.get_by_id(uuid4()) is None

    @pytest.mark.asyncio
    async def test_mark_uploaded_transitions_pending(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))

        updated = await repo.mark_uploaded(created.id)
        assert updated is not None
        assert updated.status == FileStatus.UPLOADED
        assert updated.uploaded_at is not None

    @pytest.mark.asyncio
    async def test_mark_uploaded_is_no_op_when_already_uploaded(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        first = await repo.mark_uploaded(created.id)
        assert first is not None

        second = await repo.mark_uploaded(created.id)
        assert second is None  # WHERE status == PENDING no longer matches

    @pytest.mark.asyncio
    async def test_mark_uploaded_missing_returns_none(
        self,
        repo: FileObjectRepository,
    ) -> None:
        assert await repo.mark_uploaded(uuid4()) is None

    @pytest.mark.asyncio
    async def test_mark_deleted_from_pending(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        deleted = await repo.mark_deleted(created.id)
        assert deleted is not None
        assert deleted.status == FileStatus.DELETED
        assert deleted.deleted_at is not None

    @pytest.mark.asyncio
    async def test_mark_deleted_from_uploaded(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        await repo.mark_uploaded(created.id)

        deleted = await repo.mark_deleted(created.id)
        assert deleted is not None
        assert deleted.status == FileStatus.DELETED

    @pytest.mark.asyncio
    async def test_mark_deleted_twice_is_no_op(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        first = await repo.mark_deleted(created.id)
        assert first is not None

        second = await repo.mark_deleted(created.id)
        assert second is None  # WHERE status != DELETED no longer matches

    @pytest.mark.asyncio
    async def test_object_key_is_unique(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        shared_key = f"live_chat/test/{uuid4()}-dup.txt"
        await repo.create(_make_file_object(user_id, object_key=shared_key))

        with pytest.raises(Exception):  # IntegrityError wrapped by SQLAlchemy
            await repo.create(_make_file_object(user_id, object_key=shared_key))

    @pytest.mark.asyncio
    async def test_supports_all_contexts(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        for context in FileContext:
            obj = _make_file_object(
                user_id,
                context=context,
                object_key=f"{context.value}/test/{uuid4()}.bin",
            )
            created = await repo.create(obj)
            assert created.context == context

    @pytest.mark.asyncio
    async def test_mark_uploaded_on_deleted_returns_none(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        await repo.mark_deleted(created.id)

        assert await repo.mark_uploaded(created.id) is None

    @pytest.mark.asyncio
    async def test_mark_uploaded_on_failed_returns_none(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(
            _make_file_object(user_id, status=FileStatus.FAILED),
        )
        assert await repo.mark_uploaded(created.id) is None

    @pytest.mark.asyncio
    async def test_mark_deleted_missing_returns_none(
        self,
        repo: FileObjectRepository,
    ) -> None:
        assert await repo.mark_deleted(uuid4()) is None

    @pytest.mark.asyncio
    async def test_create_with_nonexistent_user_id_violates_fk(
        self,
        repo: FileObjectRepository,
    ) -> None:
        orphan = _make_file_object(uuid4())  # user id never inserted
        with pytest.raises(IntegrityError):
            await repo.create(orphan)

    @pytest.mark.asyncio
    async def test_default_status_is_pending(
        self,
        db_session: AsyncSession,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        # Construct without explicit status to exercise the column default.
        file_obj = FileObject(
            id=uuid4(),
            bucket="syncdesk-files",
            object_key=f"live_chat/test/{uuid4()}-default.txt",
            original_filename="default.txt",
            content_type="text/plain",
            size_bytes=64,
            context=FileContext.LIVE_CHAT_MESSAGE,
            uploaded_by_user_id=user_id,
        )
        created = await repo.create(file_obj)
        assert created.status == FileStatus.PENDING

    @pytest.mark.asyncio
    async def test_created_at_is_timezone_aware(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        assert created.created_at is not None
        assert created.created_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_uploaded_at_is_timezone_aware(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        updated = await repo.mark_uploaded(created.id)
        assert updated is not None
        assert updated.uploaded_at is not None
        assert updated.uploaded_at.tzinfo is not None

    @pytest.mark.asyncio
    async def test_deleted_at_is_timezone_aware(
        self,
        repo: FileObjectRepository,
        user_id: UUID,
    ) -> None:
        created = await repo.create(_make_file_object(user_id))
        deleted = await repo.mark_deleted(created.id)
        assert deleted is not None
        assert deleted.deleted_at is not None
        assert deleted.deleted_at.tzinfo is not None
