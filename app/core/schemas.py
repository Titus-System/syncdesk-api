from pydantic import BaseModel


class BaseDTO(BaseModel):
    model_config = {"extra": "forbid"}


class PaginatedItems[T](BaseModel):
    total: int
    page: int
    limit: int
    items: list[T]
