"""End-to-end HTTP tests for ``GET /api/tickets/dashboard/agent-closings``."""
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
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
        description="Teste E2E closings",
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


class TestAgentClosingsAuth:
    @pytest.mark.asyncio
    async def test_returns_403_without_auth(self, client: AsyncClient) -> None:
        response = await client.get("/api/tickets/dashboard/agent-closings")
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_returns_200_with_admin(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/agent-closings", headers=headers
        )

        assert response.status_code == 200, response.text


class TestAgentClosingsValidation:
    @pytest.mark.asyncio
    async def test_month_out_of_range_returns_422(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/agent-closings",
            params={"month": 13, "year": 2026},
            headers=headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_year_out_of_range_returns_422(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/agent-closings",
            params={"month": 5, "year": 1999},
            headers=headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_invalid_level_returns_422(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/agent-closings",
            params={"level": "N99"},
            headers=headers,
        )

        assert response.status_code == 422


class TestAgentClosingsEnvelope:
    @pytest.mark.asyncio
    async def test_success_envelope_shape(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/agent-closings",
            params={"month": 5, "year": 2026},
            headers=headers,
        )

        body = response.json()
        assert set(body.keys()) == {"data", "meta"}
        assert body["meta"]["success"] is True

        data = body["data"]
        assert data["month"] == 5
        assert data["year"] == 2026
        assert data["level"] is None
        assert "agents" in data and isinstance(data["agents"], list)

    @pytest.mark.asyncio
    async def test_defaults_to_current_month_and_year(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/agent-closings", headers=headers
        )

        today = datetime.now(UTC).date()
        data = response.json()["data"]
        assert data["month"] == today.month
        assert data["year"] == today.year


class TestAgentClosingsData:
    @pytest.mark.asyncio
    async def test_image_example_three_agents_three_types(
        self,
        client: AsyncClient,
        auth: AuthActions,
    ) -> None:
        """Reproduz a imagem da equipe de produto (escalado para 10x menor)."""
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        julia, mafe, angelina = uuid4(), uuid4(), uuid4()
        when = datetime(2026, 5, 15, tzinfo=UTC)

        counts = {
            julia: ("Julia", {"issue": 22, "new_feature": 12, "access": 50}),
            mafe: ("Mafe", {"issue": 32, "new_feature": 17, "access": 20}),
            angelina: (
                "Angelina",
                {"issue": 40, "new_feature": 25, "access": 70},
            ),
        }
        for agent_id, (name, by_type) in counts.items():
            for ttype_str, qty in by_type.items():
                ticket_type = TicketType(ttype_str)
                for _ in range(qty):
                    await _make_closed_ticket(
                        agent_id=agent_id, agent_name=name,
                        ticket_type=ticket_type, closed_at=when,
                    ).insert()

        response = await client.get(
            "/api/tickets/dashboard/agent-closings",
            params={"month": 5, "year": 2026},
            headers=headers,
        )

        data = response.json()["data"]
        by_name = {a["agent_name"]: a for a in data["agents"]}

        assert by_name["Angelina"]["issue_count"] == 40
        assert by_name["Angelina"]["access_count"] == 70
        assert by_name["Angelina"]["new_feature_count"] == 25
        assert by_name["Angelina"]["total"] == 135

        assert by_name["Mafe"]["issue_count"] == 32
        assert by_name["Mafe"]["access_count"] == 20
        assert by_name["Mafe"]["new_feature_count"] == 17
        assert by_name["Mafe"]["total"] == 69

        assert by_name["Julia"]["issue_count"] == 22
        assert by_name["Julia"]["access_count"] == 50
        assert by_name["Julia"]["new_feature_count"] == 12
        assert by_name["Julia"]["total"] == 84

        # Ordenação por total desc: Angelina > Julia > Mafe
        assert [a["agent_name"] for a in data["agents"]] == [
            "Angelina", "Julia", "Mafe",
        ]

    @pytest.mark.asyncio
    async def test_level_filter_restricts_results(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        when = datetime(2026, 5, 15, tzinfo=UTC)
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="N1 agent",
            agent_level="N1", closed_at=when,
        ).insert()
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="N3 agent",
            agent_level="N3", closed_at=when,
        ).insert()

        response = await client.get(
            "/api/tickets/dashboard/agent-closings",
            params={"month": 5, "year": 2026, "level": "N3"},
            headers=headers,
        )

        data = response.json()["data"]
        assert data["level"] == "N3"
        assert len(data["agents"]) == 1
        assert data["agents"][0]["agent_name"] == "N3 agent"

    @pytest.mark.asyncio
    async def test_other_months_are_excluded(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="May",
            closed_at=datetime(2026, 5, 15, tzinfo=UTC),
        ).insert()
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="April",
            closed_at=datetime(2026, 4, 30, 23, 59, tzinfo=UTC),
        ).insert()
        await _make_closed_ticket(
            agent_id=uuid4(), agent_name="June",
            closed_at=datetime(2026, 6, 1, 0, 0, tzinfo=UTC),
        ).insert()

        response = await client.get(
            "/api/tickets/dashboard/agent-closings",
            params={"month": 5, "year": 2026},
            headers=headers,
        )

        agents = response.json()["data"]["agents"]
        assert len(agents) == 1
        assert agents[0]["agent_name"] == "May"

    @pytest.mark.asyncio
    async def test_top_10_plus_outros(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        when = datetime(2026, 5, 15, tzinfo=UTC)
        # 12 agentes distintos com contagens 12..1
        for idx in range(12):
            agent_id = uuid4()
            for _ in range(12 - idx):
                await _make_closed_ticket(
                    agent_id=agent_id, agent_name=f"Agente {idx:02d}",
                    closed_at=when,
                ).insert()

        response = await client.get(
            "/api/tickets/dashboard/agent-closings",
            params={"month": 5, "year": 2026},
            headers=headers,
        )

        agents = response.json()["data"]["agents"]
        assert len(agents) == 11
        outros = agents[-1]
        assert outros["is_aggregate"] is True
        assert outros["agent_name"] == "Outros"
        assert outros["agent_id"] is None
        assert outros["total"] == 3  # agentes 10+11 (counts 2+1)
