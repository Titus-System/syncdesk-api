from typing import Annotated

from fastapi import Depends
from app.infra.email.resend_service import ResendEmailService
from app.core.email.strategy import EmailStrategy

from .response import (
    ResponseFactory,
    WSResponseFactory,
    get_response_factory,
    get_ws_response_factory,
)
from .security import JWTService, PasswordSecurity, ResetTokenSecurity


def get_jwt_service() -> JWTService:
    return JWTService()


def get_password_security() -> PasswordSecurity:
    return PasswordSecurity()


def get_email_service() -> EmailStrategy:
    return ResendEmailService()

def get_reset_token_security() -> ResetTokenSecurity:
    return ResetTokenSecurity()


ResponseFactoryDep = Annotated[ResponseFactory, Depends(get_response_factory)]
JWTServiceDep = Annotated[JWTService, Depends(get_jwt_service)]
PasswordSecurityDep = Annotated[PasswordSecurity, Depends(get_password_security)]
ResetTokenSecurityDep = Annotated[ResetTokenSecurity, Depends(get_reset_token_security)]
EmailServiceDep = Annotated[EmailStrategy, Depends(get_email_service)]

WSResponseFactoryDep = Annotated[WSResponseFactory, Depends(get_ws_response_factory)]
