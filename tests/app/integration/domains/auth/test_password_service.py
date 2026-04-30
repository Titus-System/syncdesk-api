import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_dispatcher import AppEvent, event_handler, get_event_dispatcher
from app.core.event_dispatcher.schemas import PasswordResetEventSchema
from app.core.security import PasswordSecurity, ResetTokenSecurity
from app.domains.auth.entities import User
from app.domains.auth.enums import OAuthProvider, TokenPurpose
from app.domains.auth.exceptions import InvalidPasswordError, InvalidResetTokenError
from app.domains.auth.models import Role as RoleModel
from app.domains.auth.repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from app.domains.auth.repositories.user_repository import UserRepository
from app.domains.auth.schemas import CreateUserDTO
from app.domains.auth.services.password_service import PasswordService
from app.domains.auth.services.user_service import UserService


class TestPasswordService:
    """Integration tests for PasswordService.

    All dependencies use real implementations against the test database,
    except EmailStrategy which is mocked (external service).
    """

    @pytest.fixture
    def password_security(self) -> PasswordSecurity:
        return PasswordSecurity()

    @pytest.fixture
    def reset_token_security(self) -> ResetTokenSecurity:
        return ResetTokenSecurity()

    @pytest.fixture
    def mock_email(self) -> AsyncMock:
        email = AsyncMock()
        email.send_welcome_email = AsyncMock()
        email.send_reset_email = AsyncMock()
        return email

    @pytest.fixture
    def user_repo(self, db_session: AsyncSession) -> UserRepository:
        return UserRepository(db=db_session)

    @pytest.fixture
    def token_repo(self, db_session: AsyncSession) -> PasswordResetTokenRepository:
        return PasswordResetTokenRepository(db=db_session)

    @pytest.fixture
    def user_service(self, user_repo: UserRepository) -> UserService:
        return UserService(repo=user_repo)

    @pytest.fixture
    def service(
        self,
        user_service: UserService,
        token_repo: PasswordResetTokenRepository,
        password_security: PasswordSecurity,
        mock_email: AsyncMock,
        reset_token_security: ResetTokenSecurity,
    ) -> PasswordService:
        return PasswordService(
            user_service=user_service,
            token_repo=token_repo,
            password_security=password_security,
            email_strategy=mock_email,
            reset_token_security=reset_token_security,
            dispatcher=get_event_dispatcher(),
        )

    @pytest.fixture
    async def local_user(
        self, user_repo: UserRepository, password_security: PasswordSecurity
    ) -> User:
        """Create a local user with a known password for tests."""
        dto = CreateUserDTO(
            email=f"pwd_{uuid4().hex[:8]}@example.com",
            username=f"user_{uuid4().hex[:8]}",
            name="Password Test User",
            password_hash=password_security.generate_password_hash("OldPassword123!"),
        )
        return await user_repo.create(dto)

    @pytest.fixture
    async def oauth_user(self, user_repo: UserRepository) -> User:
        """Create an OAuth user with no password."""
        dto = CreateUserDTO(
            email=f"oauth_{uuid4().hex[:8]}@example.com",
            oauth_provider=OAuthProvider.GOOGLE,
            oauth_provider_id=f"google-{uuid4().hex[:8]}",
        )
        return await user_repo.create(dto)

    # ── generate_random_password ──────────────────────────────────────

    def test_random_password_meets_complexity(self, service: PasswordService) -> None:
        password = service.generate_random_password()
        assert len(password) == 16
        assert any(c.islower() for c in password)
        assert any(c.isupper() for c in password)
        assert any(c.isdigit() for c in password)
        assert any(c in "!@#$%^&*()_+-=[]{}|;:',.<>?/`~\"" for c in password)

    def test_random_password_respects_custom_length(self, service: PasswordService) -> None:
        password = service.generate_random_password(length=32)
        assert len(password) == 32

    def test_random_password_is_unique_across_calls(self, service: PasswordService) -> None:
        passwords = {service.generate_random_password() for _ in range(20)}
        assert len(passwords) == 20

    # ── change_password ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_change_password_success(
        self,
        service: PasswordService,
        local_user: User,
        password_security: PasswordSecurity,
    ) -> None:
        result = await service.change_password(local_user, "OldPassword123!", "NewPassword456!")
        assert result is not None
        assert password_security.verify_password("NewPassword456!", result.password_hash)

    @pytest.mark.asyncio
    async def test_change_password_wrong_current_raises(
        self, service: PasswordService, local_user: User
    ) -> None:
        with pytest.raises(InvalidPasswordError, match="Current password is incorrect"):
            await service.change_password(local_user, "WrongPassword!", "NewPassword456!")

    @pytest.mark.asyncio
    async def test_change_password_oauth_user_without_password_raises(
        self, service: PasswordService, oauth_user: User
    ) -> None:
        with pytest.raises(InvalidPasswordError, match="does not have a password set"):
            await service.change_password(oauth_user, "anything", "NewPassword456!")

    @pytest.mark.asyncio
    async def test_change_password_persists_in_db(
        self,
        service: PasswordService,
        local_user: User,
        user_repo: UserRepository,
        password_security: PasswordSecurity,
    ) -> None:
        """After changing password, re-fetching user from DB reflects the new hash."""
        await service.change_password(local_user, "OldPassword123!", "Persisted789!")
        fetched = await user_repo.get_by_id(local_user.id)
        assert fetched is not None
        assert password_security.verify_password("Persisted789!", fetched.password_hash)
        assert not password_security.verify_password("OldPassword123!", fetched.password_hash)

    @pytest.mark.asyncio
    async def test_change_password_old_password_no_longer_works(
        self,
        service: PasswordService,
        local_user: User,
        user_repo: UserRepository,
        password_security: PasswordSecurity,
    ) -> None:
        result = await service.change_password(local_user, "OldPassword123!", "Changed999!")
        assert result is not None
        assert not password_security.verify_password("OldPassword123!", result.password_hash)

    # ── create_reset_token ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_reset_token_returns_raw_token(
        self, service: PasswordService, local_user: User
    ) -> None:
        raw_token = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        assert isinstance(raw_token, str)
        assert len(raw_token) > 20

    @pytest.mark.asyncio
    async def test_create_reset_token_stored_hash_matches(
        self,
        service: PasswordService,
        local_user: User,
        token_repo: PasswordResetTokenRepository,
        reset_token_security: ResetTokenSecurity,
    ) -> None:
        """The raw token returned must match the hash stored in the DB."""
        raw_token = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        token_hash = reset_token_security.hash_token(raw_token)
        stored = await token_repo.get_by_hash(token_hash)
        assert stored is not None
        assert stored.user_id == local_user.id
        assert stored.purpose == TokenPurpose.RESET

    @pytest.mark.asyncio
    async def test_create_invite_token_has_correct_purpose(
        self,
        service: PasswordService,
        local_user: User,
        token_repo: PasswordResetTokenRepository,
        reset_token_security: ResetTokenSecurity,
    ) -> None:
        raw_token = await service.create_reset_token(local_user.id, TokenPurpose.INVITE)
        token_hash = reset_token_security.hash_token(raw_token)
        stored = await token_repo.get_by_hash(token_hash)
        assert stored is not None
        assert stored.purpose == TokenPurpose.INVITE

    @pytest.mark.asyncio
    async def test_create_reset_token_invalidates_previous_tokens(
        self,
        service: PasswordService,
        local_user: User,
        token_repo: PasswordResetTokenRepository,
        reset_token_security: ResetTokenSecurity,
    ) -> None:
        """Creating a new token should invalidate all previous tokens for the same purpose."""
        first_raw = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        first_hash = reset_token_security.hash_token(first_raw)

        _second_raw = await service.create_reset_token(local_user.id, TokenPurpose.RESET)

        old_token = await token_repo.get_by_hash(first_hash)
        assert old_token is not None
        assert old_token.used_at is not None, "Previous token should have been invalidated"

    @pytest.mark.asyncio
    async def test_create_reset_token_different_purpose_does_not_invalidate(
        self,
        service: PasswordService,
        local_user: User,
        token_repo: PasswordResetTokenRepository,
        reset_token_security: ResetTokenSecurity,
    ) -> None:
        """An INVITE token should not invalidate an existing RESET token."""
        reset_raw = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        _invite_raw = await service.create_reset_token(local_user.id, TokenPurpose.INVITE)

        reset_hash = reset_token_security.hash_token(reset_raw)
        reset_stored = await token_repo.get_by_hash(reset_hash)
        assert reset_stored is not None
        assert reset_stored.used_at is None, "RESET token should remain valid"

    # ── consume_token ─────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_consume_token_success(
        self, service: PasswordService, local_user: User
    ) -> None:
        raw_token = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        token = await service.consume_token(raw_token)
        assert token.user_id == local_user.id
        assert token.purpose == TokenPurpose.RESET
        assert token.used_at is not None

    @pytest.mark.asyncio
    async def test_consume_token_twice_raises(
        self, service: PasswordService, local_user: User
    ) -> None:
        """A token can only be consumed once."""
        raw_token = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        await service.consume_token(raw_token)
        with pytest.raises(InvalidResetTokenError):
            await service.consume_token(raw_token)

    @pytest.mark.asyncio
    async def test_consume_token_invalid_raw_raises(self, service: PasswordService) -> None:
        with pytest.raises(InvalidResetTokenError):
            await service.consume_token("totally-bogus-token-value")

    @pytest.mark.asyncio
    async def test_consume_token_after_invalidation_raises(
        self, service: PasswordService, local_user: User
    ) -> None:
        """If a new token was created (invalidating the old), consuming the old one should fail."""
        first_raw = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        _second_raw = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        with pytest.raises(InvalidResetTokenError):
            await service.consume_token(first_raw)

    # ── reset_password ────────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_reset_password_success(
        self,
        service: PasswordService,
        local_user: User,
        password_security: PasswordSecurity,
    ) -> None:
        raw_token = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        result = await service.reset_password(raw_token, "ResetNewPass1!")
        assert result is not None
        assert password_security.verify_password("ResetNewPass1!", result.password_hash)

    @pytest.mark.asyncio
    async def test_reset_password_clears_must_change_flag(
        self,
        service: PasswordService,
        user_repo: UserRepository,
        password_security: PasswordSecurity,
    ) -> None:
        """User created with must_change_password=True should have it cleared after reset."""
        dto = CreateUserDTO(
            email=f"reset_{uuid4().hex[:8]}@example.com",
            password_hash=password_security.generate_password_hash("temp"),
            must_change_password=True,
        )
        user = await user_repo.create(dto)
        raw_token = await service.create_reset_token(user.id, TokenPurpose.RESET)
        result = await service.reset_password(raw_token, "BrandNew123!")
        assert result is not None
        assert result.must_change_password is False

    @pytest.mark.asyncio
    async def test_reset_password_with_invalid_token_raises(
        self, service: PasswordService
    ) -> None:
        with pytest.raises(InvalidResetTokenError):
            await service.reset_password("fake-token", "NewPass1!")

    @pytest.mark.asyncio
    async def test_reset_password_token_cannot_be_reused(
        self,
        service: PasswordService,
        local_user: User,
    ) -> None:
        raw_token = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        await service.reset_password(raw_token, "FirstReset1!")
        with pytest.raises(InvalidResetTokenError):
            await service.reset_password(raw_token, "SecondReset2!")

    @pytest.mark.asyncio
    async def test_reset_password_persists_in_db(
        self,
        service: PasswordService,
        local_user: User,
        user_repo: UserRepository,
        password_security: PasswordSecurity,
    ) -> None:
        raw_token = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        await service.reset_password(raw_token, "DbPersist99!")
        fetched = await user_repo.get_by_id(local_user.id)
        assert fetched is not None
        assert password_security.verify_password("DbPersist99!", fetched.password_hash)

    # ── forgot_password ───────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_forgot_password_creates_token_in_db(
        self,
        service: PasswordService,
        local_user: User,
        token_repo: PasswordResetTokenRepository,
        reset_token_security: ResetTokenSecurity,
    ) -> None:
        """forgot_password must create and store a reset token in the DB."""
        # Create a sentinel token first so we can detect a NEW one was created
        first_raw = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        first_hash = reset_token_security.hash_token(first_raw)

        await service.forgot_password(local_user.email)

        # The sentinel token is now invalidated (used_at set), proving a new one was created
        old = await token_repo.get_by_hash(first_hash)
        assert old is not None
        assert old.used_at is not None

    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_email_does_nothing(
        self,
        service: PasswordService,
    ) -> None:
        """Should silently return without any side-effect (no user enumeration)."""
        await service.forgot_password("nonexistent@nowhere.com")  # must not raise

    @pytest.mark.asyncio
    async def test_forgot_password_pipeline_failure_does_not_raise(
        self,
        service: PasswordService,
        local_user: User,
        token_repo: PasswordResetTokenRepository,
    ) -> None:
        """If publishing the event raises, forgot_password must swallow the error."""
        # Temporarily corrupt the dispatcher's payload map to force an EventSchemaError
        # by publishing with the wrong event type — the try/except in forgot_password catches it
        original_map = service.dispatcher._payload_map.copy()
        del service.dispatcher._payload_map[AppEvent.USER_PASSWORD_RESET]  # type: ignore[misc]
        try:
            await service.forgot_password(local_user.email)  # should not raise
        finally:
            service.dispatcher._payload_map = original_map  # type: ignore[assignment]

    @pytest.mark.asyncio
    async def test_forgot_password_invalidates_previous_token(
        self,
        service: PasswordService,
        local_user: User,
        token_repo: PasswordResetTokenRepository,
        reset_token_security: ResetTokenSecurity,
    ) -> None:
        """Calling forgot_password twice should invalidate the first token."""
        first_raw = await service.create_reset_token(local_user.id, TokenPurpose.RESET)
        first_hash = reset_token_security.hash_token(first_raw)

        await service.forgot_password(local_user.email)

        old = await token_repo.get_by_hash(first_hash)
        assert old is not None
        assert old.used_at is not None

    # ── send_welcome_email ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_send_welcome_email_called_with_correct_params(
        self,
        service: PasswordService,
        user_repo: UserRepository,
        db_session: AsyncSession,
        mock_email: AsyncMock,
    ) -> None:
        role = RoleModel(name="client", description="client role")
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

        dto = CreateUserDTO(
            email=f"welcome_{uuid4().hex[:8]}@example.com",
            name="Welcome User",
            password_hash="hashed",
            role_ids=[role.id],
        )
        user_with_roles = await user_repo.create(dto)
        await service.send_welcome_email(user_with_roles, "raw-token", "temp-pass")

        mock_email.send_welcome_email.assert_awaited_once()
        call_args = mock_email.send_welcome_email.call_args
        assert call_args[0][0] == user_with_roles.email
        params = call_args[0][1]
        assert params.user_email == user_with_roles.email
        assert params.one_time_password == "temp-pass"
        assert "raw-token" in params.login_url

    @pytest.mark.asyncio
    async def test_send_welcome_email_admin_uses_web_url(
        self,
        service: PasswordService,
        user_repo: UserRepository,
        db_session: AsyncSession,
        mock_email: AsyncMock,
    ) -> None:
        role = RoleModel(name="admin", description="admin role")
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

        dto = CreateUserDTO(
            email=f"admin_{uuid4().hex[:8]}@example.com",
            name="Admin User",
            password_hash="hashed",
            role_ids=[role.id],
        )
        user_with_roles = await user_repo.create(dto)
        await service.send_welcome_email(user_with_roles, "tok", "pass")

        params = mock_email.send_welcome_email.call_args[0][1]
        assert params.login_url.startswith("http")  # WEB_FRONTEND_URL

    # ── send_reset_password_email ─────────────────────────────────────

    @pytest.mark.asyncio
    async def test_send_reset_password_email_called(
        self,
        service: PasswordService,
        user_repo: UserRepository,
        db_session: AsyncSession,
        mock_email: AsyncMock,
    ) -> None:
        role = RoleModel(name="user", description="user role")
        db_session.add(role)
        await db_session.commit()
        await db_session.refresh(role)

        dto = CreateUserDTO(
            email=f"rpe_{uuid4().hex[:8]}@example.com",
            password_hash="hashed",
            role_ids=[role.id],
        )
        user_with_roles = await user_repo.create(dto)
        await service.send_reset_password_email(user_with_roles, "reset-tok")

        mock_email.send_reset_email.assert_awaited_once()
        params = mock_email.send_reset_email.call_args[0][1]
        assert "reset-tok" in params.reset_url

    # ── end-to-end flow ───────────────────────────────────────────────

    @pytest.fixture
    async def captured_reset_events(self) -> list[PasswordResetEventSchema]:
        """Subscribe a real (non-mock) listener that captures PASSWORD_RESET events.

        Cleaned up via unsubscribe after the test to avoid handler accumulation.
        """
        captured: list[PasswordResetEventSchema] = []
        dispatcher = get_event_dispatcher()

        @event_handler(PasswordResetEventSchema)
        async def _capture(schema: PasswordResetEventSchema) -> None:
            captured.append(schema)

        dispatcher.subscribe(AppEvent.USER_PASSWORD_RESET, _capture)
        yield captured
        dispatcher.unsubscribe(AppEvent.USER_PASSWORD_RESET, _capture)

    @pytest.mark.asyncio
    async def test_full_forgot_and_reset_flow(
        self,
        service: PasswordService,
        local_user: User,
        user_repo: UserRepository,
        password_security: PasswordSecurity,
        captured_reset_events: list[PasswordResetEventSchema],
    ) -> None:
        """Simulate the complete forgot → event dispatched → reset → login flow."""
        await service.forgot_password(local_user.email)
        await asyncio.sleep(0)  # yield so the async task fires the capture listener

        assert len(captured_reset_events) == 1
        raw_token: str = captured_reset_events[0].raw_token

        result = await service.reset_password(raw_token, "FinalNewPass1!")
        assert result is not None

        fetched = await user_repo.get_by_id(local_user.id)
        assert fetched is not None
        assert password_security.verify_password("FinalNewPass1!", fetched.password_hash)
        assert not password_security.verify_password("OldPassword123!", fetched.password_hash)

    @pytest.mark.asyncio
    async def test_full_change_then_forgot_reset_flow(
        self,
        service: PasswordService,
        local_user: User,
        user_repo: UserRepository,
        password_security: PasswordSecurity,
        captured_reset_events: list[PasswordResetEventSchema],
    ) -> None:
        """Change password first, then forgot-password flow should still work."""
        await service.change_password(local_user, "OldPassword123!", "Middle456!")

        await service.forgot_password(local_user.email)
        await asyncio.sleep(0)  # yield so the async task fires the capture listener

        assert len(captured_reset_events) == 1
        raw_token: str = captured_reset_events[0].raw_token

        result = await service.reset_password(raw_token, "Final789!")
        assert result is not None

        fetched = await user_repo.get_by_id(local_user.id)
        assert fetched is not None
        assert password_security.verify_password("Final789!", fetched.password_hash)
        assert not password_security.verify_password("Middle456!", fetched.password_hash)
        assert not password_security.verify_password("OldPassword123!", fetched.password_hash)
