from uuid import UUID

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.dependencies import PasswordSecurityDep, ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.db.exceptions import ResourceAlreadyExistsError, ResourceNotFoundError
from app.domains.auth.dependencies import CurrentUserSessionDep, UserServiceDep, require_permission

from ..schemas import AddUserRolesDTO, CreateUserDTO, ReplaceUserDTO, UpdateUserDTO
from .swagger_utils import (
    add_user_roles_swagger,
    create_user_swagger,
    get_user_swagger,
    list_users_swagger,
    replace_user_swagger,
    update_user_swagger,
)

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
    password_security: PasswordSecurityDep,
) -> JSONResponse:
    try:
        dto_to_create = dto
        if dto.password_hash:
            dto_to_create = dto.model_copy(
                update={
                    "password_hash": password_security.generate_password_hash(dto.password_hash)
                }
            )
        user = await service.create(dto_to_create)
        return response.success(data=user.to_response_dict(), status_code=status.HTTP_201_CREATED)
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
    return response.success(
        data=[user.to_response_dict() for user in users], status_code=status.HTTP_200_OK
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
    return response.success(data=user.to_response_dict(), status_code=status.HTTP_200_OK)


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
    return response.success(
        data=user.to_response_dict(),
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
    return response.success(
        data=user.to_response_dict(),
        status_code=status.HTTP_200_OK,
    )


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
        return response.success(data=user.to_response_dict(), status_code=status.HTTP_200_OK)
    except ResourceNotFoundError as e:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"User with id '{id}' was not found."
        ) from e
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
