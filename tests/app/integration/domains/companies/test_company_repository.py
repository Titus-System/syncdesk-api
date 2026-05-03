from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.exceptions import ResourceAlreadyExistsError
from app.domains.auth.models import Role as RoleModel
from app.domains.auth.models import User as UserModel
from app.domains.auth.models import user_roles
from app.domains.companies.repositories import CompanyRepository
from app.domains.companies.schemas import (
    CreateCompanyDTO,
    ReplaceCompanyDTO,
    UpdateCompanyDTO,
)
from app.domains.products.models import Product as ProductModel


def _tax_id() -> str:
    return uuid4().hex[:14]


def _legal_name(prefix: str = "Company") -> str:
    return f"{prefix} {uuid4().hex[:8]} LTDA"


async def _make_user(
    db: AsyncSession, *, company_id: UUID | None = None, email: str | None = None
) -> UserModel:
    user = UserModel(
        email=email or f"u_{uuid4().hex[:8]}@example.com",
        password_hash="hash",
        company_id=company_id,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_product(db: AsyncSession, *, name: str | None = None) -> ProductModel:
    product = ProductModel(name=name or f"P {uuid4().hex[:8]}", description="seed")
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


class TestCompanyDTOs:
    def test_create_company_normalizes_tax_id_stripping_punctuation(self) -> None:
        dto = CreateCompanyDTO(
            legal_name="Acme LTDA",
            trade_name="Acme",
            tax_id="12.345.678/0001-90",
        )
        assert dto.tax_id == "12345678000190"

    def test_create_company_with_short_legal_name_fails(self) -> None:
        with pytest.raises(ValidationError):
            CreateCompanyDTO(legal_name="Ab", trade_name="Acme", tax_id=_tax_id())

    def test_create_company_with_short_tax_id_fails(self) -> None:
        with pytest.raises(ValidationError):
            CreateCompanyDTO(legal_name=_legal_name(), trade_name="Acme", tax_id="123")

    def test_create_company_with_long_tax_id_fails(self) -> None:
        with pytest.raises(ValidationError):
            CreateCompanyDTO(
                legal_name=_legal_name(), trade_name="Acme", tax_id="1" * 20
            )

    def test_update_company_with_all_none_fails(self) -> None:
        with pytest.raises(ValidationError):
            UpdateCompanyDTO()

    def test_update_company_with_single_field_succeeds(self) -> None:
        dto = UpdateCompanyDTO(trade_name="New Trade")
        assert dto.trade_name == "New Trade"
        assert dto.legal_name is None
        assert dto.tax_id is None


class TestCompanyRepository:
    @pytest.fixture
    def company_repo(self, db_session: AsyncSession) -> CompanyRepository:
        return CompanyRepository(db=db_session)

    @pytest.fixture
    async def company(self, company_repo: CompanyRepository) -> object:
        return await company_repo.create(
            CreateCompanyDTO(
                legal_name=_legal_name(), trade_name="Acme", tax_id=_tax_id()
            )
        )

    # ── create ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_company_success(self, company_repo: CompanyRepository) -> None:
        dto = CreateCompanyDTO(
            legal_name=_legal_name(), trade_name="Acme", tax_id=_tax_id()
        )
        company = await company_repo.create(dto)
        assert company.id is not None
        assert company.legal_name == dto.legal_name
        assert company.tax_id == dto.tax_id
        assert company.trade_name == "Acme"
        assert company.created_at is not None

    @pytest.mark.asyncio
    async def test_create_with_duplicate_tax_id_raises(
        self, company_repo: CompanyRepository
    ) -> None:
        tax_id = _tax_id()
        await company_repo.create(
            CreateCompanyDTO(legal_name=_legal_name("A"), trade_name="Acme", tax_id=tax_id)
        )
        with pytest.raises(ResourceAlreadyExistsError):
            await company_repo.create(
                CreateCompanyDTO(
                    legal_name=_legal_name("B"), trade_name="Beta", tax_id=tax_id
                )
            )

    @pytest.mark.asyncio
    async def test_create_with_duplicate_legal_name_raises(
        self, company_repo: CompanyRepository
    ) -> None:
        legal_name = _legal_name()
        await company_repo.create(
            CreateCompanyDTO(legal_name=legal_name, trade_name="Acme", tax_id=_tax_id())
        )
        with pytest.raises(ResourceAlreadyExistsError):
            await company_repo.create(
                CreateCompanyDTO(
                    legal_name=legal_name, trade_name="Beta", tax_id=_tax_id()
                )
            )

    # ── get_by_id ─────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_when_not_found(
        self, company_repo: CompanyRepository
    ) -> None:
        assert await company_repo.get_by_id(uuid4()) is None

    @pytest.mark.asyncio
    async def test_get_by_id_returns_none_for_soft_deleted(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        assert await company_repo.soft_delete(company.id) is True  # type: ignore[attr-defined]
        assert await company_repo.get_by_id(company.id) is None  # type: ignore[attr-defined]

    # ── get_all_paginated ─────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_all_paginated_returns_total_and_items(
        self, company_repo: CompanyRepository
    ) -> None:
        for _ in range(3):
            await company_repo.create(
                CreateCompanyDTO(
                    legal_name=_legal_name(), trade_name="Acme", tax_id=_tax_id()
                )
            )
        result = await company_repo.get_all_paginated(skip=0, limit=10)
        assert result.total == 3
        assert len(result.items) == 3
        assert result.page == 1
        assert result.limit == 10

    @pytest.mark.asyncio
    async def test_get_all_paginated_excludes_soft_deleted(
        self, company_repo: CompanyRepository
    ) -> None:
        kept = await company_repo.create(
            CreateCompanyDTO(
                legal_name=_legal_name("kept"), trade_name="Kept", tax_id=_tax_id()
            )
        )
        deleted = await company_repo.create(
            CreateCompanyDTO(
                legal_name=_legal_name("del"), trade_name="Del", tax_id=_tax_id()
            )
        )
        await company_repo.soft_delete(deleted.id)

        result = await company_repo.get_all_paginated(skip=0, limit=10)
        assert result.total == 1
        assert [c.id for c in result.items] == [kept.id]

    @pytest.mark.asyncio
    async def test_get_all_paginated_pagination_skip_and_limit(
        self, company_repo: CompanyRepository
    ) -> None:
        for _ in range(5):
            await company_repo.create(
                CreateCompanyDTO(
                    legal_name=_legal_name(), trade_name="Acme", tax_id=_tax_id()
                )
            )
        page = await company_repo.get_all_paginated(skip=2, limit=2)
        assert page.total == 5
        assert len(page.items) == 2
        assert page.page == 2
        assert page.limit == 2

    # ── update ────────────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_partial_fields(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        updated = await company_repo.update(
            company.id, UpdateCompanyDTO(trade_name="Renamed")  # type: ignore[attr-defined]
        )
        assert updated is not None
        assert updated.trade_name == "Renamed"
        assert updated.legal_name == company.legal_name  # type: ignore[attr-defined]
        assert updated.tax_id == company.tax_id  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_replace_company_overwrites_fields(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        new_name = _legal_name("replaced")
        new_tax = _tax_id()
        replaced = await company_repo.update(
            company.id,  # type: ignore[attr-defined]
            ReplaceCompanyDTO(legal_name=new_name, trade_name="Replaced", tax_id=new_tax),
        )
        assert replaced is not None
        assert replaced.legal_name == new_name
        assert replaced.tax_id == new_tax
        assert replaced.trade_name == "Replaced"

    @pytest.mark.asyncio
    async def test_update_returns_none_when_not_found(
        self, company_repo: CompanyRepository
    ) -> None:
        result = await company_repo.update(
            uuid4(), UpdateCompanyDTO(trade_name="Nope")
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_update_with_duplicate_tax_id_raises(
        self, company_repo: CompanyRepository
    ) -> None:
        existing_tax = _tax_id()
        await company_repo.create(
            CreateCompanyDTO(
                legal_name=_legal_name("A"), trade_name="Acme", tax_id=existing_tax
            )
        )
        target = await company_repo.create(
            CreateCompanyDTO(
                legal_name=_legal_name("B"), trade_name="Beta", tax_id=_tax_id()
            )
        )
        with pytest.raises(ResourceAlreadyExistsError):
            await company_repo.update(
                target.id, UpdateCompanyDTO(tax_id=existing_tax)
            )

    # ── soft_delete ───────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_soft_delete_returns_true_first_time(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        assert await company_repo.soft_delete(company.id) is True  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_soft_delete_already_deleted_returns_false(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        await company_repo.soft_delete(company.id)  # type: ignore[attr-defined]
        assert await company_repo.soft_delete(company.id) is False  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_soft_delete_unknown_id_returns_false(
        self, company_repo: CompanyRepository
    ) -> None:
        assert await company_repo.soft_delete(uuid4()) is False

    # ── associate_users / disassociate_users ──────────────────────────

    @pytest.mark.asyncio
    async def test_associate_users_sets_company_id(
        self,
        company_repo: CompanyRepository,
        db_session: AsyncSession,
        company: object,
    ) -> None:
        user = await _make_user(db_session)
        await company_repo.associate_users(company.id, [user.id])  # type: ignore[attr-defined]

        result = await db_session.execute(
            select(UserModel).where(UserModel.id == user.id)
        )
        refreshed = result.scalar_one()
        assert refreshed.company_id == company.id  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_associate_users_with_empty_list_is_noop(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        # Não deve levantar nem persistir nada
        await company_repo.associate_users(company.id, [])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_disassociate_users_clears_only_company_users(
        self,
        company_repo: CompanyRepository,
        db_session: AsyncSession,
        company: object,
    ) -> None:
        other_company = await company_repo.create(
            CreateCompanyDTO(
                legal_name=_legal_name("other"), trade_name="Other", tax_id=_tax_id()
            )
        )
        own_user = await _make_user(db_session, company_id=company.id)  # type: ignore[attr-defined]
        outsider = await _make_user(db_session, company_id=other_company.id)

        await company_repo.disassociate_users(
            company.id, [own_user.id, outsider.id]  # type: ignore[attr-defined]
        )

        result = await db_session.execute(
            select(UserModel).where(UserModel.id.in_([own_user.id, outsider.id]))
        )
        users_by_id = {u.id: u for u in result.scalars().all()}
        assert users_by_id[own_user.id].company_id is None
        assert users_by_id[outsider.id].company_id == other_company.id

    # ── get_company_users_paginated ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_company_users_paginated_loads_roles_eagerly(
        self,
        company_repo: CompanyRepository,
        db_session: AsyncSession,
        company: object,
    ) -> None:
        role = RoleModel(name=f"role_{uuid4().hex[:8]}")
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

        user = await _make_user(db_session, company_id=company.id)  # type: ignore[attr-defined]
        await db_session.execute(
            user_roles.insert().values(user_id=user.id, role_id=role.id)
        )
        await db_session.commit()

        users, total = await company_repo.get_company_users_paginated(
            company.id, skip=0, limit=10  # type: ignore[attr-defined]
        )
        assert total == 1
        assert len(users) == 1
        # Acesso a .roles não pode disparar lazy load (regressão do MissingGreenlet)
        assert len(users[0].roles) == 1
        assert users[0].roles[0].id == role.id

    @pytest.mark.asyncio
    async def test_get_company_users_paginated_excludes_other_companies(
        self,
        company_repo: CompanyRepository,
        db_session: AsyncSession,
        company: object,
    ) -> None:
        other_company = await company_repo.create(
            CreateCompanyDTO(
                legal_name=_legal_name("other"), trade_name="Other", tax_id=_tax_id()
            )
        )
        own_user = await _make_user(db_session, company_id=company.id)  # type: ignore[attr-defined]
        await _make_user(db_session, company_id=other_company.id)

        users, total = await company_repo.get_company_users_paginated(
            company.id, skip=0, limit=10  # type: ignore[attr-defined]
        )
        assert total == 1
        assert [u.id for u in users] == [own_user.id]

    # ── add_products / remove_products ────────────────────────────────

    @pytest.mark.asyncio
    async def test_add_products_creates_relationship(
        self,
        company_repo: CompanyRepository,
        db_session: AsyncSession,
        company: object,
    ) -> None:
        product = await _make_product(db_session)
        await company_repo.add_products(company.id, [product.id])  # type: ignore[attr-defined]

        from app.domains.companies.models import company_products

        result = await db_session.execute(
            select(company_products).where(
                company_products.c.company_id == company.id,  # type: ignore[attr-defined]
                company_products.c.product_id == product.id,
            )
        )
        assert result.first() is not None

    @pytest.mark.asyncio
    async def test_add_products_idempotent_on_duplicate(
        self,
        company_repo: CompanyRepository,
        db_session: AsyncSession,
        company: object,
    ) -> None:
        product = await _make_product(db_session)
        await company_repo.add_products(company.id, [product.id])  # type: ignore[attr-defined]
        # Segunda chamada não deve falhar (on_conflict_do_nothing)
        await company_repo.add_products(company.id, [product.id])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_add_products_with_unknown_id_raises_value_error(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        with pytest.raises(ValueError, match="product_ids"):
            await company_repo.add_products(company.id, [9_999_999])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_add_products_with_empty_list_is_noop(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        await company_repo.add_products(company.id, [])  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_remove_products_success(
        self,
        company_repo: CompanyRepository,
        db_session: AsyncSession,
        company: object,
    ) -> None:
        from app.domains.companies.models import company_products

        product = await _make_product(db_session)
        await company_repo.add_products(company.id, [product.id])  # type: ignore[attr-defined]
        await company_repo.remove_products(company.id, [product.id])  # type: ignore[attr-defined]

        result = await db_session.execute(
            select(company_products).where(
                company_products.c.company_id == company.id,  # type: ignore[attr-defined]
                company_products.c.product_id == product.id,
            )
        )
        assert result.first() is None

    @pytest.mark.asyncio
    async def test_remove_products_with_empty_list_is_noop(
        self, company_repo: CompanyRepository, company: object
    ) -> None:
        await company_repo.remove_products(company.id, [])  # type: ignore[attr-defined]
