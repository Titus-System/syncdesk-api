from datetime import UTC, datetime, timedelta
from uuid import UUID

from beanie import PydanticObjectId
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.core.logger import get_logger
from app.domains.auth.dependencies import CurrentUserSessionDep
from app.domains.auth.entities import UserWithRoles
from app.domains.live_chat.dependencies import ConversationServiceDep

from .dependencies import FileServiceDep
from .enums import FileContext, FileStatus
from .exceptions import (
    FileAccessForbiddenError,
    FileNotReadyError,
    FileTooLargeError,
    InvalidFileContextError,
    UnsupportedFileTypeError,
)
from .metrics import file_download_urls_total
from .models import FileObject
from .schemas import (
    ConfirmUploadResponse,
    DownloadUrlResponse,
    PresignUploadRequest,
    PresignUploadResponse,
)
from .swagger_utils import (
    confirm_upload_swagger,
    delete_file_swagger,
    download_url_swagger,
    presign_upload_swagger,
)

settings = get_settings()
logger = get_logger("app.domains.files.router")

files_router = APIRouter()


def _is_admin(user: UserWithRoles) -> bool:
    return "admin" in {role.strip().lower() for role in user.roles_names()}


def _parse_conversation_id(value: str | None) -> PydanticObjectId:
    if not value:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="conversation_id required in context_ref",
        )
    try:
        return PydanticObjectId(value)
    except Exception as e:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid conversation_id: {value}",
        ) from e


async def _ensure_user_can_read_chat_file(
    file_obj: FileObject,
    user: UserWithRoles,
    conversation_service: ConversationServiceDep,
) -> None:
    """Authorize a download URL for a live_chat_message file.

    Allowed readers: conversation participants and admins. The conversation id
    is recovered from the object key (``live_chat/{conversation_id}/...``)
    because the file record does not store it explicitly.
    """
    if _is_admin(user):
        return

    try:
        conversation_id = file_obj.object_key.split("/")[1]
    except IndexError as e:
        logger.error(
            "Object key has unexpected shape for live_chat_message",
            extra={"file_id": str(file_obj.id), "object_key": file_obj.object_key},
        )
        raise AppHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot determine conversation owner",
        ) from e

    participants = await conversation_service.get_participants(PydanticObjectId(conversation_id))
    if participants is None or user.id not in (participants.client_id, participants.agent_id):
        logger.warning(
            "Download rejected: user is not a participant of the conversation",
            extra={
                "file_id": str(file_obj.id),
                "user_id": str(user.id),
                "conversation_id": conversation_id,
            },
        )
        raise AppHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a participant of this conversation",
        )


@files_router.post("/presign-upload", tags=["Files"], **presign_upload_swagger)
async def presign_upload(
    request: PresignUploadRequest,
    auth: CurrentUserSessionDep,
    file_service: FileServiceDep,
    conversation_service: ConversationServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user, _ = auth

    if request.context == FileContext.LIVE_CHAT_MESSAGE:
        conversation_id = _parse_conversation_id(request.context_ref.get("conversation_id"))
        participants = await conversation_service.get_participants(conversation_id)
        if participants is None or user.id not in (participants.client_id, participants.agent_id):
            logger.warning(
                "Presign rejected: user is not a participant",
                extra={
                    "user_id": str(user.id),
                    "conversation_id": str(conversation_id),
                    "context": request.context.value,
                },
            )
            raise AppHTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not a participant of this conversation",
            )

    try:
        _, presigned_response = await file_service.request_upload(user_id=user.id, request=request)
    except (FileTooLargeError, UnsupportedFileTypeError, InvalidFileContextError) as e:
        raise AppHTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    data = PresignUploadResponse.model_validate(presigned_response).model_dump(mode="json")
    return response.success(data=data, status_code=status.HTTP_201_CREATED)


@files_router.post("/{file_id}/confirm", tags=["Files"], **confirm_upload_swagger)
async def confirm_upload(
    file_id: UUID,
    auth: CurrentUserSessionDep,
    file_service: FileServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user, _ = auth
    try:
        file_obj = await file_service.confirm_upload(user_id=user.id, file_id=file_id)
    except FileAccessForbiddenError as e:
        raise AppHTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except FileNotReadyError as e:
        raise AppHTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

    if file_obj is None:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    payload = ConfirmUploadResponse(file_id=file_obj.id, status=file_obj.status)
    return response.success(data=payload.model_dump(mode="json"), status_code=status.HTTP_200_OK)


@files_router.get("/{file_id}/download-url", tags=["Files"], **download_url_swagger)
async def get_download_url(
    file_id: UUID,
    auth: CurrentUserSessionDep,
    file_service: FileServiceDep,
    conversation_service: ConversationServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user, _ = auth
    file_obj = await file_service.get_by_id(file_id)
    if file_obj is None or file_obj.status != FileStatus.UPLOADED:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if file_obj.context == FileContext.LIVE_CHAT_MESSAGE:
        await _ensure_user_can_read_chat_file(file_obj, user, conversation_service)
    # user_avatar: any authenticated user can read.

    url = await file_service.get_download_url(file_obj)
    if url is None:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not available")

    file_download_urls_total.labels(context=file_obj.context.value).inc()
    expires_in = settings.S3_PRESIGNED_DOWNLOAD_EXPIRES_SECONDS
    expires_at = datetime.now(UTC) + timedelta(seconds=expires_in)
    data = DownloadUrlResponse(url=url, expires_at=expires_at).model_dump(mode="json")
    return response.success(data=data, status_code=status.HTTP_200_OK)


@files_router.delete("/{file_id}", tags=["Files"], **delete_file_swagger)
async def delete_file(
    file_id: UUID,
    auth: CurrentUserSessionDep,
    file_service: FileServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user, _ = auth
    file_obj = await file_service.get_by_id(file_id)
    if file_obj is None or file_obj.status == FileStatus.DELETED:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    if file_obj.uploaded_by_user_id != user.id and not _is_admin(user):
        logger.warning(
            "Delete rejected: user is neither uploader nor admin",
            extra={
                "file_id": str(file_id),
                "user_id": str(user.id),
                "uploader_id": str(file_obj.uploaded_by_user_id),
            },
        )
        raise AppHTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access forbidden")

    deleted = await file_service.delete(file_id)
    if deleted is None:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    payload = ConfirmUploadResponse(file_id=deleted.id, status=deleted.status)
    return response.success(data=payload.model_dump(mode="json"), status_code=status.HTTP_200_OK)
