from fastapi import APIRouter, status
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.db.exceptions import ResourceAlreadyExistsError

from ..dependencies import CurrentUserSessionDep, RoleServiceDep, require_permission
from ..schemas import AddRolePermissionsDTO, CreateRoleDTO, ReplaceRoleDTO, UpdateRoleDTO
from .swagger_utils import (
    add_role_perms_swagger,
    create_role_swagger,
    delete_role_swagger,
    get_role_perms_swagger,
    get_role_swagger,
    list_roles_swagger,
    replace_role_swagger,
    update_role_swagger,
)

role_router = APIRouter()


@role_router.post(
    "/",
    tags=["Roles"],
    dependencies=[require_permission("role:create")],
    **create_role_swagger,
)
async def create_role(
    dto: CreateRoleDTO,
    _auth: CurrentUserSessionDep,
    service: RoleServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        role = await service.create(dto)
        return response.success(
            data=role.__dict__,
            status_code=status.HTTP_201_CREATED,
        )
    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Role with name '{dto.name}' already exists",
        ) from e


@role_router.get(
    "/",
    tags=["Roles"],
    dependencies=[require_permission("role:list")],
    **list_roles_swagger,
)
async def get_roles(
    _auth: CurrentUserSessionDep, service: RoleServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    roles = await service.get_all()
    return response.success(
        data=[role.__dict__ for role in roles],
        status_code=status.HTTP_200_OK,
    )


@role_router.get(
    "/{id}", tags=["Roles"], dependencies=[require_permission("role:read")],
    **get_role_swagger,
)
async def get_role(
    id: int, _auth: CurrentUserSessionDep, service: RoleServiceDep, response: ResponseFactoryDep
) -> JSONResponse:
    role = await service.get_one(id=id)
    if not role:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Role with id '{id}' was not found."
        )
    return response.success(
        data=role.__dict__,
        status_code=status.HTTP_200_OK,
    )


@role_router.put(
    "/{id}", tags=["Roles"], dependencies=[require_permission("role:replace")],
    **replace_role_swagger,
)
async def replace_role(
    id: int,
    dto: ReplaceRoleDTO,
    _auth: CurrentUserSessionDep,
    service: RoleServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    role = await service.update(id, dto)
    if role is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Role with id '{id}' was not found."
        )
    return response.success(
        data=role.__dict__,
        status_code=status.HTTP_200_OK,
    )


@role_router.patch(
    "/{id}", tags=["Roles"], dependencies=[require_permission("role:update")],
    **update_role_swagger,
)
async def update_role(
    id: int,
    dto: UpdateRoleDTO,
    _auth: CurrentUserSessionDep,
    service: RoleServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    role = await service.update(id, dto)
    if role is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Role with id '{id}' was not found."
        )
    return response.success(
        data=role.__dict__,
        status_code=status.HTTP_200_OK,
    )


@role_router.delete(
    "/{id}", tags=["Roles"], dependencies=[require_permission("role:delete")],
    **delete_role_swagger,
)
async def delete_role(
    id: int,
    _auth: CurrentUserSessionDep,
    service: RoleServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    role = await service.delete(id)
    if role is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Role with id '{id}' was not found."
        )
    return response.success(
        data=role.__dict__,
        status_code=status.HTTP_200_OK,
    )


@role_router.get(
    "/{id}/permissions",
    tags=["Roles", "Permissions"],
    dependencies=[require_permission("role:read_permissions")],
    **get_role_perms_swagger,
)
async def get_role_permissions(
    id: int,
    _auth: CurrentUserSessionDep,
    service: RoleServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    role = await service.get_with_permissions(id)
    if role is None:
        raise AppHTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Role with id '{id}' was not found."
        )
    return response.success(data=role.__dict__, status_code=status.HTTP_200_OK)


@role_router.post(
    "/{id}/permissions",
    tags=["Roles", "Permissions"],
    dependencies=[require_permission("role:add_permissions")],
    **add_role_perms_swagger,
)
async def add_role_permissions(
    id: int,
    dto: AddRolePermissionsDTO,
    _auth: CurrentUserSessionDep,
    service: RoleServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    role = await service.add_permissions(id, dto.ids)
    return response.success(data=role.__dict__, status_code=status.HTTP_200_OK)
