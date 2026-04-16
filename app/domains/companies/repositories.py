from sqlalchemy.ext.asyncio import AsyncSession

from app.domains.companies.entities import Company as CompanyEntity
from app.domains.companies.models import Company as CompanyModel


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
