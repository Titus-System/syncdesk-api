from uuid import UUID

from pydantic import model_validator

from app.core.schemas import BaseDTO, PaginatedItems
from app.domains.companies.entities import Company
from app.domains.products.entities import Product
from app.schemas.response import GenericSuccessContent


def validate_product_fields(name: str | None, description: str | None) -> None:
    errors: list[str] = []
    if name is not None:
        len_name = len(name)
        if len_name > 127 or len_name < 3:
            errors.append("Product name must be between 3 and 127 characters")

    if description is not None:
        len_desc = len(description)
        if len_desc > 500 or len_desc < 3:
            errors.append("Product description must be between 3 and 500 characters")

    if errors:
        raise ValueError("; ".join(errors))


class CreateProductDTO(BaseDTO):
    name: str
    description: str

    @model_validator(mode="after")
    def validate_fields(self) -> "CreateProductDTO":
        validate_product_fields(self.name, self.description)
        return self


class UpdateProductDTO(BaseDTO):
    name: str | None = None
    description: str | None = None

    @model_validator(mode="after")
    def validate_fields(self) -> "UpdateProductDTO":
        if self.name is None and self.description is None:
            raise ValueError("Product update payload must have at least one valid attribute")
        validate_product_fields(self.name, self.description)
        return self


class ReplaceProductDTO(CreateProductDTO):
    pass


class AddProductToCompaniesDTO(BaseDTO):
    company_ids: list[UUID]


class RemoveProductFromCompaniesDTO(BaseDTO):
    company_ids: list[UUID]


CreateProductResponse = GenericSuccessContent[Product]

GetProductsResponse = GenericSuccessContent[PaginatedItems[Product]]

GetProductResponse = GenericSuccessContent[Product]

ReplaceProductResponse = GenericSuccessContent[Product]

UpdateProductResponse = GenericSuccessContent[Product]

GetProductCompaniesResponse = GenericSuccessContent[PaginatedItems[Company]]
