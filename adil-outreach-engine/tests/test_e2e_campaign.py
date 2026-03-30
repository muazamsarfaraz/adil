"""End-to-end integration tests for campaign stats and CSV export endpoints."""

import csv
import io
import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact, ContactStatus
from app.models.outreach_event import EventChannel, EventType, OutreachEvent


CAMPAIGN_PAYLOAD = {
    "name": "Test Campaign",
    "slug": "test-campaign",
    "goal": "signup",
    "templates": {"initial": {"subject": "Test", "body": "Hello {{contact_name}}"}},
    "cadence": [{"day": 0, "action": "send_initial"}],
    "llm_config": {"research": {"provider": "gemini", "model": "gemini-2.5-flash"}},
    "auto_send": False,
    "sender_name": "Test",
    "sender_email": "test@example.com",
    "reply_to": "test@example.com",
}

CONTACTS_PAYLOAD = {
    "contacts": [
        {"name": "Alice", "email": "alice@example.com", "firm_name": "Alice Law"},
        {"name": "Bob", "email": "bob@example.com", "firm_name": "Bob Legal"},
    ]
}


@pytest.fixture
async def campaign_with_contacts(client: AsyncClient, auth_headers: dict):
    """Create a campaign and add two contacts, returning (campaign_id, contact_ids)."""
    resp = await client.post("/api/v1/outreach/campaigns", json=CAMPAIGN_PAYLOAD, headers=auth_headers)
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk",
        json=CONTACTS_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["created"] == 2

    # Fetch contact IDs
    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/contacts", headers=auth_headers)
    contacts = resp.json()["items"]
    contact_ids = [c["id"] for c in contacts]

    return campaign_id, contact_ids


# -------------------------------------------------------------------------
# Stats endpoint tests
# -------------------------------------------------------------------------


async def test_stats_initial(client: AsyncClient, auth_headers: dict, campaign_with_contacts):
    """Stats for a fresh campaign should show all contacts as pending."""
    campaign_id, _ = campaign_with_contacts

    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/stats", headers=auth_headers)
    assert resp.status_code == 200
    stats = resp.json()

    assert stats["campaign_id"] == campaign_id
    assert stats["campaign_name"] == "Test Campaign"
    assert stats["total_contacts"] == 2
    assert stats["pending"] == 2
    assert stats["emailed"] == 0
    assert stats["opened"] == 0
    assert stats["replied"] == 0
    assert stats["converted"] == 0
    assert stats["open_rate"] == 0.0
    assert stats["reply_rate"] == 0.0
    assert stats["conversion_rate"] == 0.0
    assert stats["last_activity"] is None


async def test_stats_after_events(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    campaign_with_contacts,
):
    """Stats should reflect correct counts and rates after simulating events."""
    campaign_id, contact_ids = campaign_with_contacts

    # Simulate: both contacts emailed, one opened, one replied
    for cid in contact_ids:
        contact = await db_session.get(Contact, uuid.UUID(cid))
        contact.status = ContactStatus.emailed
        db_session.add(
            OutreachEvent(
                contact_id=uuid.UUID(cid),
                event_type=EventType.email_sent,
                channel=EventChannel.email,
                subject="Test",
            )
        )

    # First contact also opened
    db_session.add(
        OutreachEvent(
            contact_id=uuid.UUID(contact_ids[0]),
            event_type=EventType.email_opened,
            channel=EventChannel.email,
        )
    )

    # Second contact replied
    contact_bob = await db_session.get(Contact, uuid.UUID(contact_ids[1]))
    contact_bob.status = ContactStatus.replied
    db_session.add(
        OutreachEvent(
            contact_id=uuid.UUID(contact_ids[1]),
            event_type=EventType.reply_received,
            channel=EventChannel.email,
            content="I am interested",
        )
    )

    await db_session.commit()

    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/stats", headers=auth_headers)
    assert resp.status_code == 200
    stats = resp.json()

    assert stats["total_contacts"] == 2
    assert stats["emailed"] == 1
    assert stats["replied"] == 1
    assert stats["opened"] == 1

    # sent_total = emailed(1) + replied(1) = 2
    assert stats["open_rate"] == 0.5
    assert stats["reply_rate"] == 0.5
    assert stats["conversion_rate"] == 0.0
    assert stats["last_activity"] is not None


async def test_stats_404_nonexistent(client: AsyncClient, auth_headers: dict):
    """Stats for a non-existent campaign should return 404."""
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/outreach/campaigns/{fake_id}/stats", headers=auth_headers)
    assert resp.status_code == 404


async def test_stats_requires_auth(client: AsyncClient, campaign_with_contacts):
    """Stats endpoint should require API key auth."""
    campaign_id, _ = campaign_with_contacts
    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/stats")
    assert resp.status_code == 401


# -------------------------------------------------------------------------
# Export endpoint tests
# -------------------------------------------------------------------------


async def test_export_csv(client: AsyncClient, auth_headers: dict, campaign_with_contacts):
    """Export should return a valid CSV with all contacts."""
    campaign_id, _ = campaign_with_contacts

    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/export", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "attachment" in resp.headers["content-disposition"]
    assert "test-campaign" in resp.headers["content-disposition"]

    # Parse CSV
    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) == 2

    emails = {row["email"] for row in rows}
    assert "alice@example.com" in emails
    assert "bob@example.com" in emails

    # Check all expected columns exist
    expected_cols = {
        "contact_id",
        "name",
        "email",
        "firm_name",
        "phone",
        "website",
        "status",
        "metadata",
        "research_data",
        "last_event_type",
        "last_event_date",
        "total_events",
        "created_at",
        "updated_at",
    }
    assert expected_cols == set(reader.fieldnames)


async def test_export_csv_with_events(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    campaign_with_contacts,
):
    """Export should include event data when events exist."""
    campaign_id, contact_ids = campaign_with_contacts

    # Add an event for the first contact
    db_session.add(
        OutreachEvent(
            contact_id=uuid.UUID(contact_ids[0]),
            event_type=EventType.email_sent,
            channel=EventChannel.email,
            subject="Hello Alice",
        )
    )
    await db_session.commit()

    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/export", headers=auth_headers)
    assert resp.status_code == 200

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)

    # Find Alice's row
    alice_row = next(r for r in rows if r["email"] == "alice@example.com")
    assert alice_row["total_events"] == "1"
    assert alice_row["last_event_type"] == "email_sent"
    assert alice_row["last_event_date"] != ""

    # Bob should have no events
    bob_row = next(r for r in rows if r["email"] == "bob@example.com")
    assert bob_row["total_events"] == "0"
    assert bob_row["last_event_type"] == ""


async def test_export_404_nonexistent(client: AsyncClient, auth_headers: dict):
    """Export for a non-existent campaign should return 404."""
    fake_id = str(uuid.uuid4())
    resp = await client.get(f"/api/v1/outreach/campaigns/{fake_id}/export", headers=auth_headers)
    assert resp.status_code == 404


async def test_export_requires_auth(client: AsyncClient, campaign_with_contacts):
    """Export endpoint should require API key auth."""
    campaign_id, _ = campaign_with_contacts
    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/export")
    assert resp.status_code == 401


# -------------------------------------------------------------------------
# Full lifecycle test
# -------------------------------------------------------------------------


async def test_campaign_lifecycle(client: AsyncClient, auth_headers: dict):
    """Full lifecycle: create campaign, add contacts, check stats, export CSV."""
    # 1. Create campaign
    resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={
            "name": "Lifecycle Test",
            "slug": "lifecycle-test",
            "goal": "signup",
            "templates": {"initial": {"subject": "Test", "body": "Hello {{contact_name}}"}},
            "cadence": [{"day": 0, "action": "send_initial"}],
            "llm_config": {"research": {"provider": "gemini", "model": "gemini-2.5-flash"}},
            "auto_send": False,
            "sender_name": "Test",
            "sender_email": "test@example.com",
            "reply_to": "test@example.com",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    # 2. Add contacts
    resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk",
        json={
            "contacts": [
                {"name": "Alice", "email": "alice@lifecycle.com", "firm_name": "Alice Law"},
                {"name": "Bob", "email": "bob@lifecycle.com", "firm_name": "Bob Legal"},
            ]
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    assert resp.json()["created"] == 2

    # 3. Check stats before any activity
    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/stats", headers=auth_headers)
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_contacts"] == 2
    assert stats["pending"] == 2
    assert stats["emailed"] == 0

    # 4. Verify campaign is still draft
    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert resp.json()["status"] == "draft"

    # 5. Export CSV
    resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}/export", headers=auth_headers)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "alice@lifecycle.com" in resp.text
    assert "bob@lifecycle.com" in resp.text
