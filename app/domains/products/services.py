from uuid import UUID
from app.domains.products.repositories import ProductRepository
from app.domains.products.entities import Product as ProductEntity
from app.domains.companies.entities import Company as CompanyEntity
from app.domains.products.schemas import CreateProductDTO, UpdateProductDTO, ReplaceProductDTO
from app.core.schemas import PaginatedItems

class ProductService:
    def __init__(self, repo: ProductRepository) -> None:
        self.repo = repo

    async def create(self, dto: CreateProductDTO) -> ProductEntity:
        return await self.repo.create(dto)

    async def get_by_id(self, product_id: int) -> ProductEntity | None:
        return await self.repo.get_by_id(product_id)

    async def get_all_paginated(self, page: int, limit: int) -> PaginatedItems[ProductEntity]:
        skip = (page - 1) * limit
        return await self.repo.get_all_paginated(skip, limit)

    async def update(self, product_id: int, dto: UpdateProductDTO | ReplaceProductDTO) -> ProductEntity | None:
        return await self.repo.update(product_id, dto)

    async def soft_delete(self, product_id: int) -> bool:
        return await self.repo.soft_delete(product_id)

    async def get_product_companies_paginated(self, product_id: int, page: int, limit: int) -> tuple[list[CompanyEntity], int]:
        skip = (page - 1) * limit
        return await self.repo.get_product_companies_paginated(product_id, skip, limit)

    async def add_companies(self, product_id: int, company_ids: list[UUID]) -> None:
        if not await self.get_by_id(product_id):
            raise ValueError(f"Product {product_id} not found")
        await self.repo.add_companies(product_id, company_ids)

    async def remove_companies(self, product_id: int, company_ids: list[UUID]) -> None:
        if not await self.get_by_id(product_id):
            raise ValueError(f"Product {product_id} not found")
        await self.repo.remove_companies(product_id, company_ids)