"""End-to-end tests for the auth endpoints (register, login, refresh, /me, logout)."""

import pytest
from httpx import AsyncClient

from tests.app.e2e.conftest import AuthActions


class TestRegister:
    """POST /api/auth/register"""

    @pytest.mark.asyncio
    async def test_register_success(self, client: AsyncClient, auth: AuthActions) -> None:
        r = await client.post(
            "/api/auth/register",
            json={"email": "new@test.com", "username": "newuser", "password": "Pass1234!"},
        )
        assert r.status_code == 201

        data = r.json()["data"]
        assert data["email"] == "new@test.com"
        assert data["username"] == "newuser"
        assert "access_token" in data
        assert "refresh_token" in data
        assert "id" in data

    @pytest.mark.asyncio
    async def test_register_does_not_leak_password_hash(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        r = await client.post(
            "/api/auth/register",
            json={"email": "noleak@test.com", "username": "noleak", "password": "Pass1234!"},
        )
        assert r.status_code == 201
        data = r.json()["data"]
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_register_duplicate_email(self, client: AsyncClient, auth: AuthActions) -> None:
        await auth.register(email="dup@test.com", username="dup1")

        r = await client.post(
            "/api/auth/register",
            json={"email": "dup@test.com", "username": "dup2", "password": "Secure123!"},
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_register_missing_fields(self, client: AsyncClient) -> None:
        r = await client.post("/api/auth/register", json={"email": "x@x.com"})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_register_empty_body(self, client: AsyncClient) -> None:
        r = await client.post("/api/auth/register", json={})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_register_assigns_default_user_role(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        """Public registration should auto-assign the default 'user' role."""
        await auth.register(email="defrole@test.com", username="defrole")
        login_tokens = await auth.login(email="defrole@test.com")
        me_r = await client.get(
            "/api/auth/me", headers=auth.auth_headers(login_tokens["access_token"])
        )
        assert me_r.status_code == 200

        roles = me_r.json()["data"]["roles"]
        role_names = {r["name"] for r in roles}
        assert "user" in role_names

    @pytest.mark.asyncio
    async def test_register_ignores_role_ids_field(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        """Even if role_ids is sent in the payload, it should be ignored (422 or just ignored)."""
        r = await client.post(
            "/api/auth/register",
            json={
                "email": "ignoreroles@test.com",
                "username": "ignoreroles",
                "password": "Pass1234!",
                "role_ids": [1],
            },
        )
        # Pydantic may either ignore extra fields or the request still succeeds
        # without assigning the requested roles
        if r.status_code == 201:
            login_tokens = await auth.login(email="ignoreroles@test.com", password="Pass1234!")
            me_r = await client.get(
                "/api/auth/me", headers=auth.auth_headers(login_tokens["access_token"])
            )
            roles = me_r.json()["data"]["roles"]
            role_names = {rl["name"] for rl in roles}
            # Should NOT have admin role — only the default "user" role
            assert "admin" not in role_names

    @pytest.mark.asyncio
    async def test_admin_can_assign_roles_via_user_endpoint(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        """Admins can assign roles to users via /users/{id}/roles."""
        admin_tokens = await auth.register_and_login_admin(
            email="rolesetup@test.com", username="rolesetup"
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        # Create a custom role
        r = await client.post("/api/roles/", json={"name": "reg_role_a"}, headers=admin_headers)
        role_id = r.json()["data"]["id"]

        # Register a regular user
        await auth.register(email="withroles@test.com", username="withroles")
        login_tokens = await auth.login(email="withroles@test.com")
        me_r = await client.get(
            "/api/auth/me", headers=auth.auth_headers(login_tokens["access_token"])
        )
        user_id = me_r.json()["data"]["id"]

        # Admin assigns the role
        r = await client.post(
            f"/api/users/{user_id}/roles",
            json={"role_ids": [role_id]},
            headers=admin_headers,
        )
        assert r.status_code == 200

        # Verify role assignment via re-login
        login_tokens = await auth.login(email="withroles@test.com")
        me_r = await client.get(
            "/api/auth/me", headers=auth.auth_headers(login_tokens["access_token"])
        )
        roles = me_r.json()["data"]["roles"]
        role_names = {rl["name"] for rl in roles}
        assert "reg_role_a" in role_names


class TestLogin:
    """POST /api/auth/login"""

    @pytest.mark.asyncio
    async def test_login_success(self, client: AsyncClient, auth: AuthActions) -> None:
        await auth.register(email="login@test.com", username="loginuser")
        r = await client.post(
            "/api/auth/login",
            json={"email": "login@test.com", "password": "Secure123!"},
        )
        assert r.status_code == 200

        data = r.json()["data"]
        assert "access_token" in data
        assert "refresh_token" in data

    @pytest.mark.asyncio
    async def test_login_preserves_roles(self, client: AsyncClient, auth: AuthActions) -> None:
        """Roles assigned via admin should persist through login."""
        admin_tokens = await auth.register_and_login_admin(
            email="loginrsetup@test.com", username="loginrsetup"
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])
        r = await client.post("/api/roles/", json={"name": "login_role"}, headers=admin_headers)
        role_id = r.json()["data"]["id"]

        # Register user, get their ID, then assign role via admin
        await auth.register(email="loginroles@test.com", username="loginroles")
        login_tokens = await auth.login(email="loginroles@test.com")
        me_r = await client.get(
            "/api/auth/me", headers=auth.auth_headers(login_tokens["access_token"])
        )
        user_id = me_r.json()["data"]["id"]

        await client.post(
            f"/api/users/{user_id}/roles",
            json={"role_ids": [role_id]},
            headers=admin_headers,
        )

        # Re-login to get fresh tokens with updated roles
        login_tokens = await auth.login(email="loginroles@test.com")
        me_r = await client.get(
            "/api/auth/me", headers=auth.auth_headers(login_tokens["access_token"])
        )
        assert me_r.status_code == 200
        roles = me_r.json()["data"]["roles"]
        role_names = {rl["name"] for rl in roles}
        assert "login_role" in role_names

    @pytest.mark.asyncio
    async def test_login_wrong_password(self, client: AsyncClient, auth: AuthActions) -> None:
        await auth.register(email="wrongpw@test.com", username="wrongpw")
        r = await client.post(
            "/api/auth/login",
            json={"email": "wrongpw@test.com", "password": "BadPassword!"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_login_nonexistent_user(self, client: AsyncClient) -> None:
        r = await client.post(
            "/api/auth/login",
            json={"email": "ghost@test.com", "password": "Nope1234!"},
        )
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_login_missing_fields(self, client: AsyncClient) -> None:
        r = await client.post("/api/auth/login", json={"email": "x@x.com"})
        assert r.status_code == 422


class TestMe:
    """GET /api/auth/me"""

    @pytest.mark.asyncio
    async def test_me_success(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login(email="me@test.com", username="meuser")
        r = await client.get("/api/auth/me", headers=auth.auth_headers(tokens["access_token"]))
        assert r.status_code == 200

        data = r.json()["data"]
        assert data["email"] == "me@test.com"
        assert "roles" in data

    @pytest.mark.asyncio
    async def test_me_does_not_leak_password_hash(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login(email="menoleak@test.com", username="menoleak")
        r = await client.get("/api/auth/me", headers=auth.auth_headers(tokens["access_token"]))
        assert r.status_code == 200
        assert "password_hash" not in r.json()["data"]

    @pytest.mark.asyncio
    async def test_me_no_token(self, client: AsyncClient) -> None:
        r = await client.get("/api/auth/me")
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_me_invalid_token(self, client: AsyncClient) -> None:
        r = await client.get("/api/auth/me", headers={"Authorization": "Bearer invalid.token.here"})
        assert r.status_code == 401


class TestRefresh:
    """POST /api/auth/refresh"""

    @pytest.mark.asyncio
    async def test_refresh_success(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login(email="refresh@test.com", username="refreshuser")
        r = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            headers=auth.auth_headers(tokens["access_token"]),
        )
        assert r.status_code == 200

        new_tokens = r.json()["data"]
        assert "access_token" in new_tokens
        assert "refresh_token" in new_tokens
        # refresh_token is always rotated
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

    @pytest.mark.asyncio
    async def test_refresh_then_me_works(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login(email="refme@test.com", username="refme")

        r = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            headers=auth.auth_headers(tokens["access_token"]),
        )
        assert r.status_code == 200
        new_tokens = r.json()["data"]

        r = await client.get("/api/auth/me", headers=auth.auth_headers(new_tokens["access_token"]))
        assert r.status_code == 200
        assert r.json()["data"]["email"] == "refme@test.com"

    @pytest.mark.asyncio
    async def test_refresh_no_token(self, client: AsyncClient) -> None:
        r = await client.post("/api/auth/refresh", json={"refresh_token": "nope"})
        assert r.status_code == 403


class TestLogout:
    """POST /api/auth/logout"""

    @pytest.mark.asyncio
    async def test_logout_success(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login(email="logout@test.com", username="logoutuser")
        r = await client.post("/api/auth/logout", headers=auth.auth_headers(tokens["access_token"]))
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_logout_invalidates_session(self, client: AsyncClient, auth: AuthActions) -> None:
        tokens = await auth.register_and_login(email="logoutinv@test.com", username="logoutinv")
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post("/api/auth/logout", headers=headers)
        assert r.status_code == 200

        r = await client.get("/api/auth/me", headers=headers)
        assert r.status_code == 401, "Session should be invalid after logout"

    @pytest.mark.asyncio
    async def test_logout_no_token(self, client: AsyncClient) -> None:
        r = await client.post("/api/auth/logout")
        assert r.status_code == 403


class TestFullAuthFlow:
    """Complete auth lifecycle in a single test."""

    @pytest.mark.asyncio
    async def test_register_login_me_refresh_logout(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        # 1. Register
        reg = await auth.register(email="flow@test.com", username="flowuser", password="Flow123!")
        assert reg["email"] == "flow@test.com"

        # 2. Login
        tokens = await auth.login(email="flow@test.com", password="Flow123!")
        headers = auth.auth_headers(tokens["access_token"])

        # 3. /me
        r = await client.get("/api/auth/me", headers=headers)
        assert r.status_code == 200
        me = r.json()["data"]
        assert me["email"] == "flow@test.com"
        assert "password_hash" not in me

        # 4. Refresh
        r = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            headers=headers,
        )
        assert r.status_code == 200
        new_tokens = r.json()["data"]
        new_headers = auth.auth_headers(new_tokens["access_token"])

        # 5. /me with new tokens
        r = await client.get("/api/auth/me", headers=new_headers)
        assert r.status_code == 200

        # 6. Logout
        r = await client.post("/api/auth/logout", headers=new_headers)
        assert r.status_code == 200

        # 7. /me after logout should fail
        r = await client.get("/api/auth/me", headers=new_headers)
        assert r.status_code == 401

    @pytest.mark.asyncio
    async def test_full_auth_flow_with_admin_assigned_roles(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        """Complete auth lifecycle with admin-assigned roles."""
        # 0. Setup: create admin and custom roles
        admin_tokens = await auth.register_and_login_admin(
            email="flowadmin@test.com", username="flowadmin"
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])
        r1 = await client.post("/api/roles/", json={"name": "flow_editor"}, headers=admin_headers)
        r2 = await client.post("/api/roles/", json={"name": "flow_viewer"}, headers=admin_headers)
        editor_id = r1.json()["data"]["id"]
        viewer_id = r2.json()["data"]["id"]

        # 1. Register a regular user
        reg = await auth.register(
            email="flowroles@test.com",
            username="flowroles",
            password="Flow123!",
        )
        assert reg["email"] == "flowroles@test.com"

        # 2. Admin assigns roles to the user
        login_tokens = await auth.login(email="flowroles@test.com", password="Flow123!")
        me_r = await client.get(
            "/api/auth/me", headers=auth.auth_headers(login_tokens["access_token"])
        )
        user_id = me_r.json()["data"]["id"]

        await client.post(
            f"/api/users/{user_id}/roles",
            json={"role_ids": [editor_id, viewer_id]},
            headers=admin_headers,
        )

        # 3. Re-login to get fresh tokens with roles in JWT
        tokens = await auth.login(email="flowroles@test.com", password="Flow123!")
        headers = auth.auth_headers(tokens["access_token"])

        # 4. /me — roles should be present
        r = await client.get("/api/auth/me", headers=headers)
        assert r.status_code == 200
        me = r.json()["data"]
        assert me["email"] == "flowroles@test.com"
        role_names = {role["name"] for role in me["roles"]}
        assert role_names >= {"flow_editor", "flow_viewer"}

        # 5. Refresh
        r = await client.post(
            "/api/auth/refresh",
            json={"refresh_token": tokens["refresh_token"]},
            headers=headers,
        )
        assert r.status_code == 200
        new_tokens = r.json()["data"]
        new_headers = auth.auth_headers(new_tokens["access_token"])

        # 6. /me after refresh — roles should still be present
        r = await client.get("/api/auth/me", headers=new_headers)
        assert r.status_code == 200
        refreshed_roles = {role["name"] for role in r.json()["data"]["roles"]}
        assert refreshed_roles >= {"flow_editor", "flow_viewer"}

        # 7. Logout
        r = await client.post("/api/auth/logout", headers=new_headers)
        assert r.status_code == 200

        # 8. /me after logout should fail
        r = await client.get("/api/auth/me", headers=new_headers)
        assert r.status_code == 401
