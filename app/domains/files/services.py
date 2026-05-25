import re
from uuid import UUID, uuid4

from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings
from app.core.logger import get_logger
from app.core.storage import ObjectStorage

from .enums import FileContext, FileStatus
from .exceptions import (
    FileAccessForbiddenError,
    FileNotReadyError,
    FileTooLargeError,
    InvalidFileContextError,
    UnsupportedFileTypeError,
)
from .metrics import (
    file_confirms_total,
    file_deletes_total,
    file_upload_size_bytes,
    file_uploads_total,
)
from .models import FileObject
from .repositories import FileObjectRepository
from .schemas import PresignUploadRequest, PresignUploadResponse

settings = get_settings()

# Allowed mime types and maximum size in bytes, per upload context.
FILE_UPLOAD_LIMITS: dict[FileContext, tuple[frozenset[str], int]] = {
    FileContext.LIVE_CHAT_MESSAGE: (
        frozenset(
            {
                "image/png",
                "image/jpeg",
                "image/webp",
                "image/gif",
                "application/pdf",
                "audio/mpeg",
                "audio/ogg",
                "audio/webm",
            }
        ),
        25 * 1024 * 1024,
    ),
    FileContext.USER_AVATAR: (
        frozenset({"image/png", "image/jpeg", "image/webp"}),
        2 * 1024 * 1024,
    ),
}

_SLUG_RE = re.compile(r"[^a-zA-Z0-9._-]+")
_MAX_SLUG_LEN = 120


def _slugify(filename: str) -> str:
    cleaned = _SLUG_RE.sub("-", filename).strip("-")[:_MAX_SLUG_LEN]
    return cleaned or "file"


def _sanitize_filename(filename: str) -> str:
    if not filename.strip() or "/" in filename or ".." in filename:
        raise InvalidFileContextError("filename contains forbidden segments")
    return filename


class FileService:
    """Domain service for file objects.

    Authorization beyond ownership (e.g. conversation participation, admin
    overrides) is enforced upstream by the router; the service stays
    provider- and domain-agnostic.
    """

    def __init__(self, repo: FileObjectRepository, object_storage: ObjectStorage) -> None:
        self._repo = repo
        self._storage = object_storage
        self._logger = get_logger("app.domains.files")

    async def request_upload(
        self, user_id: UUID, request: PresignUploadRequest
    ) -> tuple[FileObject, PresignUploadResponse]:
        filename = _sanitize_filename(request.filename)
        self._validate_constraints(request)

        file_id = uuid4()
        object_key = self._build_object_key(
            context=request.context,
            user_id=user_id,
            file_id=file_id,
            filename=filename,
            context_ref=request.context_ref,
        )
        max_size = FILE_UPLOAD_LIMITS[request.context][1]
        context_label = request.context.value

        try:
            presigned = await self._storage.generate_presigned_upload(
                object_key=object_key,
                content_type=request.content_type,
                max_size_bytes=max_size,
                expires_in_seconds=settings.S3_PRESIGNED_UPLOAD_EXPIRES_SECONDS,
            )
        except (ClientError, BotoCoreError) as exc:
            self._logger.error(
                "Failed to generate presigned upload",
                extra={
                    "file_id": str(file_id),
                    "context": context_label,
                    "object_key": object_key,
                },
                exc_info=exc,
            )
            file_uploads_total.labels(status="storage_error", context=context_label).inc()
            raise

        file_obj = FileObject(
            id=file_id,
            bucket=settings.S3_BUCKET_DEFAULT,
            object_key=object_key,
            original_filename=filename,
            content_type=request.content_type,
            size_bytes=request.size_bytes,
            context=request.context,
            status=FileStatus.PENDING,
            uploaded_by_user_id=user_id,
        )
        created = await self._repo.create(file_obj)

        file_uploads_total.labels(status="pending", context=context_label).inc()
        file_upload_size_bytes.labels(context=context_label).observe(request.size_bytes)
        self._logger.info(
            "Presigned upload requested",
            extra={
                "file_id": str(created.id),
                "user_id": str(user_id),
                "context": context_label,
                "object_key": object_key,
                "size_bytes": request.size_bytes,
            },
        )

        response = PresignUploadResponse(
            file_id=created.id,
            upload_url=presigned.url,
            method=presigned.method,
            fields=presigned.fields,
            expires_at=presigned.expires_at,
            max_size_bytes=max_size,
        )
        return created, response

    async def get_by_id(self, file_id: UUID) -> FileObject | None:
        return await self._repo.get_by_id(file_id)

    async def confirm_upload(self, user_id: UUID, file_id: UUID) -> FileObject | None:
        file_obj = await self._repo.get_by_id(file_id)
        if file_obj is None or file_obj.status == FileStatus.DELETED:
            return None
        if file_obj.uploaded_by_user_id != user_id:
            self._logger.warning(
                "Confirm rejected: user is not the uploader",
                extra={
                    "file_id": str(file_id),
                    "user_id": str(user_id),
                    "uploader_id": str(file_obj.uploaded_by_user_id),
                },
            )
            raise FileAccessForbiddenError()

        context_label = file_obj.context.value
        if file_obj.status == FileStatus.UPLOADED:
            file_confirms_total.labels(result="idempotent", context=context_label).inc()
            return file_obj

        try:
            size = await self._storage.get_object_size(file_obj.object_key)
        except (ClientError, BotoCoreError) as exc:
            self._logger.error(
                "Storage backend error while confirming upload",
                extra={"file_id": str(file_id), "object_key": file_obj.object_key},
                exc_info=exc,
            )
            file_confirms_total.labels(result="storage_error", context=context_label).inc()
            raise FileNotReadyError("Storage backend unreachable; retry later") from exc

        if size is None:
            self._logger.info(
                "Confirm called before object was uploaded to storage",
                extra={"file_id": str(file_id), "object_key": file_obj.object_key},
            )
            file_confirms_total.labels(result="not_ready", context=context_label).inc()
            raise FileNotReadyError("Object not yet present in storage")

        updated = await self._repo.mark_uploaded(file_id)
        file_uploads_total.labels(status="uploaded", context=context_label).inc()
        file_confirms_total.labels(result="ok", context=context_label).inc()
        self._logger.info(
            "Upload confirmed",
            extra={"file_id": str(file_id), "context": context_label, "size_bytes": size},
        )
        return updated or file_obj

    async def get_download_url(self, file_obj: FileObject) -> str | None:
        if file_obj.status != FileStatus.UPLOADED:
            return None
        try:
            return await self._storage.generate_presigned_download_url(
                object_key=file_obj.object_key,
                expires_in_seconds=settings.S3_PRESIGNED_DOWNLOAD_EXPIRES_SECONDS,
            )
        except (ClientError, BotoCoreError) as exc:
            self._logger.error(
                "Failed to generate presigned download URL",
                extra={"file_id": str(file_obj.id), "object_key": file_obj.object_key},
                exc_info=exc,
            )
            raise

    async def delete(self, file_id: UUID) -> FileObject | None:
        deleted = await self._repo.mark_deleted(file_id)
        if deleted is not None:
            file_deletes_total.labels(context=deleted.context.value).inc()
            self._logger.info(
                "File soft-deleted",
                extra={"file_id": str(deleted.id), "context": deleted.context.value},
            )
        return deleted

    # ----- helpers -----

    @staticmethod
    def _validate_constraints(request: PresignUploadRequest) -> None:
        limits = FILE_UPLOAD_LIMITS.get(request.context)
        if limits is None:
            raise InvalidFileContextError(f"Unknown context: {request.context}")
        allowed_types, max_size = limits
        if request.content_type not in allowed_types:
            raise UnsupportedFileTypeError(request.content_type)
        if request.size_bytes > max_size:
            raise FileTooLargeError(limit=max_size, actual=request.size_bytes)

    @staticmethod
    def _build_object_key(
        context: FileContext,
        user_id: UUID,
        file_id: UUID,
        filename: str,
        context_ref: dict[str, str],
    ) -> str:
        if context == FileContext.LIVE_CHAT_MESSAGE:
            conversation_id = context_ref.get("conversation_id")
            if not conversation_id:
                raise InvalidFileContextError("conversation_id required in context_ref")
            return f"live_chat/{conversation_id}/{file_id}-{_slugify(filename)}"
        if context == FileContext.USER_AVATAR:
            extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
            return f"avatars/users/{user_id}.{extension}"
        raise InvalidFileContextError(f"Unknown context: {context}")
