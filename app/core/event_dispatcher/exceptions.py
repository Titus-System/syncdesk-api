from typing import Any


class EventSchemaError(TypeError):
    def __init__(self, message: str | None = None, errors: list[dict[str, Any]] | None = None):
        self.errors = errors
        super().__init__(message)


class InvalidHandlerError(TypeError):
    def __init__(self, message: str | None = None, errors: list[dict[str, Any]] | None = None):
        self.errors = errors
        super().__init__(message)
