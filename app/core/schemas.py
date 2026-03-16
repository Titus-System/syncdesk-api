from pydantic import BaseModel


class BaseDTO(BaseModel):
    model_config = {"extra": "forbid"}
