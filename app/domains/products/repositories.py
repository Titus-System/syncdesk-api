from typing import Any
from uuid import UUID
from datetime import datetime, UTC
from sqlalchemy import select, update, delete, exc, func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.products.entities import Product as ProductEntity
from app.domains.products.models import Product as ProductModel
from app.domains.companies.models import Company as CompanyModel, company_products
from app.domains.companies.entities import Company as CompanyEntity
from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.products.schemas import CreateProductDTO, UpdateProductDTO, ReplaceProductDTO
from app.core.schemas import PaginatedItems

class ProductRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_entity(self, model: ProductModel) -> ProductEntity:
        return ProductEntity(
            id=model.id,
            name=model.name,
            # VS Code Strict Fix: A Entidade exige 'str', mas o model aceita nulo.
            description=model.description or "", 
            created_at=model.created_at,
        )

    def _to_company_entity(self, model: CompanyModel) -> CompanyEntity:
        return CompanyEntity(
            id=model.id,
            legal_name=model.legal_name,
            tax_id=model.tax_id,
            created_at=model.created_at,
            trade_name=model.trade_name,
        )

    async def create(self, dto: CreateProductDTO) -> ProductEntity:
        try:
            model = ProductModel(**dto.model_dump())
            self.db.add(model)
            await self.db.flush()
            await self.db.commit()
            return self._to_entity(model)
        except exc.IntegrityError as e:
            await self.db.rollback()
            raise ResourceAlreadyExistsError("Product", dto.name) from e

    async def get_by_id(self, product_id: int) -> ProductEntity | None:
        result = await self.db.execute(
            select(ProductModel).where(ProductModel.id == product_id, ProductModel.deleted_at.is_(None))
        )
        model = result.scalar_one_or_none()
        return self._to_entity(model) if model else None

    async def get_all_paginated(self, skip: int, limit: int) -> PaginatedItems[ProductEntity]:
        total_result = await self.db.execute(
            select(func.count(ProductModel.id)).select_from(ProductModel).where(ProductModel.deleted_at.is_(None))
        )
        total = total_result.scalar_one() or 0

        result = await self.db.execute(
            select(ProductModel)
            .where(ProductModel.deleted_at.is_(None))
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

    async def update(self, product_id: int, dto: UpdateProductDTO | ReplaceProductDTO) -> ProductEntity | None:
        try:
            update_data = dto.model_dump(exclude_unset=True)
            # Evita o CompileError do SQLAlchemy caso não existam dados a atualizar
            if not update_data:
                return await self.get_by_id(product_id)

            result = await self.db.execute(
                update(ProductModel)
                .where(ProductModel.id == product_id, ProductModel.deleted_at.is_(None))
                .values(**update_data)
                .returning(ProductModel)
            )
            model = result.scalar_one_or_none()
            if model:
                await self.db.commit()
                return self._to_entity(model)
            return None
        except exc.IntegrityError as e:
            await self.db.rollback()
            raise ResourceAlreadyExistsError("Product", "name") from e

    async def soft_delete(self, product_id: int) -> bool:
        result = await self.db.execute(
            update(ProductModel)
            .where(ProductModel.id == product_id, ProductModel.deleted_at.is_(None))
            .values(deleted_at=datetime.now(UTC).replace(tzinfo=None))
            .returning(ProductModel.id)
        )
        model_id = result.scalar_one_or_none()
        if model_id:
            await self.db.commit()
            return True
        return False

    async def get_product_companies_paginated(self, product_id: int, skip: int, limit: int) -> tuple[list[CompanyEntity], int]:
        total_result = await self.db.execute(
            select(func.count(CompanyModel.id))
            .select_from(CompanyModel)
            .join(company_products, CompanyModel.id == company_products.c.company_id)
            .where(company_products.c.product_id == product_id, CompanyModel.deleted_at.is_(None))
        )
        total = total_result.scalar_one() or 0

        result = await self.db.execute(
            select(CompanyModel)
            .join(company_products, CompanyModel.id == company_products.c.company_id)
            .where(company_products.c.product_id == product_id, CompanyModel.deleted_at.is_(None))
            .offset(skip)
            .limit(limit)
        )
        models = result.scalars().all()
        return [self._to_company_entity(m) for m in models], total

    async def add_companies(self, product_id: int, company_ids: list[UUID]) -> None:
        if not company_ids:
            return
        from datetime import timedelta
        now = datetime.now(UTC).replace(tzinfo=None)
        future = now + timedelta(days=365)
        
        values: list[dict[str, Any]] = [
            {"company_id": cid, "product_id": product_id, "bought_at": now, "support_until": future}
            for cid in set(company_ids)
        ]

        try:
            await self.db.execute(pg_insert(company_products).values(values).on_conflict_do_nothing())
            await self.db.commit()
        except exc.IntegrityError as e:
            await self.db.rollback()
            raise ValueError("One or more company_ids do not exist") from e

    async def remove_companies(self, product_id: int, company_ids: list[UUID]) -> None:
        if not company_ids:
            return
        await self.db.execute(
            delete(company_products)
            .where(company_products.c.product_id == product_id, company_products.c.company_id.in_(company_ids))
        )
        await self.db.commit()