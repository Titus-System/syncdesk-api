"""Integration tests for ``TicketService.get_issues_by_product_chart``.

Usa UserService, TicketRepository e EventDispatcher reais (Mongo + Postgres).
Cobre defaults de período, materialização de meses zerados, ordenação e
mapeamento DB → DTO.
"""
from collections.abc import AsyncGenerator
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.event_dispatcher.event_dispatcher import EventDispatcher
from app.core.event_dispatcher.schemas import EVENT_PAYLOAD_MAP
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
    TicketLevel,
    TicketStatus,
    TicketType,
)
from app.domains.ticket.repositories import TicketRepository
from app.domains.ticket.schemas import IssuesByProductChartFiltersDTO
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
    return EventDispatcher(EVENT_PAYLOAD_MAP, get_logger("test.issues_chart"))


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


def _make_ticket(
    *,
    product: str,
    creation_date: datetime,
    ticket_type: TicketType = TicketType.ISSUE,
    status: TicketStatus = TicketStatus.IN_PROGRESS,
    company_id: UUID | None = None,
) -> Ticket:
    cid = company_id or uuid4()
    return Ticket(
        triage_id=PydanticObjectId(),
        type=ticket_type,
        criticality=TicketCriticality.HIGH,
        product=product,
        status=status,
        level=TicketLevel.N1,
        creation_date=creation_date,
        description="Teste de chart",
        chat_ids=[],
        agent_history=[],
        client=TicketClient(
            id=uuid4(),
            name="Cliente",
            email="c@test.com",
            company=TicketCompany(id=cid, name="Empresa"),
        ),
        comments=[],
    )


class TestDefaultPeriod:
    @pytest.mark.asyncio
    async def test_defaults_to_last_six_calendar_months(
        self, service: TicketService
    ) -> None:
        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO()
        )

        assert len(result.months) == 6
        # último mês = mês atual; primeiro = 5 meses antes
        today = datetime.now(UTC).date()
        expected_last = f"{today.year:04d}-{today.month:02d}"
        assert result.months[-1] == expected_last

    @pytest.mark.asyncio
    async def test_period_start_and_end_are_month_boundaries(
        self, service: TicketService
    ) -> None:
        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2026, 2, 15),
                date_to=date(2026, 4, 10),
            )
        )

        assert result.period_start == date(2026, 2, 1)
        assert result.period_end == date(2026, 4, 30)
        assert result.months == ["2026-02", "2026-03", "2026-04"]


class TestMonthMaterialisation:
    @pytest.mark.asyncio
    async def test_missing_months_are_filled_with_zero(
        self, service: TicketService
    ) -> None:
        # Apenas Jan e Mar têm tickets do Produto A; Feb deve aparecer com zero
        await _make_ticket(
            product="Produto A", creation_date=datetime(2026, 1, 15, tzinfo=UTC)
        ).insert()
        await _make_ticket(
            product="Produto A", creation_date=datetime(2026, 3, 10, tzinfo=UTC)
        ).insert()

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 31),
            )
        )

        assert result.months == ["2026-01", "2026-02", "2026-03"]
        assert len(result.series) == 1
        series_a = result.series[0]
        counts = {p.month: p.count for p in series_a.points}
        assert counts == {"2026-01": 1, "2026-02": 0, "2026-03": 1}
        assert series_a.total == 2

    @pytest.mark.asyncio
    async def test_empty_collection_returns_months_axis_but_no_series(
        self, service: TicketService
    ) -> None:
        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2026, 1, 1),
                date_to=date(2026, 3, 31),
            )
        )

        assert result.months == ["2026-01", "2026-02", "2026-03"]
        assert result.series == []


class TestSeriesOrdering:
    @pytest.mark.asyncio
    async def test_series_sorted_by_total_desc_then_product_asc(
        self, service: TicketService
    ) -> None:
        # Produto B = 3, Produto A = 2, Produto C = 2 → ordem: B, A, C
        for _ in range(3):
            await _make_ticket(
                product="Produto B",
                creation_date=datetime(2026, 1, 5, tzinfo=UTC),
            ).insert()
        for _ in range(2):
            await _make_ticket(
                product="Produto A",
                creation_date=datetime(2026, 1, 5, tzinfo=UTC),
            ).insert()
        for _ in range(2):
            await _make_ticket(
                product="Produto C",
                creation_date=datetime(2026, 1, 5, tzinfo=UTC),
            ).insert()

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2026, 1, 1),
                date_to=date(2026, 1, 31),
            )
        )

        assert [s.product for s in result.series] == [
            "Produto B",
            "Produto A",
            "Produto C",
        ]
        assert [s.total for s in result.series] == [3, 2, 2]


class TestCompanyFilter:
    @pytest.mark.asyncio
    async def test_company_id_restricts_to_matching_tickets(
        self, service: TicketService
    ) -> None:
        target = uuid4()
        other = uuid4()
        when = datetime(2026, 2, 10, tzinfo=UTC)
        await _make_ticket(product="P", creation_date=when, company_id=target).insert()
        await _make_ticket(product="P", creation_date=when, company_id=target).insert()
        await _make_ticket(product="P", creation_date=when, company_id=other).insert()

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                company_id=target,
                date_from=date(2026, 2, 1),
                date_to=date(2026, 2, 28),
            )
        )

        assert result.company_id == target
        assert len(result.series) == 1
        assert result.series[0].total == 2


class TestValidation:
    @pytest.mark.asyncio
    async def test_inverted_range_raises_422(
        self, service: TicketService
    ) -> None:
        with pytest.raises(AppHTTPException) as exc:
            await service.get_issues_by_product_chart(
                IssuesByProductChartFiltersDTO(
                    date_from=date(2026, 5, 1),
                    date_to=date(2026, 1, 1),
                )
            )

        assert exc.value.status_code == 422

    @pytest.mark.asyncio
    async def test_range_exceeding_max_months_raises_422(
        self, service: TicketService
    ) -> None:
        with pytest.raises(AppHTTPException) as exc:
            await service.get_issues_by_product_chart(
                IssuesByProductChartFiltersDTO(
                    date_from=date(2025, 1, 1),
                    date_to=date(2026, 12, 31),  # 24 meses
                )
            )

        assert exc.value.status_code == 422
        assert "12" in exc.value.detail


class TestTypeFilter:
    @pytest.mark.asyncio
    async def test_non_issue_types_are_excluded(
        self, service: TicketService
    ) -> None:
        when = datetime(2026, 2, 10, tzinfo=UTC)
        await _make_ticket(
            product="P", creation_date=when, ticket_type=TicketType.ISSUE
        ).insert()
        await _make_ticket(
            product="P", creation_date=when, ticket_type=TicketType.ACCESS
        ).insert()
        await _make_ticket(
            product="P", creation_date=when, ticket_type=TicketType.NEW_FEATURE
        ).insert()

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2026, 2, 1),
                date_to=date(2026, 2, 28),
            )
        )

        assert len(result.series) == 1
        assert result.series[0].total == 1


class TestPeriodEdgeCases:
    @pytest.mark.asyncio
    async def test_range_crossing_year_boundary(
        self, service: TicketService
    ) -> None:
        # Dez/2025 a Mar/2026: 4 meses, atravessa virada de ano
        for product, when in [
            ("P", datetime(2025, 12, 15, tzinfo=UTC)),
            ("P", datetime(2026, 1, 5, tzinfo=UTC)),
            ("P", datetime(2026, 3, 20, tzinfo=UTC)),
        ]:
            await _make_ticket(product=product, creation_date=when).insert()

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2025, 12, 1),
                date_to=date(2026, 3, 31),
            )
        )

        assert result.months == ["2025-12", "2026-01", "2026-02", "2026-03"]
        assert result.period_start == date(2025, 12, 1)
        assert result.period_end == date(2026, 3, 31)
        # P aparece com counts em cada mês (incl. zero no Feb)
        series_p = next(s for s in result.series if s.product == "P")
        counts = {p.month: p.count for p in series_p.points}
        assert counts == {"2025-12": 1, "2026-01": 1, "2026-02": 0, "2026-03": 1}

    @pytest.mark.asyncio
    async def test_single_month_range_when_date_from_equals_date_to(
        self, service: TicketService
    ) -> None:
        await _make_ticket(
            product="P", creation_date=datetime(2026, 3, 10, tzinfo=UTC)
        ).insert()

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2026, 3, 15),
                date_to=date(2026, 3, 15),
            )
        )

        assert result.months == ["2026-03"]
        assert result.period_start == date(2026, 3, 1)
        assert result.period_end == date(2026, 3, 31)
        assert len(result.series) == 1
        assert result.series[0].total == 1

    @pytest.mark.asyncio
    async def test_exactly_twelve_months_range_is_accepted(
        self, service: TicketService
    ) -> None:
        # Jan/2026 a Dez/2026 = 12 meses, deve passar
        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2026, 1, 1),
                date_to=date(2026, 12, 31),
            )
        )

        assert len(result.months) == 12
        assert result.months[0] == "2026-01"
        assert result.months[-1] == "2026-12"

    @pytest.mark.asyncio
    async def test_thirteen_months_range_is_rejected_with_422(
        self, service: TicketService
    ) -> None:
        with pytest.raises(AppHTTPException) as exc:
            await service.get_issues_by_product_chart(
                IssuesByProductChartFiltersDTO(
                    date_from=date(2025, 12, 1),
                    date_to=date(2026, 12, 31),
                )
            )

        assert exc.value.status_code == 422
        assert "12" in exc.value.detail

    @pytest.mark.asyncio
    async def test_only_date_from_provided_uses_today_as_implicit_end(
        self, service: TicketService
    ) -> None:
        today = datetime.now(UTC).date()
        # date_from = 2 meses atrás; date_to = None → end = hoje
        anchor = today.replace(day=1) - timedelta(days=1)  # último dia do mês anterior
        date_from = anchor.replace(day=1) - timedelta(days=1)  # último dia de 2 meses atrás
        date_from = date_from.replace(day=1)

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(date_from=date_from)
        )

        # period_end deve ser último dia do mês atual
        assert result.period_end.year == today.year
        assert result.period_end.month == today.month
        # period_start deve ser o primeiro dia do mês do date_from
        assert result.period_start == date_from.replace(day=1)

    @pytest.mark.asyncio
    async def test_only_date_to_provided_uses_six_month_default_window(
        self, service: TicketService
    ) -> None:
        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(date_to=date(2026, 5, 15))
        )

        # default = 6 meses terminando em maio/2026 = dez/2025 → mai/2026
        assert result.period_end == date(2026, 5, 31)
        assert result.period_start == date(2025, 12, 1)
        assert result.months == [
            "2025-12",
            "2026-01",
            "2026-02",
            "2026-03",
            "2026-04",
            "2026-05",
        ]

    @pytest.mark.asyncio
    async def test_leap_year_february_has_29_days(
        self, service: TicketService
    ) -> None:
        # Fev/2024 tem 29 dias (ano bissexto)
        await _make_ticket(
            product="P", creation_date=datetime(2024, 2, 29, 23, 30, tzinfo=UTC)
        ).insert()

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2024, 2, 15),
                date_to=date(2024, 2, 15),
            )
        )

        assert result.period_end == date(2024, 2, 29)
        assert result.months == ["2024-02"]
        # O ticket de 29-fev deve ser contado (dentro do range)
        assert len(result.series) == 1
        assert result.series[0].total == 1


class TestStatusInclusion:
    @pytest.mark.asyncio
    async def test_metric_counts_entry_regardless_of_current_status(
        self, service: TicketService
    ) -> None:
        when = datetime(2026, 3, 10, tzinfo=UTC)
        for status in (
            TicketStatus.OPEN,
            TicketStatus.AWAITING_ASSIGNMENT,
            TicketStatus.IN_PROGRESS,
            TicketStatus.WAITING_FOR_PROVIDER,
            TicketStatus.WAITING_FOR_VALIDATION,
            TicketStatus.FINISHED,
            TicketStatus.CANCELLED,
        ):
            await _make_ticket(
                product="P", creation_date=when, status=status
            ).insert()

        result = await service.get_issues_by_product_chart(
            IssuesByProductChartFiltersDTO(
                date_from=date(2026, 3, 1),
                date_to=date(2026, 3, 31),
            )
        )

        assert len(result.series) == 1
        assert result.series[0].total == 7
