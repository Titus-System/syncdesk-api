"""End-to-end tests for the role endpoints (CRUD + permission assignment)."""

import pytest
from httpx import AsyncClient

from tests.app.e2e.conftest import AuthActions


class TestRolesCRUD:
    """Tests for /api/roles/ endpoints."""

    @pytest.mark.asyncio
    async def test_create_role(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="roleadm@test.com", username="roleadm")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/roles/",
            json={"name": "editor", "description": "Can edit things"},
            headers=headers,
        )
        assert r.status_code == 201

        data = r.json()["data"]
        assert data["name"] == "editor"
        assert data["description"] == "Can edit things"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_role_duplicate(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="roledup@test.com", username="roledup")
        headers = auth.auth_headers(tokens["access_token"])

        await client.post("/api/roles/", json={"name": "duprole"}, headers=headers)
        r = await client.post("/api/roles/", json={"name": "duprole"}, headers=headers)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_create_role_invalid_name(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="roleinv@test.com", username="roleinv")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post("/api/roles/", json={"name": "ab"}, headers=headers)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_get_roles(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="roleget@test.com", username="roleget")
        headers = auth.auth_headers(tokens["access_token"])

        await client.post("/api/roles/", json={"name": "viewer"}, headers=headers)

        r = await client.get("/api/roles/", headers=headers)
        assert r.status_code == 200

        roles = r.json()["data"]
        assert isinstance(roles, list)
        assert any(role["name"] == "viewer" for role in roles)

    @pytest.mark.asyncio
    async def test_get_role_by_id(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="roleid@test.com", username="roleid")
        headers = auth.auth_headers(tokens["access_token"])

        create_r = await client.post("/api/roles/", json={"name": "byid_role"}, headers=headers)
        assert create_r.status_code == 201
        role_id = create_r.json()["data"]["id"]

        r = await client.get(f"/api/roles/{role_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "byid_role"

    @pytest.mark.asyncio
    async def test_get_role_not_found(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="rolenf@test.com", username="rolenf")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.get("/api/roles/99999", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_update_role(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="roleup@test.com", username="roleup")
        headers = auth.auth_headers(tokens["access_token"])

        create_r = await client.post("/api/roles/", json={"name": "upd_role"}, headers=headers)
        role_id = create_r.json()["data"]["id"]

        r = await client.patch(
            f"/api/roles/{role_id}",
            json={"description": "Updated description"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["description"] == "Updated description"

    @pytest.mark.asyncio
    async def test_delete_role(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="roledel@test.com", username="roledel")
        headers = auth.auth_headers(tokens["access_token"])

        create_r = await client.post("/api/roles/", json={"name": "del_role"}, headers=headers)
        role_id = create_r.json()["data"]["id"]

        r = await client.delete(f"/api/roles/{role_id}", headers=headers)
        assert r.status_code == 200

        r = await client.get(f"/api/roles/{role_id}", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_roles_require_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/roles/")
        assert r.status_code == 403

        r = await client.post("/api/roles/", json={"name": "noauth"})
        assert r.status_code == 403
