from typing import Any
from uuid import uuid4

import pytest
from httpx import AsyncClient

from app.core.event_dispatcher import get_event_dispatcher
from app.core.event_dispatcher.enums import AppEvent
from app.core.event_dispatcher.schemas import TicketAssigneeUpdatedEventSchema
from app.domains.live_chat.entities import Conversation
from app.domains.ticket.models import Ticket
from tests.app.e2e.conftest import AuthActions


async def _create_ticket(
    client: AsyncClient,
    auth: AuthActions,
    admin_email: str,
    admin_username: str,
    client_email: str,
    client_username: str,
    product: str,
) -> tuple[dict[str, Any], dict[str, str]]:
    tokens = await auth.register_and_login_admin(email=admin_email, username=admin_username)
    headers = auth.auth_headers(tokens["access_token"])
    created_user = await auth.register(email=client_email, username=client_username)

    payload = {
        "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
        "type": "issue",
        "criticality": "high",
        "product": product,
        "description": "Erro ao emitir boleto",
        "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
        "client_id": created_user["id"],
    }

    response = await client.post("/api/tickets/", json=payload, headers=headers)
    assert response.status_code == 201, response.text

    return created_user, headers


async def _create_ticket_with_payload(
    client: AsyncClient,
    headers: dict[str, str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    response = await client.post("/api/tickets/", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _list_tickets_for_client(
    client: AsyncClient,
    headers: dict[str, str],
    client_id: str,
) -> list[dict[str, Any]]:
    response = await client.get(
        "/api/tickets/",
        params={"client_id": client_id, "page": 1, "page_size": 20},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


class TestTicketRoutes:
    @pytest.mark.asyncio
    async def test_create_ticket_uses_official_initial_status(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ticket-admin-create@test.com",
            username="ticketadmincreate",
        )
        headers = auth.auth_headers(tokens["access_token"])
        created_user = await auth.register(
            email="ticket-client-create@test.com",
            username="ticketclientcreate",
        )

        response = await client.post(
            "/api/tickets/",
            json={
                "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
                "type": "issue",
                "criticality": "medium",
                "product": "Produto Status Inicial",
                "description": "Primeiro ticket oficial",
                "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
                "client_id": created_user["id"],
            },
            headers=headers,
        )
        assert response.status_code == 201
        assert response.json()["data"]["status"] == "awaiting_assignment"

    @pytest.mark.asyncio
    async def test_get_tickets_returns_official_paginated_shape(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-page@test.com",
            admin_username="ticketadminpage",
            client_email="ticket-client-page@test.com",
            client_username="ticketclientpage",
            product="Produto Contrato Paginado",
        )

        response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"], "product": "Produto Contrato Paginado"},
            headers=headers,
        )
        assert response.status_code == 200

        data = response.json()["data"]
        assert isinstance(data, dict)
        assert data["page"] == 1
        assert data["page_size"] == 20
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["product"] == "Produto Contrato Paginado"
        assert data["items"][0]["status"] == "awaiting_assignment"

    @pytest.mark.asyncio
    async def test_get_ticket_by_id_returns_single_ticket(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-byid@test.com",
            admin_username="ticketadminbyid",
            client_email="ticket-client-byid@test.com",
            client_username="ticketclientbyid",
            product="Produto Contrato ById",
        )

        list_response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"], "product": "Produto Contrato ById"},
            headers=headers,
        )
        ticket_id = list_response.json()["data"]["items"][0]["id"]

        response = await client.get(f"/api/tickets/{ticket_id}", headers=headers)
        assert response.status_code == 200
        assert response.json()["data"]["id"] == ticket_id

    @pytest.mark.asyncio
    async def test_partial_patch_is_the_official_update_route(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-patch@test.com",
            admin_username="ticketadminpatch",
            client_email="ticket-client-patch@test.com",
            client_username="ticketclientpatch",
            product="Produto Contrato Patch",
        )

        list_response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"], "product": "Produto Contrato Patch"},
            headers=headers,
        )
        ticket_id = list_response.json()["data"]["items"][0]["id"]

        response = await client.patch(
            f"/api/tickets/{ticket_id}",
            json={
                "status": "in_progress",
                "criticality": "medium",
                "description": "Chamado assumido e em andamento.",
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["status"] == "in_progress"
        assert data["criticality"] == "medium"
        assert data["description"] == "Chamado assumido e em andamento."

    @pytest.mark.asyncio
    async def test_assign_ticket_returns_200_and_updates_ticket_history_and_status(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-stubs@test.com",
            admin_username="ticketadminstubs",
            client_email="ticket-client-stubs@test.com",
            client_username="ticketclientstubs",
            product="Produto Contrato Stubs",
        )

        list_response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"], "product": "Produto Contrato Stubs"},
            headers=headers,
        )
        ticket_id = list_response.json()["data"]["items"][0]["id"]

        agent_data = await auth.register_agent(
            email="ticket-agent-assign@test.com",
            username="ticketagentassign",
        )
        agent_tokens = await auth.login(email="ticket-agent-assign@test.com")
        agent_user = await auth.me(agent_tokens["access_token"])

        assign_response = await client.post(
            f"/api/tickets/{ticket_id}/assign",
            json={"agent_id": str(agent_user.id), "reason": "Primeira atribuicao"},
            headers=headers,
        )
        assert assign_response.status_code == 200, assign_response.text
        assign_data = assign_response.json()["data"]
        assert assign_data["status"] == "in_progress"
        assert assign_data["assigned_agent_id"] == str(agent_user.id)
        assert assign_data["assigned_agent_name"] == "ticketagentassign"
        assert len(assign_data["agent_history"]) == 1
        assert assign_data["agent_history"][0]["agent_id"] == agent_data["id"]
        assert assign_data["agent_history"][0]["transfer_reason"] == "Primeira atribuicao"
        assert assign_data["agent_history"][0]["exit_date"] is None

        ticket_response = await client.get(f"/api/tickets/{ticket_id}", headers=headers)
        assert ticket_response.status_code == 200, ticket_response.text
        ticket_data = ticket_response.json()["data"]
        assert ticket_data["status"] == "in_progress"
        assert ticket_data["assigned_agent_id"] == str(agent_user.id)
        assert len(ticket_data["agent_history"]) == 1

    @pytest.mark.asyncio
    async def test_assign_ticket_returns_404_for_missing_ticket(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ticket-admin-assign404@test.com",
            username="ticketadminassign404",
        )
        headers = auth.auth_headers(tokens["access_token"])
        agent_data = await auth.register_agent(
            email="ticket-agent-assign404@test.com",
            username="ticketagentassign404",
        )

        response = await client.post(
            "/api/tickets/67f0c9b8e4b0b1a2c3d4e5ff/assign",
            json={"agent_id": agent_data["id"], "reason": "Tentativa em ticket inexistente"},
            headers=headers,
        )
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_assign_ticket_returns_404_for_missing_agent(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-missingagent@test.com",
            admin_username="ticketadminmissingagent",
            client_email="ticket-client-missingagent@test.com",
            client_username="ticketclientmissingagent",
            product="Produto Missing Agent",
        )
        items = await _list_tickets_for_client(client, headers, created_user["id"])
        ticket_id = items[0]["id"]

        response = await client.post(
            f"/api/tickets/{ticket_id}/assign",
            json={"agent_id": str(uuid4()), "reason": "Agente inexistente"},
            headers=headers,
        )
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_assign_ticket_requires_permission(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, admin_headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-assignperm@test.com",
            admin_username="ticketadminassignperm",
            client_email="ticket-client-assignperm@test.com",
            client_username="ticketclientassignperm",
            product="Produto Assign Permission",
        )
        items = await _list_tickets_for_client(client, admin_headers, created_user["id"])
        ticket_id = items[0]["id"]

        user_tokens = await auth.register_and_login(
            email="ticket-user-assignperm@test.com",
            username="ticketuserassignperm",
        )
        agent_data = await auth.register_agent(
            email="ticket-agent-assignperm@test.com",
            username="ticketagentassignperm",
        )

        response = await client.post(
            f"/api/tickets/{ticket_id}/assign",
            json={"agent_id": agent_data["id"], "reason": "Sem permissao"},
            headers=auth.auth_headers(user_tokens["access_token"]),
        )
        assert response.status_code == 403, response.text

    @pytest.mark.asyncio
    async def test_other_contract_stubs_remain_501(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-stubs@test.com",
            admin_username="ticketadminstubs",
            client_email="ticket-client-stubs@test.com",
            client_username="ticketclientstubs",
            product="Produto Contrato Stubs",
        )

        list_response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"], "product": "Produto Contrato Stubs"},
            headers=headers,
        )
        ticket_id = list_response.json()["data"]["items"][0]["id"]

        escalate_response = await client.post(
            f"/api/tickets/{ticket_id}/escalate",
            json={
                "target_department_id": "dept-finance",
                "target_department_name": "Financeiro",
                "target_level": "N2",
                "reason": "Escalar",
            },
            headers=headers,
        )
        assert escalate_response.status_code == 501

        transfer_response = await client.post(
            f"/api/tickets/{ticket_id}/transfer",
            json={"target_agent_id": str(uuid4()), "reason": "Transferir"},
            headers=headers,
        )
        assert transfer_response.status_code == 501

    @pytest.mark.asyncio
    async def test_get_ticket_queue_requires_authentication_and_permission(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        unauthenticated = await client.get("/api/tickets/queue")
        assert unauthenticated.status_code == 403

        user_tokens = await auth.register_and_login(
            email="ticket-user-queueperm@test.com",
            username="ticketuserqueueperm",
        )
        forbidden = await client.get(
            "/api/tickets/queue",
            headers=auth.auth_headers(user_tokens["access_token"]),
        )
        assert forbidden.status_code == 403

    @pytest.mark.asyncio
    async def test_get_ticket_queue_returns_sorted_items_and_supports_filters(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        await Ticket.delete_all()
        await Conversation.delete_all()

        tokens = await auth.register_and_login_admin(
            email="ticket-admin-queue@test.com",
            username="ticketadminqueue",
        )
        headers = auth.auth_headers(tokens["access_token"])
        admin_user = await auth.me(tokens["access_token"])

        created_user = await auth.register(
            email="ticket-client-queue@test.com",
            username="ticketclientqueue",
        )

        base_payload = {
            "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
            "description": "Ticket para fila",
            "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
            "client_id": created_user["id"],
        }

        await _create_ticket_with_payload(
            client,
            headers,
            {
                **base_payload,
                "type": "issue",
                "criticality": "low",
                "product": "Fila Assigned Low",
            },
        )

        await _create_ticket_with_payload(
            client,
            headers,
            {
                **base_payload,
                "type": "issue",
                "criticality": "high",
                "product": "Fila Assigned High",
            },
        )

        await _create_ticket_with_payload(
            client,
            headers,
            {
                **base_payload,
                "type": "issue",
                "criticality": "medium",
                "product": "Fila Unassigned Medium",
            },
        )

        await _create_ticket_with_payload(
            client,
            headers,
            {
                **base_payload,
                "type": "new_feature",
                "criticality": "medium",
                "product": "Fila Feature Medium",
            },
        )

        items = await _list_tickets_for_client(client, headers, created_user["id"])
        ticket_ids_by_product = {item["product"]: item["id"] for item in items}

        assign_high_response = await client.post(
            f"/api/tickets/{ticket_ids_by_product['Fila Assigned High']}/take",
            headers=headers,
        )
        assert assign_high_response.status_code == 200, assign_high_response.text

        assign_low_response = await client.post(
            f"/api/tickets/{ticket_ids_by_product['Fila Assigned Low']}/take",
            headers=headers,
        )
        assert assign_low_response.status_code == 200, assign_low_response.text

        queue_response = await client.get(
            "/api/tickets/queue",
            params={"page": 1, "page_size": 20},
            headers=headers,
        )
        assert queue_response.status_code == 200, queue_response.text
        queue_data = queue_response.json()["data"]
        assert queue_data["page"] == 1
        assert queue_data["page_size"] == 20
        assert queue_data["total"] == 4
        queue_products = [item["product"] for item in queue_data["items"]]
        assert queue_products[:4] == [
            "Fila Assigned High",
            "Fila Unassigned Medium",
            "Fila Feature Medium",
            "Fila Assigned Low",
        ]

        status_response = await client.get(
            "/api/tickets/queue",
            params={"status": "in_progress", "page": 1, "page_size": 20},
            headers=headers,
        )
        assert status_response.status_code == 200, status_response.text
        status_items = status_response.json()["data"]["items"]
        assert {item["product"] for item in status_items} == {
            "Fila Assigned High",
            "Fila Assigned Low",
        }
        assert all(item["status"] == "in_progress" for item in status_items)

        type_response = await client.get(
            "/api/tickets/queue",
            params={"type": "new_feature", "page": 1, "page_size": 20},
            headers=headers,
        )
        assert type_response.status_code == 200, type_response.text
        type_items = type_response.json()["data"]["items"]
        assert len(type_items) == 1
        assert type_items[0]["product"] == "Fila Feature Medium"
        assert type_items[0]["type"] == "new_feature"

        unassigned_response = await client.get(
            "/api/tickets/queue",
            params={"unassigned_only": True, "page": 1, "page_size": 20},
            headers=headers,
        )
        assert unassigned_response.status_code == 200, unassigned_response.text
        unassigned_items = unassigned_response.json()["data"]["items"]
        assert any(item["product"] == "Fila Unassigned Medium" for item in unassigned_items)
        assert all(item["unassigned"] is True for item in unassigned_items)

        assignee_response = await client.get(
            "/api/tickets/queue",
            params={"assignee_id": str(admin_user.id), "page": 1, "page_size": 20},
            headers=headers,
        )
        assert assignee_response.status_code == 200, assignee_response.text
        assignee_items = assignee_response.json()["data"]["items"]
        assert len(assignee_items) == 2
        assert assignee_items[0]["product"] == "Fila Assigned High"
        assert assignee_items[0]["criticality"] == "high"
        assert assignee_items[1]["product"] == "Fila Assigned Low"
        assert assignee_items[1]["criticality"] == "low"
        assert all(item["assignee_id"] == str(admin_user.id) for item in assignee_items)

    @pytest.mark.asyncio
    async def test_assign_ticket_publishes_ticket_assignee_updated_event_in_http_flow(
        self, client: AsyncClient, auth: AuthActions, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-event@test.com",
            admin_username="ticketadminevent",
            client_email="ticket-client-event@test.com",
            client_username="ticketclientevent",
            product="Produto Event Assign",
        )
        items = await _list_tickets_for_client(client, headers, created_user["id"])
        ticket_id = items[0]["id"]
        agent_data = await auth.register_agent(
            email="ticket-agent-event@test.com",
            username="ticketagentevent",
        )

        dispatcher = get_event_dispatcher()
        original_publish = dispatcher.publish
        published: list[TicketAssigneeUpdatedEventSchema] = []

        async def spy_publish(event: AppEvent, payload: Any) -> None:
            if event == AppEvent.TICKET_ASSIGNEE_UPDATED:
                assert isinstance(payload, TicketAssigneeUpdatedEventSchema)
                published.append(payload)
            await original_publish(event, payload)

        monkeypatch.setattr(dispatcher, "publish", spy_publish)

        response = await client.post(
            f"/api/tickets/{ticket_id}/assign",
            json={"agent_id": agent_data["id"], "reason": "Validando publish"},
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert len(published) == 1
        assert str(published[0].ticket_id) == ticket_id
        assert str(published[0].new_agent_id) == agent_data["id"]
        assert published[0].reason == "Validando publish"

    @pytest.mark.asyncio
    async def test_openapi_exposes_only_official_update_route(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        _ = auth
        response = await client.get("/openapi.json")
        assert response.status_code == 200

        paths = response.json()["paths"]
        assert "/api/tickets/" in paths
        assert "/api/tickets/queue" in paths
        assert "/api/tickets/{ticket_id}" in paths
        assert "/api/tickets/{ticket_id}/assign" in paths
        assert "/api/tickets/{ticket_id}/escalate" in paths
        assert "/api/tickets/{ticket_id}/transfer" in paths
        assert "/api/tickets/{ticket_id}/comments" in paths
        assert "/api/tickets/{ticket_id}/status" not in paths

    @pytest.mark.asyncio
    async def test_comment_on_ticket_returns_created_comment(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-comment@test.com",
            admin_username="ticketadmincomment",
            client_email="ticket-client-comment@test.com",
            client_username="ticketclientcomment",
            product="Produto Contrato Comment",
        )

        list_response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"], "product": "Produto Contrato Comment"},
            headers=headers,
        )
        ticket_id = list_response.json()["data"]["items"][0]["id"]

        response = await client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"text": "Cliente confirmou o erro.", "internal": False},
            headers=headers,
        )
        assert response.status_code == 201, response.text
        data = response.json()["data"]
        assert data["text"] == "Cliente confirmou o erro."
        assert data["internal"] is False
        assert data["author"] == "ticketadmincomment"
        assert "comment_id" in data
        assert "date" in data

    @pytest.mark.asyncio
    async def test_get_ticket_comments_returns_added_comments_in_order(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-listcomments@test.com",
            admin_username="ticketadminlistcomments",
            client_email="ticket-client-listcomments@test.com",
            client_username="ticketclientlistcomments",
            product="Produto Contrato ListComments",
        )

        list_response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"], "product": "Produto Contrato ListComments"},
            headers=headers,
        )
        ticket_id = list_response.json()["data"]["items"][0]["id"]

        first = await client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"text": "Primeiro comentário interno.", "internal": True},
            headers=headers,
        )
        assert first.status_code == 201, first.text
        second = await client.post(
            f"/api/tickets/{ticket_id}/comments",
            json={"text": "Segundo comentário público.", "internal": False},
            headers=headers,
        )
        assert second.status_code == 201, second.text

        response = await client.get(
            f"/api/tickets/{ticket_id}/comments",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        data: list[dict[str, Any]] = response.json()["data"]
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["text"] == "Primeiro comentário interno."
        assert data[0]["internal"] is True
        assert data[1]["text"] == "Segundo comentário público."
        assert data[1]["internal"] is False

    @pytest.mark.asyncio
    async def test_get_comments_returns_empty_list_for_ticket_without_comments(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        created_user, headers = await _create_ticket(
            client=client,
            auth=auth,
            admin_email="ticket-admin-nocomments@test.com",
            admin_username="ticketadminnocomments",
            client_email="ticket-client-nocomments@test.com",
            client_username="ticketclientnocomments",
            product="Produto Contrato NoComments",
        )

        list_response = await client.get(
            "/api/tickets/",
            params={"client_id": created_user["id"], "product": "Produto Contrato NoComments"},
            headers=headers,
        )
        ticket_id = list_response.json()["data"]["items"][0]["id"]

        response = await client.get(
            f"/api/tickets/{ticket_id}/comments",
            headers=headers,
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"] == []

    @pytest.mark.asyncio
    async def test_comment_on_missing_ticket_returns_404(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ticket-admin-comment404@test.com",
            username="ticketadmincomment404",
        )
        headers = auth.auth_headers(tokens["access_token"])

        missing_id = "67f0c9b8e4b0b1a2c3d4e5ff"
        response = await client.post(
            f"/api/tickets/{missing_id}/comments",
            json={"text": "Comentário em ticket inexistente.", "internal": False},
            headers=headers,
        )
        assert response.status_code == 404, response.text

    @pytest.mark.asyncio
    async def test_get_comments_for_missing_ticket_returns_404(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ticket-admin-listcomments404@test.com",
            username="ticketadminlistcomments404",
        )
        headers = auth.auth_headers(tokens["access_token"])

        missing_id = "67f0c9b8e4b0b1a2c3d4e5ff"
        response = await client.get(
            f"/api/tickets/{missing_id}/comments",
            headers=headers,
        )
        assert response.status_code == 404, response.text
