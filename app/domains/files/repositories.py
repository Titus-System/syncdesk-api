from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .enums import FileContext, FileStatus
from .models import FileObject


class FileObjectRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, file_obj: FileObject) -> FileObject:
        self.db.add(file_obj)
        await self.db.commit()
        await self.db.refresh(file_obj)
        return file_obj

    async def get_by_id(self, file_id: UUID) -> FileObject | None:
        result = await self.db.execute(select(FileObject).where(FileObject.id == file_id))
        return result.scalar_one_or_none()

    async def mark_uploaded(self, file_id: UUID) -> FileObject | None:
        stmt = (
            update(FileObject)
            .where(FileObject.id == file_id, FileObject.status == FileStatus.PENDING)
            .values(status=FileStatus.UPLOADED, uploaded_at=datetime.now(UTC))
            .returning(FileObject)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.scalar_one_or_none()

    async def mark_deleted(self, file_id: UUID) -> FileObject | None:
        stmt = (
            update(FileObject)
            .where(FileObject.id == file_id, FileObject.status != FileStatus.DELETED)
            .values(status=FileStatus.DELETED, deleted_at=datetime.now(UTC))
            .returning(FileObject)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.scalar_one_or_none()

    async def mark_failed(self, file_id: UUID) -> FileObject | None:
        """Transition a still-``pending`` row to ``failed``.

        Used by the pending-cleanup worker when the object never landed in
        the storage backend. Guarded by ``status == PENDING`` so re-runs and
        races with a late confirm don't overwrite a successful upload.
        """
        stmt = (
            update(FileObject)
            .where(FileObject.id == file_id, FileObject.status == FileStatus.PENDING)
            .values(status=FileStatus.FAILED)
            .returning(FileObject)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.scalar_one_or_none()

    async def mark_purged(self, file_id: UUID, purged_at: datetime) -> FileObject | None:
        """Stamp ``purged_at`` after the storage object has been removed.

        Guarded by ``status == DELETED`` and ``purged_at IS NULL`` so the
        worker is idempotent and never undoes/repeats a previous purge.
        """
        stmt = (
            update(FileObject)
            .where(
                FileObject.id == file_id,
                FileObject.status == FileStatus.DELETED,
                FileObject.purged_at.is_(None),
            )
            .values(purged_at=purged_at)
            .returning(FileObject)
        )
        result = await self.db.execute(stmt)
        await self.db.commit()
        return result.scalar_one_or_none()

    async def find_stale_pending(
        self, older_than: datetime, *, limit: int
    ) -> list[FileObject]:
        """Return ``pending`` rows created before ``older_than``.

        Ordered by ``created_at`` ascending so the oldest are processed first
        and a tight batch limit keeps each tick bounded.
        """
        stmt = (
            select(FileObject)
            .where(
                FileObject.status == FileStatus.PENDING,
                FileObject.created_at < older_than,
            )
            .order_by(FileObject.created_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_chat_files_to_expire(
        self, uploaded_before: datetime, *, limit: int
    ) -> list[FileObject]:
        """Return ``uploaded`` chat-message files older than ``uploaded_before``.

        Avatars are deliberately excluded by the ``context`` filter.
        """
        stmt = (
            select(FileObject)
            .where(
                FileObject.status == FileStatus.UPLOADED,
                FileObject.context == FileContext.LIVE_CHAT_MESSAGE,
                FileObject.uploaded_at < uploaded_before,
            )
            .order_by(FileObject.uploaded_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def find_files_to_purge(
        self, deleted_before: datetime, *, limit: int
    ) -> list[FileObject]:
        """Return ``deleted`` rows still holding a storage object.

        ``purged_at IS NULL`` distinguishes rows that still need physical
        removal from ones already reconciled by an earlier tick.
        """
        stmt = (
            select(FileObject)
            .where(
                FileObject.status == FileStatus.DELETED,
                FileObject.deleted_at < deleted_before,
                FileObject.purged_at.is_(None),
            )
            .order_by(FileObject.deleted_at.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())
