from typing import Annotated

from fastapi import Depends

from .response import ResponseFactory, get_response_factory
from .security import JWTService, PasswordSecurity


def get_jwt_service() -> JWTService:
    return JWTService()


def get_password_security() -> PasswordSecurity:
    return PasswordSecurity()


ResponseFactoryDep = Annotated[ResponseFactory, Depends(get_response_factory)]
JWTServiceDep = Annotated[JWTService, Depends(get_jwt_service)]
PasswordSecurityDep = Annotated[PasswordSecurity, Depends(get_password_security)]
