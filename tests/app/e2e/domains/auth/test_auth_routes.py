"""End-to-end tests for the auth endpoints (register, login, refresh, /me, logout)."""

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from tests.app.e2e.conftest import AuthActions, FakeEmailStrategy


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


# ────────────────────────────────────────────────────────
# Admin Register
# ────────────────────────────────────────────────────────


class TestAdminRegister:
    """POST /api/auth/admin/register"""

    @pytest.mark.asyncio
    async def test_admin_register_creates_user(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="aradmin1@test.com", username="aradmin1"
        )
        headers = auth.auth_headers(admin_tokens["access_token"])

        r = await client.post(
            "/api/auth/admin/register",
            json={"email": "aruser1@test.com", "name": "AR User 1"},
            headers=headers,
        )
        assert r.status_code == 201
        data = r.json()["data"]
        assert data["email"] == "aruser1@test.com"
        assert "id" in data
        assert "password_hash" not in data

    @pytest.mark.asyncio
    async def test_admin_register_user_can_login_with_generated_password(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        """The auto-generated password sent in the welcome email must work."""
        admin_tokens = await auth.register_and_login_admin(
            email="aradmin2@test.com", username="aradmin2"
        )
        headers = auth.auth_headers(admin_tokens["access_token"])

        r = await client.post(
            "/api/auth/admin/register",
            json={"email": "arlogin@test.com", "name": "AR Login"},
            headers=headers,
        )
        assert r.status_code == 201

        # Extract auto-generated password from the captured welcome email
        welcome = fake_email.last_welcome()
        assert welcome is not None
        assert welcome.to == "arlogin@test.com"
        otp = welcome.params.one_time_password

        # Login with the generated password
        tokens = await auth.login(email="arlogin@test.com", password=otp)
        assert "access_token" in tokens

    @pytest.mark.asyncio
    async def test_admin_register_sets_must_change_password(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="aradmin3@test.com", username="aradmin3"
        )
        headers = auth.auth_headers(admin_tokens["access_token"])

        r = await client.post(
            "/api/auth/admin/register",
            json={"email": "arflag@test.com"},
            headers=headers,
        )
        assert r.status_code == 201

        # Extract password and login
        otp = fake_email.last_welcome().params.one_time_password
        login_r = await auth.login_raw(email="arflag@test.com", password=otp)
        assert login_r.status_code == 200
        assert login_r.json()["data"]["must_change_password"] is True

    @pytest.mark.asyncio
    async def test_admin_register_sends_welcome_email(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="aradmin4@test.com", username="aradmin4"
        )
        headers = auth.auth_headers(admin_tokens["access_token"])

        await client.post(
            "/api/auth/admin/register",
            json={"email": "arwelcome@test.com"},
            headers=headers,
        )

        assert len([e for e in fake_email.sent if e.kind == "welcome"]) >= 1
        welcome = fake_email.last_welcome()
        assert welcome is not None
        assert welcome.to == "arwelcome@test.com"
        assert welcome.params.one_time_password  # non-empty
        assert "token=" in welcome.params.login_url

    @pytest.mark.asyncio
    async def test_admin_register_with_role_ids(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        """Admin can assign specific roles during registration."""
        admin_tokens = await auth.register_and_login_admin(
            email="aradmin5@test.com", username="aradmin5"
        )
        headers = auth.auth_headers(admin_tokens["access_token"])

        # Create a custom role
        role_r = await client.post(
            "/api/roles/", json={"name": "ar_custom_role"}, headers=headers
        )
        role_id = role_r.json()["data"]["id"]

        r = await client.post(
            "/api/auth/admin/register",
            json={"email": "arroles@test.com", "role_ids": [role_id]},
            headers=headers,
        )
        assert r.status_code == 201

        # Verify roles directly from the admin_register response
        data = r.json()["data"]
        role_names = {rl["name"] for rl in data["roles"]}
        assert "ar_custom_role" in role_names

    @pytest.mark.asyncio
    async def test_admin_register_duplicate_email_fails(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        admin_tokens = await auth.register_and_login_admin(
            email="aradmin6@test.com", username="aradmin6"
        )
        headers = auth.auth_headers(admin_tokens["access_token"])

        await client.post(
            "/api/auth/admin/register",
            json={"email": "ardup@test.com"},
            headers=headers,
        )

        r = await client.post(
            "/api/auth/admin/register",
            json={"email": "ardup@test.com"},
            headers=headers,
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_admin_register_requires_admin_permission(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        """Regular users must not be able to admin-register others."""
        tokens = await auth.register_and_login(
            email="arnonadmin@test.com", username="arnonadmin"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/auth/admin/register",
            json={"email": "shouldfail@test.com"},
            headers=headers,
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_admin_register_unauthenticated_fails(self, client: AsyncClient, auth: AuthActions) -> None:
        r = await client.post(
            "/api/auth/admin/register",
            json={"email": "unauth@test.com"},
        )
        assert r.status_code == 403


# ────────────────────────────────────────────────────────
# Change Password
# ────────────────────────────────────────────────────────


class TestChangePassword:
    """POST /api/auth/change-password"""

    @pytest.mark.asyncio
    async def test_change_password_success(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login(
            email="cpok@test.com", username="cpok", password="OldPass1!"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": "OldPass1!", "new_password": "NewPass1!"},
            headers=headers,
        )
        assert r.status_code == 200

        # Old password no longer works
        old_login = await auth.login_raw(email="cpok@test.com", password="OldPass1!")
        assert old_login.status_code == 401

        # New password works
        new_tokens = await auth.login(email="cpok@test.com", password="NewPass1!")
        assert "access_token" in new_tokens

    @pytest.mark.asyncio
    async def test_change_password_wrong_current(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login(
            email="cpwrong@test.com", username="cpwrong", password="Correct1!"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": "Wrong1!!!", "new_password": "NewPass1!"},
            headers=headers,
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_change_password_clears_must_change_flag(
        self, client: AsyncClient, auth: AuthActions, db_session: AsyncSession
    ) -> None:
        """After change-password, must_change_password flag is cleared."""
        # Register normally (with username so can_login() works), then
        # simulate admin-provisioned state by setting the flag via DB.
        old_pw = "OldFlag1!"
        await auth.register(
            email="cpflag@test.com", username="cpflag", password=old_pw
        )
        login_r = await auth.login_raw(email="cpflag@test.com", password=old_pw)
        user_id = login_r.json()["data"]["access_token"]  # just to confirm login works
        assert login_r.status_code == 200

        # Set must_change_password via DB
        await db_session.execute(
            text(
                "UPDATE users SET must_change_password = true WHERE email = :email"
            ),
            {"email": "cpflag@test.com"},
        )
        await db_session.flush()

        # Re-login — flag should be True
        login_r = await auth.login_raw(email="cpflag@test.com", password=old_pw)
        assert login_r.json()["data"]["must_change_password"] is True
        headers = auth.auth_headers(login_r.json()["data"]["access_token"])

        # Change password
        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": old_pw, "new_password": "Changed1!"},
            headers=headers,
        )
        assert r.status_code == 200

        # Re-login – flag should now be False
        login2 = await auth.login_raw(email="cpflag@test.com", password="Changed1!")
        assert login2.status_code == 200
        assert login2.json()["data"]["must_change_password"] is False

    @pytest.mark.asyncio
    async def test_change_password_unauthenticated(self, client: AsyncClient, auth: AuthActions) -> None:
        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": "x", "new_password": "y"},
        )
        assert r.status_code == 403

    @pytest.mark.asyncio
    async def test_change_password_weak_new_password(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login(
            email="cpweak@test.com", username="cpweak", password="Strong1!"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": "Strong1!", "new_password": "weak"},
            headers=headers,
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_change_password_preserves_session(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        """The current session should still work after changing password."""
        tokens = await auth.register_and_login(
            email="cpsess@test.com", username="cpsess", password="Before1!"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": "Before1!", "new_password": "After1!!"},
            headers=headers,
        )
        assert r.status_code == 200

        # Session still valid
        me_r = await client.get("/api/auth/me", headers=headers)
        assert me_r.status_code == 200


# ────────────────────────────────────────────────────────
# Forgot Password
# ────────────────────────────────────────────────────────


class TestForgotPassword:
    """POST /api/auth/forgot-password"""

    @pytest.mark.asyncio
    async def test_forgot_password_existing_email(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        await auth.register(email="fpexist@test.com", username="fpexist")

        r = await client.post(
            "/api/auth/forgot-password", json={"email": "fpexist@test.com"}
        )
        assert r.status_code == 200
        assert "reset link has been sent" in r.json()["data"]["message"].lower()

        reset_mail = fake_email.last_reset()
        assert reset_mail is not None
        assert reset_mail.to == "fpexist@test.com"
        assert "token=" in reset_mail.params.reset_url

    @pytest.mark.asyncio
    async def test_forgot_password_nonexistent_email_no_leak(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        """Non-existent emails should get the same 200 response (no info leak)."""
        r = await client.post(
            "/api/auth/forgot-password", json={"email": "ghost@nowhere.com"}
        )
        assert r.status_code == 200
        assert "reset link has been sent" in r.json()["data"]["message"].lower()

        # No email should have been dispatched
        assert fake_email.last_reset() is None

    @pytest.mark.asyncio
    async def test_forgot_password_missing_email_field(self, client: AsyncClient, auth: AuthActions) -> None:
        r = await client.post("/api/auth/forgot-password", json={})
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_forgot_password_invalid_email_format(self, client: AsyncClient, auth: AuthActions) -> None:
        r = await client.post("/api/auth/forgot-password", json={"email": "not-an-email"})
        assert r.status_code == 422


# ────────────────────────────────────────────────────────
# Reset Password
# ────────────────────────────────────────────────────────


class TestResetPassword:
    """POST /api/auth/reset-password"""

    @pytest.mark.asyncio
    async def test_reset_password_success(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        await auth.register(
            email="rpok@test.com", username="rpok", password="Original1!"
        )

        # Trigger forgot-password
        await client.post("/api/auth/forgot-password", json={"email": "rpok@test.com"})
        reset_mail = fake_email.last_reset()
        assert reset_mail is not None
        raw_token = FakeEmailStrategy.extract_token_from_url(reset_mail.params.reset_url)

        # Reset
        r = await client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "Reset1!!!"},
        )
        assert r.status_code == 200

        # Login with new password
        tokens = await auth.login(email="rpok@test.com", password="Reset1!!!")
        assert "access_token" in tokens

    @pytest.mark.asyncio
    async def test_reset_password_old_password_stops_working(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        await auth.register(
            email="rpold@test.com", username="rpold", password="OldPw1!!!"
        )

        await client.post("/api/auth/forgot-password", json={"email": "rpold@test.com"})
        raw_token = FakeEmailStrategy.extract_token_from_url(
            fake_email.last_reset().params.reset_url
        )

        await client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "NewPw1!!!"},
        )

        old_login = await auth.login_raw(email="rpold@test.com", password="OldPw1!!!")
        assert old_login.status_code == 401

    @pytest.mark.asyncio
    async def test_reset_password_invalid_token(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        r = await client.post(
            "/api/auth/reset-password",
            json={"token": "completely-invalid-token", "new_password": "Valid1!!!"},
        )
        assert r.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_token_reuse(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        """Using the same reset token twice should fail on the second attempt."""
        await auth.register(
            email="rpreuse@test.com", username="rpreuse", password="First1!!"
        )

        await client.post("/api/auth/forgot-password", json={"email": "rpreuse@test.com"})
        raw_token = FakeEmailStrategy.extract_token_from_url(
            fake_email.last_reset().params.reset_url
        )

        # First use — should succeed
        r1 = await client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "Second1!"},
        )
        assert r1.status_code == 200

        # Second use — must fail
        r2 = await client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "Third1!!"},
        )
        assert r2.status_code == 400

    @pytest.mark.asyncio
    async def test_reset_password_clears_must_change_flag(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        """Admin-registered user resets password via token → must_change_password cleared."""
        admin_tokens = await auth.register_and_login_admin(
            email="rpadmin@test.com", username="rpadmin"
        )
        admin_headers = auth.auth_headers(admin_tokens["access_token"])

        await client.post(
            "/api/auth/admin/register",
            json={"email": "rpflag@test.com"},
            headers=admin_headers,
        )
        otp = fake_email.last_welcome().params.one_time_password

        # Confirm must_change_password is True
        login_r = await auth.login_raw(email="rpflag@test.com", password=otp)
        assert login_r.json()["data"]["must_change_password"] is True

        # Trigger forgot-password and reset
        await client.post("/api/auth/forgot-password", json={"email": "rpflag@test.com"})
        raw_token = FakeEmailStrategy.extract_token_from_url(
            fake_email.last_reset().params.reset_url
        )

        r = await client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "ResetFlag1!"},
        )
        assert r.status_code == 200

        # Re-login — flag should be cleared
        login2 = await auth.login_raw(email="rpflag@test.com", password="ResetFlag1!")
        assert login2.status_code == 200
        assert login2.json()["data"]["must_change_password"] is False

    @pytest.mark.asyncio
    async def test_reset_password_weak_password(
        self, client: AsyncClient, auth: AuthActions, fake_email: FakeEmailStrategy
    ) -> None:
        await auth.register(
            email="rpweak@test.com", username="rpweak", password="Strong1!"
        )

        await client.post("/api/auth/forgot-password", json={"email": "rpweak@test.com"})
        raw_token = FakeEmailStrategy.extract_token_from_url(
            fake_email.last_reset().params.reset_url
        )

        r = await client.post(
            "/api/auth/reset-password",
            json={"token": raw_token, "new_password": "weak"},
        )
        assert r.status_code == 422


# ────────────────────────────────────────────────────────
# First Access Full Lifecycle
# ────────────────────────────────────────────────────────


class TestFirstAccessFlow:
    """Complete first-access lifecycle: admin creates user → user logs in →
    must_change_password is True → user changes password → flag cleared."""

    @pytest.mark.asyncio
    async def test_first_access_full_lifecycle(
        self, client: AsyncClient, auth: AuthActions, db_session: AsyncSession
    ) -> None:
        """Simulates: admin provisions a user → user logs in →
        must_change_password is True → user changes password → flag cleared
        → user can access protected resources."""
        initial_pw = "Initial1!"

        # 1. Register user normally (username required by can_login()),
        #    then set must_change_password=True to simulate admin provisioning
        await auth.register(
            email="fanew@test.com", username="fanew", password=initial_pw
        )
        await db_session.execute(
            text(
                "UPDATE users SET must_change_password = true WHERE email = :email"
            ),
            {"email": "fanew@test.com"},
        )
        await db_session.flush()

        # 2. User logs in — must_change_password should be True
        login_r = await auth.login_raw(email="fanew@test.com", password=initial_pw)
        assert login_r.status_code == 200
        login_data = login_r.json()["data"]
        assert login_data["must_change_password"] is True
        user_headers = auth.auth_headers(login_data["access_token"])

        # 3. User changes password
        r = await client.post(
            "/api/auth/change-password",
            json={"current_password": initial_pw, "new_password": "MyNew1!!!"},
            headers=user_headers,
        )
        assert r.status_code == 200

        # 4. Re-login — flag should be cleared
        login2 = await auth.login_raw(email="fanew@test.com", password="MyNew1!!!")
        assert login2.status_code == 200
        assert login2.json()["data"]["must_change_password"] is False

        # 5. Verify the user can access protected resources
        r = await client.get(
            "/api/auth/me",
            headers=auth.auth_headers(login2.json()["data"]["access_token"]),
        )
        assert r.status_code == 200
        assert r.json()["data"]["email"] == "fanew@test.com"

