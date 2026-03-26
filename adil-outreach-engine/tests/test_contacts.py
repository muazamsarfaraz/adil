import pytest
from httpx import AsyncClient


@pytest.fixture
async def campaign_id(client: AsyncClient, auth_headers: dict) -> str:
    response = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Contact Test Campaign", "slug": "contact-test", "goal": "signup"},
        headers=auth_headers,
    )
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_contact(client: AsyncClient, auth_headers: dict, campaign_id: str):
    payload = {
        "name": "Samara Iqbal",
        "email": "info@aramaslaw.com",
        "firm_name": "Aramas Family Law",
        "website": "https://www.aramaslaw.com",
        "metadata": {"specialisms": ["islamic_family_law"], "location": "Manchester"},
    }
    response = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Samara Iqbal"
    assert data["email"] == "info@aramaslaw.com"
    assert data["status"] == "pending"
    assert data["campaign_id"] == campaign_id


@pytest.mark.asyncio
async def test_create_contact_invalid_campaign(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    payload = {"name": "Test", "email": "test@example.com"}
    response = await client.post(
        f"/api/v1/outreach/campaigns/{fake_id}/contacts",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bulk_create_contacts(client: AsyncClient, auth_headers: dict, campaign_id: str):
    payload = {
        "contacts": [
            {"name": "Contact A", "email": "a@example.com", "firm_name": "Firm A"},
            {"name": "Contact B", "email": "b@example.com", "firm_name": "Firm B"},
            {"name": "Contact C", "email": "c@example.com"},
        ]
    }
    response = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["created"] == 3
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_list_contacts(client: AsyncClient, auth_headers: dict, campaign_id: str):
    # Create contacts
    for i in range(3):
        await client.post(
            f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
            json={"name": f"List Contact {i}", "email": f"list{i}@example.com"},
            headers=auth_headers,
        )
    response = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3
    assert len(data["items"]) >= 3


@pytest.mark.asyncio
async def test_list_contacts_filter_status(client: AsyncClient, auth_headers: dict, campaign_id: str):
    await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Pending Contact", "email": "pending@example.com"},
        headers=auth_headers,
    )
    response = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts?status=pending",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert all(item["status"] == "pending" for item in data["items"])


@pytest.mark.asyncio
async def test_get_contact_detail(client: AsyncClient, auth_headers: dict, campaign_id: str):
    create_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Detail Contact", "email": "detail@example.com"},
        headers=auth_headers,
    )
    contact_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/outreach/contacts/{contact_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == contact_id
    assert "events" in data


@pytest.mark.asyncio
async def test_get_contact_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/outreach/contacts/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_contact(client: AsyncClient, auth_headers: dict, campaign_id: str):
    create_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Update Contact", "email": "update@example.com"},
        headers=auth_headers,
    )
    contact_id = create_resp.json()["id"]
    response = await client.patch(
        f"/api/v1/outreach/contacts/{contact_id}",
        json={"name": "Updated Name", "firm_name": "New Firm"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    assert response.json()["firm_name"] == "New Firm"


@pytest.mark.asyncio
async def test_delete_contact(client: AsyncClient, auth_headers: dict, campaign_id: str):
    create_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Delete Contact", "email": "delete@example.com"},
        headers=auth_headers,
    )
    contact_id = create_resp.json()["id"]
    response = await client.delete(f"/api/v1/outreach/contacts/{contact_id}", headers=auth_headers)
    assert response.status_code == 204

    get_resp = await client.get(f"/api/v1/outreach/contacts/{contact_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_contact(client: AsyncClient, auth_headers: dict, campaign_id: str):
    create_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Retry Contact", "email": "retry@example.com"},
        headers=auth_headers,
    )
    contact_id = create_resp.json()["id"]

    # Update status to unresponsive so retry is valid
    await client.patch(
        f"/api/v1/outreach/contacts/{contact_id}",
        json={"status": "unresponsive"},
        headers=auth_headers,
    )

    response = await client.post(f"/api/v1/outreach/contacts/{contact_id}/retry", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["current_cadence_step"] == 0
