from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.products.entities import Product as ProductEntity
from app.domains.products.models import Product as ProductModel


class ProductRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _to_entity(self, model: ProductModel) -> ProductEntity:
        return ProductEntity(
            id=model.id,
            name=model.name,
            description=model.description,
            created_at=model.created_at,
        )
