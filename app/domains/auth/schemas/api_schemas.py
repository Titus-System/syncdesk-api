import re

from pydantic import BaseModel, EmailStr, field_validator


class UserCreatedResponse(BaseModel):
    id: str
    email: str
    username: str
    access_token: str
    refresh_token: str


class RefreshSessionRequest(BaseModel):
    refresh_token: str


class RefreshSessionResponse(BaseModel):
    access_token: str
    refresh_token: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str


class RegisterUserRequest(BaseModel):
    email: EmailStr
    username: str
    password: str

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
