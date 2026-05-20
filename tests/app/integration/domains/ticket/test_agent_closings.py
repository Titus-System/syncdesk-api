"""Integration tests for ``TicketService.get_agent_closings_chart``.

Usa UserService, TicketRepository e EventDispatcher reais.
"""
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
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
from app.domains.ticket.schemas import AgentClosingsChartFiltersDTO
from app.domains.ticket.services import TicketService


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
    return EventDispatcher(EVENT_PAYLOAD_MAP, get_logger("test.agent_closings"))


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
    dispatcher: EventDispatcher,
) -> TicketService:
    return TicketService(repository, user_service, dispatcher)


def _make_closed_ticket(
    *,
    agent_id: UUID,
    agent_name: str,
    agent_level: str = "N1",
    ticket_type: TicketType = TicketType.ISSUE,
    closed_at: datetime,
) -> Ticket:
    snapshot = TicketHistory(
        agent_id=agent_id,
        name=agent_name,
        level=agent_level,
        assignment_date=closed_at,
        exit_date=None,
    )
    return Ticket(
        triage_id=PydanticObjectId(),
        type=ticket_type,
        criticality=TicketCriticality.HIGH,
        product="Sistema",
        status=TicketStatus.FINISHED,
        level=TicketLevel.N1,
        creation_date=closed_at,
        description="Teste closings",
        chat_ids=[],
        agent_history=[snapshot],
        client=TicketClient(
            id=uuid4(),
            name="Cliente",
            email="c@test.com",
            company=TicketCompany(id=uuid4(), name="Empresa"),
        ),
        comments=[],
        closed_at=closed_at,
        closed_by_agent=snapshot,
    )


class TestAgentClosingsDefaults:
    @pytest.mark.asyncio
    async def test_uses_current_month_year_when_filters_empty(
        self, service: TicketService
    ) -> None:
        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO()
        )

        today = datetime.now(UTC).date()
        assert result.month == today.month
        assert result.year == today.year
        assert result.level is None

    @pytest.mark.asyncio
    async def test_empty_collection_returns_empty_agents(
        self, service: TicketService
    ) -> None:
        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(month=1, year=2026)
        )

        assert result.agents == []


class TestAgentClosingsPivot:
    @pytest.mark.asyncio
    async def test_pivot_creates_three_counters_per_agent(
        self, service: TicketService
    ) -> None:
        angelina = uuid4()
        when = datetime(2026, 5, 15, tzinfo=UTC)
        # Angelina: 4 issue + 7 access + 2 new_feature
        for _ in range(4):
            await _make_closed_ticket(
                agent_id=angelina, agent_name="Angelina",
                ticket_type=TicketType.ISSUE, closed_at=when,
            ).insert()
        for _ in range(7):
            await _make_closed_ticket(
                agent_id=angelina, agent_name="Angelina",
                ticket_type=TicketType.ACCESS, closed_at=when,
            ).insert()
        for _ in range(2):
            await _make_closed_ticket(
                agent_id=angelina, agent_name="Angelina",
                ticket_type=TicketType.NEW_FEATURE, closed_at=when,
            ).insert()

        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(month=5, year=2026)
        )

        assert len(result.agents) == 1
        bucket = result.agents[0]
        assert bucket.agent_name == "Angelina"
        assert bucket.issue_count == 4
        assert bucket.access_count == 7
        assert bucket.new_feature_count == 2
        assert bucket.total == 13
        assert bucket.is_aggregate is False

    @pytest.mark.asyncio
    async def test_reproduces_image_example(
        self, service: TicketService
    ) -> None:
        """Cenário da imagem (numeros simplificados, mas mantendo proporções)."""
        julia = uuid4()
        mafe = uuid4()
        angelina = uuid4()
        when = datetime(2026, 5, 15, tzinfo=UTC)

        counts = {
            julia: ("Julia", {"issue": 22, "new_feature": 12, "access": 50}),
            mafe: ("Mafe", {"issue": 32, "new_feature": 17, "access": 20}),
            angelina: ("Angelina", {"issue": 40, "new_feature": 25, "access": 70}),
        }
        for agent_id, (name, by_type) in counts.items():
            for ttype_str, qty in by_type.items():
                ticket_type = TicketType(ttype_str)
                for _ in range(qty):
                    await _make_closed_ticket(
                        agent_id=agent_id, agent_name=name,
                        ticket_type=ticket_type, closed_at=when,
                    ).insert()

        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(month=5, year=2026)
        )

        by_name = {a.agent_name: a for a in result.agents}
        assert by_name["Angelina"].issue_count == 40
        assert by_name["Angelina"].new_feature_count == 25
        assert by_name["Angelina"].access_count == 70
        assert by_name["Mafe"].total == 69
        assert by_name["Julia"].issue_count == 22


class TestAgentClosingsOrdering:
    @pytest.mark.asyncio
    async def test_sorted_by_total_desc_then_name_asc(
        self, service: TicketService
    ) -> None:
        when = datetime(2026, 5, 15, tzinfo=UTC)
        zebra, alpha, beta = uuid4(), uuid4(), uuid4()
        # 3 agentes, 2 com mesmo total (empate → ordem alfabética)
        for _ in range(5):
            await _make_closed_ticket(
                agent_id=zebra, agent_name="Zebra", closed_at=when,
            ).insert()
        for _ in range(3):
            await _make_closed_ticket(
                agent_id=alpha, agent_name="Alpha", closed_at=when,
            ).insert()
        for _ in range(3):
            await _make_closed_ticket(
                agent_id=beta, agent_name="Beta", closed_at=when,
            ).insert()

        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(month=5, year=2026)
        )

        assert [a.agent_name for a in result.agents] == ["Zebra", "Alpha", "Beta"]


class TestAgentClosingsTopTenPlusOutros:
    @pytest.mark.asyncio
    async def test_outros_bucket_aggregates_eleventh_onward(
        self, service: TicketService
    ) -> None:
        when = datetime(2026, 5, 15, tzinfo=UTC)
        # 12 agentes distintos: contagens 12, 11, ..., 1 (total 78)
        for idx in range(12):
            agent_id = uuid4()
            for _ in range(12 - idx):
                await _make_closed_ticket(
                    agent_id=agent_id, agent_name=f"Agente {idx:02d}",
                    closed_at=when,
                ).insert()

        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(month=5, year=2026)
        )

        assert len(result.agents) == 11
        outros = result.agents[-1]
        assert outros.is_aggregate is True
        assert outros.agent_name == "Outros"
        assert outros.agent_id is None
        # agentes 10 e 11 (contagens 2 + 1) = 3
        assert outros.total == 3
        assert outros.issue_count == 3
        assert outros.access_count == 0
        assert outros.new_feature_count == 0


class TestAgentClosingsLevelFilter:
    @pytest.mark.asyncio
    async def test_filter_by_level_restricts_to_matching_agents(
        self, service: TicketService
    ) -> None:
        when = datetime(2026, 5, 15, tzinfo=UTC)
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="N1 agent",
            agent_level="N1", closed_at=when,
        ).insert()
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="N2 agent",
            agent_level="N2", closed_at=when,
        ).insert()

        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(
                month=5, year=2026, level=TicketLevel.N2
            )
        )

        assert len(result.agents) == 1
        assert result.agents[0].agent_name == "N2 agent"


class TestAgentClosingsPeriodEdges:
    @pytest.mark.asyncio
    async def test_month_window_excludes_first_day_of_next_month(
        self, service: TicketService
    ) -> None:
        # Ticket no exato segundo do mês seguinte: deve ficar fora
        boundary = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="X", closed_at=boundary,
        ).insert()

        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(month=5, year=2026)
        )

        assert result.agents == []

    @pytest.mark.asyncio
    async def test_month_window_includes_last_second_of_month(
        self, service: TicketService
    ) -> None:
        last = datetime(2026, 5, 31, 23, 59, 59, tzinfo=UTC)
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="X", closed_at=last,
        ).insert()

        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(month=5, year=2026)
        )

        assert len(result.agents) == 1

    @pytest.mark.asyncio
    async def test_december_window_rolls_over_to_next_year(
        self, service: TicketService
    ) -> None:
        when = datetime(2026, 12, 15, tzinfo=UTC)
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="X", closed_at=when,
        ).insert()
        # Ticket de janeiro do próximo ano não deve entrar
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="Y",
            closed_at=datetime(2027, 1, 1, tzinfo=UTC),
        ).insert()

        result = await service.get_agent_closings_chart(
            AgentClosingsChartFiltersDTO(month=12, year=2026)
        )

        assert len(result.agents) == 1
        assert result.agents[0].agent_name == "X"
