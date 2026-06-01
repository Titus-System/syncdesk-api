from enum import Enum


class EmailOutboxStatus(str, Enum):
    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    RETRY = "RETRY"
    DEAD = "DEAD"


class EmailEventType(str, Enum):
    WELCOME_INVITE = "WELCOME_INVITE"
    PASSWORD_RESET = "PASSWORD_RESET"


def status_values(enum_class: type[Enum]) -> list[str]:
    return [m.value for m in enum_class]
