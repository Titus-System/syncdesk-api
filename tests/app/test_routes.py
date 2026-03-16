from typing import Any

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_root(client: AsyncClient) -> None:
    """Test that the root endpoint returns 200 OK and valid JSON."""
    response = await client.get("/")
    assert response.status_code == 200

    response_json = response.json()
    data: dict[Any, Any] = response_json.get("data")
    meta: dict[Any, Any] = response_json.get("meta")
    assert data.get("status") == "ok"
    assert meta.get("request_id")

    response = await client.post("/")
    print(f"response: {response.json()}")
    assert response.status_code == 405


@pytest.mark.asyncio
async def test_metrics_routes(client: AsyncClient) -> None:
    response = await client.get("/metrics")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_api_check(client: AsyncClient) -> None:
    response = await client.get("/api")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_docs(client: AsyncClient) -> None:
    response = await client.get("/docs")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient) -> None:
    response = await client.get("/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_ping(client: AsyncClient) -> None:
    response = await client.get("/ping")
    assert response.status_code == 200

    response_json = response.json()
    data: dict[object, object] = response_json.get("data")
    assert data["message"] == "pong"
