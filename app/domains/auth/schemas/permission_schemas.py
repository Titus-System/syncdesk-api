import re

from pydantic import BaseModel, field_validator


def validate_permission_name(name: str) -> str:
    role_name_re = re.compile(r"^[a-z_]{3,}:[a-z_]{3,}$")
    if not role_name_re.match(name):
        raise ValueError(
            "Permission name must follow the pattern '<resource>:<action>' "
            "using lowercase letters and '_' with at least 3 characters each."
        )
    return name


class CreatePermissionDTO(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return validate_permission_name(value)


class ReplacePermissionDTO(CreatePermissionDTO):
    pass


class UpdatePermissionDTO(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str | None) -> str | None:
        if value is not None:
            return validate_permission_name(value)
        return value
