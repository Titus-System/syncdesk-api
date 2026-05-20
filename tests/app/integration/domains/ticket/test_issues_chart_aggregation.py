"""Integration tests for ``TicketRepository.aggregate_issues_by_product``.

Exercem o pipeline Mongo direto, verificando o shape bruto da resposta
antes da materialização de meses zerados feita no service.
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


def _make_ticket(
    *,
    product: str = "Produto X",
    ticket_type: TicketType = TicketType.ISSUE,
    creation_date: datetime,
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
        description="Teste de agregação",
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


class TestMalformedProduct:
    @pytest.mark.asyncio
    async def test_groups_empty_string_product_as_distinct_bucket(
        self, repository: TicketRepository,
        mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    ) -> None:
        # Ticket válido pelo modelo (product: str aceita "")
        await _make_ticket(
            product="", creation_date=datetime(2026, 1, 10, tzinfo=UTC)
        ).insert()
        await _make_ticket(
            product="Normal", creation_date=datetime(2026, 1, 10, tzinfo=UTC)
        ).insert()

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 2, 1, tzinfo=UTC),
            company_id=None,
        )

        products = {row["_id"]["product"] for row in rows}
        assert "" in products
        assert "Normal" in products

    @pytest.mark.asyncio
    async def test_groups_null_product_as_null_id(
        self,
        repository: TicketRepository,
        mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    ) -> None:
        # product=null no Mongo simula ticket malformado (não é alcançável via Pydantic).
        # Inserimos direto via motor para bypass da validação.
        from bson.binary import Binary
        from uuid import uuid4 as _uuid4
        from beanie import PydanticObjectId

        client_id = _uuid4()
        company_id = _uuid4()
        doc = {
            "_id": PydanticObjectId(),
            "triage_id": PydanticObjectId(),
            "type": "issue",
            "criticality": "high",
            "product": None,
            "status": "in_progress",
            "level": "N1",
            "creation_date": datetime(2026, 1, 15, tzinfo=UTC),
            "description": "ticket sem produto",
            "chat_ids": [],
            "agent_history": [],
            "client": {
                "id": Binary(client_id.bytes, subtype=4),
                "name": "Cliente",
                "email": "c@test.com",
                "company": {
                    "id": Binary(company_id.bytes, subtype=4),
                    "name": "Empresa",
                },
            },
            "comments": [],
        }
        await mongo_db_conn["tickets"].insert_one(doc)

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 2, 1, tzinfo=UTC),
            company_id=None,
        )

        # O service depois fará str(... or "") para coercer null → ""
        # Aqui só verificamos que o pipeline não engole o registro
        assert len(rows) == 1
        assert rows[0]["count"] == 1
        assert rows[0]["_id"]["product"] is None


class TestIssuesChartAggregation:
    @pytest.mark.asyncio
    async def test_groups_by_year_month_and_product(
        self, repository: TicketRepository
    ) -> None:
        await _make_ticket(
            product="Produto 1",
            creation_date=datetime(2026, 1, 5, tzinfo=UTC),
        ).insert()
        await _make_ticket(
            product="Produto 1",
            creation_date=datetime(2026, 1, 20, tzinfo=UTC),
        ).insert()
        await _make_ticket(
            product="Produto 2",
            creation_date=datetime(2026, 1, 10, tzinfo=UTC),
        ).insert()

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 2, 1, tzinfo=UTC),
            company_id=None,
        )

        triples = {
            (row["_id"]["year"], row["_id"]["month"], row["_id"]["product"]): row["count"]
            for row in rows
        }
        assert triples == {
            (2026, 1, "Produto 1"): 2,
            (2026, 1, "Produto 2"): 1,
        }

    @pytest.mark.asyncio
    async def test_filters_out_non_issue_types(
        self, repository: TicketRepository
    ) -> None:
        when = datetime(2026, 2, 10, tzinfo=UTC)
        await _make_ticket(
            ticket_type=TicketType.ISSUE,
            product="P",
            creation_date=when,
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.ACCESS,
            product="P",
            creation_date=when,
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.NEW_FEATURE,
            product="P",
            creation_date=when,
        ).insert()

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 2, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 3, 1, tzinfo=UTC),
            company_id=None,
        )

        assert len(rows) == 1
        assert rows[0]["count"] == 1

    @pytest.mark.asyncio
    async def test_filters_by_company_id_when_provided(
        self, repository: TicketRepository
    ) -> None:
        target_company = uuid4()
        other_company = uuid4()
        when = datetime(2026, 3, 1, tzinfo=UTC)
        await _make_ticket(product="P", creation_date=when, company_id=target_company).insert()
        await _make_ticket(product="P", creation_date=when, company_id=target_company).insert()
        await _make_ticket(product="P", creation_date=when, company_id=other_company).insert()

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 3, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 4, 1, tzinfo=UTC),
            company_id=target_company,
        )

        assert len(rows) == 1
        assert rows[0]["count"] == 2

    @pytest.mark.asyncio
    async def test_excludes_tickets_outside_creation_date_window(
        self, repository: TicketRepository
    ) -> None:
        before = datetime(2025, 12, 31, 23, 59, tzinfo=UTC)
        inside = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
        after = datetime(2026, 2, 1, 0, 0, tzinfo=UTC)  # excluído pelo $lt
        await _make_ticket(product="P", creation_date=before).insert()
        await _make_ticket(product="P", creation_date=inside).insert()
        await _make_ticket(product="P", creation_date=after).insert()

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 2, 1, tzinfo=UTC),
            company_id=None,
        )

        assert len(rows) == 1
        assert rows[0]["count"] == 1

    @pytest.mark.asyncio
    async def test_counts_include_finished_and_cancelled_tickets(
        self, repository: TicketRepository
    ) -> None:
        # A métrica conta entrada (creation_date), independente do status atual
        when = datetime(2026, 4, 15, tzinfo=UTC)
        await _make_ticket(
            product="P", creation_date=when, status=TicketStatus.IN_PROGRESS
        ).insert()
        await _make_ticket(
            product="P", creation_date=when, status=TicketStatus.FINISHED
        ).insert()
        await _make_ticket(
            product="P", creation_date=when, status=TicketStatus.CANCELLED
        ).insert()

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 4, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 5, 1, tzinfo=UTC),
            company_id=None,
        )

        assert len(rows) == 1
        assert rows[0]["count"] == 3

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_match(
        self, repository: TicketRepository
    ) -> None:
        await _make_ticket(
            product="P", creation_date=datetime(2026, 1, 1, tzinfo=UTC)
        ).insert()

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 6, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 7, 1, tzinfo=UTC),
            company_id=None,
        )

        assert rows == []

    @pytest.mark.asyncio
    async def test_sorted_by_product_then_year_then_month(
        self, repository: TicketRepository
    ) -> None:
        await _make_ticket(
            product="Zebra", creation_date=datetime(2026, 3, 1, tzinfo=UTC)
        ).insert()
        await _make_ticket(
            product="Alpha", creation_date=datetime(2026, 2, 1, tzinfo=UTC)
        ).insert()
        await _make_ticket(
            product="Alpha", creation_date=datetime(2026, 1, 1, tzinfo=UTC)
        ).insert()

        rows = await repository.aggregate_issues_by_product(
            date_from=datetime(2026, 1, 1, tzinfo=UTC),
            date_to_exclusive=datetime(2026, 4, 1, tzinfo=UTC),
            company_id=None,
        )

        ordered = [(r["_id"]["product"], r["_id"]["month"]) for r in rows]
        assert ordered == [("Alpha", 1), ("Alpha", 2), ("Zebra", 3)]
