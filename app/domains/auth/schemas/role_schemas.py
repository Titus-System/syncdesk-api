import re

from pydantic import BaseModel, field_validator


def validate_role_name(name: str) -> str:
    role_name_re = re.compile(r"^[A-Za-z_]{3,}$")
    if not role_name_re.match(name):
        raise ValueError(
            "Role name can have only letters and _ and cannot have less than 3 characters."
        )
    return name


class CreateRoleDTO(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_role_name(value)


class ReplaceRoleDTO(CreateRoleDTO):
    pass


class UpdateRoleDTO(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            return validate_role_name(value)
        return value


class AddRolePermissionsDTO(BaseModel):
    ids: list[int]
