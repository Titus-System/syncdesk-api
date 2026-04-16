from typing import Annotated

from fastapi import Depends

from app.db.postgres.dependencies import PgSessionDep
from app.domains.products.repositories import ProductRepository
from app.domains.products.services import ProductService


def get_product_repository(db: PgSessionDep) -> ProductRepository:
    return ProductRepository(db)


ProductRepoDep = Annotated[ProductRepository, Depends(get_product_repository)]


def get_product_service(repo: ProductRepoDep) -> ProductService:
    return ProductService(repo)


ProductServiceDep = Annotated[ProductService, Depends(get_product_service)]
