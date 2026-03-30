import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_campaign(client: AsyncClient, auth_headers: dict):
    payload = {
        "name": "Test Campaign",
        "slug": "test-campaign",
        "goal": "signup",
        "auto_send": False,
        "sender_name": "Test Sender",
        "sender_email": "test@example.com",
        "reply_to": "reply@example.com",
    }
    response = await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Campaign"
    assert data["slug"] == "test-campaign"
    assert data["goal"] == "signup"
    assert data["status"] == "draft"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_campaign_duplicate_slug(client: AsyncClient, auth_headers: dict):
    payload = {
        "name": "Campaign A",
        "slug": "duplicate-slug",
        "goal": "signup",
    }
    await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    response = await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_campaigns(client: AsyncClient, auth_headers: dict):
    # Create two campaigns
    for i in range(2):
        await client.post(
            "/api/v1/outreach/campaigns",
            json={"name": f"List Campaign {i}", "slug": f"list-camp-{i}", "goal": "signup"},
            headers=auth_headers,
        )
    response = await client.get("/api/v1/outreach/campaigns", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_campaigns_filter_status(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Filter Campaign", "slug": "filter-camp", "goal": "signup"},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/outreach/campaigns?status=draft", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert all(item["status"] == "draft" for item in data["items"])


@pytest.mark.asyncio
async def test_get_campaign_detail(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Detail Campaign", "slug": "detail-camp", "goal": "booking"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == campaign_id
    assert "stats" in data


@pytest.mark.asyncio
async def test_get_campaign_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/outreach/campaigns/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Update Campaign", "slug": "update-camp", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.patch(
        f"/api/v1/outreach/campaigns/{campaign_id}",
        json={"name": "Updated Name", "auto_send": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    assert response.json()["auto_send"] is True


@pytest.mark.asyncio
async def test_delete_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Delete Campaign", "slug": "delete-camp", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.delete(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify it's gone (soft delete — should return 404 or status=deleted)
    get_resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_launch_campaign(client: AsyncClient, auth_headers: dict):
    from unittest.mock import AsyncMock, patch, MagicMock

    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Launch Campaign", "slug": "launch-camp", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]

    mock_pool = AsyncMock()
    mock_job = MagicMock()
    mock_job.job_id = "test-job-id"
    mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

    with patch("app.api.campaigns.get_arq_pool", return_value=mock_pool):
        response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/launch", headers=auth_headers)
    assert response.status_code == 202
    assert response.json()["message"] == "Campaign launched"
    assert response.json()["campaign_id"] == campaign_id


@pytest.mark.asyncio
async def test_launch_already_active_campaign(client: AsyncClient, auth_headers: dict, db_session):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Already Active", "slug": "already-active", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]

    # Manually set campaign to active (simulating a prior launch)
    from app.models.campaign import Campaign
    import uuid as _uuid

    campaign = await db_session.get(Campaign, _uuid.UUID(campaign_id))
    campaign.status = "active"
    await db_session.commit()

    response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/launch", headers=auth_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_pause_campaign(client: AsyncClient, auth_headers: dict, db_session):
    from app.models.campaign import Campaign
    import uuid as _uuid

    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Pause Campaign", "slug": "pause-camp", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]

    # Manually set campaign to active
    campaign = await db_session.get(Campaign, _uuid.UUID(campaign_id))
    campaign.status = "active"
    await db_session.commit()

    # Then pause
    response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/pause", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_pause_non_active_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Pause Draft", "slug": "pause-draft", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/pause", headers=auth_headers)
    assert response.status_code == 409
