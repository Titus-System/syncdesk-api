"""End-to-end tests for the permission endpoints (CRUD + role assignment)."""

import pytest
from httpx import AsyncClient

from tests.app.e2e.conftest import AuthActions


class TestPermissionsCRUD:
    """Tests for /api/permissions/ endpoints."""

    @pytest.mark.asyncio
    async def test_create_permission(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="permadm@test.com", username="permadm")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/permissions/",
            json={"name": "users:read", "description": "Read users"},
            headers=headers,
        )
        assert r.status_code == 201

        data = r.json()["data"]
        assert data["name"] == "users:read"
        assert data["description"] == "Read users"
        assert "id" in data

    @pytest.mark.asyncio
    async def test_create_permission_duplicate(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(email="permdup@test.com", username="permdup")
        headers = auth.auth_headers(tokens["access_token"])

        await client.post("/api/permissions/", json={"name": "dup:perm"}, headers=headers)
        r = await client.post("/api/permissions/", json={"name": "dup:perm"}, headers=headers)
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_create_permission_invalid_name(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(email="perminv@test.com", username="perminv")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post("/api/permissions/", json={"name": "invalid-name"}, headers=headers)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_get_permissions(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="permget@test.com", username="permget")
        headers = auth.auth_headers(tokens["access_token"])

        await client.post("/api/permissions/", json={"name": "items:list"}, headers=headers)

        r = await client.get("/api/permissions/", headers=headers)
        assert r.status_code == 200

        perms = r.json()["data"]
        assert isinstance(perms, list)
        assert any(p["name"] == "items:list" for p in perms)

    @pytest.mark.asyncio
    async def test_get_permission_by_id(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="permbyid@test.com", username="permbyid")
        headers = auth.auth_headers(tokens["access_token"])

        create_r = await client.post(
            "/api/permissions/", json={"name": "docs:view"}, headers=headers
        )
        perm_id = create_r.json()["data"]["id"]

        r = await client.get(f"/api/permissions/{perm_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "docs:view"

    @pytest.mark.asyncio
    async def test_get_permission_not_found(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="permnf@test.com", username="permnf")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.get("/api/permissions/99999", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_update_permission(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="permup@test.com", username="permup")
        headers = auth.auth_headers(tokens["access_token"])

        create_r = await client.post(
            "/api/permissions/", json={"name": "data:update"}, headers=headers
        )
        perm_id = create_r.json()["data"]["id"]

        r = await client.patch(
            f"/api/permissions/{perm_id}",
            json={"description": "Updated desc"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["description"] == "Updated desc"

    @pytest.mark.asyncio
    async def test_delete_permission(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="permdel@test.com", username="permdel")
        headers = auth.auth_headers(tokens["access_token"])

        create_r = await client.post(
            "/api/permissions/", json={"name": "files:delete"}, headers=headers
        )
        perm_id = create_r.json()["data"]["id"]

        r = await client.delete(f"/api/permissions/{perm_id}", headers=headers)
        assert r.status_code == 200

        r = await client.get(f"/api/permissions/{perm_id}", headers=headers)
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_permissions_require_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/permissions/")
        assert r.status_code == 403

        r = await client.post("/api/permissions/", json={"name": "no:auth"})
        assert r.status_code == 403
