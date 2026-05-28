from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.db.exceptions import ResourceNotFoundError
from app.domains.auth.dependencies import (
    CurrentUserSessionDep,
    UserLevelServiceDep,
    require_permission,
)
from app.domains.auth.schemas.user_level_schemas import (
    DeleteUserLevelResponseDTO,
    LevelResponseDTO,
    LevelUserResponseDTO,
    LevelUsersResponseDTO,
    UserLevelResponseDTO,
    UserLevelsResponseDTO,
)

user_level_router = APIRouter()


@user_level_router.post(
    "/users/{user_id}/levels/{level_id}",
    tags=["Users", "Levels"],
    dependencies=[require_permission("user_level:create")],
)
async def add_user_level(
    user_id: UUID,
    level_id: int,
    auth: CurrentUserSessionDep,
    service: UserLevelServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    current_user, _session = auth
    try:
        user_level = await service.add_user_level(user_id, level_id, current_user)
    except ResourceNotFoundError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except PermissionError as e:
        raise AppHTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e)) from e

    data = UserLevelResponseDTO.model_validate(user_level).model_dump(mode="json")
    return response.success(data=data, status_code=status.HTTP_200_OK)


@user_level_router.get(
    "/users/{user_id}/levels",
    tags=["Users", "Levels"],
    dependencies=[require_permission("user_level:read")],
)
async def get_user_levels(
    user_id: UUID,
    auth: CurrentUserSessionDep,
    service: UserLevelServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    current_user, _session = auth
    try:
        levels = await service.get_user_levels(user_id, current_user)
    except ResourceNotFoundError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except PermissionError as e:
        raise AppHTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e

    data = UserLevelsResponseDTO(
        user_id=user_id,
        levels=[LevelResponseDTO.model_validate(level) for level in levels],
    ).model_dump(mode="json")
    return response.success(data=data, status_code=status.HTTP_200_OK)


@user_level_router.get(
    "/levels/{level_id}/users",
    tags=["Levels", "Users"],
    dependencies=[require_permission("user_level:read")],
)
async def get_level_users(
    level_id: int,
    auth: CurrentUserSessionDep,
    service: UserLevelServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    current_user, _session = auth
    try:
        level, users = await service.get_level_users(level_id, current_user)
    except ResourceNotFoundError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except PermissionError as e:
        raise AppHTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e

    data = LevelUsersResponseDTO(
        level=LevelResponseDTO.model_validate(level),
        users=[LevelUserResponseDTO.model_validate(user) for user in users],
    ).model_dump(mode="json")
    return response.success(data=data, status_code=status.HTTP_200_OK)


@user_level_router.delete(
    "/users/{user_id}/levels/{level_id}",
    tags=["Users", "Levels"],
    dependencies=[require_permission("user_level:delete")],
)
async def delete_user_level(
    user_id: UUID,
    level_id: int,
    auth: CurrentUserSessionDep,
    service: UserLevelServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    current_user, _session = auth
    try:
        await service.delete_user_level(user_id, level_id, current_user)
    except ResourceNotFoundError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    except PermissionError as e:
        raise AppHTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e

    data = DeleteUserLevelResponseDTO(
        user_id=user_id,
        level_id=level_id,
        deleted=True,
    ).model_dump(mode="json")
    return response.success(data=data, status_code=status.HTTP_200_OK)
