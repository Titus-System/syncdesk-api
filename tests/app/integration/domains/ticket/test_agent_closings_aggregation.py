"""Integration tests for ``TicketRepository.aggregate_agent_closings``.

Exercem o pipeline raw que agrupa tickets finished por (agent_id, type)
dentro da janela de closed_at. UUIDs entram no $match como Binary subtype 4.
"""
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

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


def _make_closed_ticket(
    *,
    agent_id: UUID,
    agent_name: str = "Agente",
    agent_level: str = "N1",
    ticket_type: TicketType = TicketType.ISSUE,
    closed_at: datetime,
    status: TicketStatus = TicketStatus.FINISHED,
    include_closed_by_agent: bool = True,
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
        status=status,
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
        closed_by_agent=snapshot if include_closed_by_agent else None,
    )


class TestAgentClosingsAggregation:
    @pytest.mark.asyncio
    async def test_groups_by_agent_id_and_type(
        self, repository: TicketRepository
    ) -> None:
        julia = uuid4()
        mafe = uuid4()
        when = datetime(2026, 5, 15, tzinfo=UTC)

        # Julia: 2 issue + 1 access
        await _make_closed_ticket(
            agent_id=julia, agent_name="Julia",
            ticket_type=TicketType.ISSUE, closed_at=when,
        ).insert()
        await _make_closed_ticket(
            agent_id=julia, agent_name="Julia",
            ticket_type=TicketType.ISSUE, closed_at=when,
        ).insert()
        await _make_closed_ticket(
            agent_id=julia, agent_name="Julia",
            ticket_type=TicketType.ACCESS, closed_at=when,
        ).insert()
        # Mafe: 1 new_feature
        await _make_closed_ticket(
            agent_id=mafe, agent_name="Mafe",
            ticket_type=TicketType.NEW_FEATURE, closed_at=when,
        ).insert()

        rows = await repository.aggregate_agent_closings(
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 6, 1, tzinfo=UTC),
            level=None,
        )

        triples = {
            (str(row["agent_name"]), str(row["_id"]["type"])): row["count"]
            for row in rows
        }
        assert triples == {
            ("Julia", "issue"): 2,
            ("Julia", "access"): 1,
            ("Mafe", "new_feature"): 1,
        }

    @pytest.mark.asyncio
    async def test_excludes_non_finished_tickets(
        self, repository: TicketRepository
    ) -> None:
        agent = uuid4()
        when = datetime(2026, 5, 10, tzinfo=UTC)
        await _make_closed_ticket(
            agent_id=agent, closed_at=when, status=TicketStatus.FINISHED,
        ).insert()
        # Cancelado com closed_at no banco mas status != finished
        await _make_closed_ticket(
            agent_id=agent, closed_at=when, status=TicketStatus.CANCELLED,
        ).insert()
        # in_progress (não terminal)
        await _make_closed_ticket(
            agent_id=agent, closed_at=when, status=TicketStatus.IN_PROGRESS,
        ).insert()

        rows = await repository.aggregate_agent_closings(
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 6, 1, tzinfo=UTC),
            level=None,
        )

        assert len(rows) == 1
        assert rows[0]["count"] == 1

    @pytest.mark.asyncio
    async def test_excludes_tickets_outside_closed_at_window(
        self, repository: TicketRepository
    ) -> None:
        agent = uuid4()
        before = datetime(2026, 4, 30, 23, 59, tzinfo=UTC)
        inside = datetime(2026, 5, 15, tzinfo=UTC)
        boundary = datetime(2026, 6, 1, 0, 0, tzinfo=UTC)  # excluído pelo $lt
        for closed_at in (before, inside, boundary):
            await _make_closed_ticket(agent_id=agent, closed_at=closed_at).insert()

        rows = await repository.aggregate_agent_closings(
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 6, 1, tzinfo=UTC),
            level=None,
        )

        assert len(rows) == 1
        assert rows[0]["count"] == 1

    @pytest.mark.asyncio
    async def test_excludes_tickets_without_closed_by_agent(
        self, repository: TicketRepository
    ) -> None:
        agent_with = uuid4()
        agent_without = uuid4()
        when = datetime(2026, 5, 15, tzinfo=UTC)
        await _make_closed_ticket(
            agent_id=agent_with, closed_at=when, include_closed_by_agent=True
        ).insert()
        await _make_closed_ticket(
            agent_id=agent_without, closed_at=when, include_closed_by_agent=False
        ).insert()

        rows = await repository.aggregate_agent_closings(
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 6, 1, tzinfo=UTC),
            level=None,
        )

        assert len(rows) == 1
        assert rows[0]["count"] == 1

    @pytest.mark.asyncio
    async def test_filters_by_level_when_provided(
        self, repository: TicketRepository
    ) -> None:
        n1 = uuid4()
        n2 = uuid4()
        when = datetime(2026, 5, 15, tzinfo=UTC)
        await _make_closed_ticket(
            agent_id=n1, agent_level="N1", closed_at=when,
        ).insert()
        await _make_closed_ticket(
            agent_id=n2, agent_level="N2", closed_at=when,
        ).insert()
        await _make_closed_ticket(
            agent_id=n2, agent_level="N2", closed_at=when,
        ).insert()

        rows = await repository.aggregate_agent_closings(
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 6, 1, tzinfo=UTC),
            level=TicketLevel.N2,
        )

        assert len(rows) == 1
        assert rows[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_match(
        self, repository: TicketRepository
    ) -> None:
        await _make_closed_ticket(
            agent_id=uuid4(),
            closed_at=datetime(2026, 5, 15, tzinfo=UTC),
        ).insert()

        rows = await repository.aggregate_agent_closings(
            period_start=datetime(2026, 6, 1, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 7, 1, tzinfo=UTC),
            level=None,
        )

        assert rows == []

    @pytest.mark.asyncio
    async def test_ticket_without_closed_at_is_excluded(
        self, repository: TicketRepository
    ) -> None:
        """Tickets legacy (finished antes deste PR) têm closed_at=None.
        Devem ficar fora do dashboard.
        """
        from bson.binary import Binary
        client_id = uuid4()
        company_id = uuid4()
        agent_id = uuid4()
        doc = {
            "_id": PydanticObjectId(),
            "triage_id": PydanticObjectId(),
            "type": "issue",
            "criticality": "high",
            "product": "P",
            "status": "finished",
            "level": "N1",
            "creation_date": datetime(2026, 5, 15, tzinfo=UTC),
            "description": "legacy",
            "chat_ids": [],
            "agent_history": [],
            "client": {
                "id": Binary(client_id.bytes, subtype=4),
                "name": "C",
                "email": "c@t.com",
                "company": {
                    "id": Binary(company_id.bytes, subtype=4),
                    "name": "E",
                },
            },
            "comments": [],
            "closed_at": None,
            "closed_by_agent": None,
        }
        await Ticket.get_motor_collection().insert_one(doc)

        rows = await repository.aggregate_agent_closings(
            period_start=datetime(2026, 5, 1, tzinfo=UTC),
            period_end_exclusive=datetime(2026, 6, 1, tzinfo=UTC),
            level=None,
        )

        assert rows == []
