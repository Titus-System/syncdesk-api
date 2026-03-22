class ChatRoomNotFoundError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"ChatRoom does not exist. {message or ''}")


class InvalidMessageError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Invalid chat message payload. {message or ''}")
