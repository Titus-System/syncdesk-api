from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .enums import FileStatus
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
