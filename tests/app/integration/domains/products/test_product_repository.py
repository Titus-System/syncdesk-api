from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.companies.models import Company as CompanyModel
from app.domains.companies.models import company_products
from app.domains.companies.repositories import CompanyRepository
from app.domains.companies.schemas import CreateCompanyDTO
from app.domains.products.repositories import ProductRepository
from app.domains.products.schemas import (
    CreateProductDTO,
    ReplaceProductDTO,
    UpdateProductDTO,
)


def _tax_id() -> str:
    return uuid4().hex[:14]


def _legal_name(prefix: str = "Company") -> str:
    return f"{prefix} {uuid4().hex[:8]} LTDA"


def _product_name(prefix: str = "Product") -> str:
    return f"{prefix} {uuid4().hex[:8]}"


async def _make_company(db: AsyncSession, *, soft_deleted: bool = False) -> CompanyModel:
    repo = CompanyRepository(db=db)
    company = await repo.create(
        CreateCompanyDTO(
            legal_name=_legal_name(), trade_name="Acme", tax_id=_tax_id()
        )
    )
    if soft_deleted:
        await repo.soft_delete(company.id)
    result = await db.execute(select(CompanyModel).where(CompanyModel.id == company.id))
    return result.scalar_one()


class TestProductDTOs:
    def test_create_product_with_short_name_fails(self) -> None:
        with pytest.raises(ValidationError):
            CreateProductDTO(name="ab", description="A valid description")

    def test_create_product_with_short_description_fails(self) -> None:
        with pytest.raises(ValidationError):
            CreateProductDTO(name=_product_name(), description="x")

    def test_update_product_with_all_none_fails(self) -> None:
        with pytest.raises(ValidationError):
            UpdateProductDTO()

    def test_update_product_with_single_field_succeeds(self) -> None:
        dto = UpdateProductDTO(description="A valid new description")
        assert dto.description == "A valid new description"
        assert dto.name is None


class TestProductRepository:
    @pytest.fixture
    def product_repo(self, db_session: AsyncSession) -> ProductRepository:
        return ProductRepository(db=db_session)

    @pytest.fixture
    async def product(self, product_repo: ProductRepository) -> object:
        return await product_repo.create(
            CreateProductDTO(name=_product_name(), description="Initial description")
        )

    # ── create / get_by_id ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_product_success(self, product_repo: ProductRepository) -> None:
        dto = CreateProductDTO(name=_product_name(), description="A great product")
        product = await product_repo.create(dto)
        assert product.id is not None
        assert product.name == dto.name
        assert product.description == "A great product"
        assert product.created_at is not None

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(
        self, product_repo: ProductRepository
    ) -> None:
        assert await product_repo.get_by_id(9_999_999) is None

    @pytest.mark.asyncio
    async def test_get_by_id_excludes_soft_deleted(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        await product_repo.soft_delete(product.id)  # type: ignore[attr-defined]
        assert await product_repo.get_by_id(product.id) is None  # type: ignore[attr-defined]

    # ── get_all_paginated ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_all_paginated_returns_total_and_items(
        self, product_repo: ProductRepository
    ) -> None:
        for _ in range(3):
            await product_repo.create(
                CreateProductDTO(name=_product_name(), description="Some desc")
            )
        result = await product_repo.get_all_paginated(skip=0, limit=10)
        assert result.total == 3
        assert len(result.items) == 3
        assert result.page == 1

    @pytest.mark.asyncio
    async def test_get_all_paginated_excludes_soft_deleted(
        self, product_repo: ProductRepository
    ) -> None:
        kept = await product_repo.create(
            CreateProductDTO(name=_product_name("kept"), description="Some desc")
        )
        deleted = await product_repo.create(
            CreateProductDTO(name=_product_name("del"), description="Some desc")
        )
        await product_repo.soft_delete(deleted.id)

        result = await product_repo.get_all_paginated(skip=0, limit=10)
        assert result.total == 1
        assert [p.id for p in result.items] == [kept.id]

    # ── update ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_partial_fields(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        updated = await product_repo.update(
            product.id, UpdateProductDTO(description="Refreshed description")  # type: ignore[attr-defined]
        )
        assert updated is not None
        assert updated.description == "Refreshed description"
        assert updated.name == product.name  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_replace_product_overwrites_fields(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        new_name = _product_name("replaced")
        replaced = await product_repo.update(
            product.id,  # type: ignore[attr-defined]
            ReplaceProductDTO(name=new_name, description="Brand new description"),
        )
        assert replaced is not None
        assert replaced.name == new_name
        assert replaced.description == "Brand new description"

    @pytest.mark.asyncio
    async def test_update_with_empty_dto_returns_current_state(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        # ProductRepository.update tem um early-return quando exclude_unset() fica vazio
        empty_dto = UpdateProductDTO.model_construct()
        result = await product_repo.update(product.id, empty_dto)  # type: ignore[attr-defined]
        assert result is not None
        assert result.id == product.id  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_update_returns_none_when_not_found(
        self, product_repo: ProductRepository
    ) -> None:
        assert (
            await product_repo.update(
                9_999_999, UpdateProductDTO(description="Anything works")
            )
            is None
        )

    # ── soft_delete ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_soft_delete_returns_true_first_time(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        assert await product_repo.soft_delete(product.id) is True  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_soft_delete_already_deleted_returns_false(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        await product_repo.soft_delete(product.id)  # type: ignore[attr-defined]
        assert await product_repo.soft_delete(product.id) is False  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_soft_delete_unknown_id_returns_false(
        self, product_repo: ProductRepository
    ) -> None:
        assert await product_repo.soft_delete(9_999_999) is False

    # ── get_product_companies_paginated ───────────────────────────────

    @pytest.mark.asyncio
    async def test_get_product_companies_paginated_returns_companies(
        self,
        product_repo: ProductRepository,
        db_session: AsyncSession,
        product: object,
    ) -> None:
        company = await _make_company(db_session)
        await product_repo.add_companies(product.id, [company.id])  # type: ignore[attr-defined]

        companies, total = await product_repo.get_product_companies_paginated(
            product.id, skip=0, limit=10  # type: ignore[attr-defined]
        )
        assert total == 1
        assert len(companies) == 1
        assert companies[0].id == company.id

    @pytest.mark.asyncio
    async def test_get_product_companies_excludes_soft_deleted_companies(
        self,
        product_repo: ProductRepository,
        db_session: AsyncSession,
        product: object,
    ) -> None:
        kept = await _make_company(db_session)
        soft_deleted = await _make_company(db_session)
        await product_repo.add_companies(  # type: ignore[attr-defined]
            product.id, [kept.id, soft_deleted.id]
        )

        repo = CompanyRepository(db=db_session)
        await repo.soft_delete(soft_deleted.id)

        companies, total = await product_repo.get_product_companies_paginated(
            product.id, skip=0, limit=10  # type: ignore[attr-defined]
        )
        assert total == 1
        assert [c.id for c in companies] == [kept.id]

    # ── add_companies / remove_companies ──────────────────────────────

    @pytest.mark.asyncio
    async def test_add_companies_creates_relationship(
        self,
        product_repo: ProductRepository,
        db_session: AsyncSession,
        product: object,
    ) -> None:
        company = await _make_company(db_session)
        await product_repo.add_companies(product.id, [company.id])  # type: ignore[attr-defined]

        result = await db_session.execute(
            select(company_products).where(
                company_products.c.product_id == product.id,  # type: ignore[attr-defined]
                company_products.c.company_id == company.id,
            )
        )
        assert result.first() is not None

    @pytest.mark.asyncio
    async def test_add_companies_idempotent_on_duplicate(
        self,
        product_repo: ProductRepository,
        db_session: AsyncSession,
        product: object,
    ) -> None:
        company = await _make_company(db_session)
        await product_repo.add_companies(product.id, [company.id])  # type: ignore[attr-defined]
        await product_repo.add_companies(product.id, [company.id])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_add_companies_with_unknown_id_raises_value_error(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        with pytest.raises(ValueError, match="company_ids"):
            await product_repo.add_companies(product.id, [uuid4()])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_add_companies_with_empty_list_is_noop(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        await product_repo.add_companies(product.id, [])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_remove_companies_success(
        self,
        product_repo: ProductRepository,
        db_session: AsyncSession,
        product: object,
    ) -> None:
        company = await _make_company(db_session)
        await product_repo.add_companies(product.id, [company.id])  # type: ignore[attr-defined]
        await product_repo.remove_companies(product.id, [company.id])  # type: ignore[attr-defined]

        result = await db_session.execute(
            select(company_products).where(
                company_products.c.product_id == product.id,  # type: ignore[attr-defined]
                company_products.c.company_id == company.id,
            )
        )
        assert result.first() is None

    @pytest.mark.asyncio
    async def test_remove_companies_with_empty_list_is_noop(
        self, product_repo: ProductRepository, product: object
    ) -> None:
        await product_repo.remove_companies(product.id, [])  # type: ignore[attr-defined]
