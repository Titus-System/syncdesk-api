from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from beanie import PydanticObjectId
from httpx import AsyncClient

from app.domains.auth.entities import UserWithRoles
from app.domains.live_chat.entities import Conversation
from app.domains.live_chat.schemas import CreateConversationDTO
from tests.app.e2e.conftest import AuthActions


@pytest_asyncio.fixture(autouse=True)
async def cleanup_conversation_collection():
    await Conversation.delete_all()
    yield
    await Conversation.delete_all()

class TestConversationCRUD:
    create_dto = CreateConversationDTO(
        service_session_id=PydanticObjectId(),
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
    async def test_create_conversation_forbidden(
        self, client: AsyncClient, auth: AuthActions, admin_user: tuple[UserWithRoles, str]
    ) -> None:
        self.create_dto.client_id = uuid4()
        r = await client.post(
            "/api/conversations/",
            json=self.create_dto.model_dump(mode="json"),
            headers=auth.auth_headers(admin_user[1]),
        )
        assert r.status_code == 403
        assert "User cannot open a chat in the name of another user" in r.text

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
            f"/api/conversations/service_session/{self.create_dto.service_session_id}",
            headers=auth.auth_headers(admin_user[1]),
        )
        assert get_resp.status_code == 200
        data = get_resp.json()["data"]
        assert len(data) == 5
        for i in range(5):
            assert data[i]["sequential_index"] == i
            assert data[i]["client_id"] == str(self.create_dto.client_id)

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
            f"/api/conversations/service_session/{self.create_dto.service_session_id}",
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
        assert "does not correspond to a valid user" in patch_resp.text

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
        assert patch_resp.status_code == 403
