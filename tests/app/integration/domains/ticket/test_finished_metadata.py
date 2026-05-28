"""Integration tests for the persistence of ``closed_at`` and ``closed_by_agent``.

Garante que transitar para ``status=finished`` via ``update_ticket`` ou
``update_status`` popula corretamente os campos novos do Ticket, e que
outras transições terminais (cancel) NÃO populam esses campos.
"""
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import EVENT_PAYLOAD_MAP
from app.core.logger import get_logger
from app.core.security import PasswordSecurity, ResetTokenSecurity
from app.domains.auth.entities import Role, User, UserWithRoles
from app.domains.auth.repositories.password_reset_token_repository import (
    PasswordResetTokenRepository,
)
from app.domains.auth.repositories.user_level_repository import UserLevelRepository
from app.domains.auth.repositories.user_repository import UserRepository
from app.domains.auth.services.user_service import UserService
from app.domains.ticket.models import (
    Ticket,
    TicketClient,
    TicketCompany,
    TicketCriticality,
    TicketHistory,
    TicketLevel,
    TicketStatus,
    TicketType,
)
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.schemas import (
    CancelTicketRequest,
    UpdateTicketDTO,
    UpdateTicketStatusDTO,
)
from app.domains.ticket.services import TicketService


@pytest_asyncio.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None, None]:
    await Ticket.delete_all()
    yield
    await Ticket.delete_all()


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher(EVENT_PAYLOAD_MAP, get_logger("test.finished_metadata"))


@pytest.fixture
def user_service(
    db_session: AsyncSession, dispatcher: EventDispatcher
) -> UserService:
    return UserService(
        repo=UserRepository(db_session),
        dispatcher=dispatcher,
        token_repo=PasswordResetTokenRepository(db_session),
        reset_token_security=ResetTokenSecurity(),
        password_security=PasswordSecurity(),
    )


@pytest.fixture
def service(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    user_service: UserService,
    db_session: AsyncSession,
    dispatcher: EventDispatcher,
) -> TicketService:
    return TicketService(
        TicketRepository(mongo_db_conn),
        user_service,
        UserLevelRepository(db_session),
        dispatcher,
    )


def _make_ticket(
    *,
    status: TicketStatus = TicketStatus.IN_PROGRESS,
    with_active_agent: tuple[UUID, str, str] | None = None,
) -> Ticket:
    history: list[TicketHistory] = []
    if with_active_agent is not None:
        agent_id, name, level = with_active_agent
        history.append(
            TicketHistory(
                agent_id=agent_id,
                name=name,
                level=level,
                assignment_date=datetime.now(UTC) - timedelta(hours=1),
                exit_date=None,
            )
        )
    return Ticket(
        triage_id=PydanticObjectId(),
        type=TicketType.ISSUE,
        criticality=TicketCriticality.HIGH,
        product="Sistema",
        status=status,
        level=TicketLevel.N1,
        creation_date=datetime.now(UTC) - timedelta(days=1),
        description="Teste finished metadata",
        chat_ids=[],
        agent_history=history,
        client=TicketClient(
            id=uuid4(),
            name="Cliente",
            email="c@test.com",
            company=TicketCompany(id=uuid4(), name="Empresa"),
        ),
        comments=[],
    )


class TestUpdateTicketFinishedMetadata:
    @pytest.mark.asyncio
    async def test_finishing_via_patch_populates_closed_at_and_closed_by_agent(
        self, service: TicketService
    ) -> None:
        agent_id = uuid4()
        ticket = await _make_ticket(
            with_active_agent=(agent_id, "Julia", "N2")
        ).insert()
        assert ticket.id is not None

        before = datetime.now(UTC)
        await service.update_ticket(
            ticket.id, UpdateTicketDTO(status=TicketStatus.FINISHED)
        )
        after = datetime.now(UTC)

        reloaded = await Ticket.get(ticket.id)
        assert reloaded is not None
        assert reloaded.status == TicketStatus.FINISHED
        assert reloaded.closed_at is not None
        # Beanie devolve datetime naive após roundtrip; normalizamos para UTC.
        closed_at = reloaded.closed_at
        if closed_at.tzinfo is None:
            closed_at = closed_at.replace(tzinfo=UTC)
        # MongoDB trunca datetime para precisão de milissegundo, então closed_at
        # pode ficar até ~1ms abaixo de `before`. Tolerância de 1s cobre folgado.
        tolerance = timedelta(seconds=1)
        assert before - tolerance <= closed_at <= after + tolerance
        assert reloaded.closed_by_agent is not None
        assert reloaded.closed_by_agent.agent_id == agent_id
        assert reloaded.closed_by_agent.name == "Julia"
        assert reloaded.closed_by_agent.level == "N2"

    @pytest.mark.asyncio
    async def test_finishing_without_active_agent_sets_closed_by_agent_none(
        self, service: TicketService
    ) -> None:
        ticket = await _make_ticket(
            status=TicketStatus.IN_PROGRESS, with_active_agent=None
        ).insert()
        assert ticket.id is not None

        await service.update_ticket(
            ticket.id, UpdateTicketDTO(status=TicketStatus.FINISHED)
        )

        reloaded = await Ticket.get(ticket.id)
        assert reloaded is not None
        assert reloaded.status == TicketStatus.FINISHED
        assert reloaded.closed_at is not None
        assert reloaded.closed_by_agent is None

    @pytest.mark.asyncio
    async def test_closed_by_agent_is_snapshot_not_reference(
        self, service: TicketService
    ) -> None:
        """Mudanças posteriores em agent_history não devem alterar o snapshot."""
        agent_id = uuid4()
        ticket = await _make_ticket(
            with_active_agent=(agent_id, "Original", "N1")
        ).insert()
        assert ticket.id is not None

        await service.update_ticket(
            ticket.id, UpdateTicketDTO(status=TicketStatus.FINISHED)
        )

        # Reload, mutar o agent_history original
        reloaded = await Ticket.get(ticket.id)
        assert reloaded is not None
        snapshot_name_before = reloaded.closed_by_agent.name  # type: ignore[union-attr]
        # Tentando mutar via repo direto:
        if reloaded.agent_history:
            reloaded.agent_history[0].name = "Renomeado"
        await reloaded.save()

        # Reload novamente — snapshot deve estar intacto
        again = await Ticket.get(ticket.id)
        assert again is not None
        assert again.closed_by_agent is not None
        assert again.closed_by_agent.name == snapshot_name_before
        assert again.agent_history[0].name == "Renomeado"

    @pytest.mark.asyncio
    async def test_non_finished_transition_does_not_set_closed_at(
        self, service: TicketService
    ) -> None:
        ticket = await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            with_active_agent=(uuid4(), "X", "N1"),
        ).insert()
        assert ticket.id is not None

        # Transição para waiting_for_provider (não terminal)
        await service.update_ticket(
            ticket.id, UpdateTicketDTO(status=TicketStatus.WAITING_FOR_PROVIDER)
        )

        reloaded = await Ticket.get(ticket.id)
        assert reloaded is not None
        assert reloaded.closed_at is None
        assert reloaded.closed_by_agent is None


class TestUpdateStatusFinishedMetadata:
    @pytest.mark.asyncio
    async def test_finishing_via_legacy_status_route_populates_metadata(
        self, service: TicketService
    ) -> None:
        agent_id = uuid4()
        ticket = await _make_ticket(
            with_active_agent=(agent_id, "Mafe", "N3")
        ).insert()
        assert ticket.id is not None

        actor = UserWithRoles(
            id=agent_id,
            email="mafe@test.com",
            name="Mafe",
            username="mafe",
            roles=[Role(id=99, name="agent")],
        )
        await service.update_status(
            ticket.id,
            UpdateTicketStatusDTO(status=TicketStatus.FINISHED),
            actor=actor,
        )

        reloaded = await Ticket.get(ticket.id)
        assert reloaded is not None
        assert reloaded.status == TicketStatus.FINISHED
        assert reloaded.closed_at is not None
        assert reloaded.closed_by_agent is not None
        assert reloaded.closed_by_agent.agent_id == agent_id


class TestCancellingDoesNotSetClosedAt:
    @pytest.mark.asyncio
    async def test_cancel_ticket_does_not_populate_closed_at(
        self, service: TicketService
    ) -> None:
        ticket = await _make_ticket(
            with_active_agent=(uuid4(), "X", "N1")
        ).insert()
        assert ticket.id is not None

        await service.cancel_ticket(
            ticket.id,
            CancelTicketRequest(reason="cliente desistiu"),
        )

        reloaded = await Ticket.get(ticket.id)
        assert reloaded is not None
        assert reloaded.status == TicketStatus.CANCELLED
        assert reloaded.closed_at is None
        assert reloaded.closed_by_agent is None
