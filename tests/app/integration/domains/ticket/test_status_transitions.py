import asyncio
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from fastapi import status as http_status
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import (
    EVENT_PAYLOAD_MAP,
    TicketCancelledEventSchema,
    TicketClosedEventSchema,
)
from app.core.exceptions import AppHTTPException
from app.core.logger import get_logger
from app.core.security import PasswordSecurity, ResetTokenSecurity
from app.domains.auth.repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from app.domains.auth.repositories.user_repository import UserRepository
from app.domains.auth.services.user_service import UserService
from app.domains.ticket.models import (
    Ticket,
    TicketClient,
    TicketCompany,
    TicketCriticality,
    TicketHistory,
    TicketStatus,
    TicketType,
)
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.schemas import CancelTicketRequest, UpdateTicketDTO
from app.domains.ticket.services import TicketService


NON_TERMINAL_STATUSES = [
    s
    for s in TicketStatus
    if s not in {TicketStatus.FINISHED, TicketStatus.CANCELLED}
]


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_tickets() -> AsyncGenerator[None, None]:
    await Ticket.delete_all()
    yield
    await Ticket.delete_all()


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher(EVENT_PAYLOAD_MAP, get_logger("test.ticket_transitions"))


@pytest.fixture
def user_service(db_session: AsyncSession, dispatcher: EventDispatcher) -> UserService:
    return UserService(
        repo=UserRepository(db_session),
        dispatcher=dispatcher,
        token_repo=PasswordResetTokenRepository(db_session),
        reset_token_security=ResetTokenSecurity(),
        password_security=PasswordSecurity(),
    )


@pytest.fixture
def ticket_service(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    user_service: UserService,
    dispatcher: EventDispatcher,
) -> TicketService:
    return TicketService(TicketRepository(mongo_db_conn), user_service, dispatcher)


async def _drain_background_tasks() -> None:
    pending = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


def _make_ticket(
    *,
    status: TicketStatus = TicketStatus.AWAITING_ASSIGNMENT,
    with_active_agent: bool = False,
) -> Ticket:
    agent_history: list[TicketHistory] = []
    if with_active_agent:
        agent_history.append(
            TicketHistory(
                agent_id=uuid4(),
                name="Agente Atual",
                level="N1",
                assignment_date=datetime.now(UTC),
                exit_date=None,
                transfer_reason=None,
            )
        )
    return Ticket(
        triage_id=PydanticObjectId(),
        type=TicketType.ISSUE,
        criticality=TicketCriticality.HIGH,
        product="Sistema",
        status=status,
        creation_date=datetime.now(UTC),
        description="Erro de teste",
        chat_ids=[],
        agent_history=agent_history,
        client=TicketClient(
            id=uuid4(),
            name="Cliente",
            email="cliente@test.com",
            company=TicketCompany(id=uuid4(), name="Empresa"),
        ),
        comments=[],
    )


def _spy_on_publish(
    dispatcher: EventDispatcher, target_event: AppEvent
) -> list[Any]:
    received: list[Any] = []
    original_publish = dispatcher.publish

    async def spy(event: AppEvent, payload: Any) -> None:
        if event == target_event:
            received.append(payload)
        await original_publish(event, payload)

    dispatcher.publish = spy  # type: ignore[method-assign]
    return received


class TestCancelTicketTransitions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("starting_status", NON_TERMINAL_STATUSES)
    async def test_cancel_succeeds_from_every_non_terminal_status(
        self,
        ticket_service: TicketService,
        starting_status: TicketStatus,
    ) -> None:
        ticket = await _make_ticket(status=starting_status).insert()
        assert ticket.id is not None

        result = await ticket_service.cancel_ticket(
            ticket.id, CancelTicketRequest(reason="cliente desistiu")
        )

        assert result.status == TicketStatus.CANCELLED
        reloaded = await Ticket.get(ticket.id)
        assert reloaded is not None
        assert reloaded.status == TicketStatus.CANCELLED

    @pytest.mark.asyncio
    async def test_cancel_publishes_ticket_cancelled_event(
        self,
        ticket_service: TicketService,
        dispatcher: EventDispatcher,
    ) -> None:
        received = _spy_on_publish(dispatcher, AppEvent.TICKET_CANCELLED)
        ticket = await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        assert ticket.id is not None

        await ticket_service.cancel_ticket(
            ticket.id, CancelTicketRequest(reason="duplicado")
        )
        await _drain_background_tasks()

        assert len(received) == 1
        event = received[0]
        assert isinstance(event, TicketCancelledEventSchema)
        assert event.ticket_id == ticket.id
        assert event.previous_status == TicketStatus.IN_PROGRESS
        assert event.reason == "duplicado"

    @pytest.mark.asyncio
    async def test_cancel_closes_active_agent_assignment(
        self,
        ticket_service: TicketService,
    ) -> None:
        ticket = await _make_ticket(
            status=TicketStatus.IN_PROGRESS, with_active_agent=True
        ).insert()
        assert ticket.id is not None

        await ticket_service.cancel_ticket(
            ticket.id, CancelTicketRequest(reason="erro de classificação")
        )

        reloaded = await Ticket.get(ticket.id)
        assert reloaded is not None
        active = [h for h in reloaded.agent_history if h.exit_date is None]
        assert active == []
        assert reloaded.agent_history[-1].transfer_reason == "erro de classificação"

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "terminal_status", [TicketStatus.FINISHED, TicketStatus.CANCELLED]
    )
    async def test_cancel_rejects_terminal_tickets(
        self,
        ticket_service: TicketService,
        terminal_status: TicketStatus,
    ) -> None:
        ticket = await _make_ticket(status=terminal_status).insert()
        assert ticket.id is not None

        with pytest.raises(AppHTTPException) as exc_info:
            await ticket_service.cancel_ticket(
                ticket.id, CancelTicketRequest(reason="tentativa")
            )

        assert exc_info.value.status_code == http_status.HTTP_400_BAD_REQUEST

    @pytest.mark.asyncio
    async def test_cancel_returns_404_when_ticket_missing(
        self, ticket_service: TicketService
    ) -> None:
        with pytest.raises(AppHTTPException) as exc_info:
            await ticket_service.cancel_ticket(
                PydanticObjectId(), CancelTicketRequest(reason="inexistente")
            )

        assert exc_info.value.status_code == http_status.HTTP_404_NOT_FOUND


class TestUpdateTicketStatusTransitions:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (TicketStatus.AWAITING_ASSIGNMENT, TicketStatus.IN_PROGRESS),
            (TicketStatus.IN_PROGRESS, TicketStatus.WAITING_FOR_PROVIDER),
            (TicketStatus.IN_PROGRESS, TicketStatus.WAITING_FOR_VALIDATION),
            (TicketStatus.WAITING_FOR_PROVIDER, TicketStatus.IN_PROGRESS),
            (TicketStatus.WAITING_FOR_VALIDATION, TicketStatus.FINISHED),
        ],
    )
    async def test_update_accepts_allowed_status_change(
        self,
        ticket_service: TicketService,
        from_status: TicketStatus,
        to_status: TicketStatus,
    ) -> None:
        ticket = await _make_ticket(status=from_status).insert()
        assert ticket.id is not None

        result = await ticket_service.update_ticket(
            ticket.id, UpdateTicketDTO(status=to_status)
        )

        assert result.status == to_status

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "from_status,to_status",
        [
            (TicketStatus.OPEN, TicketStatus.FINISHED),
            (TicketStatus.AWAITING_ASSIGNMENT, TicketStatus.FINISHED),
            (TicketStatus.WAITING_FOR_PROVIDER, TicketStatus.FINISHED),
        ],
    )
    async def test_update_rejects_forbidden_status_change(
        self,
        ticket_service: TicketService,
        from_status: TicketStatus,
        to_status: TicketStatus,
    ) -> None:
        ticket = await _make_ticket(status=from_status).insert()
        assert ticket.id is not None

        with pytest.raises(AppHTTPException) as exc_info:
            await ticket_service.update_ticket(
                ticket.id, UpdateTicketDTO(status=to_status)
            )

        assert exc_info.value.status_code == http_status.HTTP_400_BAD_REQUEST
        assert from_status.value in exc_info.value.detail
        assert to_status.value in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_update_to_finished_publishes_ticket_closed_event(
        self,
        ticket_service: TicketService,
        dispatcher: EventDispatcher,
    ) -> None:
        received = _spy_on_publish(dispatcher, AppEvent.TICKET_CLOSED)
        ticket = await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        assert ticket.id is not None

        await ticket_service.update_ticket(
            ticket.id, UpdateTicketDTO(status=TicketStatus.FINISHED)
        )
        await _drain_background_tasks()

        assert len(received) == 1
        event = received[0]
        assert isinstance(event, TicketClosedEventSchema)
        assert event.ticket_id == ticket.id

    @pytest.mark.asyncio
    async def test_update_to_cancelled_via_patch_is_rejected_only_when_invalid(
        self,
        ticket_service: TicketService,
    ) -> None:
        ticket = await _make_ticket(status=TicketStatus.FINISHED).insert()
        assert ticket.id is not None

        with pytest.raises(AppHTTPException) as exc_info:
            await ticket_service.update_ticket(
                ticket.id, UpdateTicketDTO(status=TicketStatus.CANCELLED)
            )

        assert exc_info.value.status_code == http_status.HTTP_400_BAD_REQUEST
