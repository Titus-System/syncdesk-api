class UserCannotLoseLoginMethodError(Exception):
    def __init__(self) -> None:
        super().__init__("User must have at least one login method.")


class SessionNotFoundError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Session does not exist. {message or ''}")


class SessionExpiredError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Session has expired. {message or ''}")


class InvalidSessionError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Invalid session. {message or ''}")


class UserNotFoundError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"User does not exist. {message or ''}")


class UserPasswordNotConfiguredError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Password not configured for user. {message or ''}")


class InvalidPasswordError(Exception):
    def __init__(self, user_email: str) -> None:
        super().__init__(f"Invalid password for user {user_email}")


class InvalidCredentialsError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Invalid credentials. {message or ''}")
