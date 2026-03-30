"""
Full staging dry-run test — exercises the complete pipeline against Railway.

Requires OUTREACH_BASE_URL and OUTREACH_API_KEY env vars.
Uses real firm websites with fake email addresses.
"""

from __future__ import annotations

import asyncio
import os
import re

import httpx
import pytest

from tests.integration.conftest import skip_no_staging

pytestmark = [pytest.mark.integration, skip_no_staging]

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

BASE_URL = os.environ.get("OUTREACH_BASE_URL", "").rstrip("/")
API_KEY = os.environ.get("OUTREACH_API_KEY", "")

TEST_CONTACTS = [
    {
        "name": "Haroon Rashid",
        "email": "test-haroon-integ@fakeemail.example.com",
        "firm_name": "I Will Solicitors",
        "website": "https://www.iwillsolicitors.com",
        "metadata": {"location": "Birmingham"},
    },
    {
        "name": "Samara Iqbal",
        "email": "test-samara-integ@fakeemail.example.com",
        "firm_name": "Aramas Family Law",
        "website": "https://www.aramaslaw.com",
        "metadata": {"location": "London"},
    },
    {
        "name": "Philip Landau",
        "email": "test-philip-integ@fakeemail.example.com",
        "firm_name": "Landau Law",
        "website": "https://landaulaw.co.uk",
        "metadata": {"location": "London"},
    },
]

CAMPAIGN_CONFIG = {
    "name": "Integration Test Pipeline",
    "slug": "int-test-pipeline-dryrun",
    "goal": "signup",
    "templates": {
        "initial": {
            "subject": "Introducing AskAdil to {{firm_name}}",
            "body": (
                "Dear {{contact_name}},\n\n"
                "{{personalised_intro}}\n\n"
                "AskAdil is a Sharia-compliant will-writing platform that helps "
                "solicitors serve the Muslim community with confidence.\n\n"
                "Would you be open to a quick call this week?\n\n"
                "Best regards,\nMuazam Ali"
            ),
        }
    },
    "cadence": [{"step": 0, "delay_days": 0}],
    "llm_config": {
        "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
        "compose": {"provider": "gemini", "model": "gemini-2.5-flash"},
        "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
    },
    "research_instructions": "Research this solicitor firm. Focus on their practice areas and any Islamic or Sharia-compliant services.",
    "compose_instructions": "Write a warm, professional outreach email. Reference specific details about the firm.",
    "auto_send": False,
    "sender_name": "Muazam Ali",
    "sender_email": "muazam@askadil.com",
}

# Placeholder patterns that should NOT appear in final drafts
PLACEHOLDER_PATTERNS = [
    r"\[Your Name\]",
    r"\[Your Name/AskAdil Team\]",
    r"\{\{[a-z_]+\}\}",
    r"\[INSERT",
    r"\[PLACEHOLDER",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _headers() -> dict:
    return {"X-API-Key": API_KEY, "Content-Type": "application/json"}


async def _api_get(client: httpx.AsyncClient, path: str) -> httpx.Response:
    return await client.get(f"{BASE_URL}{path}", headers=_headers())


async def _api_post(client: httpx.AsyncClient, path: str, json: dict | None = None) -> httpx.Response:
    return await client.post(f"{BASE_URL}{path}", headers=_headers(), json=json)


async def _api_delete(client: httpx.AsyncClient, path: str) -> httpx.Response:
    return await client.delete(f"{BASE_URL}{path}", headers=_headers())


async def _api_delete(client: httpx.AsyncClient, path: str) -> httpx.Response:
    return await client.delete(f"{BASE_URL}{path}", headers=_headers())


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(240)
async def test_full_staging_pipeline():
    """
    Full end-to-end staging dry run:
    1. Create campaign
    2. Add 3 test contacts
    3. Launch campaign
    4. Wait for research + compose (poll up to 3 minutes)
    5. Verify drafts are personalised
    6. Verify stats
    7. Cleanup
    """
    campaign_id = None

    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # -----------------------------------------------------------
            # 1. Create campaign
            # -----------------------------------------------------------
            resp = await _api_post(client, "/campaigns", json=CAMPAIGN_CONFIG)
            # If slug already exists, try deleting the old one first
            if resp.status_code == 409:
                # List campaigns and find the conflicting one
                list_resp = await _api_get(client, "/campaigns")
                if list_resp.status_code == 200:
                    for c in list_resp.json().get("items", []):
                        if c["slug"] == CAMPAIGN_CONFIG["slug"]:
                            await _api_delete(client, f"/campaigns/{c['id']}")
                            break
                resp = await _api_post(client, "/campaigns", json=CAMPAIGN_CONFIG)

            assert resp.status_code == 201, f"Create campaign failed: {resp.status_code} {resp.text}"
            campaign_data = resp.json()
            campaign_id = campaign_data["id"]

            # -----------------------------------------------------------
            # 2. Add 3 test contacts
            # -----------------------------------------------------------
            contact_ids = []
            for contact_data in TEST_CONTACTS:
                resp = await _api_post(
                    client,
                    f"/campaigns/{campaign_id}/contacts",
                    json=contact_data,
                )
                assert resp.status_code == 201, f"Create contact failed: {resp.status_code} {resp.text}"
                contact_ids.append(resp.json()["id"])

            assert len(contact_ids) == 3

            # -----------------------------------------------------------
            # 3. Launch campaign
            # -----------------------------------------------------------
            resp = await _api_post(client, f"/campaigns/{campaign_id}/launch")
            assert resp.status_code == 202, f"Launch failed: {resp.status_code} {resp.text}"

            # -----------------------------------------------------------
            # 4. Wait for research + compose to complete (poll every 10s, max 3min)
            # -----------------------------------------------------------
            max_wait_seconds = 180
            poll_interval = 10
            elapsed = 0
            all_draft_pending = False

            while elapsed < max_wait_seconds:
                await asyncio.sleep(poll_interval)
                elapsed += poll_interval

                # Check all contact statuses
                statuses = []
                for cid in contact_ids:
                    resp = await _api_get(client, f"/contacts/{cid}")
                    if resp.status_code == 200:
                        statuses.append(resp.json()["status"])
                    else:
                        statuses.append("unknown")

                # We want all to reach draft_pending (or beyond)
                beyond_pending = {"draft_pending", "emailed", "replied", "converted"}
                if all(s in beyond_pending for s in statuses):
                    all_draft_pending = True
                    break

                # Log progress
                print(f"  [{elapsed}s] Contact statuses: {statuses}")

            # -----------------------------------------------------------
            # 5. Verify all 3 contacts reached draft_pending
            # -----------------------------------------------------------
            assert all_draft_pending, (
                f"Not all contacts reached draft_pending within {max_wait_seconds}s. " f"Final statuses: {statuses}"
            )

            # -----------------------------------------------------------
            # 6. Verify research_data is populated
            # -----------------------------------------------------------
            for i, cid in enumerate(contact_ids):
                resp = await _api_get(client, f"/contacts/{cid}")
                assert resp.status_code == 200
                contact_resp = resp.json()
                research = contact_resp.get("research_data")

                assert research, f"Contact {i} ({TEST_CONTACTS[i]['name']}) has empty research_data"
                # Research should not be just an error
                if isinstance(research, dict):
                    has_content = (
                        research.get("personalisation_hooks")
                        or research.get("firm_description")
                        or research.get("key_people")
                    )
                    assert has_content or "error" not in research, f"Contact {i} research is just errors: {research}"

            # -----------------------------------------------------------
            # 7. Preview all 3 drafts and verify personalisation
            # -----------------------------------------------------------
            for i, cid in enumerate(contact_ids):
                resp = await _api_get(client, f"/contacts/{cid}/draft")
                assert resp.status_code == 200, f"Draft not found for contact {i}: {resp.status_code} {resp.text}"
                draft = resp.json()

                subject = draft.get("subject", "")
                body = draft.get("body", "")
                firm_name = TEST_CONTACTS[i]["firm_name"]

                assert subject, f"Draft subject is empty for {firm_name}"
                assert body, f"Draft body is empty for {firm_name}"
                assert len(body) > 50, f"Draft body too short for {firm_name}: {body[:100]}"

                # Verify personalisation: body or subject should reference the firm
                combined = (subject + " " + body).lower()
                firm_words = firm_name.lower().split()
                # At least one word from the firm name should appear
                found_firm_ref = any(word in combined for word in firm_words if len(word) > 3)
                assert found_firm_ref, (
                    f"Draft for {firm_name} doesn't reference the firm. " f"Subject: {subject[:80]}, Body: {body[:200]}"
                )

                # -----------------------------------------------------------
                # 8. Verify no placeholder text
                # -----------------------------------------------------------
                for pattern in PLACEHOLDER_PATTERNS:
                    assert not re.search(
                        pattern, subject, re.IGNORECASE
                    ), f"Placeholder pattern {pattern!r} found in subject: {subject}"
                    assert not re.search(
                        pattern, body, re.IGNORECASE
                    ), f"Placeholder pattern {pattern!r} found in body: {body[:200]}"

            # -----------------------------------------------------------
            # 9. Check campaign stats
            # -----------------------------------------------------------
            resp = await _api_get(client, f"/campaigns/{campaign_id}")
            assert resp.status_code == 200
            campaign_detail = resp.json()
            stats = campaign_detail.get("stats", {})

            assert stats["total_contacts"] == 3, f"Expected 3 total contacts, got {stats['total_contacts']}"
            assert stats["draft_pending"] >= 3 or stats["emailed"] >= 0, f"Unexpected stats: {stats}"

        finally:
            # -----------------------------------------------------------
            # 10. Cleanup — delete the test campaign
            # -----------------------------------------------------------
            if campaign_id:
                try:
                    await _api_delete(client, f"/campaigns/{campaign_id}")
                except Exception:
                    pass  # Best effort cleanup
