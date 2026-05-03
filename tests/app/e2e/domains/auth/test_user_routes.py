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

    # ── Deactivate ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_deactivate_user(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(
            email="deactadm@test.com", username="deactadm"
        )
        headers = auth.auth_headers(tokens["access_token"])

        target = await auth.register(email="deacttarget@test.com", username="deacttarget")
        target_id = target["id"]

        r = await client.patch(f"/api/users/{target_id}/deactivate", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["id"] == target_id
        assert data["is_active"] is False
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_deactivate_user_is_idempotent(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="deactidemadm@test.com", username="deactidemadm"
        )
        headers = auth.auth_headers(tokens["access_token"])

        target = await auth.register(
            email="deactidemtarget@test.com", username="deactidemtgt"
        )
        target_id = target["id"]

        first = await client.patch(f"/api/users/{target_id}/deactivate", headers=headers)
        assert first.status_code == 200
        assert first.json()["data"]["is_active"] is False

        second = await client.patch(f"/api/users/{target_id}/deactivate", headers=headers)
        assert second.status_code == 200
        assert second.json()["data"]["is_active"] is False

    @pytest.mark.asyncio
    async def test_deactivate_user_not_found(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="deactnf@test.com", username="deactnf"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.patch(
            "/api/users/00000000-0000-0000-0000-000000000000/deactivate",
            headers=headers,
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_deactivate_user_invalid_uuid(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="deactbad@test.com", username="deactbad"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.patch("/api/users/not-a-uuid/deactivate", headers=headers)
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_deactivate_user_requires_auth(self, client: AsyncClient) -> None:
        r = await client.patch(
            "/api/users/00000000-0000-0000-0000-000000000000/deactivate"
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_deactivate_user_requires_permission(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        regular = await auth.register_and_login(
            email="deactreg@test.com", username="deactreg"
        )
        headers = auth.auth_headers(regular["access_token"])

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.patch(f"/api/users/{user_id}/deactivate", headers=headers)
        assert r.status_code == 403

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

    # ── Update roles (PATCH) ────────────────────────────

    @pytest.mark.asyncio
    async def test_update_user_roles_add_and_remove(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="rolepatch@test.com", username="rolepatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        role_a = (
            await client.post("/api/roles/", json={"name": "patch_a"}, headers=headers)
        ).json()["data"]
        role_b = (
            await client.post("/api/roles/", json={"name": "patch_b"}, headers=headers)
        ).json()["data"]

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        await client.post(
            f"/api/users/{user_id}/roles",
            json={"role_ids": [role_a["id"]]},
            headers=headers,
        )

        r = await client.patch(
            f"/api/users/{user_id}/roles",
            json={"add_role_ids": [role_b["id"]], "remove_role_ids": [role_a["id"]]},
            headers=headers,
        )
        assert r.status_code == 200

        role_ids = {role["id"] for role in r.json()["data"]["roles"]}
        assert role_b["id"] in role_ids
        assert role_a["id"] not in role_ids

    @pytest.mark.asyncio
    async def test_update_user_roles_empty_payload(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="emptypatch@test.com", username="emptypatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.patch(
            f"/api/users/{user_id}/roles",
            json={"add_role_ids": [], "remove_role_ids": []},
            headers=headers,
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_update_user_roles_intersection(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="interpatch@test.com", username="interpatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        role_r = await client.post(
            "/api/roles/", json={"name": "interpatchrole"}, headers=headers
        )
        role_id = role_r.json()["data"]["id"]

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.patch(
            f"/api/users/{user_id}/roles",
            json={"add_role_ids": [role_id], "remove_role_ids": [role_id]},
            headers=headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_roles_exceeds_limit(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="limitpatch@test.com", username="limitpatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.patch(
            f"/api/users/{user_id}/roles",
            json={"add_role_ids": list(range(1, 12)), "remove_role_ids": []},
            headers=headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_update_user_roles_unknown_role(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="unkrolepatch@test.com", username="unkrolepatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.patch(
            f"/api/users/{user_id}/roles",
            json={"add_role_ids": [999999], "remove_role_ids": []},
            headers=headers,
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user_roles_unknown_user(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="unkupatch@test.com", username="unkupatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        role_r = await client.post(
            "/api/roles/", json={"name": "ghostpatchrole"}, headers=headers
        )
        role_id = role_r.json()["data"]["id"]

        r = await client.patch(
            "/api/users/00000000-0000-0000-0000-000000000000/roles",
            json={"add_role_ids": [role_id], "remove_role_ids": []},
            headers=headers,
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_update_user_roles_dedupes_input(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="duppatch@test.com", username="duppatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        role_r = await client.post(
            "/api/roles/", json={"name": "duppatchrole"}, headers=headers
        )
        role_id = role_r.json()["data"]["id"]

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.patch(
            f"/api/users/{user_id}/roles",
            json={"add_role_ids": [role_id, role_id], "remove_role_ids": []},
            headers=headers,
        )
        assert r.status_code == 200
        role_ids = [role["id"] for role in r.json()["data"]["roles"]]
        assert role_ids.count(role_id) == 1

    # ── Remove roles (DELETE) ───────────────────────────

    @pytest.mark.asyncio
    async def test_remove_user_roles(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login_admin(
            email="roledel@test.com", username="roledel"
        )
        headers = auth.auth_headers(tokens["access_token"])

        role_r = await client.post("/api/roles/", json={"name": "delrole"}, headers=headers)
        role_id = role_r.json()["data"]["id"]

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        await client.post(
            f"/api/users/{user_id}/roles",
            json={"role_ids": [role_id]},
            headers=headers,
        )

        r = await client.request(
            "DELETE",
            f"/api/users/{user_id}/roles",
            json={"role_ids": [role_id]},
            headers=headers,
        )
        assert r.status_code == 200

        role_ids = {role["id"] for role in r.json()["data"]["roles"]}
        assert role_id not in role_ids

    @pytest.mark.asyncio
    async def test_remove_user_roles_empty_list(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="emroldel@test.com", username="emroldel"
        )
        headers = auth.auth_headers(tokens["access_token"])

        me_r = await client.get("/api/auth/me", headers=headers)
        user_id = me_r.json()["data"]["id"]

        r = await client.request(
            "DELETE",
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
