from typing import Any
from uuid import UUID

from app.core.config import get_settings
from app.core.http.schemas import SessionDeviceInfo
from app.core.logger import get_logger
from app.core.security import JWTService, PasswordSecurity
from app.domains.auth.entities import Session, User, UserWithRoles
from app.domains.auth.enums import TokenPurpose
from app.domains.auth.schemas.api_schemas import AdminRegisterUserRequest, LoginResponse
from app.domains.auth.services.password_service import PasswordService

from ..exceptions import (
    InvalidCredentialsError,
    InvalidPasswordError,
    InvalidSessionError,
    SessionNotFoundError,
    UserNotFoundError,
    UserPasswordNotConfiguredError,
)
from ..schemas import (
    CreateUserDTO,
    RefreshSessionRequest,
    RegisterUserRequest,
    UserLoginRequest,
)
from ..metrics import login_total, registration_total, token_refresh_total
from ..services.session_service import SessionService
from .role_service import RoleService
from .user_service import UserService


class AuthService:
    def __init__(
        self,
        user_service: UserService,
        session_service: SessionService,
        jwt_service: JWTService,
        password_security: PasswordSecurity,
        role_service: RoleService,
        password_service: PasswordService,
    ):
        self.user_service = user_service
        self.session_service = session_service
        self.jwt_service = jwt_service
        self.passwordSecurity = password_security
        self.role_service = role_service
        self.password_service = password_service
        self.logger = get_logger("app.auth.service")

    async def register(
        self, dto: RegisterUserRequest, device_info: SessionDeviceInfo | None = None
    ) -> dict[str, Any]:
        password_hash = self.passwordSecurity.generate_password_hash(dto.password)

        default_role_name = get_settings().DEFAULT_ROLE_NAME
        default_role = await self.role_service.get_by_name(default_role_name)
        default_role_ids = [default_role.id] if default_role else []

        create_user_dto = CreateUserDTO(
            email=dto.email,
            password_hash=password_hash,
            username=dto.username,
            name=dto.name,
            role_ids=default_role_ids,
        )
        user = await self.user_service.create(create_user_dto)
        role_names = [r.name for r in user.roles] if user.roles is not None else []
        access_token, refresh_token = await self.session_service.init_session(
            user.id, role_names, device_info
        )

        registration_total.labels(method="self").inc()
        self.logger.info("User registered", extra={"user_id": str(user.id), "email": user.email})

        return {
            "id": str(user.id),
            "email": user.email,
            "username": user.username,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    async def login(
        self, dto: UserLoginRequest, device_info: SessionDeviceInfo | None = None
    ) -> LoginResponse:
        user = await self.user_service.get_by_email_with_roles(email=dto.email)
        if user is None:
            login_total.labels(status="user_not_found").inc()
            self.logger.info("Login failed: user not found", extra={"email": dto.email})
            raise UserNotFoundError()

        password_hash = user.password_hash
        if not password_hash:
            self.logger.info(
                "Login failed: password not configured",
                extra={"user_id": str(user.id), "email": user.email},
            )
            login_total.labels(status="no_password").inc()
            raise UserPasswordNotConfiguredError()

        is_authenticated = self.passwordSecurity.verify_password(dto.password, password_hash)
        if not is_authenticated:
            login_total.labels(status="invalid_password").inc()
            self.logger.warning(
                "Login failed: invalid password",
                extra={"user_id": str(user.id), "email": dto.email},
            )
            raise InvalidPasswordError(user.email)

        role_names = [r.name for r in user.roles] if user.roles is not None else []
        access_token, refresh_token = await self.session_service.init_session(
            user.id, role_names, device_info
        )

        login_total.labels(status="success").inc()
        self.logger.info("User logged in", extra={"user_id": str(user.id)})

        response = LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            must_accept_terms=user.must_accept_terms,
            must_change_password=user.must_change_password,
        )
        return response

    async def _validate_refresh_request(
        self,
        session: Session,
        current_user_id: UUID,
        dto: RefreshSessionRequest,
        device_info: SessionDeviceInfo | None,
    ) -> bool:
        if not self.passwordSecurity.verify_token_hash(
            dto.refresh_token, session.refresh_token_hash
        ):
            return False

        # TODO: Implement log to track ip changes.
        if not session.matches_device_fingerprint(device_info):
            # TODO: send email "Active session tried to be acessed from a different source."
            return False

        token_user_id = UUID(self.jwt_service.decode_refresh_token(dto.refresh_token)["sub"])
        return token_user_id == current_user_id

    async def refresh_session(
        self,
        current_user: UserWithRoles,
        current_session: Session,
        dto: RefreshSessionRequest,
        device_info: SessionDeviceInfo | None,
    ) -> dict[str, str]:
        valid_refresh = await self._validate_refresh_request(
            current_session, current_user.id, dto, device_info
        )
        if not valid_refresh:
            token_refresh_total.labels(status="invalid").inc()
            self.logger.warning(
                "Invalid refresh attempt, session revoked",
                extra={"user_id": str(current_user.id), "session_id": str(current_session.id)},
            )
            await self.session_service.revoke(current_session.id)
            raise InvalidSessionError("New login required.")

        access_token = self.jwt_service.create_access_token(
            current_session.user_id, current_user.roles_names(), current_session.id
        )
        new_refresh_token = self.jwt_service.create_refresh_token(
            current_session.user_id, current_user.roles_names(), current_session.id
        )
        new_refresh_token_hash = self.passwordSecurity.generate_token_hash(new_refresh_token)

        time_delta = get_settings().refresh_token_timedelta
        await self.session_service.refresh(current_session, new_refresh_token_hash, time_delta)

        token_refresh_total.labels(status="success").inc()
        return {"access_token": access_token, "refresh_token": new_refresh_token}

    async def load_current_user_session(self, access_token: str) -> tuple[UserWithRoles, Session]:
        try:
            payload = self.jwt_service.decode_access_token(access_token)
        except Exception as e:
            raise InvalidCredentialsError() from e

        try:
            user_id = UUID(payload["sub"])
            session_id = UUID(payload["sid"])
        except (ValueError, KeyError) as e:
            raise InvalidCredentialsError() from e

        user = await self.user_service.get_by_id_with_roles(user_id)
        if user is None:
            raise UserNotFoundError()
        if not user.can_login():
            raise InvalidCredentialsError("User is not active or does not have a login method.")

        session = await self.session_service.get_by_id(session_id)
        if session is None:
            raise SessionNotFoundError()
        if not session.is_valid():
            raise InvalidSessionError()

        if user_id != session.user_id:
            raise InvalidCredentialsError()

        return user, session

    async def logout(self, _user: User, session: Session) -> None:
        await self.session_service.revoke(session.id)

    async def admin_register(self, dto: AdminRegisterUserRequest) -> UserWithRoles:
        password = self.password_service.generate_random_password()
        password_hash = self.passwordSecurity.generate_password_hash(password)

        create_dto = CreateUserDTO(
            email=dto.email,
            password_hash=password_hash,
            name=dto.name,
            role_ids=dto.role_ids,
            must_change_password=True,
        )

        user = await self.user_service.create(create_dto)

        registration_total.labels(method="admin").inc()
        self.logger.info("Admin registered user", extra={"user_id": str(user.id), "email": dto.email})

        raw_token = await self.password_service.create_reset_token(user.id, TokenPurpose.INVITE)

        try:
            await self.password_service.send_welcome_email(user, raw_token, password)
        except Exception:
            self.logger.exception("Welcome email dispatch failed after admin_register")

        return user
