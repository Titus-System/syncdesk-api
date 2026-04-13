import json
import logging
import os
from contextvars import ContextVar
from datetime import UTC, datetime
from functools import lru_cache
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue
from typing import Any

from app.core.config import get_settings

request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)
user_id_ctx: ContextVar[str | None] = ContextVar("user_id", default=None)


class ContextQueueHandler(QueueHandler):
    """Snapshots context vars onto the record before enqueuing.

    The QueueListener processes records in a separate thread where
    ContextVar values from the originating async task are not visible.
    """

    def prepare(self, record: logging.LogRecord) -> logging.LogRecord:
        record = super().prepare(record)
        ctx_request_id = request_id_ctx.get()
        if ctx_request_id:
            record.request_id = ctx_request_id  # type: ignore[attr-defined]

        ctx_user_id = user_id_ctx.get()
        if ctx_user_id:
            record.user_id = ctx_user_id  # type: ignore[attr-defined]

        return record


class JsonFormatter(logging.Formatter):
    _DEFAULT_KEYS = frozenset(
        logging.LogRecord("", 0, "", 0, None, None, None).__dict__.keys()
        | {"message", "taskName", "request_id", "user_id"}
    )

    def format(self, record: logging.LogRecord) -> str:
        log_record: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "message": record.getMessage(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        rid = getattr(record, "request_id", None)
        if rid:
            log_record["request_id"] = rid

        uid = getattr(record, "user_id", None)
        if uid:
            log_record["user_id"] = uid

        # Capture extra fields passed via logger.info("msg", extra={...})
        extra = {k: v for k, v in record.__dict__.items() if k not in self._DEFAULT_KEYS}
        if extra:
            log_record["extra"] = extra

        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record, ensure_ascii=False)


class DevFormatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[1;31m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self.LEVEL_COLORS.get(record.levelname, self.RESET)
        ts = datetime.now(UTC).strftime("%H:%M:%S")
        rid = getattr(record, "request_id", None)
        uid = getattr(record, "user_id", None)
        ctx_parts = [rid[:8] if rid else None, f"u:{uid[:8]}" if uid else None]
        ctx = " [" + " ".join(p for p in ctx_parts if p) + "]" if any(ctx_parts) else ""

        base = (
            f"{color}{ts} {record.levelname:<7}{self.RESET}"
            f" {record.name} · {record.funcName}:{record.lineno}"
            f"{ctx} — {record.getMessage()}"
        )
        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)

        return base


class AsyncLoggerRoot:
    """Initializes the root 'app' logger once and manages the QueueListener."""

    def __init__(self) -> None:
        if not os.path.exists("logs"):
            os.makedirs("logs")

        settings = get_settings()
        is_dev = settings.ENVIRONMENT == "development"

        json_formatter = JsonFormatter()
        max_file_size = 10 * 1024 * 1024  # 10MB
        backup_count = 5

        # File handlers (always JSON)
        file_handler = RotatingFileHandler(
            "logs/app.json", maxBytes=max_file_size, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(json_formatter)
        file_handler.setLevel(logging.INFO)

        error_handler = RotatingFileHandler(
            "logs/error.json", maxBytes=max_file_size, backupCount=backup_count, encoding="utf-8"
        )
        error_handler.setFormatter(json_formatter)
        error_handler.setLevel(logging.ERROR)

        # Console: plaintext in dev, JSON in production
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(DevFormatter() if is_dev else json_formatter)
        stream_handler.setLevel(logging.DEBUG)

        # Centralized logging queue — snapshots context vars before enqueuing
        self.log_queue: Queue[logging.LogRecord] = Queue(-1)
        queue_handler = ContextQueueHandler(self.log_queue)

        # Root app logger
        root = logging.getLogger("app")
        root.setLevel(logging.DEBUG)
        root.addHandler(queue_handler)

        # Queue listener to handle log records asynchronously
        self.listener = QueueListener(
            self.log_queue,
            file_handler,
            error_handler,
            stream_handler,
            respect_handler_level=True,
        )
        self.listener.start()

    def stop(self) -> None:
        self.listener.stop()


class Logger:
    """Thin wrapper around a stdlib logger with stacklevel-aware convenience methods."""

    def __init__(self, name: str = "app") -> None:
        self._logger = logging.getLogger(name)

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        self._logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        self._logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        self._logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        self._logger.error(message, *args, **kwargs)

    def exception(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        kwargs.setdefault("exc_info", True)
        self._logger.error(message, *args, **kwargs)


@lru_cache
def _init_root() -> AsyncLoggerRoot:
    return AsyncLoggerRoot()


def get_logger(name: str = "app") -> Logger:
    _init_root()
    return Logger(name)


def stop_logger() -> None:
    _init_root().stop()
