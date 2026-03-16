"""Quick integration test for the auth module against the running server."""

import sys
from typing import Any

import httpx

BASE = "http://127.0.0.1:8000/api"
TIMEOUT = 15.0

EMAIL = "authflow@test.com"
USERNAME = "authflow"
PASSWORD = "Secure123!"


def log(label: str, status: int, body: dict[Any, Any] | str) -> None:
    ok = "PASS" if isinstance(body, dict) and body.get("data") is not None else "FAIL"
    if isinstance(body, dict) and body.get("type"):
        ok = f"ERR {body.get('status')}"
    print(f"[{ok}] {label}  (HTTP {status})")
    if ok.startswith("ERR") or ok == "FAIL":
        detail = body.get("detail", "") if isinstance(body, dict) else body
        print(f"       detail: {detail}")


def main() -> None:
    client = httpx.Client(timeout=TIMEOUT)
    errors: list[str] = []

    # ── 1. REGISTER ──────────────────────────────────────────────
    print("\n=== 1. REGISTER ===")
    r = client.post(
        f"{BASE}/auth/register",
        json={
            "email": EMAIL,
            "username": USERNAME,
            "password": PASSWORD,
        },
    )
    body = r.json()
    log("POST /auth/register", r.status_code, body)

    if r.status_code == 409:
        print("       (user already exists, continuing with login)")
    elif r.status_code == 201:
        reg_data = body["data"]
        assert "access_token" in reg_data, "Missing access_token in register response"
        assert "refresh_token" in reg_data, "Missing refresh_token in register response"
        assert "password_hash" not in reg_data, "password_hash leaked in register response!"
        print(f"       user_id: {reg_data['id']}")
    else:
        errors.append(f"Register failed: {r.status_code}")

    # ── 2. LOGIN ─────────────────────────────────────────────────
    print("\n=== 2. LOGIN ===")
    r = client.post(
        f"{BASE}/auth/login",
        json={
            "email": EMAIL,
            "password": PASSWORD,
        },
    )
    body = r.json()
    log("POST /auth/login", r.status_code, body)

    if r.status_code != 200:
        errors.append(f"Login failed: {r.status_code} - {body}")
        print("\n❌ Cannot continue without login. Errors:", errors)
        sys.exit(1)

    access_token = body["data"]["access_token"]
    refresh_token = body["data"]["refresh_token"]
    headers = {"Authorization": f"Bearer {access_token}"}
    print(f"       access_token: {access_token[:50]}...")
    print(f"       refresh_token: {refresh_token[:50]}...")

    # ── 3. LOGIN with wrong password ─────────────────────────────
    print("\n=== 3. LOGIN (wrong password) ===")
    r = client.post(
        f"{BASE}/auth/login",
        json={
            "email": EMAIL,
            "password": "WrongPass123!",
        },
    )
    body = r.json()
    log("POST /auth/login (bad pw)", r.status_code, body)
    if r.status_code != 401:
        errors.append(f"Bad password should return 401, got {r.status_code}")

    # ── 4. /ME ───────────────────────────────────────────────────
    print("\n=== 4. GET /auth/me ===")
    r = client.get(f"{BASE}/auth/me", headers=headers)
    body = r.json()
    log("GET /auth/me", r.status_code, body)

    if r.status_code == 200:
        me_data = body["data"]
        if "password_hash" in me_data:
            errors.append("password_hash is leaked in /me response!")
            print("       ⚠️ password_hash LEAKED!")
        else:
            print("       ✓ password_hash not in response")
        print(f"       email: {me_data.get('email')}")
        print(f"       roles: {me_data.get('roles')}")
    else:
        errors.append(f"/me failed: {r.status_code}")

    # ── 5. /ME without token ─────────────────────────────────────
    print("\n=== 5. GET /auth/me (no token) ===")
    r = client.get(f"{BASE}/auth/me")
    body = r.json()
    log("GET /auth/me (no token)", r.status_code, body)
    if r.status_code != 401 and r.status_code != 403:
        errors.append(f"/me without token should return 401/403, got {r.status_code}")
    else:
        print("       ✓ Correctly rejected unauthenticated request")

    # ── 6. REFRESH ───────────────────────────────────────────────
    print("\n=== 6. POST /auth/refresh ===")
    r = client.post(
        f"{BASE}/auth/refresh",
        json={"refresh_token": refresh_token},
        headers=headers,
    )
    body = r.json()
    log("POST /auth/refresh", r.status_code, body)

    if r.status_code == 200:
        new_access = body["data"]["access_token"]
        new_refresh = body["data"]["refresh_token"]
        print(f"       new access_token: {new_access[:50]}...")
        print(f"       new refresh_token: {new_refresh[:50]}...")
        # Use new tokens from now on
        access_token = new_access
        refresh_token = new_refresh
        headers = {"Authorization": f"Bearer {access_token}"}
    else:
        errors.append(f"Refresh failed: {r.status_code}")

    # ── 7. /ME with refreshed token ──────────────────────────────
    print("\n=== 7. GET /auth/me (refreshed token) ===")
    r = client.get(f"{BASE}/auth/me", headers=headers)
    body = r.json()
    log("GET /auth/me (refreshed)", r.status_code, body)
    if r.status_code != 200:
        errors.append(f"/me with refreshed token failed: {r.status_code}")

    # ── 8. ROLES CRUD (auth required) ────────────────────────────
    print("\n=== 8. ROLES CRUD ===")
    # Create role
    r = client.post(
        f"{BASE}/roles/",
        json={"name": "test_admin", "description": "Test admin role"},
        headers=headers,
    )
    body = r.json()
    log("POST /roles/", r.status_code, body)
    role_id = None
    if r.status_code == 201:
        role_id = body["data"]["id"]
        print(f"       role_id: {role_id}")
    elif r.status_code == 409:
        print("       (role already exists)")

    # Get roles
    r = client.get(f"{BASE}/roles/", headers=headers)
    body = r.json()
    log("GET /roles/", r.status_code, body)
    if r.status_code == 200 and role_id is None:
        roles = body["data"]
        for ro in roles:
            if ro.get("name") == "test_admin":
                role_id = ro["id"]
                break

    # Roles without auth
    r = client.get(f"{BASE}/roles/")
    body = r.json()
    log("GET /roles/ (no auth)", r.status_code, body)
    if r.status_code != 401 and r.status_code != 403:
        errors.append(f"Roles without auth should return 401/403, got {r.status_code}")
    else:
        print("       ✓ Correctly rejected unauthenticated request")

    # ── 9. PERMISSIONS CRUD (auth required) ──────────────────────
    print("\n=== 9. PERMISSIONS CRUD ===")
    r = client.post(
        f"{BASE}/permissions/",
        json={"name": "users:read", "description": "Read users"},
        headers=headers,
    )
    body = r.json()
    log("POST /permissions/", r.status_code, body)
    perm_id = None
    if r.status_code == 201:
        perm_id = body["data"]["id"]
        print(f"       perm_id: {perm_id}")
    elif r.status_code == 409:
        print("       (permission already exists)")

    # Get permissions
    r = client.get(f"{BASE}/permissions/", headers=headers)
    body = r.json()
    log("GET /permissions/", r.status_code, body)
    if r.status_code == 200 and perm_id is None:
        perms = body["data"]
        for p in perms:
            if p.get("name") == "users:read":
                perm_id = p["id"]
                break

    # Permissions without auth
    r = client.get(f"{BASE}/permissions/")
    body = r.json()
    log("GET /permissions/ (no auth)", r.status_code, body)
    if r.status_code != 401 and r.status_code != 403:
        errors.append(f"Permissions without auth should return 401/403, got {r.status_code}")
    else:
        print("       ✓ Correctly rejected unauthenticated request")

    # ── 10. USERS (auth required) ────────────────────────────────
    print("\n=== 10. USERS ===")
    r = client.get(f"{BASE}/users/", headers=headers)
    body = r.json()
    log("GET /users/", r.status_code, body)
    if r.status_code == 200:
        users = body["data"]
        for u in users:
            if "password_hash" in u:
                errors.append("password_hash leaked in GET /users/!")
                print("       ⚠️ password_hash LEAKED in user list!")
                break
        else:
            print("       ✓ No password_hash in user list")

    r = client.get(f"{BASE}/users/")
    body = r.json()
    log("GET /users/ (no auth)", r.status_code, body)
    if r.status_code != 401 and r.status_code != 403:
        errors.append(f"Users without auth should return 401/403, got {r.status_code}")
    else:
        print("       ✓ Correctly rejected unauthenticated request")

    # ── 11. LOGOUT ───────────────────────────────────────────────
    print("\n=== 11. LOGOUT ===")
    r = client.post(f"{BASE}/auth/logout", headers=headers)
    body = r.json()
    log("POST /auth/logout", r.status_code, body)
    if r.status_code != 200:
        errors.append(f"Logout failed: {r.status_code}")

    # ── 12. /ME after logout (should fail) ────────────────────────
    print("\n=== 12. GET /auth/me (after logout) ===")
    r = client.get(f"{BASE}/auth/me", headers=headers)
    body = r.json()
    log("GET /auth/me (after logout)", r.status_code, body)
    if r.status_code == 200:
        errors.append("/me should fail after logout!")
    else:
        print("       ✓ Correctly rejected after logout")

    # ── SUMMARY ──────────────────────────────────────────────────
    print("\n" + "=" * 50)
    if errors:
        print(f"❌ {len(errors)} ISSUE(S) FOUND:")
        for i, e in enumerate(errors, 1):
            print(f"   {i}. {e}")
    else:
        print("✅ ALL TESTS PASSED")
    print("=" * 50)

    client.close()
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
