"""End-to-end tests for the user endpoints (CRUD + role assignment)."""

import pytest
from httpx import AsyncClient

from tests.app.e2e.conftest import AuthActions


class TestUsersCRUD:
    """Tests for /api/users/ endpoints."""

    # ── Create ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_user(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="useradm@test.com", username="useradm")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/users/",
            json={
                "email": "newuser@test.com",
                "password_hash": "somehashedvalue",
                "username": "newuser",
            },
            headers=headers,
        )
        assert r.status_code == 201

        data = r.json()["data"]
        assert data["email"] == "newuser@test.com"
        assert data["username"] == "newuser"
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_create_user_duplicate_email(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(email="dupuser@test.com", username="dupuser")
        headers = auth.auth_headers(tokens["access_token"])

        await client.post(
            "/api/users/",
            json={"email": "dup@email.com", "password_hash": "hash"},
            headers=headers,
        )
        r = await client.post(
            "/api/users/",
            json={"email": "dup@email.com", "password_hash": "hash"},
            headers=headers,
        )
        assert r.status_code == 409

    # ── Read ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_get_users(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(
            email="listusers@test.com", username="listusers"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.get("/api/users/", headers=headers)
        assert r.status_code == 200

        users = r.json()["data"]
        assert isinstance(users, list)
        assert len(users) >= 1

    @pytest.mark.asyncio
    async def test_get_user_by_id(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="byid@test.com", username="byiduser")
        headers = auth.auth_headers(tokens["access_token"])

        # The registering user was created via /auth/register; fetch their id from /me
        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.get(f"/api/users/{user_id}", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["email"] == "byid@test.com"

    @pytest.mark.asyncio
    async def test_get_user_not_found(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="nfuser@test.com", username="nfuser")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.get("/api/users/00000000-0000-0000-0000-000000000000", headers=headers)
        assert r.status_code == 404

    # ── Update (PATCH) ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_update_user(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="upuser@test.com", username="upuser")
        headers = auth.auth_headers(tokens["access_token"])

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.patch(
            f"/api/users/{user_id}",
            json={"name": "Updated Name"},
            headers=headers,
        )
        assert r.status_code == 200
        assert r.json()["data"]["name"] == "Updated Name"

    # ── Role assignment ─────────────────────────────────

    @pytest.mark.asyncio
    async def test_add_roles_to_user(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="roleadd@test.com", username="roleadd")
        headers = auth.auth_headers(tokens["access_token"])

        # Create a role first
        role_r = await client.post("/api/roles/", json={"name": "testers"}, headers=headers)
        role_id = role_r.json()["data"]["id"]

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.post(
            f"/api/users/{user_id}/roles",
            json={"role_ids": [role_id]},
            headers=headers,
        )
        assert r.status_code == 200

        data = r.json()["data"]
        assert "roles" in data
        assert any(role["id"] == role_id for role in data["roles"])

    @pytest.mark.asyncio
    async def test_add_roles_empty_list(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="emrole@test.com", username="emrole")
        headers = auth.auth_headers(tokens["access_token"])

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.post(
            f"/api/users/{user_id}/roles",
            json={"role_ids": []},
            headers=headers,
        )
        assert r.status_code == 400

    # ── Auth guard ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_users_require_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/users/")
        assert r.status_code == 403

        r = await client.post(
            "/api/users/",
            json={"email": "noauth@test.com", "password_hash": "hash"},
        )
        assert r.status_code == 403

    # ── password_hash never leaked ──────────────────────

    @pytest.mark.asyncio
    async def test_password_hash_excluded(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(email="noleak@test.com", username="noleak")
        headers = auth.auth_headers(tokens["access_token"])

        me_r = await client.get("/api/auth/me", headers=headers)
        assert "password_hash" not in me_r.json()["data"]

        all_r = await client.get("/api/users/", headers=headers)
        for user in all_r.json()["data"]:
            assert "password_hash" not in user
