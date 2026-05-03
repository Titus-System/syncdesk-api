"""End-to-end tests for the /api/companies endpoints (CRUD + relationships)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.app.e2e.conftest import AuthActions


def _tax_id() -> str:
    return uuid4().hex[:14]


def _legal_name(prefix: str = "Acme") -> str:
    return f"{prefix} {uuid4().hex[:8]} LTDA"


async def _create_company(
    client: AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    payload = {
        "legal_name": _legal_name(),
        "trade_name": "Acme",
        "tax_id": _tax_id(),
    }
    payload.update(overrides)
    r = await client.post("/api/companies/", json=payload, headers=headers)
    assert r.status_code == 201, f"Create company failed: {r.text}"
    return r.json()["data"]


class TestCompaniesCRUD:
    """Tests for /api/companies/ CRUD endpoints."""

    # ── Create ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ccreate@test.com", username="ccreate"
        )
        headers = auth.auth_headers(tokens["access_token"])

        legal_name = _legal_name()
        tax_id = _tax_id()
        r = await client.post(
            "/api/companies/",
            json={
                "legal_name": legal_name,
                "trade_name": "Acme",
                "tax_id": tax_id,
            },
            headers=headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        assert data["id"] is not None
        assert data["legal_name"] == legal_name
        assert data["tax_id"] == tax_id
        assert data["trade_name"] == "Acme"
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_company_normalizes_tax_id(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cnorm@test.com", username="cnorm"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/companies/",
            json={
                "legal_name": _legal_name(),
                "trade_name": "Acme",
                "tax_id": "12.345.678/0001-90",
            },
            headers=headers,
        )
        assert r.status_code == 201
        assert r.json()["data"]["tax_id"] == "12345678000190"

    @pytest.mark.asyncio
    async def test_create_company_duplicate_tax_id(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cdup@test.com", username="cdup"
        )
        headers = auth.auth_headers(tokens["access_token"])

        tax_id = _tax_id()
        await _create_company(client, headers, tax_id=tax_id)

        r = await client.post(
            "/api/companies/",
            json={
                "legal_name": _legal_name("Other"),
                "trade_name": "Other",
                "tax_id": tax_id,
            },
            headers=headers,
        )
        assert r.status_code == 409

    @pytest.mark.asyncio
    async def test_create_company_invalid_payload(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cinv@test.com", username="cinv"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/companies/",
            json={"legal_name": "Ab", "trade_name": "A", "tax_id": "123"},
            headers=headers,
        )
        assert r.status_code == 422

    # ── Read ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_companies(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="clist@test.com", username="clist"
        )
        headers = auth.auth_headers(tokens["access_token"])

        await _create_company(client, headers)
        await _create_company(client, headers)

        r = await client.get("/api/companies/", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 2
        assert isinstance(data["items"], list)
        assert data["page"] == 1

    @pytest.mark.asyncio
    async def test_list_companies_pagination(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cpag@test.com", username="cpag"
        )
        headers = auth.auth_headers(tokens["access_token"])

        for _ in range(3):
            await _create_company(client, headers)

        r = await client.get(
            "/api/companies/", params={"page": 1, "limit": 2}, headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["limit"] == 2
        assert len(data["items"]) <= 2

    @pytest.mark.asyncio
    async def test_get_company_by_id(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cget@test.com", username="cget"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_company(client, headers)

        r = await client.get(f"/api/companies/{created['id']}", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_company_not_found(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cnf@test.com", username="cnf"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.get(
            "/api/companies/00000000-0000-0000-0000-000000000000", headers=headers
        )
        assert r.status_code == 404

    # ── Update (PATCH) ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_patch_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cpatch@test.com", username="cpatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_company(client, headers)

        r = await client.patch(
            f"/api/companies/{created['id']}",
            json={"trade_name": "Renamed Trade"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["trade_name"] == "Renamed Trade"
        assert data["legal_name"] == created["legal_name"]

    @pytest.mark.asyncio
    async def test_patch_company_empty_payload_rejected(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cpatchemp@test.com", username="cpatchemp"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_company(client, headers)

        r = await client.patch(
            f"/api/companies/{created['id']}", json={}, headers=headers
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_company_not_found(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cpatchnf@test.com", username="cpatchnf"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.patch(
            "/api/companies/00000000-0000-0000-0000-000000000000",
            json={"trade_name": "Acme"},
            headers=headers,
        )
        assert r.status_code == 404

    # ── Replace (PUT) ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_put_company_overwrites_all_fields(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cput@test.com", username="cput"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_company(client, headers)
        new_legal = _legal_name("Replaced")
        new_tax = _tax_id()

        r = await client.put(
            f"/api/companies/{created['id']}",
            json={
                "legal_name": new_legal,
                "trade_name": "Replaced",
                "tax_id": new_tax,
            },
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["legal_name"] == new_legal
        assert data["tax_id"] == new_tax

    @pytest.mark.asyncio
    async def test_put_company_duplicate_tax_id(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cputdup@test.com", username="cputdup"
        )
        headers = auth.auth_headers(tokens["access_token"])

        existing = await _create_company(client, headers)
        target = await _create_company(client, headers)

        r = await client.put(
            f"/api/companies/{target['id']}",
            json={
                "legal_name": _legal_name(),
                "trade_name": "Acme",
                "tax_id": existing["tax_id"],
            },
            headers=headers,
        )
        assert r.status_code == 409

    # ── Delete ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_soft_delete_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cdel@test.com", username="cdel"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_company(client, headers)

        r = await client.delete(f"/api/companies/{created['id']}", headers=headers)
        assert r.status_code == 200

        # Após soft delete, GET retorna 404
        get_r = await client.get(
            f"/api/companies/{created['id']}", headers=headers
        )
        assert get_r.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_delete_company_idempotent_returns_404(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cdelidem@test.com", username="cdelidem"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_company(client, headers)
        await client.delete(f"/api/companies/{created['id']}", headers=headers)

        r = await client.delete(f"/api/companies/{created['id']}", headers=headers)
        assert r.status_code == 404

    # ── Auth guard ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_companies_require_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/companies/")
        assert r.status_code == 403

        r = await client.post(
            "/api/companies/",
            json={
                "legal_name": _legal_name(),
                "trade_name": "Acme",
                "tax_id": _tax_id(),
            },
        )
        assert r.status_code == 403


class TestCompanyProducts:
    """Tests for /api/companies/{id}/products endpoints."""

    @pytest.mark.asyncio
    async def test_add_products_to_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cprod@test.com", username="cprod"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)
        product = await client.post(
            "/api/products/",
            json={"name": f"P {uuid4().hex[:6]}", "description": "Initial desc"},
            headers=headers,
        )
        assert product.status_code == 201
        product_id = product.json()["data"]["id"]

        r = await client.post(
            f"/api/companies/{company['id']}/products",
            json={"product_ids": [product_id]},
            headers=headers,
        )
        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_add_products_to_unknown_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cproduc@test.com", username="cproduc"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/companies/00000000-0000-0000-0000-000000000000/products",
            json={"product_ids": [1]},
            headers=headers,
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_add_unknown_products_returns_404(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cprodunk@test.com", username="cprodunk"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)

        r = await client.post(
            f"/api/companies/{company['id']}/products",
            json={"product_ids": [9_999_999]},
            headers=headers,
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_single_product_from_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cprodrm@test.com", username="cprodrm"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)
        product = (
            await client.post(
                "/api/products/",
                json={"name": f"P {uuid4().hex[:6]}", "description": "Initial desc"},
                headers=headers,
            )
        ).json()["data"]
        await client.post(
            f"/api/companies/{company['id']}/products",
            json={"product_ids": [product["id"]]},
            headers=headers,
        )

        r = await client.delete(
            f"/api/companies/{company['id']}/products/{product['id']}",
            headers=headers,
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_remove_products_batch(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cprodbatch@test.com", username="cprodbatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)
        product_ids: list[int] = []
        for _ in range(2):
            res = await client.post(
                "/api/products/",
                json={"name": f"P {uuid4().hex[:6]}", "description": "Initial desc"},
                headers=headers,
            )
            product_ids.append(res.json()["data"]["id"])

        await client.post(
            f"/api/companies/{company['id']}/products",
            json={"product_ids": product_ids},
            headers=headers,
        )

        r = await client.request(
            "DELETE",
            f"/api/companies/{company['id']}/products",
            json={"product_ids": product_ids},
            headers=headers,
        )
        assert r.status_code == 200


class TestCompanyUsers:
    """Tests for /api/companies/{id}/users endpoints."""

    @pytest.mark.asyncio
    async def test_assign_users_to_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="cuadm@test.com", username="cuadm"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)
        new_user = (
            await client.post(
                "/api/users/",
                json={
                    "email": f"member_{uuid4().hex[:6]}@test.com",
                    "password_hash": "hash",
                    "username": f"member_{uuid4().hex[:6]}",
                },
                headers=headers,
            )
        ).json()["data"]

        r = await client.post(
            f"/api/companies/{company['id']}/users",
            json={"user_ids": [new_user["id"]]},
            headers=headers,
        )
        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_remove_user_from_company(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="curm@test.com", username="curm"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)
        member = (
            await client.post(
                "/api/users/",
                json={
                    "email": f"rm_{uuid4().hex[:6]}@test.com",
                    "password_hash": "hash",
                    "username": f"rm_{uuid4().hex[:6]}",
                },
                headers=headers,
            )
        ).json()["data"]
        await client.post(
            f"/api/companies/{company['id']}/users",
            json={"user_ids": [member["id"]]},
            headers=headers,
        )

        r = await client.delete(
            f"/api/companies/{company['id']}/users/{member['id']}", headers=headers
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_remove_users_batch(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="curmb@test.com", username="curmb"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)
        user_ids: list[str] = []
        for _ in range(2):
            res = await client.post(
                "/api/users/",
                json={
                    "email": f"b_{uuid4().hex[:6]}@test.com",
                    "password_hash": "hash",
                    "username": f"b_{uuid4().hex[:6]}",
                },
                headers=headers,
            )
            user_ids.append(res.json()["data"]["id"])

        await client.post(
            f"/api/companies/{company['id']}/users",
            json={"user_ids": user_ids},
            headers=headers,
        )

        r = await client.request(
            "DELETE",
            f"/api/companies/{company['id']}/users",
            json={"user_ids": user_ids},
            headers=headers,
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_list_company_users_excludes_password_hash(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="culist@test.com", username="culist"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)
        member = (
            await client.post(
                "/api/users/",
                json={
                    "email": f"l_{uuid4().hex[:6]}@test.com",
                    "password_hash": "hash",
                    "username": f"l_{uuid4().hex[:6]}",
                },
                headers=headers,
            )
        ).json()["data"]
        await client.post(
            f"/api/companies/{company['id']}/users",
            json={"user_ids": [member["id"]]},
            headers=headers,
        )

        r = await client.get(
            f"/api/companies/{company['id']}/users", headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert len(data["items"]) == 1
        for user in data["items"]:
            assert "password_hash" not in user
