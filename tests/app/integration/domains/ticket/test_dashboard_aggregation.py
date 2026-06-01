"""Integration tests for ``TicketRepository.aggregate_dashboard``.

Focam no formato bruto da resposta do pipeline `$facet` (antes de qualquer
transformação no service). Garantem que mudanças no Mongo, no shape do
documento ou na pipeline não quebrem o contrato esperado pelo service.
"""
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
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


def _make_ticket(
    *,
    ticket_type: TicketType = TicketType.ISSUE,
    status: TicketStatus = TicketStatus.AWAITING_ASSIGNMENT,
    criticality: TicketCriticality = TicketCriticality.HIGH,
    creation_date: datetime | None = None,
    active_agent: tuple[UUID, str] | None = None,
) -> Ticket:
    history: list[TicketHistory] = []
    base_time = creation_date or datetime.now(UTC)
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
        description="Teste de agregação",
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


class TestFacetShape:
    @pytest.mark.asyncio
    async def test_result_has_three_facet_keys(
        self, repository: TicketRepository
    ) -> None:
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert set(result.keys()) == {
            "kpis",
            "open_breakdown",
            "assigned_breakdown_raw",
        }

    @pytest.mark.asyncio
    async def test_empty_match_returns_empty_arrays_per_facet(
        self, repository: TicketRepository
    ) -> None:
        # Sem tickets do tipo solicitado: facet retorna arrays vazios em todos os subpipelines
        await _make_ticket(
            ticket_type=TicketType.ACCESS, status=TicketStatus.IN_PROGRESS
        ).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["kpis"] == []
        assert result["open_breakdown"] == []
        assert result["assigned_breakdown_raw"] == []


class TestKpisFacet:
    @pytest.mark.asyncio
    async def test_open_count_excludes_finished_and_cancelled(
        self, repository: TicketRepository
    ) -> None:
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        await _make_ticket(status=TicketStatus.AWAITING_ASSIGNMENT).insert()
        await _make_ticket(status=TicketStatus.FINISHED).insert()
        await _make_ticket(status=TicketStatus.CANCELLED).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        kpis = result["kpis"][0]
        assert kpis["open_count"] == 2
        assert kpis["cancelled_count"] == 1

    @pytest.mark.asyncio
    async def test_unassigned_count_only_counts_open_tickets_without_active_agent(
        self, repository: TicketRepository
    ) -> None:
        # Aberto sem agente
        await _make_ticket(status=TicketStatus.AWAITING_ASSIGNMENT).insert()
        # Aberto com agente ativo
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            active_agent=(uuid4(), "Julia"),
        ).insert()
        # Cancelado sem agente — não conta como unassigned (não é aberto)
        await _make_ticket(status=TicketStatus.CANCELLED).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["kpis"][0]["unassigned_count"] == 1

    @pytest.mark.asyncio
    async def test_overdue_uses_sla_per_criticality(
        self, repository: TicketRepository
    ) -> None:
        now = datetime.now(UTC)
        # high SLA = 1d → criado há 2d, está overdue
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            criticality=TicketCriticality.HIGH,
            creation_date=now - timedelta(days=2),
        ).insert()
        # medium SLA = 3d → criado há 2d, NÃO está overdue
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            criticality=TicketCriticality.MEDIUM,
            creation_date=now - timedelta(days=2),
        ).insert()
        # low SLA = 5d → criado há 10d, está overdue
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            criticality=TicketCriticality.LOW,
            creation_date=now - timedelta(days=10),
        ).insert()
        # Finalizado antigo: nunca overdue
        await _make_ticket(
            status=TicketStatus.FINISHED,
            criticality=TicketCriticality.HIGH,
            creation_date=now - timedelta(days=30),
        ).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["kpis"][0]["overdue_count"] == 2


class TestOpenBreakdownFacet:
    @pytest.mark.asyncio
    async def test_groups_only_open_tickets_by_status(
        self, repository: TicketRepository
    ) -> None:
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        await _make_ticket(status=TicketStatus.AWAITING_ASSIGNMENT).insert()
        await _make_ticket(status=TicketStatus.FINISHED).insert()
        await _make_ticket(status=TicketStatus.CANCELLED).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        counts_by_status = {row["_id"]: row["count"] for row in result["open_breakdown"]}
        assert counts_by_status == {
            "in_progress": 2,
            "awaiting_assignment": 1,
        }

    @pytest.mark.asyncio
    async def test_open_breakdown_uses_status_string_as_id(
        self, repository: TicketRepository
    ) -> None:
        await _make_ticket(status=TicketStatus.WAITING_FOR_PROVIDER).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        ids = {row["_id"] for row in result["open_breakdown"]}
        assert "waiting_for_provider" in ids


class TestAssignedBreakdownFacet:
    @pytest.mark.asyncio
    async def test_groups_open_tickets_by_active_agent_id(
        self, repository: TicketRepository
    ) -> None:
        julia_id = uuid4()
        mafe_id = uuid4()
        for _ in range(2):
            await _make_ticket(
                status=TicketStatus.IN_PROGRESS,
                active_agent=(julia_id, "Julia"),
            ).insert()
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            active_agent=(mafe_id, "Mafe"),
        ).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        rows = result["assigned_breakdown_raw"]
        assert len(rows) == 2
        by_agent = {row["agent_name"]: row["count"] for row in rows}
        assert by_agent == {"Julia": 2, "Mafe": 1}

    @pytest.mark.asyncio
    async def test_assigned_breakdown_sorted_descending_by_count(
        self, repository: TicketRepository
    ) -> None:
        loser = uuid4()
        winner = uuid4()
        for _ in range(3):
            await _make_ticket(
                status=TicketStatus.IN_PROGRESS,
                active_agent=(winner, "Winner"),
            ).insert()
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            active_agent=(loser, "Loser"),
        ).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        counts = [row["count"] for row in result["assigned_breakdown_raw"]]
        assert counts == sorted(counts, reverse=True)
        assert result["assigned_breakdown_raw"][0]["agent_name"] == "Winner"

    @pytest.mark.asyncio
    async def test_excludes_tickets_with_closed_assignments_only(
        self, repository: TicketRepository
    ) -> None:
        agent_id = uuid4()
        now = datetime.now(UTC)
        ticket = Ticket(
            triage_id=PydanticObjectId(),
            type=TicketType.ISSUE,
            criticality=TicketCriticality.HIGH,
            product="Sistema",
            status=TicketStatus.IN_PROGRESS,
            level=TicketLevel.N1,
            creation_date=now,
            description="histórico fechado",
            chat_ids=[],
            agent_history=[
                TicketHistory(
                    agent_id=agent_id,
                    name="Encerrado",
                    level="N1",
                    assignment_date=now - timedelta(days=2),
                    exit_date=now - timedelta(days=1),
                ),
            ],
            client=TicketClient(
                id=uuid4(),
                name="Cliente",
                email="c@test.com",
                company=TicketCompany(id=uuid4(), name="Empresa"),
            ),
            comments=[],
        )
        await ticket.insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["assigned_breakdown_raw"] == []
        assert result["kpis"][0]["unassigned_count"] == 1

    @pytest.mark.asyncio
    async def test_excludes_finished_and_cancelled_tickets(
        self, repository: TicketRepository
    ) -> None:
        agent_id = uuid4()
        await _make_ticket(
            status=TicketStatus.FINISHED,
            active_agent=(agent_id, "Veterano"),
        ).insert()
        await _make_ticket(
            status=TicketStatus.CANCELLED,
            active_agent=(agent_id, "Veterano"),
        ).insert()

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["assigned_breakdown_raw"] == []


class TestTypeFilter:
    @pytest.mark.asyncio
    async def test_filters_documents_by_type(
        self, repository: TicketRepository
    ) -> None:
        await _make_ticket(
            ticket_type=TicketType.ISSUE, status=TicketStatus.IN_PROGRESS
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.ACCESS, status=TicketStatus.IN_PROGRESS
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.NEW_FEATURE, status=TicketStatus.IN_PROGRESS
        ).insert()

        for ticket_type in [
            TicketType.ISSUE,
            TicketType.ACCESS,
            TicketType.NEW_FEATURE,
        ]:
            result = await repository.aggregate_dashboard(ticket_type)
            assert result["kpis"][0]["open_count"] == 1, (
                f"Esperava 1 aberto para {ticket_type.value}"
            )


async def _insert_raw_ticket(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    *,
    creation_date: Any,
    status: str = "in_progress",
    criticality: str = "high",
    include_creation_date: bool = True,
) -> None:
    """Insere um ticket direto no Mongo, contornando a validação do Beanie.

    Permite ``creation_date`` como string, null ou ausente — situações
    impossíveis via o modelo Pydantic mas presentes em dados legados.
    """
    from bson.binary import Binary

    doc: dict[str, Any] = {
        "_id": PydanticObjectId(),
        "triage_id": PydanticObjectId(),
        "type": "issue",
        "criticality": criticality,
        "product": "Sistema",
        "status": status,
        "level": "N1",
        "description": "ticket legado",
        "chat_ids": [],
        "agent_history": [],
        "client": {
            "id": Binary(uuid4().bytes, subtype=4),
            "name": "Cliente",
            "email": "c@test.com",
            "company": {
                "id": Binary(uuid4().bytes, subtype=4),
                "name": "Empresa",
            },
        },
        "comments": [],
    }
    if include_creation_date:
        doc["creation_date"] = creation_date
    await Ticket.get_motor_collection().insert_one(doc)


class TestMalformedCreationDate:
    """Regressão do crash de produção:
    ``$dateAdd requires startDate to be convertible to a date``.

    Documentos com creation_date inválido não devem abortar a agregação.
    """

    @pytest.mark.asyncio
    async def test_string_creation_date_does_not_break_aggregation(
        self,
        repository: TicketRepository,
        mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    ) -> None:
        # creation_date como string lixo (não convertível para date)
        await _insert_raw_ticket(mongo_db_conn, creation_date="not-a-date")

        # Não deve levantar exceção
        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["kpis"][0]["open_count"] == 1
        # Sem data calculável → não conta como vencido
        assert result["kpis"][0]["overdue_count"] == 0

    @pytest.mark.asyncio
    async def test_null_creation_date_does_not_break_aggregation(
        self,
        repository: TicketRepository,
        mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    ) -> None:
        await _insert_raw_ticket(mongo_db_conn, creation_date=None)

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["kpis"][0]["open_count"] == 1
        assert result["kpis"][0]["overdue_count"] == 0

    @pytest.mark.asyncio
    async def test_missing_creation_date_does_not_break_aggregation(
        self,
        repository: TicketRepository,
        mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    ) -> None:
        await _insert_raw_ticket(
            mongo_db_conn, creation_date=None, include_creation_date=False
        )

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["kpis"][0]["open_count"] == 1
        assert result["kpis"][0]["overdue_count"] == 0

    @pytest.mark.asyncio
    async def test_iso_string_creation_date_is_recovered_and_counts_as_overdue(
        self,
        repository: TicketRepository,
        mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    ) -> None:
        # String ISO válida e antiga: $convert recupera → conta no overdue
        # (high SLA = 1 dia, criado há 30 dias)
        old_iso = (datetime.now(UTC) - timedelta(days=30)).isoformat()
        await _insert_raw_ticket(
            mongo_db_conn, creation_date=old_iso, criticality="high"
        )

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        assert result["kpis"][0]["open_count"] == 1
        assert result["kpis"][0]["overdue_count"] == 1

    @pytest.mark.asyncio
    async def test_mixed_valid_and_invalid_documents(
        self,
        repository: TicketRepository,
        mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
    ) -> None:
        """Cenário realista de produção: documentos bons e ruins juntos.

        - 1 válido vencido (Date, high SLA, 10 dias atrás)
        - 1 válido não vencido (Date, low SLA, 1h atrás)
        - 1 corrompido (string lixo)
        - 1 corrompido (null)

        Resultado esperado: agregação não quebra; open_count conta os 4;
        overdue_count conta apenas o válido vencido.
        """
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            criticality=TicketCriticality.HIGH,
            creation_date=datetime.now(UTC) - timedelta(days=10),
        ).insert()
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            criticality=TicketCriticality.LOW,
            creation_date=datetime.now(UTC) - timedelta(hours=1),
        ).insert()
        await _insert_raw_ticket(mongo_db_conn, creation_date="garbage")
        await _insert_raw_ticket(mongo_db_conn, creation_date=None)

        result = await repository.aggregate_dashboard(TicketType.ISSUE)

        kpis = result["kpis"][0]
        assert kpis["open_count"] == 4
        assert kpis["overdue_count"] == 1
