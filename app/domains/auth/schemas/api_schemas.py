import re

from pydantic import BaseModel, EmailStr, Field, field_validator


class UserCreatedResponse(BaseModel):
    id: str
    email: str
    access_token: str
    refresh_token: str
    username: str | None = None


class RefreshSessionRequest(BaseModel):
    refresh_token: str


class RefreshSessionResponse(BaseModel):
    access_token: str
    refresh_token: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    must_change_password: bool = False
    must_accept_terms: bool = False


class RegisterUserRequest(BaseModel):
    email: EmailStr
    password: str
    name: str | None = None
    username: str | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        password_regex = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$")
        if not password_regex.match(v):
            raise ValueError("password must be 8+ chars with upper, lower, number and special char")
        return v


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class AdminRegisterUserRequest(BaseModel):
    email: EmailStr
    name: str | None = None
    role_ids: list[int] = Field(default_factory=list[int])


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        password_regex = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$")
        if not password_regex.match(v):
            raise ValueError("password must be 8+ chars with upper, lower, number and special char")
        return v


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        password_regex = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$")
        if not password_regex.match(v):
            raise ValueError("password must be 8+ chars with upper, lower, number and special char")
        return v
