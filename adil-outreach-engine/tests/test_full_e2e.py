"""Full end-to-end test of the outreach funnel.

Exercises the complete lifecycle: campaign creation -> contact add -> launch ->
research -> draft -> approve -> email -> open -> reply -> signup -> conversion,
then verifies stats, export, and pause.
"""

import csv
import io
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.outreach_event import EventChannel, EventType, OutreachEvent


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------

CAMPAIGN_PAYLOAD = {
    "name": "Solicitor Outreach Q1",
    "slug": "solicitor-outreach-q1",
    "goal": "signup",
    "templates": {
        "initial": {
            "subject": "AskAdil — free legal-tech platform for {{firm_name}}",
            "body": (
                "Dear {{contact_name}},\n\n"
                "We noticed {{firm_name}} specialises in immigration law. "
                "AskAdil can help your clients 24/7.\n\n"
                "Best,\nThe AskAdil Team"
            ),
        },
        "follow_up_1": {
            "subject": "Following up — AskAdil for {{firm_name}}",
            "body": "Hi {{contact_name}}, just checking in...",
        },
    },
    "cadence": [
        {"day": 0, "action": "send_initial"},
        {"day": 3, "action": "send_follow_up_1"},
        {"day": 7, "action": "mark_unresponsive"},
    ],
    "llm_config": {
        "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
        "compose": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
    },
    "conversion_config": {
        "signup_fields": [
            {"name": "firm_size", "type": "select", "required": True, "options": ["1-5", "6-20", "21-50", "50+"]},
            {"name": "practice_areas", "type": "text", "required": True},
            {"name": "newsletter", "type": "boolean", "required": False},
        ],
    },
    "auto_send": False,
    "sender_name": "AskAdil Outreach",
    "sender_email": "outreach@askadil.com",
    "reply_to": "outreach@askadil.com",
}

SOLICITOR_FIRMS = [
    {
        "name": "Sarah Khan",
        "email": "sarah@khanlaw.co.uk",
        "firm_name": "Khan & Partners Solicitors",
        "website": "https://khanlaw.co.uk",
        "phone": "+44 20 7123 4567",
        "metadata": {"practice_areas": "Immigration, Family", "region": "London"},
    },
    {
        "name": "James Patel",
        "email": "james@patelegal.co.uk",
        "firm_name": "Patel Legal Services",
        "website": "https://patelegal.co.uk",
        "phone": "+44 121 456 7890",
        "metadata": {"practice_areas": "Immigration, Employment", "region": "Birmingham"},
    },
    {
        "name": "Fatima Ali",
        "email": "fatima@aliassociates.co.uk",
        "firm_name": "Ali & Associates",
        "website": "https://aliassociates.co.uk",
        "phone": "+44 161 789 0123",
        "metadata": {"practice_areas": "Immigration, Housing", "region": "Manchester"},
    },
]


# ---------------------------------------------------------------------------
# Full funnel E2E test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_outreach_funnel(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
):
    """Complete outreach funnel: create -> contacts -> launch -> research ->
    draft -> approve -> send -> open -> reply -> signup -> verify conversion ->
    stats -> export -> pause.

    This is a single sequential test that tells the story of one campaign
    going through every stage of the outreach engine.
    """

    # -----------------------------------------------------------------------
    # Step 1: Create a campaign
    # -----------------------------------------------------------------------
    resp = await client.post(
        "/api/v1/outreach/campaigns",
        json=CAMPAIGN_PAYLOAD,
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Campaign creation failed: {resp.text}"
    campaign = resp.json()
    campaign_id = campaign["id"]
    campaign_slug = campaign["slug"]
    assert campaign["status"] == "draft"
    assert campaign["name"] == "Solicitor Outreach Q1"
    assert campaign["goal"] == "signup"
    assert campaign["templates"]["initial"]["subject"].startswith("AskAdil")

    # -----------------------------------------------------------------------
    # Step 2: Add 3 solicitor firms in bulk
    # -----------------------------------------------------------------------
    resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk",
        json={"contacts": SOLICITOR_FIRMS},
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Bulk create failed: {resp.text}"
    assert resp.json()["created"] == 3
    assert resp.json()["errors"] == []

    # Fetch all contacts to get IDs
    resp = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    contacts_list = resp.json()["items"]
    assert len(contacts_list) == 3
    _contact_ids = [c["id"] for c in contacts_list]

    # Pick our main contact (Sarah Khan) for the full journey
    sarah = next(c for c in contacts_list if c["email"] == "sarah@khanlaw.co.uk")
    sarah_id = sarah["id"]

    # -----------------------------------------------------------------------
    # Step 3: Launch campaign (mock arq pool)
    # -----------------------------------------------------------------------
    mock_job = AsyncMock()
    mock_job.job_id = "test-job-123"
    mock_pool = AsyncMock()
    mock_pool.enqueue_job = AsyncMock(return_value=mock_job)

    with patch("app.api.campaigns.get_arq_pool", return_value=mock_pool):
        resp = await client.post(
            f"/api/v1/outreach/campaigns/{campaign_id}/launch",
            headers=auth_headers,
        )
    assert resp.status_code == 202, f"Launch failed: {resp.text}"
    assert resp.json()["message"] == "Campaign launched"

    # Manually set campaign to active (normally the worker does this)
    from app.models.campaign import Campaign, CampaignStatus

    campaign_obj = await db_session.get(Campaign, uuid.UUID(campaign_id))
    campaign_obj.status = CampaignStatus.active
    await db_session.commit()

    # Verify campaign is now active
    resp = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}",
        headers=auth_headers,
    )
    assert resp.json()["status"] == "active"

    # -----------------------------------------------------------------------
    # Step 4: Check initial stats — 3 pending contacts
    # -----------------------------------------------------------------------
    resp = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/stats",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    stats = resp.json()
    assert stats["total_contacts"] == 3
    assert stats["pending"] == 3
    assert stats["emailed"] == 0
    assert stats["converted"] == 0

    # -----------------------------------------------------------------------
    # Step 5: Simulate research complete — PATCH Sarah's status to "ready"
    # -----------------------------------------------------------------------
    resp = await client.patch(
        f"/api/v1/outreach/contacts/{sarah_id}",
        json={"status": "ready"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Status update failed: {resp.text}"
    assert resp.json()["status"] == "ready"

    # -----------------------------------------------------------------------
    # Step 6: Create a draft — insert a draft_created outreach event
    # -----------------------------------------------------------------------
    # Set Sarah to draft_pending first
    resp = await client.patch(
        f"/api/v1/outreach/contacts/{sarah_id}",
        json={"status": "draft_pending"},
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "draft_pending"

    # Create the draft event directly in DB (simulating the compose agent)
    draft_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=uuid.UUID(sarah_id),
        event_type=EventType.draft_created,
        channel=EventChannel.system,
        subject="AskAdil — free legal-tech platform for Khan & Partners Solicitors",
        content=(
            "Dear Sarah,\n\n"
            "We noticed Khan & Partners specialises in immigration and family law. "
            "AskAdil is a free AI-powered legal platform that can help your clients "
            "get instant answers to common immigration questions 24/7.\n\n"
            "Would you be open to a quick demo?\n\n"
            "Best regards,\nThe AskAdil Team"
        ),
        metadata_={
            "personalisation_hooks": [
                "Immigration and family law specialisation",
                "London-based firm",
                "Khan & Partners brand",
            ]
        },
    )
    db_session.add(draft_event)
    await db_session.commit()

    # -----------------------------------------------------------------------
    # Step 7: Preview draft
    # -----------------------------------------------------------------------
    resp = await client.get(
        f"/api/v1/outreach/contacts/{sarah_id}/draft",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Draft preview failed: {resp.text}"
    draft = resp.json()
    assert draft["contact_id"] == sarah_id
    assert "Khan & Partners" in draft["subject"]
    assert draft["status"] == "pending_approval"
    assert len(draft["personalisation_hooks"]) == 3
    assert "immigration" in draft["body"].lower()

    # -----------------------------------------------------------------------
    # Step 8: Approve draft
    # -----------------------------------------------------------------------
    resp = await client.post(
        f"/api/v1/outreach/contacts/{sarah_id}/approve-draft",
        json={"edited_subject": None, "edited_body": None},
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Draft approval failed: {resp.text}"
    assert resp.json()["status"] == "approved"

    # After approve, status is "ready" (worker would set to "emailed" via send_email_task)
    resp = await client.get(
        f"/api/v1/outreach/contacts/{sarah_id}",
        headers=auth_headers,
    )
    assert resp.json()["status"] == "ready"

    # Manually set to emailed (simulating what send_email_task worker does)
    resp = await client.patch(
        f"/api/v1/outreach/contacts/{sarah_id}",
        json={"status": "emailed"},
        headers=auth_headers,
    )
    assert resp.status_code == 200

    # -----------------------------------------------------------------------
    # Step 9: Simulate email sent — create email_sent event
    # -----------------------------------------------------------------------
    email_sent_event = OutreachEvent(
        id=uuid.uuid4(),
        contact_id=uuid.UUID(sarah_id),
        event_type=EventType.email_sent,
        channel=EventChannel.email,
        subject="AskAdil — free legal-tech platform for Khan & Partners Solicitors",
        content="Dear Sarah...",
        metadata_={
            "sg_message_id": "abc123.smtp",
            "to": "sarah@khanlaw.co.uk",
            "from_email": "outreach@askadil.com",
        },
    )
    db_session.add(email_sent_event)
    await db_session.commit()

    # -----------------------------------------------------------------------
    # Step 10: Simulate SendGrid open event
    # -----------------------------------------------------------------------
    with patch("app.auth.webhook_verify.verify_sendgrid_signature", return_value=True):
        resp = await client.post(
            "/api/v1/outreach/webhooks/sendgrid/events",
            json=[
                {
                    "email": "sarah@khanlaw.co.uk",
                    "timestamp": int(time.time()),
                    "event": "open",
                    "sg_message_id": "abc123.smtp",
                    "contact_id": sarah_id,
                    "campaign_id": campaign_id,
                    "useragent": "Mozilla/5.0",
                    "ip": "203.0.113.42",
                }
            ],
        )
    assert resp.status_code == 200, f"SendGrid open event failed: {resp.text}"
    assert resp.json()["status"] == "ok"

    # -----------------------------------------------------------------------
    # Step 11: Simulate reply received via SendGrid inbound parse
    # -----------------------------------------------------------------------
    # Inbound parse requires a shared bearer token (?token=... or Authorization
    # header). Bypass via the same patch the unit tests use.
    with patch("app.auth.webhook_verify.verify_sendgrid_inbound_token", return_value=True):
        resp = await client.post(
            "/api/v1/outreach/webhooks/sendgrid/inbound",
            data={
                "from": "Sarah Khan <sarah@khanlaw.co.uk>",
                "to": "outreach@askadil.com",
                "subject": "Re: AskAdil — free legal-tech platform for Khan & Partners Solicitors",
                "text": "Hi, this sounds interesting! Could you tell me more about the platform and how it integrates with our existing systems?",
                "html": "",
            },
        )
    assert resp.status_code == 200, f"Inbound reply failed: {resp.text}"
    assert resp.json()["status"] == "ok"
    assert resp.json()["contact_id"] == sarah_id

    # Verify contact status changed to replied
    resp = await client.get(
        f"/api/v1/outreach/contacts/{sarah_id}",
        headers=auth_headers,
    )
    assert resp.json()["status"] == "replied"

    # -----------------------------------------------------------------------
    # Step 12: Check events timeline — should show full history
    # -----------------------------------------------------------------------
    resp = await client.get(
        f"/api/v1/outreach/contacts/{sarah_id}/events",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Events timeline failed: {resp.text}"
    timeline = resp.json()
    assert timeline["contact_id"] == sarah_id
    assert timeline["contact_name"] == "Sarah Khan"
    assert timeline["contact_status"] == "replied"

    # Should have: draft_created, draft_approved, email_sent, email_opened, reply_received
    assert timeline["total_events"] >= 5
    event_types = [e["event_type"] for e in timeline["events"]]
    assert "draft_created" in event_types
    assert "draft_approved" in event_types
    assert "email_sent" in event_types
    assert "email_opened" in event_types
    assert "reply_received" in event_types

    # -----------------------------------------------------------------------
    # Step 13: Simulate signup conversion
    # -----------------------------------------------------------------------
    # Sarah needs to be in emailed/replied status for the signup flow.
    # The signup endpoint uses _get_active_campaign_by_slug which requires active campaign.
    resp = await client.post(
        f"/api/v1/outreach/signup/{campaign_slug}",
        json={
            "ref": sarah_id,
            "firm_size": "6-20",
            "practice_areas": "Immigration, Family Law",
            "newsletter": True,
        },
    )
    assert resp.status_code == 201, f"Signup failed: {resp.text}"
    conversion = resp.json()
    assert conversion["type"] == "signup"
    assert conversion["contact_id"] == sarah_id
    assert "Signup completed" in conversion["message"]

    # -----------------------------------------------------------------------
    # Step 14: Verify conversion — contact status should be "converted"
    # -----------------------------------------------------------------------
    resp = await client.get(
        f"/api/v1/outreach/contacts/{sarah_id}",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "converted"

    # -----------------------------------------------------------------------
    # Step 15: Check final stats
    # -----------------------------------------------------------------------
    resp = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/stats",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    final_stats = resp.json()
    assert final_stats["total_contacts"] == 3
    assert final_stats["converted"] == 1
    assert final_stats["conversion_rate"] > 0
    # 2 contacts still pending (James and Fatima)
    assert final_stats["pending"] == 2
    assert final_stats["last_activity"] is not None

    # -----------------------------------------------------------------------
    # Step 16: Export CSV — should include all contacts and event data
    # -----------------------------------------------------------------------
    resp = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/export",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    assert "solicitor-outreach-q1" in resp.headers["content-disposition"]

    reader = csv.DictReader(io.StringIO(resp.text))
    rows = list(reader)
    assert len(rows) == 3

    # Check Sarah's row has conversion data
    sarah_row = next(r for r in rows if r["email"] == "sarah@khanlaw.co.uk")
    assert sarah_row["status"] == "converted"
    assert sarah_row["firm_name"] == "Khan & Partners Solicitors"
    assert int(sarah_row["total_events"]) >= 5
    assert sarah_row["last_event_date"] != ""

    # Check other contacts are still pending
    james_row = next(r for r in rows if r["email"] == "james@patelegal.co.uk")
    assert james_row["status"] == "pending"

    fatima_row = next(r for r in rows if r["email"] == "fatima@aliassociates.co.uk")
    assert fatima_row["status"] == "pending"

    # Verify all expected CSV columns
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

    # -----------------------------------------------------------------------
    # Step 17: Pause campaign
    # -----------------------------------------------------------------------
    resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/pause",
        headers=auth_headers,
    )
    assert resp.status_code == 200, f"Pause failed: {resp.text}"
    assert resp.json()["status"] == "paused"

    # Verify campaign is paused
    resp = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}",
        headers=auth_headers,
    )
    assert resp.json()["status"] == "paused"
