import pytest

from app.core.event_dispatcher.decorators import event_handler
from app.core.event_dispatcher.exceptions import EventSchemaError
from app.core.event_dispatcher.schemas import DispatcherSchema


class FakePayload(DispatcherSchema):
    value: int


class OtherPayload(DispatcherSchema):
    other: str


class TestEventHandlerDecorator:
    async def test_calls_handler_with_correct_payload(self) -> None:
        received: list[FakePayload] = []

        @event_handler(FakePayload)
        async def handler(payload: FakePayload) -> None:
            received.append(payload)

        await handler(FakePayload(value=42))

        assert len(received) == 1
        assert received[0].value == 42

    async def test_raises_on_wrong_payload_type(self) -> None:
        @event_handler(FakePayload)
        async def handler(payload: FakePayload) -> None:
            pass

        with pytest.raises(EventSchemaError, match="expected.*FakePayload.*got OtherPayload"):
            await handler(OtherPayload(other="wrong"))

    async def test_exception_in_handler_is_caught_and_logged(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        @event_handler(FakePayload)
        async def handler(payload: FakePayload) -> None:
            raise ValueError("boom")

        await handler(FakePayload(value=1))

        assert "Event handler failed" in caplog.text

    async def test_exception_in_handler_does_not_propagate(self) -> None:
        @event_handler(FakePayload)
        async def handler(payload: FakePayload) -> None:
            raise RuntimeError("should not propagate")

        await handler(FakePayload(value=1))

    async def test_sets_event_payload_types_attribute(self) -> None:
        @event_handler(FakePayload, OtherPayload)
        async def handler(payload: DispatcherSchema) -> None:
            pass

        assert hasattr(handler, "__event_payload_types__")
        assert handler.__event_payload_types__ == (FakePayload, OtherPayload)  # type: ignore[attr-defined]

    async def test_preserves_function_name(self) -> None:
        @event_handler(FakePayload)
        async def my_handler(payload: FakePayload) -> None:
            pass

        assert my_handler.__name__ == "my_handler"

    async def test_no_payload_types_skips_validation(self) -> None:
        @event_handler()
        async def handler(payload: OtherPayload) -> None:
            pass

        await handler(OtherPayload(other="anything"))

    async def test_accepts_multiple_payload_types(self) -> None:
        received: list[DispatcherSchema] = []

        @event_handler(FakePayload, OtherPayload)
        async def handler(payload: DispatcherSchema) -> None:
            received.append(payload)

        await handler(FakePayload(value=1))
        await handler(OtherPayload(other="ok"))

        assert len(received) == 2
