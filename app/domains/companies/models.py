from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Table, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.postgres.base import Base

if TYPE_CHECKING:
    from app.domains.auth.models import User
    from app.domains.products.models import Product


company_products = Table(
    "company_products",
    Base.metadata,
    Column("company_id", PG_UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True),
    Column("product_id", Integer, ForeignKey("products.id"), primary_key=True),
    Column("bought_at", DateTime, nullable=False, server_default=func.now()),
    Column("support_until", DateTime, nullable=False),
)


class Company(Base):
    __tablename__ = "companies"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    legal_name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    trade_name: Mapped[str] = mapped_column(String(255), unique=False, nullable=True, index=True)
    tax_id: Mapped[str] = mapped_column(String(14), nullable=False, unique=True, index=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    users: Mapped[list[User]] = relationship(back_populates="company")
    products: Mapped[list["Product"]] = relationship(
        secondary=company_products, back_populates="companies"
    )

    def __repr__(self) -> str:
        return f"<Company(id={self.id}, trade_name={self.trade_name})>"
