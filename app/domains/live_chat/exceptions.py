from typing import Any


class ChatRoomNotFoundError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"ChatRoom does not exist. {message or ''}")


class InvalidMessageError(Exception):
    def __init__(
        self, message: str | None = None, errors: list[dict[str, Any]] | None = None
    ) -> None:
        self.errors = errors
        super().__init__(f"Invalid chat message payload. {message or ''}")


class CreateChatRoomError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Server could no ceate chat room. {message or ''}")
