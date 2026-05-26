from datetime import UTC, datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.config import get_settings
from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.core.logger import get_logger
from app.db.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.domains.auth.dependencies import CurrentUserSessionDep, UserServiceDep, require_permission
from app.domains.auth.schemas.user_schemas import RemoveUserRolesDTO, UpdateUserRolesDTO
from app.domains.files.dependencies import FileServiceDep
from app.domains.files.enums import FileContext, FileStatus

from ..schemas import (
    AddUserRolesDTO,
    CreateUserDTO,
    CurrentUserAvatarDTO,
    ReplaceUserDTO,
    SetUserAvatarDTO,
    UpdateUserDTO,
    UserResponseDTO,
)
from .swagger_utils import (
    add_user_roles_swagger,
    clear_avatar_swagger,
    create_user_swagger,
    deactivate_user_swagger,
    get_my_avatar_swagger,
    get_user_swagger,
    list_users_swagger,
    remove_user_roles_swagger,
    replace_user_swagger,
    set_avatar_swagger,
    update_user_roles_swagger,
    update_user_swagger,
)

logger = get_logger("app.auth.user_router")

user_router = APIRouter()


@user_router.post(
    "/",
    tags=["Users"],
    dependencies=[require_permission("user:create")],
    **create_user_swagger,
)
async def create_user(
    dto: CreateUserDTO,
    _auth: CurrentUserSessionDep,
    service: UserServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        user = await service.create(dto)
        safe_data = UserResponseDTO.model_validate(user).model_dump(mode="json")
        return response.success(data=safe_data, status_code=status.HTTP_201_CREATED)
    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"User with email {dto.email} already exists.",
        ) from e


@user_router.get(
    "/",
    tags=["Users"],
    dependencies=[require_permission("user:list")],
    **list_users_swagger,
)
async def get_users(
    _auth: CurrentUserSessionDep, service: UserServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    users = await service.get_all_with_roles()
    safe_data = [UserResponseDTO.model_validate(user).model_dump(mode="json") for user in users]
    return response.success(
        data=safe_data, status_code=status.HTTP_200_OK
    )


@user_router.get(
    "/{id}", tags=["Users"], dependencies=[require_permission("user:read")],
    **get_user_swagger,
)
async def get_user(
    id: UUID, _auth: CurrentUserSessionDep, service: UserServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    user = await service.get_by_id_with_roles(id)
    if not user:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id '{id}' was not found."
        )
    safe_data = UserResponseDTO.model_validate(user).model_dump(mode="json")
    return response.success(data=safe_data, status_code=status.HTTP_200_OK)


@user_router.put(
    "/{id}", tags=["Users"], dependencies=[require_permission("user:replace")],
    **replace_user_swagger,
)
async def replace_user(
    id: UUID,
    dto: ReplaceUserDTO,
    _auth: CurrentUserSessionDep,
    service: UserServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user = await service.update(id, dto)
    if user is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id '{id}' was not found."
        )
    safe_data = UserResponseDTO.model_validate(user).model_dump(mode="json")
    return response.success(
        data=safe_data,
        status_code=status.HTTP_200_OK,
    )


@user_router.patch(
    "/{id}", tags=["Users"], dependencies=[require_permission("user:update")],
    **update_user_swagger,
)
async def update_user(
    id: UUID,
    dto: UpdateUserDTO,
    _auth: CurrentUserSessionDep,
    service: UserServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user = await service.update(id, dto)
    if user is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id '{id}' was not found."
        )
    safe_data = UserResponseDTO.model_validate(user).model_dump(mode="json")
    return response.success(
        data=safe_data,
        status_code=status.HTTP_200_OK,
    )


@user_router.patch(
    "/{user_id}/deactivate",
    tags=["Users"],
    dependencies=[require_permission("user:update")],
    **deactivate_user_swagger,
)
async def deactivate_user(
    user_id: UUID,
    _auth: CurrentUserSessionDep,
    service: UserServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    user = await service.deactivate(user_id)
    if user is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User with id '{user_id}' was not found.",
        )
    return response.success(
        data=user.to_response_dict(),
        status_code=status.HTTP_200_OK,
    )


@user_router.get("/me/avatar", tags=["Users", "Files"], **get_my_avatar_swagger)
async def get_my_avatar(
    auth: CurrentUserSessionDep,
    user_service: UserServiceDep,
    file_service: FileServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    """Return the current user's avatar metadata + a fresh presigned URL.

    Saves the frontend a second round-trip. Returns all-null when the
    user has no avatar so the client branches on a single check.
    """
    user, _ = auth
    file_id = user.avatar_file_id

    data: dict[str, str | None] = {
        "file_id": None,
        "download_url": None,
        "expires_at": None,
    }

    if file_id is not None:
        file_obj = await file_service.get_by_id(file_id)
        if file_obj is not None and file_obj.status == FileStatus.UPLOADED:
            url = await file_service.get_download_url(file_obj)
            if url is not None:
                expires_in = get_settings().S3_PRESIGNED_DOWNLOAD_EXPIRES_SECONDS
                data = {
                    "file_id": str(file_id),
                    "download_url": url,
                    "expires_at": (datetime.now(UTC) + timedelta(seconds=expires_in)).isoformat(),
                }
        else:
            # FK still points at a row that's gone or not in UPLOADED.
            # Surface as "no avatar" instead of leaking inconsistency.
            logger.warning(
                "Avatar file_id on user points to a missing/non-uploaded file",
                extra={
                    "user_id": str(user.id),
                    "avatar_file_id": str(file_id),
                },
            )

    payload = CurrentUserAvatarDTO.model_validate(data).model_dump(mode="json")
    return response.success(data=payload, status_code=status.HTTP_200_OK)


@user_router.put("/me/avatar", tags=["Users", "Files"], **set_avatar_swagger)
async def set_my_avatar(
    dto: SetUserAvatarDTO,
    auth: CurrentUserSessionDep,
    user_service: UserServiceDep,
    file_service: FileServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    """Point the current user's avatar at a confirmed FileObject.

    Cross-domain validation lives here, at the composition layer (same
    pattern PR3 uses in chat_router). The user service only deals with
    the ``users.avatar_file_id`` column; the files service is consulted
    to vet the new file and to soft-delete the previous avatar.
    """
    user, _ = auth
    log_ctx = {"user_id": str(user.id), "file_id": str(dto.file_id)}

    file_obj = await file_service.get_by_id(dto.file_id)
    if file_obj is None:
        logger.info(
            "Set avatar rejected: file_id does not reference a known file",
            extra=log_ctx,
        )
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="file_id does not reference a known file",
        )
    if file_obj.uploaded_by_user_id != user.id:
        logger.warning(
            "Set avatar rejected: file_id was uploaded by a different user",
            extra={**log_ctx, "uploader_id": str(file_obj.uploaded_by_user_id)},
        )
        raise AppHTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="file_id was not uploaded by the current user",
        )
    if file_obj.context != FileContext.USER_AVATAR:
        logger.warning(
            "Set avatar rejected: wrong file context",
            extra={**log_ctx, "context": file_obj.context.value},
        )
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"file_id has context {file_obj.context.value!r}, "
                "expected 'user_avatar'"
            ),
        )
    if file_obj.status != FileStatus.UPLOADED:
        logger.info(
            "Set avatar rejected: file is not in 'uploaded' status",
            extra={**log_ctx, "status": file_obj.status.value},
        )
        raise AppHTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"file_id has status {file_obj.status.value!r}, "
                "expected 'uploaded'"
            ),
        )

    result = await user_service.set_avatar(user.id, dto.file_id)
    if result is None:
        logger.error(
            "Set avatar failed: authenticated user vanished from the database",
            extra=log_ctx,
        )
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current user not found",
        )
    updated_user, previous_file_id = result

    if previous_file_id is not None and previous_file_id != dto.file_id:
        try:
            await file_service.delete(previous_file_id)
        except Exception:
            logger.warning(
                "Previous avatar cleanup failed; row will be reconciled by retention worker",
                extra={**log_ctx, "previous_file_id": str(previous_file_id)},
                exc_info=True,
            )

    safe_data = UserResponseDTO.model_validate(updated_user).model_dump(mode="json")
    return response.success(data=safe_data, status_code=status.HTTP_200_OK)


@user_router.delete("/me/avatar", tags=["Users", "Files"], **clear_avatar_swagger)
async def clear_my_avatar(
    auth: CurrentUserSessionDep,
    user_service: UserServiceDep,
    file_service: FileServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    """Remove the current user's avatar.

    Soft-deletes the previous FileObject (if any) and zeroes the
    ``avatar_file_id`` column. Idempotent — succeeds even when the user
    had no avatar to begin with.
    """
    user, _ = auth
    result = await user_service.set_avatar(user.id, None)
    if result is None:
        logger.error(
            "Clear avatar failed: authenticated user vanished from the database",
            extra={"user_id": str(user.id)},
        )
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Current user not found",
        )
    updated_user, previous_file_id = result

    if previous_file_id is not None:
        try:
            await file_service.delete(previous_file_id)
        except Exception:
            logger.warning(
                "Previous avatar cleanup failed; row will be reconciled by retention worker",
                extra={
                    "user_id": str(user.id),
                    "previous_file_id": str(previous_file_id),
                },
                exc_info=True,
            )

    safe_data = UserResponseDTO.model_validate(updated_user).model_dump(mode="json")
    return response.success(data=safe_data, status_code=status.HTTP_200_OK)


@user_router.post(
    "/{id}/roles", tags=["users", "Roles"], dependencies=[require_permission("user:add_roles")],
    **add_user_roles_swagger,
)
async def add_user_roles(
    id: UUID,
    dto: AddUserRolesDTO,
    _auth: CurrentUserSessionDep,
    service: UserServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    if not dto.role_ids:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No role ids were informed"
        )
    try:
        user = await service.add_roles(id, dto.role_ids)
        safe_data = UserResponseDTO.model_validate(user).model_dump(mode="json")
        return response.success(data=safe_data, status_code=status.HTTP_200_OK)
    except ResourceNotFoundError as e:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id '{id}' was not found."
        ) from e
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e


@user_router.delete(
    "/{user_id}/roles",
    tags=["Users", "Roles"],
    dependencies=[require_permission("user:update_roles")],
    **remove_user_roles_swagger,
)
async def remove_user_roles(
    user_id: UUID,
    dto: RemoveUserRolesDTO,
    _auth: CurrentUserSessionDep,
    service: UserServiceDep,
    response: ResponseFactoryDep
) -> JSONResponse:
    if not dto.role_ids:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No role ids were informed"
        )
    try:
        user = await service.remove_roles(user_id, dto.role_ids)
        safe_data = UserResponseDTO.model_validate(user).model_dump(mode="json")
        return response.success(data=safe_data, status_code=status.HTTP_200_OK)
    except ResourceNotFoundError as e:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id '{user_id}' was not found."
        ) from e
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    

@user_router.patch(
    "/{user_id}/roles",
    tags=["Users", "Roles"],
    dependencies=[require_permission("user:update_roles")],
    **update_user_roles_swagger,
)
async def update_user_roles(
    user_id: UUID,
    dto: UpdateUserRolesDTO,
    _auth: CurrentUserSessionDep,
    service: UserServiceDep,
    response: ResponseFactoryDep
) -> JSONResponse:
    if not dto.add_role_ids and not dto.remove_role_ids:
        raise AppHTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No role ids were informed"
        )

    try:
        user = await service.update_user_roles(user_id, dto)
        safe_data = UserResponseDTO.model_validate(user).model_dump(mode="json")
        return response.success(data=safe_data, status_code=status.HTTP_200_OK)
    except ResourceNotFoundError as e:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id '{user_id}' was not found."
        ) from e
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e