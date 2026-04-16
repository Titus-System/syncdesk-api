from app.domains.companies.repositories import CompanyRepository


class CompanyService:
    def __init__(self, repo: CompanyRepository) -> None:
        self.repo = repo
