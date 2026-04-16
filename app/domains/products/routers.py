from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse

from app.core.dependencies import ResponseFactoryDep
from app.domains.auth.dependencies import CurrentUserSessionDep, require_permission
from app.domains.products.dependencies import ProductServiceDep
from app.domains.products.schemas import (
    AddProductToCompaniesDTO,
    CreateProductDTO,
    RemoveProductFromCompaniesDTO,
    ReplaceProductDTO,
    UpdateProductDTO,
)
from app.domains.products.swagger_utils import (
    add_companies_swagger,
    create_product_swagger,
    get_product_companies_swagger,
    get_product_swagger,
    get_products_swagger,
    remove_companies_swagger,
    remove_company_swagger,
    replace_product_swagger,
    soft_delete_product_swagger,
    update_product_swagger,
)

product_router = APIRouter(tags=["Products"])


@product_router.post(
    "/",
    dependencies=[require_permission("product:create")],
    **create_product_swagger,
)
async def create_product(
    dto: CreateProductDTO,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.get(
    "/",
    dependencies=[require_permission("product:list")],
    **get_products_swagger,
)
async def get_products(
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    limit: int = Query(default=20, ge=1, description="Number of products per page."),
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.get(
    "/{product_id}",
    dependencies=[require_permission("product:read")],
    **get_product_swagger,
)
async def get_product(
    product_id: int,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.put(
    "/{product_id}",
    dependencies=[require_permission("product:replace")],
    **replace_product_swagger,
)
async def replace_product(
    product_id: int,
    dto: ReplaceProductDTO,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.patch(
    "/{product_id}",
    dependencies=[require_permission("product:update")],
    **update_product_swagger,
)
async def update_product(
    product_id: int,
    dto: UpdateProductDTO,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.delete(
    "/{product_id}",
    dependencies=[require_permission("product:soft_delete")],
    **soft_delete_product_swagger,
)
async def soft_delete_product(
    product_id: int,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.post(
    "/{product_id}/companies",
    dependencies=[require_permission("product:add_companies")],
    **add_companies_swagger,
)
async def add_product_to_companies(
    product_id: int,
    dto: AddProductToCompaniesDTO,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.delete(
    "/{product_id}/companies",
    dependencies=[require_permission("product:remove_companies")],
    **remove_companies_swagger,
)
async def remove_product_from_companies(
    product_id: int,
    dto: RemoveProductFromCompaniesDTO,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.delete(
    "/{product_id}/companies/{company_id}",
    dependencies=[require_permission("product:remove_company")],
    **remove_company_swagger,
)
async def remove_product_company(
    product_id: int,
    company_id: UUID,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))


@product_router.get(
    "/{product_id}/companies",
    dependencies=[require_permission("product:list_companies")],
    **get_product_companies_swagger,
)
async def get_product_companies(
    product_id: int,
    auth: CurrentUserSessionDep,
    service: ProductServiceDep,
    response: ResponseFactoryDep,
    page: int = Query(default=1, ge=1, description="Page number (1-indexed)."),
    limit: int = Query(default=20, ge=1, description="Number of companies per page."),
) -> JSONResponse:
    return response.error(exc=HTTPException(status_code=501, detail="Not implemented"))
