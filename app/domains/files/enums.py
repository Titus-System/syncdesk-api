from enum import Enum


class FileContext(Enum):
    LIVE_CHAT_MESSAGE = "live_chat_message"
    USER_AVATAR = "user_avatar"


class FileStatus(Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    FAILED = "failed"
    DELETED = "deleted"


def enum_values(enum_class: type[Enum]) -> list[str]:
    """Return the string values of an Enum class (used by SQLAlchemy native enums)."""
    return [member.value for member in enum_class]
