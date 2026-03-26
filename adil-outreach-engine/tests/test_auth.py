import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/outreach/campaigns")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-API-Key header"


@pytest.mark.asyncio
async def test_invalid_api_key_returns_403(client: AsyncClient):
    response = await client.get(
        "/api/v1/outreach/campaigns",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key"


@pytest.mark.asyncio
async def test_valid_api_key_passes(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/outreach/campaigns", headers=auth_headers)
    assert response.status_code == 200
