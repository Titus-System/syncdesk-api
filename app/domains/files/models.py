from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres.base import Base

from .enums import FileContext, FileStatus, enum_values


class FileObject(Base):
    __tablename__ = "file_objects"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    bucket: Mapped[str] = mapped_column(String(63), nullable=False)
    object_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(127), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    context: Mapped[FileContext] = mapped_column(
        SqlEnum(
            FileContext,
            name="file_context",
            native_enum=True,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        index=True,
    )
    status: Mapped[FileStatus] = mapped_column(
        SqlEnum(
            FileStatus,
            name="file_status",
            native_enum=True,
            create_constraint=False,
            values_callable=enum_values,
        ),
        nullable=False,
        default=FileStatus.PENDING,
        index=True,
    )
    uploaded_by_user_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id"),
        nullable=False,
        index=True,
    )
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_file_objects_status_created_at", "status", "created_at"),
        Index("ix_file_objects_context_uploaded_at", "context", "uploaded_at"),
        Index("ix_file_objects_status_deleted_at", "status", "deleted_at"),
    )
