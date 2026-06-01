from uuid import UUID

from pydantic import model_validator

from app.core.schemas import BaseDTO, PaginatedItems
from app.domains.auth.entities import User
from app.domains.companies.entities import Company, CompanyProduct
from app.domains.products.entities import Product
from app.schemas.response import GenericSuccessContent


def validate_company_fields(
    legal_name: str | None, trade_name: str | None, tax_id: str | None
) -> None:
    errors: list[str] = []

    def check_length(value: str | None, field: str, min_len: int, max_len: int) -> None:
        if value is not None and not (min_len <= len(value) <= max_len):
            errors.append(f"Company {field} must be between {min_len} and {max_len} characters")

    check_length(legal_name, "legal_name", 3, 255)
    check_length(trade_name, "trade_name", 3, 255)
    check_length(tax_id, "tax_id", 11, 14)

    if errors:
        raise ValueError("; ".join(errors))


def normalize_tax_id(tax_id: str) -> str:
    tax_id = tax_id.lower()
    norm = "".join(char for char in tax_id if char.isalnum())
    return norm


class CreateCompanyDTO(BaseDTO):
    legal_name: str
    trade_name: str
    tax_id: str

    @model_validator(mode="after")
    def validate_fields(self) -> "CreateCompanyDTO":
        self.tax_id = normalize_tax_id(self.tax_id)
        validate_company_fields(self.legal_name, self.trade_name, self.tax_id)
        return self


class UpdateCompanyDTO(BaseDTO):
    legal_name: str | None = None
    trade_name: str | None = None
    tax_id: str | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> "UpdateCompanyDTO":
        if self.legal_name is None and self.trade_name is None and self.tax_id is None:
            raise ValueError("Company update payload must have at least one valid attribute")
        if self.tax_id is not None:
            self.tax_id = normalize_tax_id(self.tax_id)
        validate_company_fields(self.legal_name, self.trade_name, self.tax_id)
        return self


class ReplaceCompanyDTO(CreateCompanyDTO):
    pass


class AddCompanyProductDTO(BaseDTO):
    product_ids: list[int]


class RemoveCompanyProductDTO(AddCompanyProductDTO):
    pass


UpdateCompanyResponse = GenericSuccessContent[Company]

ReplaceCompanyResponse = GenericSuccessContent[Company]

AddCompanyProductResponse = GenericSuccessContent[list[CompanyProduct]]

CreateCompanyResponse = GenericSuccessContent[Company]

GetCompaniesResponse = GenericSuccessContent[PaginatedItems[Company]]

GetCompanyResponse = GenericSuccessContent[Company]


class AddCompanyUsersDTO(BaseDTO):
    user_ids: list[UUID]


class RemoveCompanyUsersDTO(AddCompanyUsersDTO):
    pass


GetCompanyUsersResponse = GenericSuccessContent[PaginatedItems[User]]

GetCompanyProductsResponse = GenericSuccessContent[PaginatedItems[Product]]
