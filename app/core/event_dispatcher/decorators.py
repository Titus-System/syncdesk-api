from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any, ParamSpec

from app.core.event_dispatcher.exceptions import EventSchemaError
from app.core.event_dispatcher.schemas import DispatcherSchema
from app.core.logger import get_logger

logger = get_logger()

P = ParamSpec("P")


def event_handler(
    *payload_types: type[DispatcherSchema],
) -> Callable[
    [Callable[P, Coroutine[Any, Any, None]]],
    Callable[P, Coroutine[Any, Any, None]],
]:
    """Required decorator for all event handlers registered via ``EventDispatcher.subscribe``.

    Responsibilities:
        - Declares which ``DispatcherSchema`` subtypes this handler accepts.
          ``subscribe`` uses this metadata to validate wiring at startup.
        - Validates the payload type at call time, raising ``EventSchemaError`` on mismatch.
        - Wraps the handler body in ``try/except`` with structured logging,
          so individual handler failures are logged but never propagate.

    Args:
        *payload_types: One or more ``DispatcherSchema`` subclasses that this handler accepts.

    Example::

        @event_handler(TriageFinishedEventSchema)
        async def on_triage_finished(self, payload: TriageFinishedEventSchema) -> None:
            ...
    """
    def decorator(
        fn: Callable[P, Coroutine[Any, Any, None]]
    ) -> Callable[P, Coroutine[Any, Any, None]]:
        @wraps(fn)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> None:
            payload = args[-1] if args else kwargs.get("payload")
            if payload_types and not isinstance(payload, payload_types):
                expected = ", ".join(t.__name__ for t in payload_types)
                raise EventSchemaError(
                    f"{fn.__qualname__} expected ({expected}), got {type(payload).__name__}"
                )

            try:
                await fn(*args, **kwargs)
            except Exception:
                logger.exception(
                    "Event handler failed: %s",
                    fn.__qualname__,
                    extra={
                        "payload": payload.model_dump()
                        if isinstance(payload, DispatcherSchema)
                        else None
                    },
                )
        wrapper.__event_payload_types__ = payload_types  # type: ignore[attr-defined]
        return wrapper

    return decorator
