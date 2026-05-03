import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from app.domains.products.repositories import ProductRepository
from app.domains.products.schemas import CreateProductDTO

@pytest.mark.asyncio
async def test_create_and_get_product(db_session: AsyncSession) -> None:
    repo = ProductRepository(db_session)
    dto = CreateProductDTO(
        name="Test Product X",
        description="A great product for testing"
    )
    
    # Test Create
    product = await repo.create(dto)
    assert product.id is not None
    assert product.name == "Test Product X"
    
    # Test Get
    fetched_product = await repo.get_by_id(product.id)
    assert fetched_product is not None
    assert fetched_product.description == "A great product for testing"