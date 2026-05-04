from typing import Any

from fastapi import status

from app.domains.companies.schemas import (
    AddCompanyProductResponse,
    CreateCompanyResponse,
    GetCompaniesResponse,
    GetCompanyProductsResponse,
    GetCompanyResponse,
    GetCompanyUsersResponse,
    ReplaceCompanyResponse,
    UpdateCompanyResponse,
)
from app.schemas.response import ErrorContent, GenericSuccessContent

create_company_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Company created successfully.",
        "model": CreateCompanyResponse,
    },
    409: {
        "description": "A company with the same tax_id or legal_name already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

create_company_swagger: dict[str, Any] = {
    "summary": "Create a new company",
    "description": (
        "Registers a new company in the system. "
        "Returns 409 if a company with the same tax_id or legal_name already exists."
    ),
    "status_code": status.HTTP_201_CREATED,
    "response_model": CreateCompanyResponse,
    "responses": create_company_responses,
}

get_companies_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Paginated list of companies retrieved successfully.",
        "model": GetCompaniesResponse,
    },
}

get_companies_swagger: dict[str, Any] = {
    "summary": "List companies",
    "description": "Returns a paginated list of companies.",
    "response_model": GetCompaniesResponse,
    "responses": get_companies_responses,
}

get_company_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Company retrieved successfully.",
        "model": GetCompanyResponse,
    },
    404: {
        "description": "Company not found.",
        "model": ErrorContent,
    },
}

get_company_swagger: dict[str, Any] = {
    "summary": "Get a company by ID",
    "description": "Returns a single company by its UUID.",
    "response_model": GetCompanyResponse,
    "responses": get_company_responses,
}

replace_company_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Company replaced successfully.",
        "model": ReplaceCompanyResponse,
    },
    404: {
        "description": "Company not found.",
        "model": ErrorContent,
    },
    409: {
        "description": "A company with the same tax_id or legal_name already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

replace_company_swagger: dict[str, Any] = {
    "summary": "Replace a company",
    "description": "Fully replaces all fields of an existing company.",
    "response_model": ReplaceCompanyResponse,
    "responses": replace_company_responses,
}

update_company_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Company updated successfully.",
        "model": UpdateCompanyResponse,
    },
    404: {
        "description": "Company not found.",
        "model": ErrorContent,
    },
    409: {
        "description": "A company with the same tax_id or legal_name already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

update_company_swagger: dict[str, Any] = {
    "summary": "Partially update a company",
    "description": "Updates only the provided fields of an existing company.",
    "response_model": UpdateCompanyResponse,
    "responses": update_company_responses,
}

soft_delete_company_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Company soft-deleted successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Company not found.",
        "model": ErrorContent,
    },
}

soft_delete_company_swagger: dict[str, Any] = {
    "summary": "Soft-delete a company",
    "description": "Marks a company as deleted without removing it from the database.",
    "response_model": GenericSuccessContent[None],
    "responses": soft_delete_company_responses,
}

add_products_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Products added to the company successfully.",
        "model": AddCompanyProductResponse,
    },
    404: {
        "description": "Company or one of the referenced products not found.",
        "model": ErrorContent,
    },
    409: {
        "description": "One or more products are already associated with this company.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

add_products_swagger: dict[str, Any] = {
    "summary": "Add products to a company",
    "description": "Associates one or more products with an existing company.",
    "status_code": status.HTTP_201_CREATED,
    "response_model": AddCompanyProductResponse,
    "responses": add_products_responses,
}

remove_products_batch_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Products removed from the company successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Company or one of the referenced products not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

remove_products_batch_swagger: dict[str, Any] = {
    "summary": "Remove products from a company (batch)",
    "description": "Removes one or more product associations from an existing company.",
    "response_model": GenericSuccessContent[None],
    "responses": remove_products_batch_responses,
}

remove_product_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Product removed from the company successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Company or product association not found.",
        "model": ErrorContent,
    },
}

remove_product_swagger: dict[str, Any] = {
    "summary": "Remove a single product from a company",
    "description": "Removes a specific product association from an existing company.",
    "response_model": GenericSuccessContent[None],
    "responses": remove_product_responses,
}

add_users_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Users assigned to the company successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Company or one of the referenced users not found.",
        "model": ErrorContent,
    },
    409: {
        "description": "One or more users are already assigned to this company.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

add_users_swagger: dict[str, Any] = {
    "summary": "Assign users to a company",
    "description": "Sets the company_id on one or more users, associating them with this company.",
    "response_model": GenericSuccessContent[None],
    "responses": add_users_responses,
}

remove_user_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "User removed from the company successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Company or user not found, or user is not assigned to this company.",
        "model": ErrorContent,
    },
}

remove_user_swagger: dict[str, Any] = {
    "summary": "Remove a user from a company",
    "description": "Clears the company_id on a specific user, disassociating them from company.",
    "response_model": GenericSuccessContent[None],
    "responses": remove_user_responses,
}

remove_users_batch_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Users removed from the company successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Company or one of the referenced users not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

remove_users_batch_swagger: dict[str, Any] = {
    "summary": "Remove users from a company (batch)",
    "description": "Clears the company_id on one or more users, disassociating them from company.",
    "response_model": GenericSuccessContent[None],
    "responses": remove_users_batch_responses,
}

get_company_users_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "List of users belonging to the company.",
        "model": GetCompanyUsersResponse,
    },
    404: {
        "description": "Company not found.",
        "model": ErrorContent,
    },
}

get_company_users_swagger: dict[str, Any] = {
    "summary": "List users of a company",
    "description": "Returns a paginated list of users associated with the given company.",
    "response_model": GetCompanyUsersResponse,
    "responses": get_company_users_responses,
}

get_company_products_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Paginated list of products associated with the company.",
        "model": GetCompanyProductsResponse,
    },
    404: {
        "description": "Company not found.",
        "model": ErrorContent,
    },
}

get_company_products_swagger: dict[str, Any] = {
    "summary": "List products of a company",
    "description": "Returns a paginated list of products associated with the given company.",
    "response_model": GetCompanyProductsResponse,
    "responses": get_company_products_responses,
}
