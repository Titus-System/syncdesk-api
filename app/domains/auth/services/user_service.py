import secrets
import string
from datetime import UTC, datetime
from uuid import UUID

from app.core.config import get_settings
from app.core.event_dispatcher import AppEvent, EventDispatcher
from app.core.event_dispatcher.schemas import WelcomeInviteEventSchema
from app.core.logger import get_logger
from app.core.security import PasswordSecurity, ResetTokenSecurity
from app.db.exceptions import ResourceNotFoundError
from app.domains.auth.enums import TokenPurpose
from app.domains.auth.exceptions import UserCannotLoseLoginMethodError
from app.domains.auth.repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from app.domains.auth.repositories.user_repository import UserRepository
from app.domains.auth.schemas.reset_password_token_schemas import CreatePasswordResetTokenDTO
from app.domains.auth.schemas.user_schemas import UpdateUserRolesDTO

from ..entities import Permission, Role, User, UserWithRoles
from ..schemas import CreateUserDTO, ReplaceUserDTO, UpdateUserDTO


class UserService:
    def __init__(
        self,
        repo: UserRepository,
        dispatcher: EventDispatcher,
        token_repo: PasswordResetTokenRepository,
        reset_token_security: ResetTokenSecurity,
        password_security: PasswordSecurity,
    ):
        self.repo: UserRepository = repo
        self.dispatcher = dispatcher
        self.token_repo = token_repo
        self.reset_token_security = reset_token_security
        self.password_security = password_security
        self.logger = get_logger("app.auth.user_service")

    async def create(self, dto: CreateUserDTO) -> UserWithRoles:
          """Create a user via the admin-invite flow.

          Always generates a one-time password (unless the user authenticates via
          OAuth), overrides any provided password_hash, marks the user as needing
          to change password on first login, and publishes USER_WELCOME_INVITE so
          the welcome email is enqueued.
          """
          await self._validate_create_support_levels(dto)

          if not dto.username:
              dto = dto.model_copy(
                  update={
                      "username": self._generate_username(),
                  }
              )

          plain_password: str | None = None
          if not dto.oauth_provider:
              plain_password = self._generate_random_password()
              dto = dto.model_copy(
                  update={
                      "password_hash": self.password_security.generate_password_hash(plain_password),
                      "must_change_password": True,
                  }
              )

          user = await self.repo.create(dto)

          if plain_password:
              await self._publish_welcome_invite(user, plain_password)

          return user

    async def _validate_create_support_levels(self, dto: CreateUserDTO) -> None:
        level_ids = list(dict.fromkeys(dto.level_ids))
        if not level_ids:
            return

        role_names = await self.repo.get_role_names_by_ids(dto.role_ids)
        if "agent" not in role_names:
            raise ValueError("Only users with agent role can receive support levels.")

        existing_level_ids = await self.repo.get_existing_level_ids(level_ids)
        missing_level_ids = set(level_ids) - existing_level_ids
        if missing_level_ids:
            raise ResourceNotFoundError("Level", ", ".join(str(id) for id in sorted(missing_level_ids)))

    @staticmethod
    def _generate_random_password(length: int = 16) -> str:
        alphabet = string.ascii_letters + string.digits + string.punctuation
        while True:
            password = "".join(secrets.choice(alphabet) for _ in range(length))
            if (
                any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in string.punctuation for c in password)
            ):
                return password

    async def _publish_welcome_invite(
        self, user: UserWithRoles, plain_password: str
    ) -> None:
        settings = get_settings()
        raw_token = self.reset_token_security.generate_token()
        token_hash = self.reset_token_security.hash_token(raw_token)
        expires_at = datetime.now(UTC).replace(tzinfo=None) + settings.invite_token_timedelta

        await self.token_repo.invalidate_user_tokens(user.id, TokenPurpose.INVITE)
        await self.token_repo.create(
            CreatePasswordResetTokenDTO(
                user_id=user.id,
                token_hash=token_hash,
                purpose=TokenPurpose.INVITE,
                expires_at=expires_at,
            )
        )

        await self.dispatcher.publish(
            AppEvent.USER_WELCOME_INVITE,
            WelcomeInviteEventSchema(
                user_id=user.id,
                user_name=user.name or str(user.id),
                user_email=user.email,
                roles=user.roles_names(),
                raw_token=raw_token,
                one_time_password=plain_password,
                max_attempts=settings.EMAIL_OUTBOX_MAX_ATTEMPTS,
            ),
        )

    async def get_all(self) -> list[User]:
        return await self.repo.get_all()

    async def get_all_with_roles(self) -> list[UserWithRoles]:
        return await self.repo.get_all_with_roles()

    async def get_by_id(self, id: UUID) -> User | None:
        return await self.repo.get_by_id(id)

    async def get_by_id_with_roles(self, id: UUID) -> UserWithRoles | None:
        return await self.repo.get_with_roles(id)

    async def get_by_email(self, email: str) -> User | None:
        return await self.repo.get_by_email(email)

    async def get_by_email_with_roles(self, email: str) -> UserWithRoles | None:
        return await self.repo.get_by_email_with_roles(email)

    async def update(self, id: UUID, dto: UpdateUserDTO | ReplaceUserDTO) -> User | None:
        user = await self.repo.get_by_id(id)
        if user is None:
            return None

        update_values = dto.model_dump(exclude={"role_ids", "level_ids"}, exclude_none=True)
        temp_user = User(**{**user.__dict__, **update_values})

        if not temp_user.can_login():
            raise UserCannotLoseLoginMethodError()

        return await self.repo.update(id, dto)

    async def delete(self, id: UUID) -> User | None:
        self.logger.info("User soft-deleted", extra={"user_id": str(id)})
        return await self.repo.soft_delete(id)

    async def deactivate(self, id: UUID) -> User | None:
        user = await self.repo.update(id, UpdateUserDTO(is_active=False))
        if user is not None:
            self.logger.info("User deactivated", extra={"user_id": str(id)})
        return user

    async def hard_delete(self, id: UUID) -> User | None:
        self.logger.warning("User hard-deleted", extra={"user_id": str(id)})
        return await self.repo.hard_delete(id)

    async def add_roles(self, id: UUID, role_ids: list[int]) -> UserWithRoles:
        user, missing_ids = await self.repo.add_roles(id, role_ids)
        if user is None:
            raise ResourceNotFoundError("User", str(id))
        if missing_ids is not None:
            raise ValueError(f"Roles not found: {missing_ids}")
        self.logger.info("Roles assigned to user", extra={"user_id": str(id), "role_ids": role_ids})
        return user

    async def remove_roles(self, user_id: UUID, role_ids: list[int]) -> UserWithRoles:
        await self.repo.remove_roles(user_id, role_ids)
        user = await self.get_by_id_with_roles(user_id)
        if user is None:
            raise ResourceNotFoundError("User", str(user_id))
        return user

    async def update_user_roles(self, user_id: UUID, dto: UpdateUserRolesDTO) -> UserWithRoles:
        user, missing_ids = await self.repo.update_user_roles(
            user_id, dto.add_role_ids, dto.remove_role_ids
        )
        if missing_ids:
            self.logger.warning(
                "Update user roles failed: roles not found",
                extra={"user_id": str(user_id), "missing_role_ids": list(missing_ids)},
            )
            raise ValueError(f"Roles not found: {missing_ids}")
        if user is None:
            self.logger.warning(
                "Update user roles failed: user not found",
                extra={"user_id": str(user_id)},
            )
            raise ResourceNotFoundError("User", str(user_id))
        self.logger.info(
            "User roles updated",
            extra={
                "user_id": str(user_id),
                "added": dto.add_role_ids,
                "removed": dto.remove_role_ids,
            },
        )
        return user

    async def get_user_permissions(self, id: UUID) -> list[Permission]:
        return await self.repo.get_user_permissions(id)

    async def user_exists(self, user_id: UUID) -> bool:
        return await self.repo.user_exists(user_id)

    async def get_user_roles(self, user_id: UUID) -> list[Role]:
        return await self.repo.get_user_roles(user_id)

    async def update_password(self, user_id: UUID, new_password_hash: str) -> User | None:
        return await self.repo.update_password(user_id, new_password_hash)

    @staticmethod
    def _generate_username() -> str:
        return f"user_{secrets.token_hex(12)}"

    async def accept_terms(self, user_id: UUID) -> User | None:
        return await self.repo.accept_terms(user_id)
    async def set_avatar(
        self, user_id: UUID, avatar_file_id: UUID | None
    ) -> tuple[UserWithRoles, UUID | None] | None:
        """Point the user's profile at ``avatar_file_id`` (or clear it).

        Returns ``(user, previous_avatar_file_id)`` so the router can
        soft-delete the prior FileObject via the files domain. Returns
        ``None`` if the user does not exist.

        Cross-domain validation (ownership, context, status of the new
        file) is handled at the router/composition layer — same pattern
        used by chat_router in PR3 — so this service stays decoupled
        from the files domain.
        """
        result = await self.repo.set_avatar(user_id, avatar_file_id)
        if result is None:
            self.logger.warning(
                "Set avatar failed: user not found",
                extra={"user_id": str(user_id)},
            )
            return None
        user, previous = result
        self.logger.info(
            "User avatar updated",
            extra={
                "user_id": str(user_id),
                "previous_file_id": str(previous) if previous else None,
                "new_file_id": str(avatar_file_id) if avatar_file_id else None,
            },
        )
        return user, previous
