from typing import Any
from uuid import UUID
from app.domains.companies.repositories import CompanyRepository
from app.domains.companies.entities import Company as CompanyEntity
from app.domains.companies.schemas import CreateCompanyDTO, UpdateCompanyDTO, ReplaceCompanyDTO
from app.core.schemas import PaginatedItems
from app.domains.products.entities import Product

class CompanyService:
    def __init__(self, repo: CompanyRepository) -> None:
        self.repo = repo

    async def create(self, dto: CreateCompanyDTO) -> CompanyEntity:
        return await self.repo.create(dto)

    async def get_by_id(self, company_id: UUID) -> CompanyEntity | None:
        return await self.repo.get_by_id(company_id)

    async def get_all_paginated(self, page: int, limit: int) -> PaginatedItems[CompanyEntity]:
        skip = (page - 1) * limit
        return await self.repo.get_all_paginated(skip, limit)

    async def update(self, company_id: UUID, dto: UpdateCompanyDTO | ReplaceCompanyDTO) -> CompanyEntity | None:
        return await self.repo.update(company_id, dto)

    async def soft_delete(self, company_id: UUID) -> bool:
        return await self.repo.soft_delete(company_id)
    
    async def get_company_products_paginated(
        self, company_id: UUID, page: int, limit: int
    ) -> PaginatedItems[Product] | None:
        if not await self.get_by_id(company_id):
            return None
        skip = (page - 1) * limit
        return await self.repo.get_company_products_paginated(company_id, skip, limit)

    async def associate_users(self, company_id: UUID, user_ids: list[UUID]) -> None:
        if not await self.get_by_id(company_id):
            raise ValueError(f"Company {company_id} not found")
        await self.repo.associate_users(company_id, user_ids)

    async def disassociate_users(self, company_id: UUID, user_ids: list[UUID]) -> None:
        if not await self.get_by_id(company_id):
            raise ValueError(f"Company {company_id} not found")
        await self.repo.disassociate_users(company_id, user_ids)

    async def get_company_users_paginated(self, company_id: UUID, page: int, limit: int) -> tuple[list[Any], int]:
        skip = (page - 1) * limit
        return await self.repo.get_company_users_paginated(company_id, skip, limit)

    async def add_products(self, company_id: UUID, product_ids: list[int]) -> None:
        if not await self.get_by_id(company_id):
            raise ValueError(f"Company {company_id} not found")
        await self.repo.add_products(company_id, product_ids)

    async def remove_products(self, company_id: UUID, product_ids: list[int]) -> None:
        if not await self.get_by_id(company_id):
            raise ValueError(f"Company {company_id} not found")
        await self.repo.remove_products(company_id, product_ids)