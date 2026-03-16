from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from uuid import UUID

from app.core.http.schemas import SessionDeviceInfo

from .enums import OAuthProvider, SessionStatus


def _utcnow() -> datetime:
    """Return the current UTC time as a timezone-naive datetime (matches DB columns)."""
    return datetime.now(UTC).replace(tzinfo=None)


def _serialize_value(value: object) -> object:
    """Convert non-JSON-serializable values to their string representations."""
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


@dataclass
class Permission:
    id: int
    name: str
    description: str | None = None

    def __repr__(self) -> str:
        return f"<Permission {self.name}>"


@dataclass
class Role:
    id: int
    name: str
    description: str | None = None

    def __repr__(self) -> str:
        return f"<Role {self.name}>"


@dataclass
class RoleWithPermissions(Role):
    permissions: list[Permission] | None = None


@dataclass
class PermissionWithRoles(Permission):
    roles: list[Role] | None = None


@dataclass
class RolePermission:
    role_id: int
    permission_id: int


@dataclass
class Session:
    id: UUID
    user_id: UUID
    refresh_token_hash: str
    status: SessionStatus
    expires_at: datetime
    created_at: datetime
    device_info: SessionDeviceInfo | None = None
    last_used_at: datetime | None = None

    def __repr__(self) -> str:
        return f"<Session {self.id}>"

    def is_expired(self) -> bool:
        """Check if session has expired."""
        return _utcnow() > self.expires_at

    def is_active(self) -> bool:
        return self.status == SessionStatus.ACTIVE

    def is_valid(self) -> bool:
        """Session is valid if active and not expired."""
        return self.is_active() and not self.is_expired()

    def is_revoked(self) -> bool:
        """Check if session was explicitly revoked."""
        return self.status == SessionStatus.REVOKED

    def mark_used(self) -> None:
        """Update last used timestamp."""
        self.last_used_at = _utcnow()

    def revoke(self) -> None:
        """Revoke this session."""
        self.status = SessionStatus.REVOKED

    def matches_device_fingerprint(self, device_info: SessionDeviceInfo | None) -> bool:
        if self.device_info is None and device_info is None:
            return True
        if self.device_info is None or device_info is None:
            return False
        return self.device_info.fingerprint() == device_info.fingerprint()


@dataclass
class User:
    id: UUID
    email: str
    password_hash: str | None = None
    username: str | None = None
    name: str | None = None
    oauth_provider: OAuthProvider | None = None
    oauth_provider_id: str | None = None
    is_active: bool = True
    is_verified: bool = False

    def __repr__(self) -> str:
        return f"<User (id={self.id}, email={self.email})>"

    def validate_email(self) -> None:
        if "@" not in self.email:
            raise ValueError("Invalid email")
        if " " in self.email:
            raise ValueError("Email cannot contain spaces")
        if not self.email:
            raise ValueError("Email required")

    def validate_username(self) -> None:
        if self.username is None:
            return
        if not self.username.isidentifier():
            raise ValueError("Invalid username")
        if len(self.username) < 3:
            raise ValueError("Username too short")

    def has_oauth(self) -> bool:
        return self.oauth_provider is not None and self.oauth_provider_id is not None

    def has_password(self) -> bool:
        return self.password_hash is not None

    def can_oauth_login(self) -> bool:
        has_provider = self.oauth_provider is not None
        has_id = self.oauth_provider_id is not None
        return has_provider and has_id and self.is_active

    def can_local_login(self) -> bool:
        has_password = self.password_hash is not None
        has_username = self.username is not None
        return has_password and has_username and self.is_active

    def is_oauth_user(self) -> bool:
        return self.has_oauth()

    def is_local_user(self) -> bool:
        return self.password_hash is not None

    def can_login(self) -> bool:
        if not self.is_active:
            return False
        return self.can_local_login() or self.can_oauth_login()

    def to_response_dict(self) -> dict[str, object]:
        """Return a dict safe for API responses, excluding sensitive fields."""
        return {k: _serialize_value(v) for k, v in self.__dict__.items() if k != "password_hash"}


@dataclass
class UserWithRoles(User):
    roles: list[Role] | None = None

    def to_response_dict(self) -> dict[str, object]:
        """Return a dict safe for API responses, excluding sensitive fields."""
        base = super().to_response_dict()
        if self.roles is not None:
            base["roles"] = [
                {k: _serialize_value(v) for k, v in role.__dict__.items()} for role in self.roles
            ]
        return base

    def roles_names(self) -> list[str]:
        return [r.name for r in self.roles] if self.roles is not None else []


@dataclass
class UserRole:
    user_id: UUID
    role_id: int
