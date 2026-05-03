from uuid import UUID
from datetime import datetime, UTC
from sqlalchemy import select, update, delete, exc, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.companies.entities import Company as CompanyEntity
from app.domains.companies.models import Company as CompanyModel, company_products
from app.domains.auth.models import User as UserModel
from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.companies.schemas import CreateCompanyDTO, UpdateCompanyDTO, ReplaceCompanyDTO
from app.core.schemas import PaginatedItems

class CompanyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_entity(self, model: CompanyModel) -> CompanyEntity:
        return CompanyEntity(
            id=model.id,
            legal_name=model.legal_name,
            tax_id=model.tax_id,
            created_at=model.created_at,
            trade_name=model.trade_name,
        )

    async def create(self, dto: CreateCompanyDTO) -> CompanyEntity:
        try:
            model = CompanyModel(**dto.model_dump())
            self.db.add(model)
            await self.db.flush()
            await self.db.commit()
            return self._to_entity(model)
        except exc.IntegrityError as e:
            await self.db.rollback()
            raise ResourceAlreadyExistsError("Company", dto.tax_id) from e

    async def get_by_id(self, company_id: UUID) -> CompanyEntity | None:
        result = await self.db.execute(
            select(CompanyModel).where(CompanyModel.id == company_id, CompanyModel.deleted_at.is_(None))
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_all_paginated(self, skip: int, limit: int) -> PaginatedItems[CompanyEntity]:
        total_result = await self.db.execute(
            select(func.count(CompanyModel.id)).where(CompanyModel.deleted_at.is_(None))
        )
        total = total_result.scalar_one() or 0

        result = await self.db.execute(
            select(CompanyModel)
            .where(CompanyModel.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
        )
        models = result.scalars().all()
        return PaginatedItems(
            items=[self._to_entity(m) for m in models],
            total=total,
            page=(skip // limit) + 1,
            limit=limit
        )

    async def update(self, company_id: UUID, dto: UpdateCompanyDTO | ReplaceCompanyDTO) -> CompanyEntity | None:
        try:
            result = await self.db.execute(
                update(CompanyModel)
                .where(CompanyModel.id == company_id, CompanyModel.deleted_at.is_(None))
                .values(**dto.model_dump(exclude_unset=True))
                .returning(CompanyModel)
            )
            model = result.scalar_one_or_none()
            if model:
                await self.db.commit()
                return self._to_entity(model)
            return None
        except exc.IntegrityError as e:
            await self.db.rollback()
            raise ResourceAlreadyExistsError("Company", "identifier") from e

    async def soft_delete(self, company_id: UUID) -> bool:
        result = await self.db.execute(
            update(CompanyModel)
            .where(CompanyModel.id == company_id, CompanyModel.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC).replace(tzinfo=None))
            .returning(CompanyModel.id)
        )
        model_id = result.scalar_one_or_none()
        if model_id:
            await self.db.commit()
            return True
        return False

    async def associate_users(self, company_id: UUID, user_ids: list[UUID]) -> None:
        if not user_ids:
            return
        await self.db.execute(
            update(UserModel).where(UserModel.id.in_(user_ids)).values(company_id=company_id)
        )
        await self.db.commit()

    async def disassociate_users(self, company_id: UUID, user_ids: list[UUID]) -> None:
        if not user_ids:
            return
        await self.db.execute(
            update(UserModel)
            .where(UserModel.id.in_(user_ids), UserModel.company_id == company_id)
            .values(company_id=None)
        )
        await self.db.commit()

    async def get_company_users_paginated(self, company_id: UUID, skip: int, limit: int) -> tuple[list[UserModel], int]:
        total_result = await self.db.execute(
            select(func.count(UserModel.id)).where(UserModel.company_id == company_id, UserModel.deleted_at.is_(None))
        )
        total = total_result.scalar_one() or 0

        result = await self.db.execute(
            select(UserModel)
            .where(UserModel.company_id == company_id, UserModel.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all()), total

    async def add_products(self, company_id: UUID, product_ids: list[int]) -> None:
        if not product_ids:
            return
        from datetime import timedelta
        now = datetime.now(UTC).replace(tzinfo=None)
        future = now + timedelta(days=365)
        
        values = [
            {"company_id": company_id, "product_id": pid, "bought_at": now, "support_until": future}
            for pid in set(product_ids)
        ]
        
        await self.db.execute(pg_insert(company_products).values(values).on_conflict_do_nothing())
        await self.db.commit()

    async def remove_products(self, company_id: UUID, product_ids: list[int]) -> None:
        if not product_ids:
            return
        await self.db.execute(
            delete(company_products)
            .where(company_products.c.company_id == company_id, company_products.c.product_id.in_(product_ids))
        )
        await self.db.commit()