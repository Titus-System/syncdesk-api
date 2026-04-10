from typing import Annotated, Any

from fastapi import Depends, WebSocket, WebSocketException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.dependencies import (
    EmailServiceDep,
    JWTServiceDep,
    PasswordSecurityDep,
    ResetTokenSecurityDep,
)
from app.core.exceptions import AppHTTPException
from app.core.logger import user_id_ctx
from app.db.postgres.dependencies import PgSessionDep
from app.domains.auth.repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from app.domains.auth.schemas import UserCompliance
from app.domains.auth.services.password_service import PasswordService

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


def get_password_reset_token_repository(db: PgSessionDep) -> PasswordResetTokenRepository:
    return PasswordResetTokenRepository(db)


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


def get_password_service(
    user_service: Annotated[UserService, Depends(get_user_service)],
    token_repo: Annotated[
        PasswordResetTokenRepository, Depends(get_password_reset_token_repository)
    ],
    password_security: PasswordSecurityDep,
    email_strategy: EmailServiceDep,
    reset_token_security: ResetTokenSecurityDep,
) -> PasswordService:
    return PasswordService(
        user_service=user_service,
        token_repo=token_repo,
        password_security=password_security,
        email_strategy=email_strategy,
        reset_token_security=reset_token_security,
    )


def get_auth_service(
    user_service: Annotated[UserService, Depends(get_user_service)],
    session_service: Annotated[SessionService, Depends(get_session_service)],
    role_service: Annotated[RoleService, Depends(get_role_service)],
    jwt_service: JWTServiceDep,
    password_security: PasswordSecurityDep,
    password_service: Annotated[PasswordService, Depends(get_password_service)],
) -> AuthService:
    return AuthService(
        user_service=user_service,
        session_service=session_service,
        jwt_service=jwt_service,
        password_security=password_security,
        role_service=role_service,
        password_service=password_service,
    )


async def get_current_user_session(
    service: Annotated[AuthService, Depends(get_auth_service)],
    credentials: Annotated[HTTPAuthorizationCredentials, Depends(bearer_scheme)],
) -> tuple[UserWithRoles, Session]:
    try:
        user, session = await service.load_current_user_session(credentials.credentials)
    except (
        InvalidCredentialsError,
        InvalidSessionError,
        SessionNotFoundError,
        UserNotFoundError,
    ) as e:
        raise AppHTTPException(status_code=401, detail=str(e)) from e

    user_id_ctx.set(str(user.id))
    return user, session


async def get_user_compliance(
    user_session: Annotated[tuple[UserWithRoles, Session], Depends(get_current_user_session)],
) -> UserCompliance:
    user = user_session[0]
    return UserCompliance(
        must_accept_terms=user.must_accept_terms, must_change_password=user.must_change_password
    )


def _extract_bearer_token(authorization: str | None) -> str:
    if not authorization:
        raise WebSocketException(code=1008, reason="Missing Authorization header")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise WebSocketException(code=1008, reason="Invalid Authorization header")
    return token


async def get_current_user_session_ws(
    ws: WebSocket,
    service: Annotated[AuthService, Depends(get_auth_service)],
) -> tuple[UserWithRoles, Session]:
    # Extract from custom subprotocol "access_token, <token>" since browsers block auth headers
    token = None
    subprotocols = ws.headers.get("Sec-WebSocket-Protocol")
    if subprotocols:
        parts = [p.strip() for p in subprotocols.split(",")]
        if "access_token" in parts:
            idx = parts.index("access_token")
            # The token should be the next part in the sequence
            if len(parts) > idx + 1:
                token = parts[idx + 1]

    # Fallback to standard Authorization header
    if not token:
        token = _extract_bearer_token(ws.headers.get("Authorization"))
        
    try:
        user, session = await service.load_current_user_session(token)
    except (
        InvalidCredentialsError,
        InvalidSessionError,
        SessionNotFoundError,
        UserNotFoundError,
    ) as e:
        raise WebSocketException(code=1008, reason=str(e)) from e

    user_id_ctx.set(str(user.id))
    return user, session


async def get_user_permissions(
    service: Annotated[UserService, Depends(get_user_service)],
    auth: Annotated[tuple[UserWithRoles, Session], Depends(get_current_user_session)],
) -> list[Permission]:
    user, _session = auth
    return await service.get_user_permissions(user.id)


async def get_user_permissions_ws(
    service: Annotated[UserService, Depends(get_user_service)],
    auth: Annotated[tuple[UserWithRoles, Session], Depends(get_current_user_session_ws)],
) -> list[Permission]:
    user, _session = auth
    return await service.get_user_permissions(user.id)


UserPermissionsDep = Annotated[list[Permission], Depends(get_user_permissions)]
UserPermissionsWsDep = Annotated[list[Permission], Depends(get_user_permissions_ws)]


async def get_user_compliance_ws(
    user_session: Annotated[tuple[UserWithRoles, Session], Depends(get_current_user_session_ws)],
) -> UserCompliance:
    user = user_session[0]
    return UserCompliance(
        must_accept_terms=user.must_accept_terms, must_change_password=user.must_change_password
    )


def require_permission(permission_name: str) -> Any:
    async def checker(permissions: UserPermissionsDep) -> bool:
        names = [p.name for p in permissions]
        if permission_name not in names:
            raise AppHTTPException(status_code=403, detail="Insufficient permissions")
        return True

    return Depends(checker)


def require_permission_ws(permission_name: str) -> Any:
    async def checker(permissions: UserPermissionsWsDep) -> bool:
        names = [p.name for p in permissions]
        if permission_name not in names:
            raise WebSocketException(code=1008, reason="Insufficient permissions")
        return True

    return Depends(checker)


def require_user_compliance() -> Any:
    async def checker(compliance: Annotated[UserCompliance, Depends(get_user_compliance)]) -> bool:
        required_actions: list[str] = []
        if compliance.must_change_password:
            required_actions.append("change_password")
        if compliance.must_accept_terms:
            required_actions.append("accept_terms")

        if required_actions:
            raise AppHTTPException(
                status_code=428,  # precondition required
                detail="Account setup required before accessing this resource.",
                errors={"required_actions": required_actions},
            )
        return True

    return Depends(checker)


def require_user_compliance_ws() -> Any:
    async def checker_ws(
        compliance: Annotated[UserCompliance, Depends(get_user_compliance_ws)],
    ) -> bool:
        required_actions: list[str] = []
        if compliance.must_change_password:
            required_actions.append("change_password")
        if compliance.must_accept_terms:
            required_actions.append("accept_terms")

        if required_actions:
            raise WebSocketException(code=1008, reason="Account setup required")
        return True

    return Depends(checker_ws)


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
CurrentUserSessionWsDep = Annotated[
    tuple[UserWithRoles, Session], Depends(get_current_user_session_ws)
]

PasswordServiceDep = Annotated[PasswordService, Depends(get_password_service)]

UserComplianceDep = Annotated[UserCompliance, Depends(get_user_compliance)]
