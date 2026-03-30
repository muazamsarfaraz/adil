#!/usr/bin/env python3
"""Send-to-self test script for the outreach engine.

Creates a test campaign, adds one contact (your email), launches the campaign,
waits for the draft, shows it for review, asks for approval, then waits for
the email_sent event.

Usage:
    python scripts/test_send_to_self.py your@email.com

    # Against Railway:
    OUTREACH_BASE_URL=https://... OUTREACH_API_KEY=... python scripts/test_send_to_self.py your@email.com
"""

import argparse
import os
import sys
import time
import uuid

import httpx

BASE_URL = os.environ.get("OUTREACH_BASE_URL", "http://localhost:8000")
API_KEY = os.environ.get("OUTREACH_API_KEY", "dev-api-key")

HEADERS = {
    "X-API-Key": API_KEY,
    "Content-Type": "application/json",
}

POLL_INTERVAL = 3  # seconds
MAX_POLL = 120  # max seconds to wait for any single stage


def api(method: str, path: str, **kwargs) -> httpx.Response:
    """Make an API request and raise on non-2xx status."""
    url = f"{BASE_URL}{path}"
    resp = httpx.request(method, url, headers=HEADERS, timeout=30, **kwargs)
    if resp.status_code >= 400:
        print(f"  ERROR {resp.status_code}: {resp.text}")
        sys.exit(1)
    return resp


def poll_contact_status(contact_id: str, target_statuses: list[str], stage_name: str) -> dict:
    """Poll contact until it reaches one of the target statuses."""
    print(f"\n  Waiting for contact to reach {target_statuses}...")
    start = time.time()
    while time.time() - start < MAX_POLL:
        resp = api("GET", f"/api/v1/contacts/{contact_id}")
        contact = resp.json()
        status = contact["status"]
        print(f"    status = {status}")
        if status in target_statuses:
            return contact
        time.sleep(POLL_INTERVAL)
    print(f"\n  TIMEOUT waiting for {stage_name} (last status: {status})")
    sys.exit(1)


def poll_for_event(contact_id: str, event_type: str, stage_name: str) -> dict | None:
    """Poll events timeline until a specific event type appears."""
    print(f"\n  Waiting for {event_type} event...")
    start = time.time()
    while time.time() - start < MAX_POLL:
        resp = api("GET", f"/api/v1/outreach/contacts/{contact_id}/events?event_type={event_type}")
        data = resp.json()
        events = data.get("events", [])
        if events:
            return events[0]
        time.sleep(POLL_INTERVAL)
    print(f"\n  TIMEOUT waiting for {stage_name}")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="Send a test email to yourself via the outreach engine.")
    parser.add_argument("email", help="Your email address to receive the test email")
    args = parser.parse_args()

    email = args.email
    slug = f"test-self-{uuid.uuid4().hex[:8]}"

    print(f"\n{'='*60}")
    print("  OUTREACH ENGINE - SEND TO SELF TEST")
    print(f"  Base URL:  {BASE_URL}")
    print(f"  Email:     {email}")
    print(f"  Slug:      {slug}")
    print(f"{'='*60}")

    # 1. Create test campaign (auto_send: false, dry_run: false)
    print("\n[1/7] Creating test campaign...")
    campaign_data = {
        "name": f"Self Test - {email}",
        "slug": slug,
        "goal": "signup",
        "auto_send": False,
        "dry_run": False,
        "sender_name": "AskAdil Test",
        "sender_email": "hello@askadil.com",
        "reply_to": "hello@askadil.com",
        "templates": {
            "initial": {
                "subject": "Test email from AskAdil outreach engine",
                "body": "Hi {{contact_name}},\n\nThis is a test email from the AskAdil outreach engine.\n\nIf you received this, the pipeline is working end-to-end.\n\nBest,\nAskAdil Team",
            }
        },
        "cadence": [{"day": 0, "action": "send_initial", "template": "initial"}],
        "llm_config": {
            "research": {"provider": "gemini", "model": "gemini-2.0-flash"},
            "compose": {"provider": "anthropic", "model": "claude-sonnet-4-20250514"},
        },
    }
    resp = api("POST", "/api/v1/campaigns", json=campaign_data)
    campaign = resp.json()
    campaign_id = campaign["id"]
    print(f"  Campaign created: {campaign_id}")

    # 2. Add one contact
    print("\n[2/7] Adding contact...")
    contact_data = {
        "name": "Test User",
        "email": email,
        "firm_name": "Test Firm",
        "website": "https://example.com",
    }
    resp = api("POST", f"/api/v1/campaigns/{campaign_id}/contacts", json=contact_data)
    contact = resp.json()
    contact_id = contact["id"]
    print(f"  Contact created: {contact_id}")

    # 3. Launch campaign
    print("\n[3/7] Launching campaign...")
    resp = api("POST", f"/api/v1/campaigns/{campaign_id}/launch")
    print(f"  Campaign launched: {resp.json()}")

    # 4. Poll until draft_pending
    print("\n[4/7] Waiting for draft...")
    poll_contact_status(contact_id, ["draft_pending"], "draft generation")

    # 5. Show draft for review
    print("\n[5/7] Fetching draft for review...")
    resp = api("GET", f"/api/v1/outreach/contacts/{contact_id}/draft")
    draft = resp.json()
    print(f"\n  {'─'*50}")
    print(f"  Subject: {draft['subject']}")
    print(f"  {'─'*50}")
    print(f"  {draft['body']}")
    print(f"  {'─'*50}")

    # Also show the email preview
    resp = api("GET", f"/api/v1/outreach/contacts/{contact_id}/email-preview")
    preview = resp.json()
    print("\n  Email Preview:")
    print(f"    From: {preview['from_name']} <{preview['from_email']}>")
    print(f"    To:   {preview['to']}")
    print(f"    Reply-To: {preview['reply_to']}")
    print(f"    Subject:  {preview['subject']}")

    # 6. Ask for confirmation
    print("\n[6/7] Approve and send?")
    answer = input("  Type 'yes' to approve and send, anything else to abort: ").strip().lower()
    if answer != "yes":
        print("\n  Aborted. Campaign and contact still exist for inspection.")
        print(f"  Campaign: {BASE_URL}/api/v1/campaigns/{campaign_id}")
        print(f"  Contact:  {BASE_URL}/api/v1/contacts/{contact_id}")
        sys.exit(0)

    # Approve the draft
    print("\n  Approving draft...")
    resp = api("POST", f"/api/v1/outreach/contacts/{contact_id}/approve-draft")
    print(f"  Draft approved: {resp.json()}")

    # 7. Wait for email_sent event
    print("\n[7/7] Waiting for email to be sent...")
    event = poll_for_event(contact_id, "email_sent", "email send")
    if event:
        print(f"\n  {'='*50}")
        print("  SUCCESS! Email sent.")
        print(f"  SendGrid Message ID: {event.get('metadata', {}).get('sendgrid_message_id', 'N/A')}")
        print(f"  Event ID: {event['id']}")
        print(f"  {'='*50}")
    else:
        # Check for email_failed
        resp = api("GET", f"/api/v1/outreach/contacts/{contact_id}/events?event_type=email_failed")
        data = resp.json()
        if data.get("events"):
            fail_event = data["events"][0]
            print(f"\n  FAILED: {fail_event.get('metadata', {}).get('error', 'Unknown error')}")
            sys.exit(1)
        print("\n  UNKNOWN: No email_sent or email_failed event found.")
        sys.exit(1)


if __name__ == "__main__":
    main()
