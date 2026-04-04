from datetime import UTC, datetime
import secrets
import string
from uuid import UUID

from app.core.config import get_settings
from app.core.email import EmailStrategy, ResetPasswordEmailParams
from app.core.email.schemas import WelcomeEmailParams
from app.core.logger import get_logger
from app.core.security import PasswordSecurity, ResetTokenSecurity
from ..enums import TokenPurpose
from ..entities import PasswordResetToken, User, UserWithRoles
from ..exceptions import InvalidPasswordError, InvalidResetTokenError
from ..schemas.reset_password_token_schemas import CreatePasswordResetTokenDTO
from ..services.user_service import UserService
from ..repositories.password_reset_token_repository import PasswordResetTokenRepository


class PasswordService:
    def __init__(
        self,
        user_service: UserService,
        token_repo: PasswordResetTokenRepository,
        password_security: PasswordSecurity,
        email_strategy: EmailStrategy,
        reset_token_security: ResetTokenSecurity,
    ):
        self.user_service = user_service
        self.token_repo = token_repo
        self.password_security = password_security
        self.email_strategy = email_strategy
        self.reset_token_security = reset_token_security
        self.logger = get_logger()

    def generate_random_password(self, length: int = 16) -> str:
        """Generate a cryptographically secure random password."""
        alphabet = string.ascii_letters + string.digits + string.punctuation

        while True:
            password = "".join(secrets.choice(alphabet) for _ in range(length))

            # enforce at least one of each category
            if (
                any(c.islower() for c in password)
                and any(c.isupper() for c in password)
                and any(c.isdigit() for c in password)
                and any(c in string.punctuation for c in password)
            ):
                return password

    async def create_reset_token(self, user_id: UUID, purpose: TokenPurpose) -> str:
        """Generate a token, hash it, store in DB, return raw token."""
        settings = get_settings()
        raw_token = self.reset_token_security.generate_token()
        token_hash = self.reset_token_security.hash_token(raw_token)
        now = datetime.now(UTC).replace(tzinfo=None)
        expires_at: datetime

        if purpose == TokenPurpose.RESET:
            expires_at = now + settings.password_reset_token_timedelta
        else:
            expires_at = now + settings.invite_token_timedelta

        dto = CreatePasswordResetTokenDTO(
            user_id=user_id, token_hash=token_hash, purpose=purpose, expires_at=expires_at
        )

        await self.token_repo.invalidate_user_tokens(user_id, purpose)
        await self.token_repo.create(dto)
        return raw_token

    async def consume_token(self, raw_token: str) -> PasswordResetToken:
        """Verify token hash, check expiry/used, mark as used."""
        token_hash = self.reset_token_security.hash_token(raw_token)
        token = await self.token_repo.consume_by_hash(token_hash)

        if not token:
            raise InvalidResetTokenError()

        if token.purpose not in {TokenPurpose.RESET, TokenPurpose.INVITE}:
            raise InvalidResetTokenError()

        return token

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> User | None:
        if not user.password_hash:
            raise InvalidPasswordError("User does not have a password set.")

        if not self.password_security.verify_password(current_password, user.password_hash):
            raise InvalidPasswordError("Current password is incorrect.")

        new_password_hash = self.password_security.generate_password_hash(new_password)
        return await self.user_service.update_password(user.id, new_password_hash)

    async def reset_password(self, raw_token: str, new_password: str) -> User | None:
        token = await self.consume_token(raw_token)
        new_password_hash = self.password_security.generate_password_hash(new_password)
        return await self.user_service.update_password(token.user_id, new_password_hash)

    async def send_welcome_email(self, user: UserWithRoles, raw_token: str, password: str) -> None:
        """Delegate to EmailService.send_welcome_email."""
        base_url: str = ""
        roles = user.roles_names()
        if "client" in roles or "user" in roles:
            base_url = get_settings().MOBILE_FRONTEND_URL
        if "agent" in roles or "admin" in roles:
            base_url = get_settings().WEB_FRONTEND_URL

        params = WelcomeEmailParams(
            user_name=user.name or str(user.id),
            user_email=user.email,
            one_time_password=password,
            login_url=base_url + f"/login?token={raw_token}",
        )
        await self.email_strategy.send_welcome_email(user.email, params)

    async def send_reset_password_email(self, user: UserWithRoles, raw_token: str) -> None:
        """Delegate to EmailService.send_password_reset_email."""
        base_url: str = ""
        roles = user.roles_names()
        if "client" in roles or "user" in roles:
            base_url = get_settings().MOBILE_FRONTEND_URL
        if "agent" in roles or "admin" in roles:
            base_url = get_settings().WEB_FRONTEND_URL

        params = ResetPasswordEmailParams(
            user_email=user.email,
            reset_url=base_url + f"/reset-password?token={raw_token}",
        )
        await self.email_strategy.send_reset_email(user.email, params)

    async def forgot_password(self, email: str) -> None:
        user = await self.user_service.get_by_email_with_roles(email)
        if user is None:
            return
        try:
            raw_token = await self.create_reset_token(user.id, TokenPurpose.RESET)
            await self.send_reset_password_email(user, raw_token)
        except Exception:
            self.logger.error("Failed forgot-password pipeline for existing user", exc_info=True)
