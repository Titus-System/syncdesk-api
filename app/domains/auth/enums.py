from enum import Enum

from app.core.http.schemas import DeviceType as DeviceType  # noqa: F401


class SessionStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    INVALID = "invalid"
    REVOKED = "revoked"


class OAuthProvider(Enum):
    LOCAL = "local"
    GOOGLE = "google"
    MICROSOFT = "microsoft"


def enum_values(enum_class: type[Enum]) -> list[str]:
    """Return enum values for a given Enum class."""
    return [member.value for member in enum_class]
