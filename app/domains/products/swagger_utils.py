from typing import Any

from fastapi import status

from app.domains.products.schemas import (
    CreateProductResponse,
    GetProductCompaniesResponse,
    GetProductResponse,
    GetProductsResponse,
    ReplaceProductResponse,
    UpdateProductResponse,
)
from app.schemas.response import ErrorContent, GenericSuccessContent

# -- POST / ------------------------------------------------------------------

create_product_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Product created successfully.",
        "model": CreateProductResponse,
    },
    409: {
        "description": "A product with the same name already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

create_product_swagger: dict[str, Any] = {
    "summary": "Create a new product",
    "description": "Registers a new product in the catalog.",
    "status_code": status.HTTP_201_CREATED,
    "response_model": CreateProductResponse,
    "responses": create_product_responses,
}

# -- GET / -------------------------------------------------------------------

get_products_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Paginated list of products retrieved successfully.",
        "model": GetProductsResponse,
    },
}

get_products_swagger: dict[str, Any] = {
    "summary": "List products",
    "description": "Returns a paginated list of products.",
    "response_model": GetProductsResponse,
    "responses": get_products_responses,
}

# -- GET /{product_id} -------------------------------------------------------

get_product_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Product retrieved successfully.",
        "model": GetProductResponse,
    },
    404: {
        "description": "Product not found.",
        "model": ErrorContent,
    },
}

get_product_swagger: dict[str, Any] = {
    "summary": "Get a product by ID",
    "description": "Returns a single product by its ID.",
    "response_model": GetProductResponse,
    "responses": get_product_responses,
}

# -- PUT /{product_id} -------------------------------------------------------

replace_product_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Product replaced successfully.",
        "model": ReplaceProductResponse,
    },
    404: {
        "description": "Product not found.",
        "model": ErrorContent,
    },
    409: {
        "description": "A product with the same name already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

replace_product_swagger: dict[str, Any] = {
    "summary": "Replace a product",
    "description": "Fully replaces all fields of an existing product.",
    "response_model": ReplaceProductResponse,
    "responses": replace_product_responses,
}

# -- PATCH /{product_id} -----------------------------------------------------

update_product_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Product updated successfully.",
        "model": UpdateProductResponse,
    },
    404: {
        "description": "Product not found.",
        "model": ErrorContent,
    },
    409: {
        "description": "A product with the same name already exists.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

update_product_swagger: dict[str, Any] = {
    "summary": "Partially update a product",
    "description": "Updates only the provided fields of an existing product.",
    "response_model": UpdateProductResponse,
    "responses": update_product_responses,
}

# -- DELETE /{product_id} ----------------------------------------------------

soft_delete_product_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Product soft-deleted successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Product not found.",
        "model": ErrorContent,
    },
}

soft_delete_product_swagger: dict[str, Any] = {
    "summary": "Soft-delete a product",
    "description": "Marks a product as deleted without removing it from the database.",
    "response_model": GenericSuccessContent[None],
    "responses": soft_delete_product_responses,
}

# -- POST /{product_id}/companies --------------------------------------------

add_companies_responses: dict[int | str, dict[str, Any]] = {
    201: {
        "description": "Companies associated with the product successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Product or one of the referenced companies not found.",
        "model": ErrorContent,
    },
    409: {
        "description": "One or more companies are already associated with this product.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

add_companies_swagger: dict[str, Any] = {
    "summary": "Add companies to a product",
    "description": "Associates one or more companies with an existing product.",
    "status_code": status.HTTP_201_CREATED,
    "response_model": GenericSuccessContent[None],
    "responses": add_companies_responses,
}

# -- DELETE /{product_id}/companies ------------------------------------------

remove_companies_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Companies removed from the product successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Product or one of the referenced companies not found.",
        "model": ErrorContent,
    },
    422: {
        "description": "Request body validation failed.",
        "model": ErrorContent,
    },
}

remove_companies_swagger: dict[str, Any] = {
    "summary": "Remove companies from a product",
    "description": "Removes one or more company associations from an existing product.",
    "response_model": GenericSuccessContent[None],
    "responses": remove_companies_responses,
}

# -- DELETE /{product_id}/companies/{company_id} -----------------------------

remove_company_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Company removed from the product successfully.",
        "model": GenericSuccessContent[None],
    },
    404: {
        "description": "Product or company association not found.",
        "model": ErrorContent,
    },
}

remove_company_swagger: dict[str, Any] = {
    "summary": "Remove a single company from a product",
    "description": "Removes a specific company association from an existing product.",
    "response_model": GenericSuccessContent[None],
    "responses": remove_company_responses,
}

# -- GET /{product_id}/companies ---------------------------------------------

get_product_companies_responses: dict[int | str, dict[str, Any]] = {
    200: {
        "description": "Paginated list of companies associated with the product.",
        "model": GetProductCompaniesResponse,
    },
    404: {
        "description": "Product not found.",
        "model": ErrorContent,
    },
}

get_product_companies_swagger: dict[str, Any] = {
    "summary": "List companies of a product",
    "description": "Returns a paginated list of companies associated with the given product.",
    "response_model": GetProductCompaniesResponse,
    "responses": get_product_companies_responses,
}
