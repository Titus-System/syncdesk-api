import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains.companies.repositories import CompanyRepository
from app.domains.companies.schemas import CreateCompanyDTO

@pytest.mark.asyncio
async def test_create_and_get_company(db_session: AsyncSession) -> None:
    repo = CompanyRepository(db_session)
    dto = CreateCompanyDTO(
        legal_name="Test Company LTDA",
        trade_name="Test Company",
        tax_id="12345678901234"
    )
    
    # Test Create
    company = await repo.create(dto)
    assert company.id is not None
    assert company.legal_name == "Test Company LTDA"
    
    # Test Get
    fetched_company = await repo.get_by_id(company.id)
    assert fetched_company is not None
    assert fetched_company.tax_id == "12345678901234"

@pytest.mark.asyncio
async def test_soft_delete_company(db_session: AsyncSession) -> None:
    repo = CompanyRepository(db_session)
    dto = CreateCompanyDTO(legal_name="Delete Me", trade_name="Delete", tax_id="00000000000000")
    company = await repo.create(dto)
    
    success = await repo.soft_delete(company.id)
    assert success is True
    
    # Deve retornar None após soft delete
    deleted_company = await repo.get_by_id(company.id)
    assert deleted_company is None