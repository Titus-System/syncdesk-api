from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.domains.auth.dependencies import CurrentUserSessionDep, require_permission
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


@company_router.post(
    "/",
    dependencies=[require_permission("company:create")],
    **create_company_swagger,
)
async def create_company(
    dto: CreateCompanyDTO,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.get(
    "/",
    dependencies=[require_permission("company:list")],
    **get_companies_swagger,
)
async def get_companies(
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    limit: int = Query(default=20, ge=1, description="Number of companies per page."),
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.get(
    "/{company_id}",
    dependencies=[require_permission("company:read")],
    **get_company_swagger,
)
async def get_company(
    company_id: UUID,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.put(
    "/{company_id}",
    dependencies=[require_permission("company:replace")],
    **replace_company_swagger,
)
async def replace_company(
    company_id: UUID,
    dto: ReplaceCompanyDTO,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.patch(
    "/{company_id}",
    dependencies=[require_permission("company:update")],
    **update_company_swagger,
)
async def update_company(
    company_id: UUID,
    dto: UpdateCompanyDTO,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.delete(
    "/{company_id}",
    dependencies=[require_permission("company:soft_delete")],
    **soft_delete_company_swagger,
)
async def soft_delete_company(
    company_id: UUID,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.post(
    "/{company_id}/products",
    dependencies=[require_permission("company:add_product")],
    **add_products_swagger,
)
async def add_company_products(
    company_id: UUID,
    dto: AddCompanyProductDTO,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.delete(
    "/{company_id}/products",
    dependencies=[require_permission("company:remove_products")],
    **remove_products_batch_swagger,
)
async def remove_company_products_batch(
    company_id: UUID,
    dto: RemoveCompanyProductDTO,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.delete(
    "/{company_id}/products/{product_id}",
    dependencies=[require_permission("company:remove_product")],
    **remove_product_swagger,
)
async def remove_company_product(
    company_id: UUID,
    product_id: int,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.post(
    "/{company_id}/users",
    dependencies=[require_permission("company:add_users")],
    **add_users_swagger,
)
async def add_company_users(
    company_id: UUID,
    dto: AddCompanyUsersDTO,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.delete(
    "/{company_id}/users",
    dependencies=[require_permission("company:remove_users")],
    **remove_users_batch_swagger,
)
async def remove_company_users_batch(
    company_id: UUID,
    dto: RemoveCompanyUsersDTO,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.delete(
    "/{company_id}/users/{user_id}",
    dependencies=[require_permission("company:remove_user")],
    **remove_user_swagger,
)
async def remove_company_user(
    company_id: UUID,
    user_id: UUID,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@company_router.get(
    "/{company_id}/users",
    dependencies=[require_permission("company:list_users")],
    **get_company_users_swagger,
)
async def get_company_users(
    company_id: UUID,
    auth: CurrentUserSessionDep,
    service: CompanyServiceDep,
    response: ResponseFactoryDep,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    limit: int = Query(default=20, ge=1, description="Number of users per page."),
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))
