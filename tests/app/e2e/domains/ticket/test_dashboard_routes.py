"""End-to-end HTTP tests for ``GET /api/tickets/dashboard``.

Exercem a rota através do AsyncClient com autenticação real (seed completo
de roles/permissões + login admin) e dados semeados diretamente no Mongo.
Validam o contrato documentado em DASHBOARD_API.md.
"""
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId, init_beanie
from httpx import AsyncClient
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.domains.live_chat.entities import Conversation
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
from tests.app.e2e.conftest import AuthActions


@pytest_asyncio.fixture(autouse=True)
async def _init_beanie_and_cleanup(
    mongo_db_conn: AsyncIOMotorDatabase[dict[str, Any]],
) -> AsyncGenerator[None, None]:
    await init_beanie(database=mongo_db_conn, document_models=[Conversation, Ticket])
    await Ticket.delete_all()
    yield
    await Ticket.delete_all()


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
        description="Teste e2e",
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


class TestDashboardRouteAuth:
    @pytest.mark.asyncio
    async def test_returns_403_without_auth(self, client: AsyncClient) -> None:
        # FastAPI Security dependency retorna 403 quando o header Authorization
        # está ausente. 401 só ocorre com token presente mas inválido.
        response = await client.get("/api/tickets/dashboard", params={"type": "issue"})

        assert response.status_code == 403
        body = response.json()
        assert body["meta"]["success"] is False
        assert body["status"] == 403

    @pytest.mark.asyncio
    async def test_returns_200_with_admin_auth(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "issue"},
            headers=headers,
        )

        assert response.status_code == 200, response.text


class TestDashboardRouteValidation:
    @pytest.mark.asyncio
    async def test_missing_type_returns_422(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get("/api/tickets/dashboard", headers=headers)

        assert response.status_code == 422
        body = response.json()
        assert body["title"] == "Validation Error"
        assert body["status"] == 422
        assert body["instance"] == "/api/tickets/dashboard"
        assert body["meta"]["success"] is False
        # errors traz a localização do campo faltante
        assert any(
            "type" in (err.get("loc") or []) for err in (body.get("errors") or [])
        )

    @pytest.mark.asyncio
    async def test_invalid_type_returns_422(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "unknown_kind"},
            headers=headers,
        )

        assert response.status_code == 422
        body = response.json()
        assert body["status"] == 422
        assert body["title"] == "Validation Error"


class TestDashboardRouteEnvelope:
    @pytest.mark.asyncio
    async def test_success_envelope_shape(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "issue"},
            headers=headers,
        )

        body = response.json()
        assert set(body.keys()) == {"data", "meta"}
        assert body["meta"]["success"] is True
        assert "timestamp" in body["meta"]

        data = body["data"]
        assert set(data.keys()) == {
            "type",
            "generated_at",
            "kpis",
            "open_breakdown",
            "assigned_breakdown",
        }
        assert data["type"] == "issue"
        assert set(data["kpis"].keys()) == {
            "open_count",
            "cancelled_count",
            "unassigned_count",
            "overdue_count",
        }

    @pytest.mark.asyncio
    async def test_open_breakdown_always_has_three_buckets_in_order(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "new_feature"},  # tipo sem nenhum ticket
            headers=headers,
        )

        buckets = response.json()["data"]["open_breakdown"]
        assert [b["bucket"] for b in buckets] == [
            "pendente",
            "em_atendimento",
            "nao_atribuidos",
        ]
        assert [b["count"] for b in buckets] == [0, 0, 0]

    @pytest.mark.asyncio
    async def test_assigned_breakdown_empty_when_no_active_assignment(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "issue"},
            headers=headers,
        )

        assert response.json()["data"]["assigned_breakdown"] == []


class TestDashboardRouteData:
    @pytest.mark.asyncio
    async def test_kpis_reflect_seeded_tickets(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        agent_id = uuid4()
        old = datetime.now(UTC) - timedelta(days=10)

        # 1 IN_PROGRESS com agente ativo (aberto, atribuído, vencido — high+10d)
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            criticality=TicketCriticality.HIGH,
            creation_date=old,
            active_agent=(agent_id, "Julia"),
        ).insert()
        # 1 AWAITING_ASSIGNMENT (aberto, sem agente, NÃO vencido — recente)
        await _make_ticket(status=TicketStatus.AWAITING_ASSIGNMENT).insert()
        # 1 CANCELLED
        await _make_ticket(status=TicketStatus.CANCELLED).insert()
        # 1 FINISHED (não conta como aberto nem como overdue)
        await _make_ticket(
            status=TicketStatus.FINISHED,
            creation_date=old,
        ).insert()

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "issue"},
            headers=headers,
        )

        data = response.json()["data"]
        assert data["kpis"]["open_count"] == 2
        assert data["kpis"]["cancelled_count"] == 1
        assert data["kpis"]["unassigned_count"] == 1
        assert data["kpis"]["overdue_count"] == 1

    @pytest.mark.asyncio
    async def test_open_breakdown_sums_to_open_count(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        await _make_ticket(status=TicketStatus.WAITING_FOR_PROVIDER).insert()
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        await _make_ticket(status=TicketStatus.IN_PROGRESS).insert()
        await _make_ticket(status=TicketStatus.AWAITING_ASSIGNMENT).insert()

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "issue"},
            headers=headers,
        )

        data = response.json()["data"]
        sum_breakdown = sum(b["count"] for b in data["open_breakdown"])
        assert sum_breakdown == data["kpis"]["open_count"] == 4

    @pytest.mark.asyncio
    async def test_assigned_breakdown_groups_by_agent_with_is_aggregate_flag(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        julia = uuid4()
        mafe = uuid4()
        for _ in range(2):
            await _make_ticket(
                status=TicketStatus.IN_PROGRESS,
                active_agent=(julia, "Julia"),
            ).insert()
        await _make_ticket(
            status=TicketStatus.IN_PROGRESS,
            active_agent=(mafe, "Mafe"),
        ).insert()

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "issue"},
            headers=headers,
        )

        rows = response.json()["data"]["assigned_breakdown"]
        assert len(rows) == 2
        # ordenação por count desc
        assert rows[0]["count"] >= rows[1]["count"]
        # nenhum item é agregado (top 10 não foi excedido)
        assert all(not r["is_aggregate"] for r in rows)
        # agent_id é string UUID válida
        assert all(UUID(r["agent_id"]) is not None for r in rows)

    @pytest.mark.asyncio
    async def test_outros_bucket_when_more_than_ten_agents(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        # 12 agentes distintos: contagens 12, 11, ..., 1
        for idx in range(12):
            agent_id = uuid4()
            for _ in range(12 - idx):
                await _make_ticket(
                    status=TicketStatus.IN_PROGRESS,
                    active_agent=(agent_id, f"Agente {idx}"),
                ).insert()

        response = await client.get(
            "/api/tickets/dashboard",
            params={"type": "issue"},
            headers=headers,
        )

        rows = response.json()["data"]["assigned_breakdown"]
        assert len(rows) == 11  # top 10 + Outros
        outros = rows[-1]
        assert outros["is_aggregate"] is True
        assert outros["agent_name"] == "Outros"
        assert outros["agent_id"] is None
        # 2 agentes fora do top: contagens 2 + 1 = 3
        assert outros["count"] == 3
        # demais agentes não são agregados
        assert all(not r["is_aggregate"] for r in rows[:10])

    @pytest.mark.asyncio
    async def test_type_filter_isolates_results(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        await _make_ticket(
            ticket_type=TicketType.ISSUE, status=TicketStatus.IN_PROGRESS
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.ACCESS, status=TicketStatus.IN_PROGRESS
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.ACCESS, status=TicketStatus.IN_PROGRESS
        ).insert()
        await _make_ticket(
            ticket_type=TicketType.NEW_FEATURE, status=TicketStatus.CANCELLED
        ).insert()

        issue = (await client.get(
            "/api/tickets/dashboard", params={"type": "issue"}, headers=headers
        )).json()["data"]
        access = (await client.get(
            "/api/tickets/dashboard", params={"type": "access"}, headers=headers
        )).json()["data"]
        new_feature = (await client.get(
            "/api/tickets/dashboard", params={"type": "new_feature"}, headers=headers
        )).json()["data"]

        assert issue["kpis"]["open_count"] == 1
        assert access["kpis"]["open_count"] == 2
        assert new_feature["kpis"]["open_count"] == 0
        assert new_feature["kpis"]["cancelled_count"] == 1
