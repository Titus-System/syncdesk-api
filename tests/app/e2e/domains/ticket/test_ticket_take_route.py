from typing import Any

import pytest
from httpx import AsyncClient

from tests.app.e2e.conftest import AuthActions

MISSING_TICKET_ID = "67f0c9b8e4b0b1a2c3d4e5ff"


async def _create_ticket_and_get_id(
    client: AsyncClient,
    auth: AuthActions,
    *,
    admin_email: str,
    admin_username: str,
    client_email: str,
    client_username: str,
) -> tuple[str, dict[str, str]]:
    tokens = await auth.register_and_login_admin(email=admin_email, username=admin_username)
    headers = auth.auth_headers(tokens["access_token"])
    created_user = await auth.register(email=client_email, username=client_username)

    create_response = await client.post(
        "/api/tickets/",
        json={
            "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
            "type": "issue",
            "criticality": "high",
            "product": "Produto Take",
            "description": "Chamado para teste de take",
            "chat_ids": [],
            "client_id": created_user["id"],
        },
        headers=headers,
    )
    assert create_response.status_code == 201, create_response.text

    list_response = await client.get(
        "/api/tickets/",
        params={"client_id": created_user["id"]},
        headers=headers,
    )
    ticket_id: str = list_response.json()["data"]["items"][0]["id"]
    return ticket_id, headers


class TestTakeTicket:
    @pytest.mark.asyncio
    async def test_agent_takes_unassigned_ticket_registers_history_entry(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        ticket_id, _ = await _create_ticket_and_get_id(
            client,
            auth,
            admin_email="take-admin-a1@test.com",
            admin_username="takeadmina1",
            client_email="take-client-a1@test.com",
            client_username="takeclienta1",
        )
        await auth.register_agent(email="take-agent-a1@test.com", username="takeagenta1")
        agent_tokens = await auth.login(email="take-agent-a1@test.com")
        agent_user = await auth.me(agent_tokens["access_token"])

        response = await client.post(
            f"/api/tickets/{ticket_id}/take",
            headers=auth.auth_headers(agent_tokens["access_token"]),
        )

        assert response.status_code == 200, response.text
        data: dict[str, Any] = response.json()["data"]
        assert data["assigned_agent_id"] == str(agent_user.id)
        history = data["agent_history"]
        assert len(history) == 1
        assert history[0]["agent_id"] == str(agent_user.id)
        assert history[0]["level"] == "agent"
        assert history[0]["transfer_reason"] == "Assumido via fila"
        assert history[0]["exit_date"] is None

    @pytest.mark.asyncio
    async def test_admin_takes_unassigned_ticket_registers_history_entry(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="take-admin-b1@test.com", username="takeadminb1"
        )
        headers = auth.auth_headers(tokens["access_token"])
        created_user = await auth.register(
            email="take-client-b1@test.com", username="takeclientb1"
        )
        create_response = await client.post(
            "/api/tickets/",
            json={
                "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
                "type": "issue",
                "criticality": "medium",
                "product": "Produto Take Admin",
                "description": "Admin takes ticket",
                "chat_ids": [],
                "client_id": created_user["id"],
            },
            headers=headers,
        )
        assert create_response.status_code == 201, create_response.text
        list_response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"]},
            headers=headers,
        )
        ticket_id: str = list_response.json()["data"]["items"][0]["id"]
        admin_user = await auth.me(tokens["access_token"])

        response = await client.post(f"/api/tickets/{ticket_id}/take", headers=headers)

        assert response.status_code == 200, response.text
        data: dict[str, Any] = response.json()["data"]
        assert data["assigned_agent_id"] == str(admin_user.id)
        history = data["agent_history"]
        assert len(history) == 1
        assert history[0]["agent_id"] == str(admin_user.id)
        assert history[0]["level"] == "admin"

    @pytest.mark.asyncio
    async def test_taking_own_assigned_ticket_is_idempotent(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        ticket_id, _ = await _create_ticket_and_get_id(
            client,
            auth,
            admin_email="take-admin-c1@test.com",
            admin_username="takeadminc1",
            client_email="take-client-c1@test.com",
            client_username="takeclientc1",
        )
        await auth.register_agent(email="take-agent-c1@test.com", username="takeagentc1")
        agent_tokens = await auth.login(email="take-agent-c1@test.com")
        agent_headers = auth.auth_headers(agent_tokens["access_token"])

        first = await client.post(f"/api/tickets/{ticket_id}/take", headers=agent_headers)
        assert first.status_code == 200, first.text

        second = await client.post(f"/api/tickets/{ticket_id}/take", headers=agent_headers)

        assert second.status_code == 200, second.text
        assert len(second.json()["data"]["agent_history"]) == 1

    @pytest.mark.asyncio
    async def test_returns_409_when_ticket_already_assigned_to_another_agent(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        ticket_id, _ = await _create_ticket_and_get_id(
            client,
            auth,
            admin_email="take-admin-d1@test.com",
            admin_username="takeadmind1",
            client_email="take-client-d1@test.com",
            client_username="takeclientd1",
        )
        await auth.register_agent(email="take-agent-d1@test.com", username="takeagentd1")
        agent_a_tokens = await auth.login(email="take-agent-d1@test.com")

        await auth.register_agent(email="take-agent-d2@test.com", username="takeagentd2")
        agent_b_tokens = await auth.login(email="take-agent-d2@test.com")

        first = await client.post(
            f"/api/tickets/{ticket_id}/take",
            headers=auth.auth_headers(agent_a_tokens["access_token"]),
        )
        assert first.status_code == 200, first.text

        second = await client.post(
            f"/api/tickets/{ticket_id}/take",
            headers=auth.auth_headers(agent_b_tokens["access_token"]),
        )

        assert second.status_code == 409, second.text

    @pytest.mark.asyncio
    async def test_user_without_permission_cannot_take_ticket(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        ticket_id, _ = await _create_ticket_and_get_id(
            client,
            auth,
            admin_email="take-admin-e1@test.com",
            admin_username="takeadmine1",
            client_email="take-client-e1@test.com",
            client_username="takecliante1",
        )
        user_tokens = await auth.register_and_login(
            email="take-user-e1@test.com", username="takeusere1"
        )

        response = await client.post(
            f"/api/tickets/{ticket_id}/take",
            headers=auth.auth_headers(user_tokens["access_token"]),
        )

        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    async def test_unauthenticated_request_is_rejected(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        ticket_id, _ = await _create_ticket_and_get_id(
            client,
            auth,
            admin_email="take-admin-f1@test.com",
            admin_username="takeadminf1",
            client_email="take-client-f1@test.com",
            client_username="takeclientf1",
        )

        response = await client.post(f"/api/tickets/{ticket_id}/take")

        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    async def test_take_nonexistent_ticket_returns_404(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        await auth.register_agent(email="take-agent-g1@test.com", username="takeagentg1")
        agent_tokens = await auth.login(email="take-agent-g1@test.com")

        response = await client.post(
            f"/api/tickets/{MISSING_TICKET_ID}/take",
            headers=auth.auth_headers(agent_tokens["access_token"]),
        )

        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_response_includes_full_ticket_contract(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        ticket_id, _ = await _create_ticket_and_get_id(
            client,
            auth,
            admin_email="take-admin-h1@test.com",
            admin_username="takeadminh1",
            client_email="take-client-h1@test.com",
            client_username="takeclienth1",
        )
        await auth.register_agent(email="take-agent-h1@test.com", username="takeagenth1")
        agent_tokens = await auth.login(email="take-agent-h1@test.com")

        response = await client.post(
            f"/api/tickets/{ticket_id}/take",
            headers=auth.auth_headers(agent_tokens["access_token"]),
        )

        assert response.status_code == 200, response.text
        data: dict[str, Any] = response.json()["data"]
        for field in (
            "id",
            "triage_id",
            "type",
            "criticality",
            "product",
            "status",
            "creation_date",
            "description",
            "chat_ids",
            "agent_history",
            "client",
            "comments",
        ):
            assert field in data, f"Campo ausente na resposta: {field}"
