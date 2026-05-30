from uuid import UUID
from fastapi import APIRouter, Query, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.core.exceptions import AppHTTPException
from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.auth.dependencies import CurrentUserSessionDep, require_permission
from app.domains.auth.schemas import UserResponseDTO
from app.domains.companies.dependencies import CompanyServiceDep
from app.domains.companies.schemas import (
    AddCompanyProductDTO,
    AddCompanyUsersDTO,
    CreateCompanyDTO,
    RemoveCompanyProductDTO,
    RemoveCompanyUsersDTO,
    ReplaceCompanyDTO,
    UpdateCompanyDTO,
)
from app.domains.companies.swagger_utils import (
    add_products_swagger,
    add_users_swagger,
    create_company_swagger,
    get_companies_swagger,
    get_company_products_swagger,
    get_company_swagger,
    get_company_users_swagger,
    remove_product_swagger,
    remove_products_batch_swagger,
    remove_user_swagger,
    remove_users_batch_swagger,
    replace_company_swagger,
    soft_delete_company_swagger,
    update_company_swagger,
)

company_router = APIRouter(tags=["Companies"])

@company_router.post("/", dependencies=[require_permission("company:create")], **create_company_swagger)
async def create_company(
    dto: CreateCompanyDTO, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        company = await service.create(dto)
        return response.success(data=jsonable_encoder(company), status_code=status.HTTP_201_CREATED)
    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

@company_router.get("/", dependencies=[require_permission("company:list")], **get_companies_swagger)
async def get_companies(
    auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1),
) -> JSONResponse:
    res = await service.get_all_paginated(page, limit)
    return response.success(data=res.model_dump(mode="json"), status_code=status.HTTP_200_OK)

@company_router.get("/{company_id}", dependencies=[require_permission("company:read")], **get_company_swagger)
async def get_company(
    company_id: UUID, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    company = await service.get_by_id(company_id)
    if not company:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return response.success(data=jsonable_encoder(company), status_code=status.HTTP_200_OK)

@company_router.put("/{company_id}", dependencies=[require_permission("company:replace")], **replace_company_swagger)
async def replace_company(
    company_id: UUID, dto: ReplaceCompanyDTO, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        company = await service.update(company_id, dto)
        if not company:
            raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        return response.success(data=jsonable_encoder(company), status_code=status.HTTP_200_OK)
    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

@company_router.patch("/{company_id}", dependencies=[require_permission("company:update")], **update_company_swagger)
async def update_company(
    company_id: UUID, dto: UpdateCompanyDTO, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        company = await service.update(company_id, dto)
        if not company:
            raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
        return response.success(data=jsonable_encoder(company), status_code=status.HTTP_200_OK)
    except ResourceAlreadyExistsError as e:
        raise AppHTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e)) from e

@company_router.delete("/{company_id}", dependencies=[require_permission("company:soft_delete")], **soft_delete_company_swagger)
async def soft_delete_company(
    company_id: UUID, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    deleted = await service.soft_delete(company_id)
    if not deleted:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return response.success(data=None, status_code=status.HTTP_200_OK)

@company_router.post("/{company_id}/products", dependencies=[require_permission("company:add_product")], **add_products_swagger)
async def add_company_products(
    company_id: UUID, dto: AddCompanyProductDTO, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        await service.add_products(company_id, dto.product_ids)
        return response.success(data=None, status_code=status.HTTP_201_CREATED)
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e
    

@company_router.get("/{company_id}/products", dependencies=[require_permission("company:read")], **get_company_products_swagger)
async def get_company_products(
    company_id: UUID, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1),
) -> JSONResponse:
    res = await service.get_company_products_paginated(company_id, page, limit)
    if res is None:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Company not found")
    return response.success(data=res.model_dump(mode="json"), status_code=status.HTTP_200_OK)

@company_router.delete("/{company_id}/products", dependencies=[require_permission("company:remove_products")], **remove_products_batch_swagger)
async def remove_company_products_batch(
    company_id: UUID, dto: RemoveCompanyProductDTO, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        await service.remove_products(company_id, dto.product_ids)
        return response.success(data=None, status_code=status.HTTP_200_OK)
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

@company_router.delete("/{company_id}/products/{product_id}", dependencies=[require_permission("company:remove_product")], **remove_product_swagger)
async def remove_company_product(
    company_id: UUID, product_id: int, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        await service.remove_products(company_id, [product_id])
        return response.success(data=None, status_code=status.HTTP_200_OK)
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

@company_router.post("/{company_id}/users", dependencies=[require_permission("company:add_users")], **add_users_swagger)
async def add_company_users(
    company_id: UUID, dto: AddCompanyUsersDTO, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        await service.associate_users(company_id, dto.user_ids)
        return response.success(data=None, status_code=status.HTTP_201_CREATED)
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

@company_router.delete("/{company_id}/users", dependencies=[require_permission("company:remove_users")], **remove_users_batch_swagger)
async def remove_company_users_batch(
    company_id: UUID, dto: RemoveCompanyUsersDTO, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        await service.disassociate_users(company_id, dto.user_ids)
        return response.success(data=None, status_code=status.HTTP_200_OK)
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

@company_router.delete("/{company_id}/users/{user_id}", dependencies=[require_permission("company:remove_user")], **remove_user_swagger)
async def remove_company_user(
    company_id: UUID, user_id: UUID, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
) -> JSONResponse:
    try:
        await service.disassociate_users(company_id, [user_id])
        return response.success(data=None, status_code=status.HTTP_200_OK)
    except ValueError as e:
        raise AppHTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e)) from e

@company_router.get("/{company_id}/users", dependencies=[require_permission("company:list_users")], **get_company_users_swagger)
async def get_company_users(
    company_id: UUID, auth: CurrentUserSessionDep, service: CompanyServiceDep, response: ResponseFactoryDep,
    page: int = Query(default=1, ge=1), limit: int = Query(default=20, ge=1),
) -> JSONResponse:
    users, total = await service.get_company_users_paginated(company_id, page, limit)
    
    # Proteção de vazamento de dados importada da Entrega 1
    safe_items = [UserResponseDTO.model_validate(u).model_dump(mode="json") for u in users]
    
    data = {
        "items": safe_items,
        "total": total,
        "page": page,
        "limit": limit
    }
    return response.success(data=data, status_code=status.HTTP_200_OK)