from uuid import UUID
from pydantic import Field, model_validator, ConfigDict
from app.core.schemas import BaseDTO
from app.domains.auth.enums import OAuthProvider

class CreateUserDTO(BaseDTO):
    email: str
    password_hash: str | None = None
    username: str | None = None
    name: str | None = None
    oauth_provider: OAuthProvider | None = None
    oauth_provider_id: str | None = None
    company_id: UUID | None = None
    is_active: bool = True
    is_verified: bool = False
    must_change_password: bool = False
    must_accept_terms: bool = True
    role_ids: list[int] = []

    @model_validator(mode="after")
    def validate_auth_method(self) -> "CreateUserDTO":
        has_password = self.password_hash is not None
        has_oauth = self.oauth_provider is not None and self.oauth_provider_id is not None
        if not has_password and not has_oauth:
            raise ValueError("User must have either password or OAuth provider.")
        return self

class UpdateUserDTO(BaseDTO):
    email: str | None = None
    password_hash: str | None = None
    username: str | None = None
    name: str | None = None
    oauth_provider: OAuthProvider | None = None
    oauth_provider_id: str | None = None
    is_active: bool | None = None
    is_verified: bool | None = None

class ReplaceUserDTO(CreateUserDTO):
    pass

class AddUserRolesDTO(BaseDTO):
    role_ids: list[int]

class RemoveUserRolesDTO(BaseDTO):
    role_ids: list[int] = Field(default_factory=list[int])

class UpdateUserRolesDTO(BaseDTO):
    add_role_ids: list[int] = Field(default_factory=list[int])
    remove_role_ids: list[int] = Field(default_factory=list[int])

    @model_validator(mode="after")
    def validate_no_intersection(self) -> "UpdateUserRolesDTO":
        inter = set(self.add_role_ids) & set(self.remove_role_ids)
        if inter:
            raise ValueError(f"No role can be in both add and remove fields. Roles {inter} are in both.")
        return self

    @model_validator(mode="after")
    def validate_field_size(self) -> "UpdateUserRolesDTO":
        limit = 10
        errors: list[str] = []
        if len(self.add_role_ids) > limit:
            errors.append("add_role_ids")
        if len(self.remove_role_ids) > limit:
            errors.append("remove_role_ids")
        if errors:
            raise ValueError(f"{' and '.join(errors)} exceed the limit of {limit} roles")
        return self

class UserCompliance(BaseDTO):
    must_change_password: bool
    must_accept_terms: bool

class RoleResponseDTO(BaseDTO):
    id: int
    name: str
    description: str | None = None
    
    model_config = ConfigDict(from_attributes=True)

class UserResponseDTO(BaseDTO):
    id: UUID
    email: str
    username: str | None = None
    name: str | None = None
    oauth_provider: OAuthProvider | None = None
    oauth_provider_id: str | None = None
    company_id: UUID | None = None
    is_active: bool
    is_verified: bool
    must_change_password: bool
    must_accept_terms: bool
    roles: list[RoleResponseDTO] | None = None

    model_config = ConfigDict(from_attributes=True)