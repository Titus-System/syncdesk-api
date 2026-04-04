from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.db.exceptions import ResourceAlreadyExistsError

from ..dependencies import CurrentUserSessionDep, PermissionServiceDep, require_permission
from ..schemas import (
    AddRolePermissionsDTO,
    CreatePermissionDTO,
    ReplacePermissionDTO,
    UpdatePermissionDTO,
)
from .swagger_utils import (
    add_perm_to_roles_swagger,
    create_perm_swagger,
    delete_perm_swagger,
    get_perm_roles_swagger,
    get_perm_swagger,
    list_perms_swagger,
    replace_perm_swagger,
    update_perm_swagger,
)

permission_router = APIRouter()


@permission_router.post(
    "/", tags=["Permissions"], dependencies=[require_permission("permission:create")],
    **create_perm_swagger,
)
async def create_permission(
    dto: CreatePermissionDTO,
    _auth: CurrentUserSessionDep,
    service: PermissionServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        permission = await service.create(dto)
        return response.success(data=permission.__dict__, status_code=status.HTTP_201_CREATED)
    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Permission with name '{dto.name}' already exists",
        ) from e


@permission_router.get(
    "/", tags=["Permissions"], dependencies=[require_permission("permission:list")],
    **list_perms_swagger,
)
async def get_permissions(
    service: PermissionServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    permissions = await service.get_all()
    return response.success(data=[p.__dict__ for p in permissions], status_code=status.HTTP_200_OK)


@permission_router.get(
    "/{id}", tags=["Permissions"], dependencies=[require_permission("permission:read")],
    **get_perm_swagger,
)
async def get_permission_by_id(
    id: int,
    _auth: CurrentUserSessionDep,
    service: PermissionServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    permission = await service.get_one(id)
    if not permission:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Permission with id '{id}' not found"
        )
    return response.success(data=permission.__dict__, status_code=status.HTTP_200_OK)


@permission_router.put(
    "/{id}", tags=["Permissions"], dependencies=[require_permission("permission:replace")],
    **replace_perm_swagger,
)
async def replace_permission(
    id: int,
    dto: ReplacePermissionDTO,
    _auth: CurrentUserSessionDep,
    service: PermissionServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    permission = await service.update(id, dto)
    if permission is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission with id '{id}' was not found.",
        )
    return response.success(data=permission.__dict__, status_code=status.HTTP_200_OK)


@permission_router.patch(
    "/{id}", tags=["Permissions"], dependencies=[require_permission("permission:update")],
    **update_perm_swagger,
)
async def update_permission(
    id: int,
    dto: UpdatePermissionDTO,
    _auth: CurrentUserSessionDep,
    service: PermissionServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    permission = await service.update(id, dto)
    if permission is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission with id '{id}' was not found.",
        )
    return response.success(data=permission.__dict__, status_code=status.HTTP_200_OK)


@permission_router.delete(
    "/{id}", tags=["Permissions"], dependencies=[require_permission("permission:delete")],
    **delete_perm_swagger,
)
async def delete_permission(
    id: int,
    _auth: CurrentUserSessionDep,
    service: PermissionServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    permission = await service.delete(id)
    if permission is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Permission with id '{id}' was not found.",
        )
    return response.success(
        data=permission.__dict__,
        status_code=status.HTTP_200_OK,
    )


@permission_router.get(
    "/{id}/roles",
    tags=["Permissions", "Roles"],
    dependencies=[require_permission("permission:read_roles")],
    **get_perm_roles_swagger,
)
async def get_permission_roles(
    id: int,
    _auth: CurrentUserSessionDep,
    service: PermissionServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    permission = await service.get_with_roles(id)
    if permission is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Permission with id '{id}' not found"
        )
    return response.success(data=permission.__dict__, status_code=status.HTTP_200_OK)


@permission_router.post(
    "/{id}/roles",
    tags=["Permissions", "Roles"],
    dependencies=[require_permission("permission:add_to_roles")],
    **add_perm_to_roles_swagger,
)
async def add_permission_to_roles(
    id: int,
    dto: AddRolePermissionsDTO,
    _auth: CurrentUserSessionDep,
    service: PermissionServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    permission = await service.add_to_roles(id, dto.ids)
    return response.success(data=permission.__dict__, status_code=status.HTTP_200_OK)
