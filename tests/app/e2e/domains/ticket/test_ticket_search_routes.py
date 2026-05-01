from collections.abc import AsyncGenerator
from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text

from app.domains.live_chat.entities import Conversation
from app.domains.ticket.models import Ticket
from tests.app.e2e.conftest import AuthActions


@pytest_asyncio.fixture(autouse=True)
async def _cleanup_mongo() -> AsyncGenerator[None, None]:
    await Ticket.delete_all()
    await Conversation.delete_all()
    yield
    await Ticket.delete_all()
    await Conversation.delete_all()


async def _create_ticket(
    client: AsyncClient,
    headers: dict[str, str],
    *,
    client_id: str,
    description: str,
    product: str,
    company_id: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "triage_id": "67f0c9b8e4b0b1a2c3d4e5f6",
        "type": "issue",
        "criticality": "high",
        "product": product,
        "description": description,
        "chat_ids": ["67f0c9b8e4b0b1a2c3d4e5f7"],
        "client_id": client_id,
    }
    if company_id is not None:
        payload["company_id"] = company_id

    response = await client.post("/api/tickets/", json=payload, headers=headers)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _list_tickets(
    client: AsyncClient,
    headers: dict[str, str],
    client_id: str,
) -> list[dict[str, Any]]:
    response = await client.get(
        "/api/tickets/",
        params={"client_id": client_id, "page": 1, "page_size": 50},
        headers=headers,
    )
    assert response.status_code == 200, response.text
    return response.json()["data"]["items"]


async def _add_comment(
    client: AsyncClient,
    headers: dict[str, str],
    ticket_id: str,
    text_value: str,
) -> None:
    response = await client.post(
        f"/api/tickets/{ticket_id}/comments",
        json={"text": text_value, "internal": False},
        headers=headers,
    )
    assert response.status_code == 201, response.text


async def _assign_ticket(
    client: AsyncClient,
    headers: dict[str, str],
    ticket_id: str,
    agent_id: str,
    reason: str = "Atribuído para teste de busca",
) -> None:
    response = await client.post(
        f"/api/tickets/{ticket_id}/assign",
        json={"agent_id": agent_id, "reason": reason},
        headers=headers,
    )
    assert response.status_code == 200, response.text


async def _attach_company_to_user(
    auth: AuthActions,
    user_id: str,
    suffix: str,
) -> UUID:
    company_id = uuid4()
    tax_id = f"{suffix:0>14s}"[:14]
    await auth.db_session.execute(
        text(
            "INSERT INTO companies (id, legal_name, trade_name, tax_id)"
            " VALUES (:id, :legal, :trade, :tax)"
        ),
        {
            "id": company_id,
            "legal": f"Empresa {suffix}",
            "trade": f"Empresa {suffix}",
            "tax": tax_id,
        },
    )
    await auth.db_session.execute(
        text("UPDATE users SET company_id = :cid WHERE id = :uid"),
        {"cid": company_id, "uid": user_id},
    )
    await auth.db_session.flush()
    return company_id


async def _search(
    client: AsyncClient,
    headers: dict[str, str],
    query: str,
) -> tuple[int, Any]:
    response = await client.get(
        "/api/tickets/search",
        params={"search_query": query},
        headers=headers,
    )
    return response.status_code, response.json() if response.content else None


class TestSearchTicketByTextRoute:
    @pytest.mark.asyncio
    async def test_unauthenticated_request_is_rejected(
        self, client: AsyncClient
    ) -> None:
        response = await client.get(
            "/api/tickets/search", params={"search_query": "boleto"}
        )
        assert response.status_code in {401, 403}

    @pytest.mark.asyncio
    async def test_user_finds_only_their_own_tickets(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="search-admin-self@test.com",
            username="searchadminself",
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        client_a = await auth.register(
            email="search-client-a@test.com",
            username="searchclienta",
        )
        client_b = await auth.register(
            email="search-client-b@test.com",
            username="searchclientb",
        )

        await _create_ticket(
            client,
            admin_headers,
            client_id=client_a["id"],
            description="Erro ao emitir boleto do cliente A",
            product="Produto Search Self A",
        )
        await _create_ticket(
            client,
            admin_headers,
            client_id=client_b["id"],
            description="Erro ao emitir boleto do cliente B",
            product="Produto Search Self B",
        )

        client_a_tokens = await auth.login(
            email="search-client-a@test.com",
        )
        client_a_headers = auth.auth_headers(client_a_tokens["access_token"])

        status_code, body = await _search(client, client_a_headers, "boleto")

        assert status_code == 200, body
        data = body["data"]
        assert len(data) == 1
        assert data[0]["description"] == "Erro ao emitir boleto do cliente A"
        assert data[0]["client"]["id"] == client_a["id"]

    @pytest.mark.asyncio
    async def test_search_matches_text_inside_comments(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="search-admin-comments@test.com",
            username="searchadmincomments",
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        client_user = await auth.register(
            email="search-client-comments@test.com",
            username="searchclientcomments",
        )
        await _create_ticket(
            client,
            admin_headers,
            client_id=client_user["id"],
            description="Pedido genérico de suporte",
            product="Produto Search Comentário",
        )
        items = await _list_tickets(client, admin_headers, client_user["id"])
        ticket_id = items[0]["id"]
        await _add_comment(
            client,
            admin_headers,
            ticket_id,
            "Cliente relatou queda na fatura mensal",
        )

        client_tokens = await auth.login(email="search-client-comments@test.com")
        client_headers = auth.auth_headers(client_tokens["access_token"])

        status_code, body = await _search(client, client_headers, "queda")

        assert status_code == 200, body
        data = body["data"]
        assert len(data) == 1
        assert data[0]["comments"][0]["text"] == "Cliente relatou queda na fatura mensal"

    @pytest.mark.asyncio
    async def test_search_is_case_insensitive(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="search-admin-case@test.com",
            username="searchadmincase",
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        client_user = await auth.register(
            email="search-client-case@test.com",
            username="searchclientcase",
        )
        await _create_ticket(
            client,
            admin_headers,
            client_id=client_user["id"],
            description="Falha CRÍTICA na importação",
            product="Produto Search Case",
        )

        client_tokens = await auth.login(email="search-client-case@test.com")
        client_headers = auth.auth_headers(client_tokens["access_token"])

        status_code, body = await _search(client, client_headers, "crítica")

        assert status_code == 200, body
        assert len(body["data"]) == 1

    @pytest.mark.asyncio
    async def test_agent_finds_only_tickets_they_were_assigned_to(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="search-admin-agent@test.com",
            username="searchadminagent",
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        client_user = await auth.register(
            email="search-client-agent@test.com",
            username="searchclientagent",
        )
        agent = await auth.register_agent(
            email="search-agent@test.com",
            username="searchagent",
        )

        await _create_ticket(
            client,
            admin_headers,
            client_id=client_user["id"],
            description="Acesso negado ao módulo financeiro",
            product="Produto Search Agente Atribuído",
        )
        await _create_ticket(
            client,
            admin_headers,
            client_id=client_user["id"],
            description="Acesso negado ao módulo de relatórios",
            product="Produto Search Agente NaoAtribuido",
        )

        items = await _list_tickets(client, admin_headers, client_user["id"])
        assigned = next(t for t in items if "financeiro" in t["description"])
        await _assign_ticket(client, admin_headers, assigned["id"], agent["id"])

        agent_tokens = await auth.login(email="search-agent@test.com")
        agent_headers = auth.auth_headers(agent_tokens["access_token"])

        status_code, body = await _search(client, agent_headers, "acesso")

        assert status_code == 200, body
        data = body["data"]
        assert len(data) == 1
        assert data[0]["description"] == "Acesso negado ao módulo financeiro"

    @pytest.mark.asyncio
    async def test_admin_finds_tickets_in_their_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        admin_data = await auth.register_admin(
            email="search-admin-company@test.com",
            username="searchadmincompany",
        )
        company_id = await _attach_company_to_user(auth, admin_data["id"], "12345")
        admin_tokens = await auth.login(email="search-admin-company@test.com")
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        client_in_company = await auth.register(
            email="search-client-company-in@test.com",
            username="searchclientcompanyin",
        )
        client_outside = await auth.register(
            email="search-client-company-out@test.com",
            username="searchclientcompanyout",
        )

        await _create_ticket(
            client,
            admin_headers,
            client_id=client_in_company["id"],
            description="Falha de sincronização na nota fiscal",
            product="Produto Search Empresa Dentro",
            company_id=str(company_id),
        )
        await _create_ticket(
            client,
            admin_headers,
            client_id=client_outside["id"],
            description="Falha de sincronização em outro grupo",
            product="Produto Search Empresa Fora",
            company_id=str(uuid4()),
        )

        status_code, body = await _search(client, admin_headers, "sincronização")

        assert status_code == 200, body
        data = body["data"]
        assert len(data) == 1
        assert data[0]["client"]["company"]["id"] == str(company_id)

    @pytest.mark.asyncio
    async def test_admin_without_company_returns_empty(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="search-admin-nocompany@test.com",
            username="searchadminnocompany",
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        client_user = await auth.register(
            email="search-client-nocompany@test.com",
            username="searchclientnocompany",
        )
        await _create_ticket(
            client,
            admin_headers,
            client_id=client_user["id"],
            description="Qualquer descrição buscável",
            product="Produto Search Sem Empresa",
        )

        status_code, body = await _search(client, admin_headers, "buscável")

        assert status_code == 200, body
        assert body["data"] == []

    @pytest.mark.asyncio
    async def test_blank_query_returns_empty_list(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="search-admin-blank@test.com",
            username="searchadminblank",
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        client_user = await auth.register(
            email="search-client-blank@test.com",
            username="searchclientblank",
        )
        await _create_ticket(
            client,
            admin_headers,
            client_id=client_user["id"],
            description="Conteúdo qualquer",
            product="Produto Search Blank",
        )

        client_tokens = await auth.login(email="search-client-blank@test.com")
        client_headers = auth.auth_headers(client_tokens["access_token"])

        status_code, body = await _search(client, client_headers, "")

        assert status_code == 200, body
        assert body["data"] == []
