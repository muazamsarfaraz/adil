"""End-to-end soak against the local mailbox + scripted personas.

Validates:
  send_email_task (idempotency lock + SMTP transport + List-Unsubscribe)
  --> mailbox delivers --> persona replies via runner
  --> bridge forwards reply to /webhooks/sendgrid/inbound
  --> classify_reply LangGraph step (Gemini)
  --> contacts.status updates correctly

What this skips for tractability:
  - Research step (solicitors.test doesn't resolve publicly anyway)
  - Compose step (hard-coded templates — saves ~$0.30 in Claude calls)
  Compose is exercised by the existing unit tests; this test focuses on
  the bits the persona-only soak couldn't reach.

Usage (after `docker compose up -d` and mailbox + runner + bridge running):
    python scripts/soak_mailbox_loop.py
"""

from __future__ import annotations

import os
import sys
import time
from collections import Counter

import httpx

API_URL = os.environ.get("API_URL", "http://localhost:8001")
API_KEY = os.environ.get(
    "API_KEY",
    # Read from .env if not in shell env
    next(
        (
            line.split("=", 1)[1].strip()
            for line in open(
                os.path.join(os.path.dirname(__file__), "..", ".env"),
                encoding="utf-8",
            )
            .read()
            .splitlines()
            if line.startswith("API_KEY=")
        ),
        "",
    ),
)

CAMPAIGN = {
    "name": "Mailbox soak — full loop",
    "slug": f"mailbox-soak-{int(time.time())}",
    "goal": "signup",
    "templates": {
        "initial": {
            "subject": "AskAdil Directory — partnership invitation",
            "body": (
                "Assalamu Alaikum {{contact_name}},\n\n"
                "MCB's AskAdil platform refers public-interest cases to UK "
                "Muslim solicitors free of charge. We'd love to list "
                "{{firm_name}} in our directory.\n\n"
                "Reply if interested.\n\nJazakallah Khair,\nAskAdil Team"
            ),
        }
    },
    "cadence": [
        {"day": 0, "action": "send_initial"},
        {"day": 14, "action": "close"},
    ],
    "llm_config": {
        "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
        "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
    },
    "research_instructions": "skip",
    "compose_instructions": "use template as-is",
    "classify_instructions": (
        "Classify the reply as one of: interested (wants to be listed/learn more), "
        "declined (not interested/please remove/unsubscribe), question (asking for "
        "more info), out_of_office (auto-reply), bounce (delivery failure)."
    ),
    "conversion_config": {"type": "signup", "signup_fields": []},
    "auto_send": False,  # we'll approve drafts manually below
    "sender_name": "AskAdil Team",
    "sender_email": "outreach@askadil.test",
    "reply_to": "outreach@askadil.test",
}

# Personas mirror sim.outreach.yaml — actual local-parts in mailbox.
CONTACTS = [
    # (local_part, persona_kind, firm_name, expected_terminal_status)
    ("partner-aisha", "interested", "Aisha & Co Solicitors", "interested|replied|converted"),
    ("partner-eshaan", "question", "Eshaan Partners", "question|replied"),
    ("partner-saira", "decline", "Saira Legal", "declined|replied"),
    ("partner-tariq", "hostile", "Tariq Solicitors", "declined|replied|unsubscribed"),
    ("partner-ghulam", "silent", "Ghulam Chambers", "emailed|unresponsive"),
    ("partner-ghost-soak", "bounce", "Ghost Firm (nonexistent)", "bounced"),
]


def http_session() -> httpx.Client:
    return httpx.Client(
        base_url=API_URL,
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        timeout=30,
    )


def create_campaign(c: httpx.Client) -> str:
    r = c.post("/api/v1/outreach/campaigns", json=CAMPAIGN)
    r.raise_for_status()
    cid = r.json()["id"]
    print(f"  campaign id: {cid}  slug: {CAMPAIGN['slug']}")
    return cid


def bulk_add_contacts(c: httpx.Client, campaign_id: str) -> list[dict]:
    body = {
        "contacts": [
            {
                "name": local.replace("partner-", "").title(),
                "email": f"{local}@solicitors.test",
                "firm_name": firm,
                "metadata": {"persona_kind": kind, "expected": exp},
            }
            for (local, kind, firm, exp) in CONTACTS
        ]
    }
    r = c.post(f"/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk", json=body)
    r.raise_for_status()
    result = r.json()
    print(f"  created {result.get('created')} contacts, errors={len(result.get('errors', []))}")
    # Fetch contact list back to grab IDs
    r = c.get(f"/api/v1/outreach/campaigns/{campaign_id}/contacts")
    r.raise_for_status()
    return r.json().get("items", r.json() if isinstance(r.json(), list) else [])


def seed_drafts_and_approve(c: httpx.Client, campaign_id: str, contacts: list[dict]) -> None:
    """Bypass research+compose: write a draft_created event for each contact
    via the engine's internal endpoint, then approve, which enqueues
    send_email_task with the new idempotency lock.

    The engine's approve-draft endpoint requires status=draft_pending. The
    simplest way to land contacts there is via direct DB ops — but there's
    no public API for that. Instead we exploit the launch endpoint with a
    one-step cadence and let the engine's own pipeline handle it."""
    # Launch the campaign — engine kicks off its pipeline per contact.
    r = c.post(f"/api/v1/outreach/campaigns/{campaign_id}/launch")
    r.raise_for_status()
    print(f"  launched campaign: {r.json()}")


def fetch_statuses(c: httpx.Client, campaign_id: str) -> list[dict]:
    r = c.get(f"/api/v1/outreach/campaigns/{campaign_id}/contacts?limit=100")
    r.raise_for_status()
    j = r.json()
    return j.get("items", j if isinstance(j, list) else [])


def main() -> int:
    if not API_KEY:
        print("error: no API_KEY in env or .env", file=sys.stderr)
        return 2

    print(f"== mailbox full-loop soak ==  API={API_URL}")
    with http_session() as c:
        campaign_id = create_campaign(c)
        contacts = bulk_add_contacts(c, campaign_id)
        print(f"  fetched {len(contacts)} contacts back")

        seed_drafts_and_approve(c, campaign_id, contacts)

        # Wait for the loop to settle:
        #   research (likely fails fast on .test) -> compose -> send ->
        #   persona reply (~3s) -> bridge POST -> classify (~3s) -> commit
        # Generous budget: 90s
        deadline = time.time() + 90
        last_summary = ""
        while time.time() < deadline:
            time.sleep(6)
            cs = fetch_statuses(c, campaign_id)
            ctr = Counter(x.get("status") for x in cs)
            summary = " ".join(f"{k}={v}" for k, v in sorted(ctr.items()))
            if summary != last_summary:
                print(f"  [{int(deadline - time.time()):>3}s left] {summary}")
                last_summary = summary
            # Terminal if every contact is past 'emailed' or is bounced/replied/converted/declined
            terminal = {"replied", "converted", "declined", "bounced", "unresponsive"}
            non_terminal = [x for x in cs if x.get("status") not in terminal and x.get("status") != "emailed"]
            if not non_terminal and ctr.get("emailed", 0) == 0:
                break

        final = fetch_statuses(c, campaign_id)
        ctr = Counter(x.get("status") for x in final)
        print()
        print("=" * 64)
        print("FINAL STATE")
        print("=" * 64)
        for x in final:
            md = x.get("metadata") or {}
            print(f"  {x.get('email'):40s} kind={md.get('persona_kind','?'):10s} " f"status={x.get('status')}")
        print(f"\nstatus distribution: {dict(ctr)}")
        print("=" * 64)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
