"""Tests for outreach endpoints: email-preview, dry-run campaign schema."""

import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.outreach_event import EventChannel, EventType, OutreachEvent


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def preview_campaign(db_session: AsyncSession):
    """Create a campaign with sender info for preview tests."""
    campaign = Campaign(
        id=uuid.uuid4(),
        name="Preview Test Campaign",
        slug=f"preview-test-{uuid.uuid4().hex[:8]}",
        goal="signup",
        status="active",
        templates={"initial": {"subject": "Test", "body": "Hello"}},
        cadence=[{"day": 0, "action": "send_initial", "template": "initial"}],
        sender_name="Preview Sender",
        sender_email="preview@example.com",
        reply_to="reply@example.com",
        auto_send=False,
    )
    db_session.add(campaign)
    await db_session.commit()
    await db_session.refresh(campaign)
    return campaign


@pytest.fixture
async def preview_contact(db_session: AsyncSession, preview_campaign):
    """Create a contact with a draft for preview tests."""
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=preview_campaign.id,
        name="Preview Contact",
        email="contact@example-law.com",
        firm_name="Example Law LLP",
        status="draft_pending",
        current_cadence_step=0,
    )
    db_session.add(contact)
    await db_session.commit()
    await db_session.refresh(contact)

    # Create a draft event
    draft = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=contact.id,
        event_type=EventType.draft_created,
        channel=EventChannel.system,
        subject="Hello from AskAdil",
        content="Dear Preview Contact,\n\nWe'd love to help your firm.\n\nBest regards,\nAskAdil",
        metadata_={"template_key": "initial", "cadence_step": 0},
    )
    db_session.add(draft)
    await db_session.commit()

    return contact


# ---------------------------------------------------------------------------
# Email Preview Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_email_preview_returns_full_email(
    client: AsyncClient, auth_headers: dict, preview_contact, preview_campaign
):
    """Email preview should return the exact email that would be sent."""
    resp = await client.get(
        f"/api/v1/outreach/contacts/{preview_contact.id}/email-preview",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    assert data["contact_id"] == str(preview_contact.id)
    assert data["to"] == "contact@example-law.com"
    assert data["from_email"] == "preview@example.com"
    assert data["from_name"] == "Preview Sender"
    assert data["reply_to"] == "reply@example.com"
    assert data["subject"] == "Hello from AskAdil"
    assert "Dear Preview Contact" in data["body_text"]
    assert data["body_html"] is not None
    assert "Dear Preview Contact" in data["body_html"]
    assert "<br>" in data["body_html"]
    assert data["draft_created_at"] is not None


@pytest.mark.asyncio
async def test_email_preview_requires_auth(client: AsyncClient, preview_contact):
    """Email preview endpoint should require API key."""
    resp = await client.get(
        f"/api/v1/outreach/contacts/{preview_contact.id}/email-preview",
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_email_preview_404_no_draft(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, preview_campaign
):
    """Email preview should return 404 if contact has no draft."""
    # Create a contact WITHOUT a draft
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=preview_campaign.id,
        name="No Draft Contact",
        email="nodraft@example.com",
        status="pending",
        current_cadence_step=0,
    )
    db_session.add(contact)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/outreach/contacts/{contact.id}/email-preview",
        headers=auth_headers,
    )
    assert resp.status_code == 404
    assert "No draft" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_email_preview_404_nonexistent_contact(client: AsyncClient, auth_headers: dict):
    """Email preview should return 404 for non-existent contact."""
    fake_id = str(uuid.uuid4())
    resp = await client.get(
        f"/api/v1/outreach/contacts/{fake_id}/email-preview",
        headers=auth_headers,
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_email_preview_html_escaping(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession, preview_campaign
):
    """Email preview HTML should properly escape special characters."""
    contact = Contact(
        id=uuid.uuid4(),
        campaign_id=preview_campaign.id,
        name="HTML Test",
        email="html@example.com",
        status="draft_pending",
        current_cadence_step=0,
    )
    db_session.add(contact)
    await db_session.commit()

    # Create a draft with HTML-like characters
    draft = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=contact.id,
        event_type=EventType.draft_created,
        channel=EventChannel.system,
        subject="Test <subject>",
        content="Body with <script>alert('xss')</script> & special chars",
    )
    db_session.add(draft)
    await db_session.commit()

    resp = await client.get(
        f"/api/v1/outreach/contacts/{contact.id}/email-preview",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    # Verify HTML escaping: raw < > should be escaped
    assert "&lt;script&gt;" in data["body_html"]
    assert "&amp;" in data["body_html"]
    assert "<script>" not in data["body_html"]


# ---------------------------------------------------------------------------
# Dry-run Campaign Schema Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_campaign_with_dry_run(client: AsyncClient, auth_headers: dict):
    """Creating a campaign with dry_run=true should work."""
    payload = {
        "name": "Dry Run Campaign",
        "slug": "dry-run-schema-test",
        "goal": "signup",
        "auto_send": True,
        "dry_run": True,
        "sender_name": "Test",
        "sender_email": "test@example.com",
    }
    resp = await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["dry_run"] is True
    assert data["auto_send"] is True


@pytest.mark.asyncio
async def test_create_campaign_dry_run_defaults_false(client: AsyncClient, auth_headers: dict):
    """dry_run should default to false when not specified."""
    payload = {
        "name": "Normal Campaign",
        "slug": "normal-schema-test",
        "goal": "signup",
    }
    resp = await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["dry_run"] is False


@pytest.mark.asyncio
async def test_update_campaign_dry_run(client: AsyncClient, auth_headers: dict):
    """Updating dry_run on an existing campaign should work."""
    # Create campaign
    payload = {
        "name": "Update Dry Run Test",
        "slug": "update-dry-run-test",
        "goal": "signup",
        "dry_run": False,
    }
    resp = await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    assert resp.status_code == 201
    campaign_id = resp.json()["id"]

    # Update dry_run to true
    resp = await client.patch(
        f"/api/v1/outreach/campaigns/{campaign_id}",
        json={"dry_run": True},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["dry_run"] is True
