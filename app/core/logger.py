import json
import logging
import os
from datetime import UTC, datetime
from functools import lru_cache
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler
from queue import Queue
from typing import Any


class JsonFormatter(logging.Formatter):
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
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_record, ensure_ascii=False)


class AsyncLogger:
    def __init__(self) -> None:
        if not os.path.exists("logs"):
            os.makedirs("logs")

        formatter = JsonFormatter()

        max_file_size = 10 * 1024 * 1024  # 10MB
        backup_count = 5

        # File handlers
        file_handler = RotatingFileHandler(
            "logs/app.json", maxBytes=max_file_size, backupCount=backup_count, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        error_handler = RotatingFileHandler(
            "logs/error.json", maxBytes=max_file_size, backupCount=backup_count, encoding="utf-8"
        )
        error_handler.setFormatter(formatter)
        error_handler.setLevel(logging.ERROR)

        # Console (also in json)
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        stream_handler.setLevel(logging.DEBUG)

        # Centralized logging queue
        self.log_queue: Queue[logging.LogRecord] = Queue(-1)
        queue_handler = QueueHandler(self.log_queue)

        # Main logger
        self.logger = logging.getLogger("app")
        self.logger.setLevel(logging.DEBUG)
        self.logger.addHandler(queue_handler)

        # Queue listener to handle log records asynchronously
        self.listener = QueueListener(
            self.log_queue,
            file_handler,
            error_handler,
            stream_handler,
        )
        self.listener.start()

    def debug(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        self.logger.debug(message, *args, **kwargs)

    def info(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        self.logger.info(message, *args, **kwargs)

    def warning(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        self.logger.warning(message, *args, **kwargs)

    def error(self, message: str, *args: Any, **kwargs: Any) -> None:
        kwargs.setdefault("stacklevel", 2)
        self.logger.error(message, *args, **kwargs)

    def stop(self) -> None:
        self.listener.stop()


@lru_cache
def get_logger() -> AsyncLogger:
    return AsyncLogger()
