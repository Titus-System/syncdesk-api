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
from app.domains.ticket.schemas import TicketDashboardFiltersDTO
from app.domains.ticket.services import TicketService, _TOP_ASSIGNEES_LIMIT


@pytest_asyncio.fixture(autouse=True)
async def _cleanup() -> AsyncGenerator[None, None]:
    await Ticket.delete_all()
    yield
    await Ticket.delete_all()


@pytest.fixture
def repository(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
) -> TicketRepository:
    return TicketRepository(mongo_db_conn)


@pytest.fixture
def dispatcher() -> EventDispatcher:
    return EventDispatcher(EVENT_PAYLOAD_MAP, get_logger("test.dashboard"))


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
    repository: TicketRepository,
    user_service: UserService,
    db_session: AsyncSession,
    dispatcher: EventDispatcher,
) -> TicketService:
    return TicketService(repository, user_service, UserLevelRepository(db_session), dispatcher)


def _make_ticket(
    *,
    ticket_type: TicketType = TicketType.ISSUE,
    status: TicketStatus = TicketStatus.AWAITING_ASSIGNMENT,
    criticality: TicketCriticality = TicketCriticality.HIGH,
    creation_date: datetime | None = None,
    active_agent: tuple[UUID, str] | None = None,
    closed_agent: tuple[UUID, str] | None = None,
) -> Ticket:
    history: list[TicketHistory] = []
    base_time = creation_date or datetime.now(UTC)
    if closed_agent is not None:
        agent_id, agent_name = closed_agent
        history.append(
            TicketHistory(
                agent_id=agent_id,
                name=agent_name,
                level="N1",
                assignment_date=base_time,
                exit_date=base_time + timedelta(minutes=5),
                transfer_reason="rotacionado",
            )
        )
    if active_agent is not None:
        agent_id, agent_name = active_agent
        history.append(
            TicketHistory(
                agent_id=agent_id,
                name=agent_name,
                level="N1",
                assignment_date=base_time,
                exit_date=None,
            )
        )
    return Ticket(
        triage_id=PydanticObjectId(),
        type=ticket_type,
        criticality=criticality,
        product="Sistema",
        status=status,
        level=TicketLevel.N1,
        creation_date=base_time,
        description="Erro de teste",
        chat_ids=[],
        agent_history=history,
        client=TicketClient(
            id=uuid4(),
            name="Cliente",
            email="cliente@test.com",
            company=TicketCompany(id=uuid4(), name="Empresa"),
        ),
        comments=[],
    )


class TestDashboardKPIs:
    @pytest.mark.asyncio
    async def test_empty_collection_returns_zeroed_kpis_and_buckets(
        self, service: TicketService
    ) -> None:
        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        assert result.kpis.open_count == 0
        assert result.kpis.cancelled_count == 0
        assert result.kpis.unassigned_count == 0
        assert result.kpis.overdue_count == 0
        # Donut de status sempre materializa os 3 buckets, mesmo zerados.
        counts = {b.bucket: b.count for b in result.open_breakdown}
        assert counts == {"pendente": 0, "em_atendimento": 0, "nao_atribuidos": 0}
        # Donut de agentes sem dados → lista vazia.
        assert result.assigned_breakdown == []

    @pytest.mark.asyncio
    async def test_counts_split_by_status_and_assignment(
        self, service: TicketService
    ) -> None:
        # 2 abertos sem assignment
        await _make_ticket(status=TicketStatus.AWAITING_ASSIGNMENT).insert()
        await _make_ticket(status=TicketStatus.OPEN).insert()
        # 1 in_progress com agente ativo
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            active_agent=(uuid4(), "Julia"),
        ).insert()
        # 1 cancelado e 1 finalizado (não contam como abertos)
        await _make_ticket(status=TicketStatus.CANCELLED).insert()
        await _make_ticket(status=TicketStatus.FINISHED).insert()

        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        assert result.kpis.open_count == 3
        assert result.kpis.cancelled_count == 1
        assert result.kpis.unassigned_count == 2

    @pytest.mark.asyncio
    async def test_overdue_uses_criticality_sla_window(
        self, service: TicketService
    ) -> None:
        old = datetime.now(UTC) - timedelta(days=10)
        recent = datetime.now(UTC) - timedelta(hours=1)
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            criticality=TicketCriticality.HIGH,
            creation_date=old,
        ).insert()  # high: 1d SLA, criado há 10d → vencido
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            criticality=TicketCriticality.LOW,
            creation_date=recent,
        ).insert()  # low: 5d SLA, criado há 1h → não vencido
        await _make_ticket(
            status=TicketStatus.FINISHED,
            criticality=TicketCriticality.HIGH,
            creation_date=old,
        ).insert()  # finalizado: não conta

        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        assert result.kpis.overdue_count == 1

    @pytest.mark.asyncio
    async def test_filters_by_ticket_type(self, service: TicketService) -> None:
        await _make_ticket(
            ticket_type=TicketType.ISSUE, status=TicketStatus.IN_PROGRESS
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.ACCESS, status=TicketStatus.IN_PROGRESS
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.NEW_FEATURE, status=TicketStatus.IN_PROGRESS
        ).insert()

        for ticket_type, expected_open in [
            (TicketType.ISSUE, 1),
            (TicketType.ACCESS, 1),
            (TicketType.NEW_FEATURE, 1),
        ]:
            result = await service.get_dashboard(
                TicketDashboardFiltersDTO(type=ticket_type)
            )
            assert result.kpis.open_count == expected_open
            assert result.type == ticket_type


class TestDashboardOpenBreakdown:
    @pytest.mark.asyncio
    async def test_groups_status_into_three_donut_buckets(
        self, service: TicketService
    ) -> None:
        await _make_ticket(status=TicketStatus.WAITING_FOR_PROVIDER).insert()
        await _make_ticket(status=TicketStatus.WAITING_FOR_VALIDATION).insert()
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        await _make_ticket(status=TicketStatus.AWAITING_ASSIGNMENT).insert()
        await _make_ticket(status=TicketStatus.OPEN).insert()

        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        counts = {b.bucket: b.count for b in result.open_breakdown}
        assert counts["pendente"] == 2
        assert counts["em_atendimento"] == 2
        assert counts["nao_atribuidos"] == 2

    @pytest.mark.asyncio
    async def test_finished_and_cancelled_excluded_from_open_breakdown(
        self, service: TicketService
    ) -> None:
        await _make_ticket(status=TicketStatus.FINISHED).insert()
        await _make_ticket(status=TicketStatus.CANCELLED).insert()
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()

        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        counts = {b.bucket: b.count for b in result.open_breakdown}
        assert counts == {"pendente": 0, "em_atendimento": 1, "nao_atribuidos": 0}


class TestDashboardAssignedBreakdown:
    @pytest.mark.asyncio
    async def test_groups_open_tickets_by_active_assignee(
        self, service: TicketService
    ) -> None:
        julia = uuid4()
        mafe = uuid4()
        for _ in range(2):
            await _make_ticket(
                status=TicketStatus.IN_PROGRESS, active_agent=(julia, "Julia")
            ).insert()
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS, active_agent=(mafe, "Mafe")
        ).insert()

        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        by_agent = {b.agent_name: b.count for b in result.assigned_breakdown}
        assert by_agent == {"Julia": 2, "Mafe": 1}
        assert all(not b.is_aggregate for b in result.assigned_breakdown)

    @pytest.mark.asyncio
    async def test_excludes_tickets_without_active_assignment(
        self, service: TicketService
    ) -> None:
        agent = uuid4()
        # Aberto, com agente fechado e sem ativo → não conta para assigned_breakdown
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            closed_agent=(agent, "Histórico"),
        ).insert()
        # Aberto, sem nenhum histórico → não conta
        await _make_ticket(status=TicketStatus.AWAITING_ASSIGNMENT).insert()

        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        assert result.assigned_breakdown == []

    @pytest.mark.asyncio
    async def test_top_10_plus_outros_aggregates_tail(
        self, service: TicketService
    ) -> None:
        # Cria 12 agentes ativos, com contagens distintas: o agente i recebe (12-i+1) tickets
        # Top 10 vão de 12, 11, ... 3. Restantes (2 agentes com 2 e 1 ticket) → "Outros" = 3.
        for idx in range(12):
            agent_id = uuid4()
            agent_name = f"Agente {idx}"
            tickets_count = 12 - idx
            for _ in range(tickets_count):
                await _make_ticket(
                    status=TicketStatus.IN_PROGRESS,
                    active_agent=(agent_id, agent_name),
                ).insert()

        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        assert len(result.assigned_breakdown) == _TOP_ASSIGNEES_LIMIT + 1
        outros = result.assigned_breakdown[-1]
        assert outros.is_aggregate is True
        assert outros.agent_name == "Outros"
        assert outros.agent_id is None
        assert outros.count == 2 + 1  # agentes 10 e 11 (3 e 2 tickets... espera)
        # Contagens: 12, 11, 10, 9, 8, 7, 6, 5, 4, 3 (top 10), 2 + 1 = 3 em "Outros"

    @pytest.mark.asyncio
    async def test_excludes_finished_and_cancelled_from_assigned_breakdown(
        self, service: TicketService
    ) -> None:
        agent = uuid4()
        await _make_ticket(
            status=TicketStatus.FINISHED,
            active_agent=(agent, "Antigo"),
        ).insert()
        await _make_ticket(
            status=TicketStatus.CANCELLED,
            active_agent=(agent, "Antigo"),
        ).insert()

        result = await service.get_dashboard(
            TicketDashboardFiltersDTO(type=TicketType.ISSUE)
        )

        assert result.assigned_breakdown == []
