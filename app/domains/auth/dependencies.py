from typing import Annotated, Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.dependencies import JWTServiceDep, PasswordSecurityDep
from app.core.exceptions import AppHTTPException
from app.db.postgres.dependencies import PgSessionDep

from .entities import Permission, Session, UserWithRoles
from .exceptions import (
    InvalidCredentialsError,
    InvalidSessionError,
    SessionNotFoundError,
    UserNotFoundError,
)
from .repositories.permission_repository import PermissionRepository
from .repositories.role_repository import RoleRepository
from .repositories.session_repository import SessionRepository
from .repositories.user_repository import UserRepository
from .services.auth_service import AuthService
from .services.permission_service import PermissionService
from .services.role_service import RoleService
from .services.session_service import SessionService
from .services.user_service import UserService

bearer_scheme = HTTPBearer()


# ============================================================
# Repositories
# ============================================================
def get_role_repository(db: PgSessionDep) -> RoleRepository:
    return RoleRepository(db)


def get_permission_repository(db: PgSessionDep) -> PermissionRepository:
    return PermissionRepository(db)


def get_user_repository(db: PgSessionDep) -> UserRepository:
    return UserRepository(db)


def get_session_repository(db: PgSessionDep) -> SessionRepository:
    return SessionRepository(db)


# ============================================================
# Services
# ============================================================
def get_role_service(
    role_repo: Annotated[RoleRepository, Depends(get_role_repository)],
) -> RoleService:
    return RoleService(role_repo)


def get_permission_service(
    permission_repo: Annotated[PermissionRepository, Depends(get_permission_repository)],
) -> PermissionService:
    return PermissionService(permission_repo)


def get_user_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserService:
    return UserService(user_repo)


def get_session_service(
    db: PgSessionDep,
    session_repo: Annotated[SessionRepository, Depends(get_session_repository)],
    jwt_service: JWTServiceDep,
) -> SessionService:
    return SessionService(db, session_repo, jwt_service)


def get_auth_service(
    user_service: Annotated[UserService, Depends(get_user_service)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    role_service: Annotated[RoleService, Depends(get_role_service)],
    jwt_service: JWTServiceDep,
    password_security: PasswordSecurityDep,
) -> AuthService:
    return AuthService(
        user_service=user_service,
        session_service=session_service,
        jwt_service=jwt_service,
        password_security=password_security,
        role_service=role_service,
    )


async def get_current_user_session(
    service: Annotated[AuthService, Depends(get_auth_service)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> tuple[UserWithRoles, Session]:
    try:
        return await service.load_current_user_session(credentials.credentials)
    except (
        InvalidCredentialsError,
        InvalidSessionError,
        SessionNotFoundError,
        UserNotFoundError,
    ) as e:
        raise AppHTTPException(status_code=401, detail=str(e)) from e


async def get_user_permissions(
    service: Annotated[UserService, Depends(get_user_service)],
    auth: Annotated[tuple[UserWithRoles, Session], Depends(get_current_user_session)],
) -> list[Permission]:
    user, _session = auth
    return await service.get_user_permissions(user.id)


UserPermissionsDep = Annotated[list[Permission], Depends(get_user_permissions)]


def require_permission(permission_name: str) -> Any:
    async def checker(permissions: UserPermissionsDep) -> bool:
        names = [p.name for p in permissions]
        if permission_name not in names:
            raise AppHTTPException(status_code=403, detail="Insufficient permissions")
        return True

    return Depends(checker)


# ============================================================
# Type Aliases for Router Use
# ============================================================
RoleServiceDep = Annotated[RoleService, Depends(get_role_service)]
RoleRepoDep = Annotated[RoleRepository, Depends(get_role_repository)]

PermissionServiceDep = Annotated[PermissionService, Depends(get_permission_service)]
PermissionRepoDep = Annotated[PermissionRepository, Depends(get_permission_repository)]

UserServiceDep = Annotated[UserService, Depends(get_user_service)]
UserRepositoryDep = Annotated[UserRepository, Depends(get_user_repository)]

SessionServiceDep = Annotated[SessionService, Depends(get_session_service)]
SessionRepoDep = Annotated[SessionRepository, Depends(get_session_repository)]

AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]

CurrentUserSessionDep = Annotated[tuple[UserWithRoles, Session], Depends(get_current_user_session)]
