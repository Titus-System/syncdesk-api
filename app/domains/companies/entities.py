from datetime import datetime
from uuid import UUID

from pydantic.dataclasses import dataclass


@dataclass
class Company:
    id: UUID
    legal_name: str
    tax_id: str
    created_at: datetime
    trade_name: str | None = None


@dataclass
class CompanyProduct:
    company_id: UUID
    product_id: int
    bought_at: datetime
    support_until: datetime
