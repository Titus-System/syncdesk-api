"""End-to-end HTTP tests for ``GET /api/tickets/dashboard/issues-by-product``.

Usa AsyncClient real com autenticação real (seed completo de
roles/permissões + login admin). Dados semeados diretamente no Mongo.
"""
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
    product: str,
    creation_date: datetime,
    ticket_type: TicketType = TicketType.ISSUE,
    company_id: UUID | None = None,
) -> Ticket:
    cid = company_id or uuid4()
    return Ticket(
        triage_id=PydanticObjectId(),
        type=ticket_type,
        criticality=TicketCriticality.HIGH,
        product=product,
        status=TicketStatus.IN_PROGRESS,
        level=TicketLevel.N1,
        creation_date=creation_date,
        description="Teste e2e issues-by-product",
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


class TestIssuesChartRouteAuth:
    @pytest.mark.asyncio
    async def test_returns_403_without_auth(self, client: AsyncClient) -> None:
        response = await client.get("/api/tickets/dashboard/issues-by-product")

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
            "/api/tickets/dashboard/issues-by-product", headers=headers
        )

        assert response.status_code == 200, response.text


class TestIssuesChartRouteValidation:
    @pytest.mark.asyncio
    async def test_inverted_range_returns_422(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={"date_from": "2026-05-01", "date_to": "2026-01-01"},
            headers=headers,
        )

        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_range_above_twelve_months_returns_422(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={"date_from": "2024-01-01", "date_to": "2026-12-31"},
            headers=headers,
        )

        assert response.status_code == 422
        body = response.json()
        assert "12" in body["detail"]

    @pytest.mark.asyncio
    async def test_invalid_date_format_returns_422(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={"date_from": "not-a-date"},
            headers=headers,
        )

        assert response.status_code == 422


class TestIssuesChartRouteEnvelope:
    @pytest.mark.asyncio
    async def test_success_envelope_shape(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={"date_from": "2026-01-01", "date_to": "2026-03-31"},
            headers=headers,
        )

        body = response.json()
        assert set(body.keys()) == {"data", "meta"}
        assert body["meta"]["success"] is True

        data = body["data"]
        assert set(data.keys()) >= {
            "period_start",
            "period_end",
            "company_id",
            "months",
            "series",
            "generated_at",
        }
        assert data["months"] == ["2026-01", "2026-02", "2026-03"]
        assert data["period_start"] == "2026-01-01"
        assert data["period_end"] == "2026-03-31"

    @pytest.mark.asyncio
    async def test_months_axis_present_with_no_data(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={"date_from": "2026-01-01", "date_to": "2026-02-28"},
            headers=headers,
        )

        data = response.json()["data"]
        assert data["months"] == ["2026-01", "2026-02"]
        assert data["series"] == []


class TestIssuesChartRouteData:
    @pytest.mark.asyncio
    async def test_matches_image_example_with_three_products(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        """Reproduz o cenário da imagem da equipe de produto:
        Produto 1: 12, 14, 7, 18, 10 (jan a mai)
        Produto 2: 10, 12, 16, 17, 20
        Produto 3:  8,  8,  5, 10, 13
        """
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        counts_by_product = {
            "Produto 1": [12, 14, 7, 18, 10],
            "Produto 2": [10, 12, 16, 17, 20],
            "Produto 3": [8, 8, 5, 10, 13],
        }
        for product, monthly_counts in counts_by_product.items():
            for month_index, count in enumerate(monthly_counts, start=1):
                for _ in range(count):
                    await _make_ticket(
                        product=product,
                        creation_date=datetime(2026, month_index, 15, tzinfo=UTC),
                    ).insert()

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={"date_from": "2026-01-01", "date_to": "2026-05-31"},
            headers=headers,
        )

        data = response.json()["data"]
        assert data["months"] == [
            "2026-01",
            "2026-02",
            "2026-03",
            "2026-04",
            "2026-05",
        ]

        by_product = {s["product"]: s for s in data["series"]}
        assert by_product["Produto 1"]["total"] == 61
        assert [p["count"] for p in by_product["Produto 1"]["points"]] == [
            12, 14, 7, 18, 10,
        ]
        assert by_product["Produto 2"]["total"] == 75
        assert [p["count"] for p in by_product["Produto 2"]["points"]] == [
            10, 12, 16, 17, 20,
        ]
        assert by_product["Produto 3"]["total"] == 44
        assert [p["count"] for p in by_product["Produto 3"]["points"]] == [
            8, 8, 5, 10, 13,
        ]

    @pytest.mark.asyncio
    async def test_series_sorted_by_total_desc(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        when = datetime(2026, 1, 10, tzinfo=UTC)
        for _ in range(3):
            await _make_ticket(product="Big", creation_date=when).insert()
        await _make_ticket(product="Small", creation_date=when).insert()

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
            headers=headers,
        )

        series = response.json()["data"]["series"]
        assert [s["product"] for s in series] == ["Big", "Small"]

    @pytest.mark.asyncio
    async def test_company_id_filter_isolates_data(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        target = uuid4()
        other = uuid4()
        when = datetime(2026, 2, 10, tzinfo=UTC)
        await _make_ticket(
            product="P", creation_date=when, company_id=target
        ).insert()
        await _make_ticket(
            product="P", creation_date=when, company_id=other
        ).insert()

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={
                "company_id": str(target),
                "date_from": "2026-02-01",
                "date_to": "2026-02-28",
            },
            headers=headers,
        )

        data = response.json()["data"]
        assert data["company_id"] == str(target)
        assert len(data["series"]) == 1
        assert data["series"][0]["total"] == 1

    @pytest.mark.asyncio
    async def test_non_issue_tickets_are_excluded(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin()
        headers = auth.auth_headers(tokens["access_token"])

        when = datetime(2026, 1, 10, tzinfo=UTC)
        await _make_ticket(
            product="P", creation_date=when, ticket_type=TicketType.ACCESS
        ).insert()
        await _make_ticket(
            product="P", creation_date=when, ticket_type=TicketType.NEW_FEATURE
        ).insert()

        response = await client.get(
            "/api/tickets/dashboard/issues-by-product",
            params={"date_from": "2026-01-01", "date_to": "2026-01-31"},
            headers=headers,
        )

        assert response.json()["data"]["series"] == []
