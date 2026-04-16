from typing import Annotated

from fastapi import Depends

from app.db.postgres.dependencies import PgSessionDep
from app.domains.companies.repositories import CompanyRepository
from app.domains.companies.services import CompanyService


def get_company_repository(db: PgSessionDep) -> CompanyRepository:
    return CompanyRepository(db)


CompanyRepositoryDep = Annotated[CompanyRepository, Depends(get_company_repository)]


def get_company_service(repo: CompanyRepositoryDep) -> CompanyService:
    return CompanyService(repo)


CompanyServiceDep = Annotated[CompanyService, Depends(get_company_service)]
