class FileNotFoundError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"File does not exist. {message or ''}")


class FileNotReadyError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"File is not in uploaded state. {message or ''}")


class FileAccessForbiddenError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Access to file is forbidden. {message or ''}")


class InvalidFileContextError(Exception):
    def __init__(self, message: str | None = None) -> None:
        super().__init__(f"Invalid file context. {message or ''}")


class FileTooLargeError(Exception):
    def __init__(self, limit: int, actual: int) -> None:
        super().__init__(f"File size {actual} exceeds limit of {limit} bytes.")


class UnsupportedFileTypeError(Exception):
    def __init__(self, content_type: str) -> None:
        super().__init__(f"Unsupported content type: {content_type}.")
