from typing import Any


class EmailDeliveryError(Exception):
    def __init__(
        self, message: str | None = None, errors: list[dict[str, Any]] | None = None
    ) -> None:
        self.errors = errors
        super().__init__(f"Failed to send email. {message}")
