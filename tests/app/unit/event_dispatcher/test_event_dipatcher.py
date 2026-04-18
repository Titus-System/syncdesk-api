import asyncio

import pytest

from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.exceptions import EventSchemaError, InvalidHandlerError
from app.core.event_dispatcher.schemas import DispatcherSchema


class FakePayload(DispatcherSchema):
    value: int


class WrongPayload(DispatcherSchema):
    other: str


EVENT1 = AppEvent.TICKET_CLOSED
PAYLOAD_MAP = {
    EVENT1: FakePayload,
    AppEvent.TRIAGE_FINISHED: FakePayload,
    AppEvent.TICKET_CREATED: FakePayload,
}


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher(PAYLOAD_MAP)


class TestEventDispatcher:
    async def test_handler_receives_payload(self, dispatcher: EventDispatcher) -> None:
        received: list[FakePayload] = []

        @event_handler(FakePayload)
        async def handler(payload: FakePayload) -> None:
            received.append(payload)

        dispatcher.subscribe(EVENT1, handler)

        await dispatcher.publish(EVENT1, FakePayload(value=42))
        await asyncio.sleep(0)

        assert len(received) == 1
        assert received[0].value == 42

    async def test_listener_without_decorator_should_fail(
        self, dispatcher: EventDispatcher
    ) -> None:
        async def handler(payload: FakePayload) -> None:
            print("passei")

        with pytest.raises(InvalidHandlerError) as e:
            dispatcher.subscribe(EVENT1, handler)
        assert "must be decorated with @event_handler" in str(e.value)

    async def test_subscribe_listener_wrong_signature_should_fail(
        self, dispatcher: EventDispatcher
    ) -> None:
        @event_handler(WrongPayload)
        async def handler(payload: WrongPayload) -> None:
            print("passei")

        with pytest.raises(InvalidHandlerError) as e:
            dispatcher.subscribe(EVENT1, handler)
        assert (
            f"Handler '{handler.__name__}' expects ({WrongPayload.__name__}), "
            f"but event '{EVENT1.value}' emits {FakePayload.__name__}"
        ) in str(e.value)

    async def test_publish_wrong_payload_should_fail(self, dispatcher: EventDispatcher) -> None:
        with pytest.raises(EventSchemaError):
            await dispatcher.publish(EVENT1, WrongPayload(other="should fail"))

    async def test_multiple_handlers_all_called(self, dispatcher: EventDispatcher) -> None:
        received: dict[str, FakePayload] = {}

        @event_handler(FakePayload)
        async def handler1(payload: FakePayload) -> None:
            received["h1"] = payload

        @event_handler(FakePayload)
        async def handler2(payload: FakePayload) -> None:
            received["h2"] = payload

        @event_handler(FakePayload)
        async def handler3(payload: FakePayload) -> None:
            received["h3"] = payload

        for fn in (handler1, handler2, handler3):
            dispatcher.subscribe(EVENT1, fn)

        await dispatcher.publish(EVENT1, FakePayload(value=42))
        await asyncio.sleep(0)
        assert len(received) == 3
        assert received["h1"].value == 42
        assert received["h2"].value == 42
        assert received["h3"].value == 42

    async def test_handler_only_called_for_subscribed_events(
        self, dispatcher: EventDispatcher
    ) -> None:
        received: dict[str, FakePayload] = {}

        @event_handler(FakePayload)
        async def handler1(payload: FakePayload) -> None:
            received["h1"] = payload

        @event_handler(FakePayload)
        async def handler2(payload: FakePayload) -> None:
            received["h2"] = payload

        dispatcher.subscribe(AppEvent.TRIAGE_FINISHED, handler1)
        dispatcher.subscribe(AppEvent.TICKET_CREATED, handler2)

        await dispatcher.publish(AppEvent.TRIAGE_FINISHED, FakePayload(value=42))
        await dispatcher.publish(AppEvent.TICKET_CREATED, FakePayload(value=43))
        await asyncio.sleep(0)

        assert len(received) == 2
        assert received["h1"].value == 42
        assert received["h2"].value == 43

    async def test_failing_handler_not_block_others(self, dispatcher: EventDispatcher) -> None:
        received: dict[str, FakePayload] = {}

        @event_handler(FakePayload)
        async def handler1(payload: FakePayload) -> None:
            raise Exception

        @event_handler(FakePayload)
        async def handler2(payload: FakePayload) -> None:
            received["h2"] = payload

        dispatcher.subscribe(EVENT1, handler1)
        dispatcher.subscribe(EVENT1, handler2)

        await dispatcher.publish(EVENT1, FakePayload(value=42))
        await asyncio.sleep(0)

        assert len(received) == 1
        assert received["h2"].value == 42

    async def test_event_with_no_subs_do_nothing(self, dispatcher: EventDispatcher) -> None:
        await dispatcher.publish(EVENT1, FakePayload(value=1))
        await asyncio.sleep(0)

    async def test_handler_subscribed_twice_only_executes_once(
        self, dispatcher: EventDispatcher
    ) -> None:
        call_count = 0

        @event_handler(FakePayload)
        async def handler(payload: FakePayload) -> None:
            nonlocal call_count
            call_count += 1

        dispatcher.subscribe(EVENT1, handler)
        dispatcher.subscribe(EVENT1, handler)

        await dispatcher.publish(EVENT1, FakePayload(value=42))
        await asyncio.sleep(0)

        assert call_count == 1

    async def test_handler_no_replay(self, dispatcher: EventDispatcher) -> None:
        received: list[FakePayload] = []

        @event_handler(FakePayload)
        async def handler(payload: FakePayload) -> None:
            received.append(payload)

        await dispatcher.publish(EVENT1, FakePayload(value=1))
        await asyncio.sleep(0)

        dispatcher.subscribe(EVENT1, handler)

        await dispatcher.publish(EVENT1, FakePayload(value=2))
        await asyncio.sleep(0)

        assert len(received) == 1
        assert received[0].value == 2
