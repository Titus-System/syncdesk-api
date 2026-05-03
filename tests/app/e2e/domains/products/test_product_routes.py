"""End-to-end tests for the /api/products endpoints (CRUD + relationships)."""

from uuid import uuid4

import pytest
from httpx import AsyncClient

from tests.app.e2e.conftest import AuthActions


def _product_name(prefix: str = "Product") -> str:
    return f"{prefix} {uuid4().hex[:8]}"


def _tax_id() -> str:
    return uuid4().hex[:14]


def _legal_name(prefix: str = "Acme") -> str:
    return f"{prefix} {uuid4().hex[:8]} LTDA"


async def _create_product(
    client: AsyncClient, headers: dict[str, str], **overrides: object
) -> dict[str, object]:
    payload = {"name": _product_name(), "description": "Initial description"}
    payload.update(overrides)
    r = await client.post("/api/products/", json=payload, headers=headers)
    assert r.status_code == 201, f"Create product failed: {r.text}"
    return r.json()["data"]


async def _create_company(
    client: AsyncClient, headers: dict[str, str]
) -> dict[str, object]:
    r = await client.post(
        "/api/companies/",
        json={
            "legal_name": _legal_name(),
            "trade_name": "Acme",
            "tax_id": _tax_id(),
        },
        headers=headers,
    )
    assert r.status_code == 201, f"Create company failed: {r.text}"
    return r.json()["data"]


class TestProductsCRUD:
    """Tests for /api/products/ CRUD endpoints."""

    # ── Create ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_create_product(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pcreate@test.com", username="pcreate"
        )
        headers = auth.auth_headers(tokens["access_token"])

        name = _product_name()
        r = await client.post(
            "/api/products/",
            json={"name": name, "description": "A great product"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        data = r.json()["data"]
        assert data["id"] is not None
        assert data["name"] == name
        assert data["description"] == "A great product"
        assert "created_at" in data

    @pytest.mark.asyncio
    async def test_create_product_invalid_payload(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pinv@test.com", username="pinv"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.post(
            "/api/products/",
            json={"name": "ab", "description": "x"},
            headers=headers,
        )
        assert r.status_code == 422

    # ── Read ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_list_products(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="plist@test.com", username="plist"
        )
        headers = auth.auth_headers(tokens["access_token"])

        await _create_product(client, headers)
        await _create_product(client, headers)

        r = await client.get("/api/products/", headers=headers)
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] >= 2
        assert isinstance(data["items"], list)

    @pytest.mark.asyncio
    async def test_list_products_pagination(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ppag@test.com", username="ppag"
        )
        headers = auth.auth_headers(tokens["access_token"])

        for _ in range(3):
            await _create_product(client, headers)

        r = await client.get(
            "/api/products/", params={"page": 1, "limit": 2}, headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["limit"] == 2
        assert len(data["items"]) <= 2

    @pytest.mark.asyncio
    async def test_get_product_by_id(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pget@test.com", username="pget"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_product(client, headers)

        r = await client.get(f"/api/products/{created['id']}", headers=headers)
        assert r.status_code == 200
        assert r.json()["data"]["id"] == created["id"]

    @pytest.mark.asyncio
    async def test_get_product_not_found(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pnf@test.com", username="pnf"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.get("/api/products/9999999", headers=headers)
        assert r.status_code == 404

    # ── Update (PATCH) ──────────────────────────────────

    @pytest.mark.asyncio
    async def test_patch_product(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ppatch@test.com", username="ppatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_product(client, headers)

        r = await client.patch(
            f"/api/products/{created['id']}",
            json={"description": "Refreshed description"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["description"] == "Refreshed description"
        assert data["name"] == created["name"]

    @pytest.mark.asyncio
    async def test_patch_product_empty_payload_rejected(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ppatchemp@test.com", username="ppatchemp"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_product(client, headers)

        r = await client.patch(
            f"/api/products/{created['id']}", json={}, headers=headers
        )
        assert r.status_code == 422

    @pytest.mark.asyncio
    async def test_patch_product_not_found(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="ppatchnf@test.com", username="ppatchnf"
        )
        headers = auth.auth_headers(tokens["access_token"])

        r = await client.patch(
            "/api/products/9999999",
            json={"description": "Anything works"},
            headers=headers,
        )
        assert r.status_code == 404

    # ── Replace (PUT) ───────────────────────────────────

    @pytest.mark.asyncio
    async def test_put_product_overwrites_all_fields(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pput@test.com", username="pput"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_product(client, headers)
        new_name = _product_name("Replaced")

        r = await client.put(
            f"/api/products/{created['id']}",
            json={"name": new_name, "description": "Brand new description"},
            headers=headers,
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["name"] == new_name
        assert data["description"] == "Brand new description"

    # ── Delete ──────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_soft_delete_product(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pdel@test.com", username="pdel"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_product(client, headers)

        r = await client.delete(f"/api/products/{created['id']}", headers=headers)
        assert r.status_code == 200

        get_r = await client.get(f"/api/products/{created['id']}", headers=headers)
        assert get_r.status_code == 404

    @pytest.mark.asyncio
    async def test_soft_delete_product_idempotent_returns_404(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pdelidem@test.com", username="pdelidem"
        )
        headers = auth.auth_headers(tokens["access_token"])

        created = await _create_product(client, headers)
        await client.delete(f"/api/products/{created['id']}", headers=headers)

        r = await client.delete(f"/api/products/{created['id']}", headers=headers)
        assert r.status_code == 404

    # ── Auth guard ──────────────────────────────────────

    @pytest.mark.asyncio
    async def test_products_require_auth(self, client: AsyncClient) -> None:
        r = await client.get("/api/products/")
        assert r.status_code == 403

        r = await client.post(
            "/api/products/",
            json={"name": _product_name(), "description": "Some desc"},
        )
        assert r.status_code == 403


class TestProductCompanies:
    """Tests for /api/products/{id}/companies endpoints."""

    @pytest.mark.asyncio
    async def test_add_companies_to_product(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pcomp@test.com", username="pcomp"
        )
        headers = auth.auth_headers(tokens["access_token"])

        product = await _create_product(client, headers)
        company = await _create_company(client, headers)

        r = await client.post(
            f"/api/products/{product['id']}/companies",
            json={"company_ids": [company["id"]]},
            headers=headers,
        )
        assert r.status_code == 201

    @pytest.mark.asyncio
    async def test_add_companies_to_unknown_product(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pcompunkp@test.com", username="pcompunkp"
        )
        headers = auth.auth_headers(tokens["access_token"])

        company = await _create_company(client, headers)

        r = await client.post(
            "/api/products/9999999/companies",
            json={"company_ids": [company["id"]]},
            headers=headers,
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_add_unknown_companies_returns_404(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pcompunkc@test.com", username="pcompunkc"
        )
        headers = auth.auth_headers(tokens["access_token"])

        product = await _create_product(client, headers)

        r = await client.post(
            f"/api/products/{product['id']}/companies",
            json={"company_ids": ["00000000-0000-0000-0000-000000000000"]},
            headers=headers,
        )
        assert r.status_code == 404

    @pytest.mark.asyncio
    async def test_remove_single_company_from_product(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pcomprm@test.com", username="pcomprm"
        )
        headers = auth.auth_headers(tokens["access_token"])

        product = await _create_product(client, headers)
        company = await _create_company(client, headers)
        await client.post(
            f"/api/products/{product['id']}/companies",
            json={"company_ids": [company["id"]]},
            headers=headers,
        )

        r = await client.delete(
            f"/api/products/{product['id']}/companies/{company['id']}",
            headers=headers,
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_remove_companies_batch(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pcompbatch@test.com", username="pcompbatch"
        )
        headers = auth.auth_headers(tokens["access_token"])

        product = await _create_product(client, headers)
        company_ids: list[str] = []
        for _ in range(2):
            company = await _create_company(client, headers)
            company_ids.append(company["id"])

        await client.post(
            f"/api/products/{product['id']}/companies",
            json={"company_ids": company_ids},
            headers=headers,
        )

        r = await client.request(
            "DELETE",
            f"/api/products/{product['id']}/companies",
            json={"company_ids": company_ids},
            headers=headers,
        )
        assert r.status_code == 200

    @pytest.mark.asyncio
    async def test_list_product_companies(
        self, client: AsyncClient, auth: AuthActions
    ) -> None:
        tokens = await auth.register_and_login_admin(
            email="pcomplist@test.com", username="pcomplist"
        )
        headers = auth.auth_headers(tokens["access_token"])

        product = await _create_product(client, headers)
        company = await _create_company(client, headers)
        await client.post(
            f"/api/products/{product['id']}/companies",
            json={"company_ids": [company["id"]]},
            headers=headers,
        )

        r = await client.get(
            f"/api/products/{product['id']}/companies", headers=headers
        )
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["id"] == company["id"]
