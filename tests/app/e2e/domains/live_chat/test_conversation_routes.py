from typing import Any
from uuid import UUID, uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from httpx import AsyncClient

from app.domains.auth.entities import UserWithRoles
from app.domains.live_chat.entities import ChatMessage, Conversation
from app.domains.live_chat.schemas import CreateConversationDTO
from tests.app.e2e.conftest import AuthActions


async def cleanup_legacy_conversation_indexes() -> None:
    collection = Conversation.get_motor_collection()
    indexes = await collection.index_information()
    legacy_indexes = ("service_session_id_1_sequential_index_1",)
    for index_name in legacy_indexes:
        if index_name in indexes:
            await collection.drop_index(index_name)


@pytest_asyncio.fixture(autouse=True)
async def cleanup_conversation_collection():
    await cleanup_legacy_conversation_indexes()
    await Conversation.delete_all()
    yield
    await Conversation.delete_all()
    await cleanup_legacy_conversation_indexes()

class TestConversationCRUD:
    create_dto = CreateConversationDTO(
        ticket_id=PydanticObjectId(),
        agent_id = uuid4(),
        client_id= uuid4()
    )

    @pytest.fixture
    async def admin_user(self, auth: AuthActions) -> tuple[UserWithRoles, str]:
        tokens = await auth.register_and_login_admin(email="convadm@test.com", username="convdm")

        user = await auth.me(tokens["access_token"])
        return user, tokens["access_token"]

    @pytest.mark.asyncio
    async def test_create_conversation(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = admin_user[0].id

        r = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 201
        data: dict[str, Any] = r.json()["data"]
        conv = Conversation(**data)
        assert conv.id is not None
        assert conv.agent_id == self.create_dto.agent_id
        assert conv.client_id == self.create_dto.client_id
        assert conv.client_id == admin_user[0].id

    @pytest.mark.asyncio
    async def test_create_conversation_admin(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = uuid4()
        r = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 201
        body = r.json()
        assert body["data"] is not None
        assert body["data"]["ticket_id"] == str(self.create_dto.ticket_id)

    @pytest.mark.asyncio
    async def test_create_conversation_not_allowed(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        unauthorized = await auth.register_and_login()
        create_resp = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(unauthorized["access_token"]),
        )
        assert create_resp is not None
        assert create_resp.status_code == 403
        body = create_resp.json()
        assert "can't create a conversation in the name of another user" in body["detail"]

    @pytest.mark.asyncio
    async def test_get_conversations(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = admin_user[0].id

        for i in range(5):
            self.create_dto.sequential_index = i
            create_resp = await client.post(
                "/api/conversations/",
                json=self.create_dto.model_dump(mode="json"),
                headers=auth.auth_headers(admin_user[1]),
            )
            assert create_resp.status_code == 201

        self.create_dto.sequential_index = 0

        get_resp = await client.get(
            f"/api/conversations/ticket/{self.create_dto.ticket_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert get_resp.status_code == 200
        data = get_resp.json()["data"]
        assert len(data) == 5
        for i in range(5):
            assert data[i]["sequential_index"] == i
            assert data[i]["client_id"] == str(self.create_dto.client_id)


    @pytest.mark.asyncio
    async def test_get_paginated_messages(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = admin_user[0].id

        # Create 3 conversations with 5 messages each (15 total)
        for i in range(3):
            self.create_dto.sequential_index = i
            create_resp = await client.post(
                "/api/conversations/",
                json=self.create_dto.model_dump(mode="json"),
                headers=auth.auth_headers(admin_user[1]),
            )
            assert create_resp.status_code == 201
            conv_id = PydanticObjectId(create_resp.json()["data"]["id"])
            conv = await Conversation.get(conv_id)
            assert conv is not None
            for j in range(5):
                msg = ChatMessage.create(
                    conv_id, admin_user[0].id, "text", f"conv {i}, msg {j}"
                )
                await conv.update({"$push": {"messages": msg.model_dump()}})

        self.create_dto.sequential_index = 0

        r = await client.get(
            f"/api/conversations/ticket/{self.create_dto.ticket_id}/messages?page=1&limit=10",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 15
        assert data["page"] == 1
        assert data["limit"] == 10
        assert data["has_next"] is True
        assert len(data["messages"]) == 10
        assert data["messages"][0]["content"] == "conv 1, msg 0"
        assert data["messages"][9]["content"] == "conv 2, msg 4"

    @pytest.mark.asyncio
    async def test_get_paginated_messages_second_page(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = admin_user[0].id

        for i in range(3):
            self.create_dto.sequential_index = i
            create_resp = await client.post(
                "/api/conversations/",
                json=self.create_dto.model_dump(mode="json"),
                headers=auth.auth_headers(admin_user[1]),
            )
            assert create_resp.status_code == 201
            conv_id = PydanticObjectId(create_resp.json()["data"]["id"])
            conv = await Conversation.get(conv_id)
            assert conv is not None
            for j in range(5):
                msg = ChatMessage.create(
                    conv_id, admin_user[0].id, "text", f"conv {i}, msg {j}"
                )
                await conv.update({"$push": {"messages": msg.model_dump()}})

        self.create_dto.sequential_index = 0

        r = await client.get(
            f"/api/conversations/ticket/{self.create_dto.ticket_id}/messages?page=2&limit=10",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 15
        assert data["page"] == 2
        assert data["has_next"] is False
        assert len(data["messages"]) == 5
        assert data["messages"][0]["content"] == "conv 0, msg 0"
        assert data["messages"][4]["content"] == "conv 0, msg 4"

    @pytest.mark.asyncio
    async def test_get_paginated_messages_unauthorized(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = admin_user[0].id
        create_resp = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(admin_user[1]),
        )
        assert create_resp.status_code == 201

        outsider = await auth.register_and_login(
            email="outsider_msg@test.com", username="outsider_msg"
        )

        r = await client.get(
            f"/api/conversations/ticket/{self.create_dto.ticket_id}/messages",
            headers=auth.auth_headers(outsider["access_token"]),
        )
        assert r.status_code == 403
        assert "not a current participant" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_paginated_messages_empty(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        fake_session_id = PydanticObjectId()
        r = await client.get(
            f"/api/conversations/ticket/{fake_session_id}/messages",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        assert r.json()["data"] == []


    @pytest.mark.asyncio
    async def test_set_conversation_agent(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = admin_user[0].id
        self.create_dto.agent_id = None
        create_resp = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(admin_user[1]),
        )
        assert create_resp.status_code == 201
        conv_id = create_resp.json()["data"]["id"]

        agent = await auth.register_agent()

        patch_resp = await client.patch(
            f"/api/conversations/{conv_id}/set-agent/{agent["id"]}",
            headers=auth.auth_headers(agent["access_token"]),
        )

        assert patch_resp.status_code == 200

        get_resp = await client.get(
            f"/api/conversations/ticket/{self.create_dto.ticket_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert get_resp.status_code == 200
        data = get_resp.json()["data"][0]
        assert agent["id"] == data["agent_id"]



    @pytest.mark.asyncio
    async def test_set_conversation_agent_not_valid(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = admin_user[0].id
        self.create_dto.agent_id = None
        create_resp = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(admin_user[1]),
        )
        assert create_resp.status_code == 201
        conv_id = create_resp.json()["data"]["id"]

        agent_id = uuid4()
        patch_resp = await client.patch(
            f"/api/conversations/{conv_id}/set-agent/{agent_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert patch_resp.status_code == 403
        body = patch_resp.json()
        assert "does not correspond to a valid agent" in body["detail"]
        self.create_dto.agent_id = uuid4()

    async def test_set_conversation_agent_not_allowed(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        create_resp = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(admin_user[1]),
        )
        assert create_resp.status_code == 201
        conv_id = create_resp.json()["data"]["id"]

        unauth_user = await auth.register_agent()
        patch_resp = await client.patch(
            f"/api/conversations/{conv_id}/set-agent/{unauth_user['id']}",
            headers=auth.auth_headers(unauth_user["access_token"]),
        )
        assert patch_resp.status_code == 403
        body = patch_resp.json()
        assert "Only admins or currently assigned agent can reassign" in body["detail"]

    @pytest.mark.asyncio
    async def test_set_conversation_agent_not_found(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        fake_conv_id = PydanticObjectId()
        agent_id = uuid4()
        patch_resp = await client.patch(
            f"/api/conversations/{fake_conv_id}/set-agent/{agent_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert patch_resp.status_code == 404


    async def test_get_conversations_from_client(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        create_resp = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(admin_user[1]),
        )
        assert create_resp.status_code == 201
        r = await client.get(
            f"/api/conversations/client/{self.create_dto.client_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        r = r.json()
        data = r["data"]
        assert isinstance(data, list)
        assert data[0]["client_id"] == str(self.create_dto.client_id)

    @pytest.mark.asyncio
    async def test_get_conversations_from_client_empty(self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]) -> None:
        # Edge: client_id nunca usado
        fake_client_id = uuid4()
        r = await client.get(
            f"/api/conversations/client/{fake_client_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data == []

    @pytest.mark.asyncio
    async def test_get_conversations_from_client_multiple(self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]) -> None:
        # Edge: client_id com múltiplas conversas
        client_id = uuid4()
        for i in range(3):
            dto = CreateConversationDTO(ticket_id=PydanticObjectId(), agent_id=uuid4(), client_id=client_id, sequential_index=i)
            create_resp = await client.post(
                "/api/conversations/",
                json=dto.model_dump(mode="json"),
                headers=auth.auth_headers(admin_user[1]),
            )
            assert create_resp.status_code == 201
        r = await client.get(
            f"/api/conversations/client/{client_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 3
        indices = [c["sequential_index"] for c in data]
        assert indices == sorted(indices)

    @pytest.mark.asyncio
    async def test_get_conversations_from_client_different_tickets(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        client_id = uuid4()
        ticket_ids = [PydanticObjectId() for _ in range(2)]
        for t_id in ticket_ids:
            dto = CreateConversationDTO(ticket_id=t_id, agent_id=uuid4(), client_id=client_id)
            create_resp = await client.post(
                "/api/conversations/",
                json=dto.model_dump(mode="json"),
                headers=auth.auth_headers(admin_user[1]),
            )
            assert create_resp.status_code == 201
        r = await client.get(
            f"/api/conversations/client/{client_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 2
        returned_tickets = {c["ticket_id"] for c in data}
        assert set(str(t) for t in ticket_ids) == returned_tickets


async def _seed_conversation(
    client: AsyncClient,
    auth: AuthActions,
    admin_token: str,
    contents: list[str],
    ticket_id: PydanticObjectId | None = None,
    client_id: Any = None,
    agent_id: Any = None,
    sequential_index: int = 0,
) -> PydanticObjectId:
    dto = CreateConversationDTO(
        ticket_id=ticket_id or PydanticObjectId(),
        agent_id=agent_id if agent_id is not None else uuid4(),
        client_id=client_id or uuid4(),
        sequential_index=sequential_index,
    )
    r = await client.post(
        "/api/conversations/",
        json=dto.model_dump(mode="json"),
        headers=auth.auth_headers(admin_token),
    )
    assert r.status_code == 201, r.text
    conv_id = PydanticObjectId(r.json()["data"]["id"])

    conv = await Conversation.get(conv_id)
    assert conv is not None
    sender = client_id if client_id is not None else conv.client_id
    for content in contents:
        msg = ChatMessage.create(conv_id, sender, "text", content)
        await conv.update({"$push": {"messages": msg.model_dump()}})
    return conv_id


class TestConversationSearch:
    @pytest.fixture
    async def admin_user(self, auth: AuthActions) -> tuple[UserWithRoles, str]:
        tokens = await auth.register_and_login_admin(
            email="search_admin@test.com", username="searchadm"
        )
        user = await auth.me(tokens["access_token"])
        return user, tokens["access_token"]

    @pytest.mark.asyncio
    async def test_admin_finds_conversation_by_message_content(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        match_id = await _seed_conversation(
            client, auth, admin_user[1], ["preciso de ajuda com o boleto"]
        )
        await _seed_conversation(client, auth, admin_user[1], ["nada relacionado"])

        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "boleto"},
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == str(match_id)

    @pytest.mark.asyncio
    async def test_search_picks_highest_match_score_per_ticket(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        best_id = await _seed_conversation(
            client, auth, admin_user[1],
            [
                "primeiro contato sobre reembolso",
                "ainda discutindo reembolso",
                "novo pedido de reembolso registrado",
            ],
            ticket_id=ticket_id, client_id=client_id, sequential_index=0,
        )
        await _seed_conversation(
            client, auth, admin_user[1],
            ["apenas uma menção a reembolso aqui"],
            ticket_id=ticket_id, client_id=client_id, sequential_index=1,
        )

        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "reembolso"},
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == str(best_id)
        assert data[0]["sequential_index"] == 0

    @pytest.mark.asyncio
    async def test_search_tiebreaker_prefers_most_recent_per_ticket(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        ticket_id = PydanticObjectId()
        client_id = uuid4()
        await _seed_conversation(
            client, auth, admin_user[1],
            ["primeira menção ao reembolso"],
            ticket_id=ticket_id, client_id=client_id, sequential_index=0,
        )
        latest_id = await _seed_conversation(
            client, auth, admin_user[1],
            ["nova mensagem sobre reembolso"],
            ticket_id=ticket_id, client_id=client_id, sequential_index=1,
        )

        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "reembolso"},
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == str(latest_id)
        assert data[0]["sequential_index"] == 1

    @pytest.mark.asyncio
    async def test_agent_only_finds_their_conversations(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        agent = await auth.register_agent(
            email="search_agent@test.com", username="searchag"
        )
        agent_id = UUID(agent["id"])

        owned_id = await _seed_conversation(
            client, auth, admin_user[1],
            ["cliente pediu cancelamento da fatura"],
            agent_id=agent_id,
        )
        await _seed_conversation(
            client, auth, admin_user[1],
            ["cliente pediu cancelamento da fatura"],
        )

        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "cancelamento"},
            headers=auth.auth_headers(agent["access_token"]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == str(owned_id)
        assert data[0]["agent_id"] == str(agent_id)

    @pytest.mark.asyncio
    async def test_client_only_finds_own_conversations(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        regular = await auth.register_and_login(
            email="search_client@test.com", username="searchcli"
        )
        regular_user = await auth.me(regular["access_token"])

        owned_id = await _seed_conversation(
            client, auth, admin_user[1],
            ["dúvida sobre o pedido"],
            client_id=regular_user.id,
        )
        await _seed_conversation(
            client, auth, admin_user[1],
            ["dúvida sobre o pedido"],
        )

        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "pedido"},
            headers=auth.auth_headers(regular["access_token"]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == str(owned_id)
        assert data[0]["client_id"] == str(regular_user.id)

    @pytest.mark.asyncio
    async def test_search_no_results_returns_empty_list(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        await _seed_conversation(
            client, auth, admin_user[1], ["mensagem qualquer"]
        )

        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "inexistente"},
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        assert r.json()["data"] == []

    @pytest.mark.asyncio
    async def test_search_is_case_insensitive(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        match_id = await _seed_conversation(
            client, auth, admin_user[1], ["Erro no LOGIN do sistema"]
        )

        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "login"},
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert len(data) == 1
        assert data[0]["id"] == str(match_id)

    @pytest.mark.asyncio
    async def test_search_missing_query_returns_400(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        r = await client.get(
            "/api/conversations/search",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 400
        assert "search_query" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_search_whitespace_only_query_returns_400(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "       "},
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 400
        assert "search_query" in r.json()["detail"]

    @pytest.mark.asyncio
    async def test_search_query_too_short_returns_422(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "abc"},
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_search_requires_authentication(
        self, client: AsyncClient
    ) -> None:
        r = await client.get(
            "/api/conversations/search",
            params={"search_query": "qualquer"},
        )
        assert r.status_code == 403
