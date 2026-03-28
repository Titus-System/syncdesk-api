from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from httpx import AsyncClient

from app.domains.auth.entities import UserWithRoles
from app.domains.live_chat.entities import ChatMessage, Conversation
from app.domains.live_chat.schemas import CreateConversationDTO
from tests.app.e2e.conftest import AuthActions


@pytest_asyncio.fixture(autouse=True)
async def cleanup_conversation_collection():
    await Conversation.delete_all()
    yield
    await Conversation.delete_all()

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
