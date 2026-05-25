from typing import Annotated

from fastapi import Depends
from app.infra.email.resend_service import ResendEmailService
from app.infra.storage.s3_object_storage import S3ObjectStorage
from app.core.email.strategy import EmailStrategy
from app.core.storage import ObjectStorage

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


def get_object_storage() -> ObjectStorage:
    return S3ObjectStorage()


ResponseFactoryDep = Annotated[ResponseFactory, Depends(get_response_factory)]
JWTServiceDep = Annotated[JWTService, Depends(get_jwt_service)]
PasswordSecurityDep = Annotated[PasswordSecurity, Depends(get_password_security)]
ResetTokenSecurityDep = Annotated[ResetTokenSecurity, Depends(get_reset_token_security)]
EmailServiceDep = Annotated[EmailStrategy, Depends(get_email_service)]
ObjectStorageDep = Annotated[ObjectStorage, Depends(get_object_storage)]

WSResponseFactoryDep = Annotated[WSResponseFactory, Depends(get_ws_response_factory)]
