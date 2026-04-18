import asyncio
from collections.abc import Callable, Coroutine, Mapping
from functools import lru_cache
from typing import Any

from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.exceptions import EventSchemaError, InvalidHandlerError
from app.core.event_dispatcher.schemas import EVENT_PAYLOAD_MAP, DispatcherSchema

EventHandler = Callable[..., Coroutine[Any, Any, None]]


class EventDispatcher:
    """Asynchronous in-process event bus that decouples domain emitters from consumers.

    Handlers are fired as independent ``asyncio.Task`` instances (fire-and-forget).
    Use ``get_event_dispatcher()`` to obtain the singleton instance.
    """

    def __init__(self, payload_map: Mapping[AppEvent, type[DispatcherSchema]]) -> None:
        self._handlers: dict[AppEvent, list[EventHandler]] = {}
        self._payload_map = payload_map

    def subscribe(self, event: AppEvent, handler: EventHandler) -> None:
        """Register a handler to react to an event.

        Subscription is idempotent — subscribing the same handler twice has no effect.

        Raises:
            InvalidHandlerError: If the handler is not decorated with ``@event_handler``,
                or if its declared payload types are incompatible with the event's schema.
        """
        handler_schema = getattr(handler, "__event_payload_types__", None)
        if handler_schema is None:
            raise InvalidHandlerError(
                f"{handler.__name__} must be decorated with @event_handler"
            )

        event_schema = self._payload_map[event]
        if event_schema not in handler_schema:
            expected = ", ".join(t.__name__ for t in handler_schema)
            raise InvalidHandlerError(
                f"Handler '{handler.__name__}' expects ({expected}), "
                f"but event '{event.value}' emits {event_schema.__name__}"
            )

        if event not in self._handlers:
            self._handlers[event] = [handler]
        else:
            if handler not in self._handlers[event]:
                self._handlers[event].append(handler)

    async def publish(self, event: AppEvent, payload: DispatcherSchema) -> None:
        """Emit an event to all subscribed handlers.

        Validates that ``payload`` is an instance of the schema mapped to ``event``
        in ``EVENT_PAYLOAD_MAP``. Each handler runs as an independent ``asyncio.Task``.

        Raises:
            EventSchemaError: If the payload type does not match the expected schema.
        """
        expected = self._payload_map[event]
        if not isinstance(payload, expected):
            raise EventSchemaError(
                f"{event.value} expects {expected.__name__}, received {type(payload).__name__}"
            )

        for handler in self._handlers.get(event, []):
            asyncio.create_task(handler(payload))


@lru_cache
def get_event_dispatcher() -> EventDispatcher:
    return EventDispatcher(EVENT_PAYLOAD_MAP)
