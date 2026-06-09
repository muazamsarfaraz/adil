#!/usr/bin/env python3
"""Seed script: AskAdil Solicitor Consortium campaign targeting Muslim-lawyer umbrella networks.

Reads data/consortium-umbrella-groups.json and creates a campaign with 7 contacts (one per
umbrella network). Goal: build a consortium where each network promotes AskAdil to its
members and/or shares a vetted referral list, solving the "no public member directories"
problem flagged in `muslim_lawyer_networks_uk_research.md`.

Usage:
    python scripts/seed_consortium_campaign.py --dry-run
    python scripts/seed_consortium_campaign.py --api-url http://localhost:8001 --api-key KEY

Cadence: 4 touches over 21 days — initial, follow-up at day 5, offer-a-call at day 12,
final note at day 21. Polite, non-aggressive — these are peer organisations, not leads.
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

DEFAULT_JSON_PATH = str(Path(__file__).resolve().parent.parent / "data" / "consortium-umbrella-groups.json")

CAMPAIGN_DATA = {
    "name": "Muslim Lawyer Consortium — Umbrella Networks Wave 1",
    "slug": "consortium-wave1",
    "goal": "partnership",
    "templates": {
        "initial": {
            "subject": "AskAdil x {{org_name}} — a partnership proposal for the Muslim legal community",
            "body": (
                "Assalamu Alaikum,\n\n"
                "I'm writing from AskAdil (askadil.org), a free AI-powered UK legal education "
                "platform run by the Muslim Council of Britain. We help British Muslims understand "
                "their rights under UK discrimination, hate-crime, and increasingly broader areas "
                "of law (family, mental capacity, immigration).\n\n"
                "In researching where to refer users, we found a clear gap: the UK has excellent "
                "Muslim lawyer networks — {{org_name}} included — but no public member directories, "
                "and no joined-up referral pathway for community members who need culturally-competent "
                "legal help.\n\n"
                "We'd like to propose a lightweight consortium:\n\n"
                "1. {{org_name}} promotes AskAdil to its members as a referral source for qualified leads\n"
                "2. Members who opt in appear in AskAdil's vetted solicitor directory (free, no hard sell)\n"
                "3. We cross-refer users to {{org_name}} events, training, and advocacy where relevant\n"
                "4. No exclusivity, no money flowing, no data-sharing beyond opt-in listings\n\n"
                "AskAdil currently serves ~1,000+ monthly users across all four UK jurisdictions and "
                "handles 1,000+ real UK case-law judgments grounded via Gemini File Search. We're "
                "adding Mental Capacity Act / Court of Protection coverage this quarter, prompted by "
                "a community request about deputyship for adults with learning disabilities.\n\n"
                "Would you be open to a 30-minute call to discuss? Happy to share the technical docs, "
                "privacy model, and how we vet referrals.\n\n"
                "Jazakallah Khair,\n"
                "Muazam Sarfaraz\n"
                "Lead Developer, AskAdil (MCB)\n"
                "muazam.sarfaraz@gmail.com\n"
                "https://askadil.org"
            ),
        },
        "follow_up_1": {
            "subject": "Re: AskAdil x {{org_name}} — quick follow-up",
            "body": (
                "Assalamu Alaikum,\n\n"
                "Following up on last week's note about a possible consortium between AskAdil and "
                "{{org_name}}. Totally understand if the timing isn't right; wanted to check whether "
                "a short introductory call would be worth scheduling.\n\n"
                "To be concrete on value: we log ~1,000 monthly user conversations covering exactly "
                "the practice areas your members work in — discrimination, family/nikah, immigration, "
                "wills, and (new this quarter) mental capacity / Court of Protection. That's a "
                "pipeline of qualified referrals sitting in front of members who choose to list.\n\n"
                "Would Tuesday or Thursday work for a call?\n\n"
                "Jazakallah Khair,\n"
                "Muazam"
            ),
        },
        "follow_up_2": {
            "subject": "Re: AskAdil consortium — another angle for {{org_name}}",
            "body": (
                "Assalamu Alaikum,\n\n"
                "One more framing that might be more interesting: we can publish a vetted-referrals "
                "resource (one-pager or section on askadil.org) that points users to {{org_name}} for "
                "specific needs — without needing any member data from you. That's the lowest-commitment "
                "way to start, and it benefits your community directly.\n\n"
                "If that's of interest — or if there's a different framing that works better for "
                "{{org_name}} — please let me know.\n\n"
                "Jazakallah Khair,\n"
                "Muazam"
            ),
        },
        "final": {
            "subject": "Re: AskAdil consortium — final note",
            "body": (
                "Assalamu Alaikum,\n\n"
                "Final note — AskAdil remains open to partnering with {{org_name}} whenever the timing "
                "is right. If you'd prefer to reconnect later, feel free to reach out at any point: "
                "muazam.sarfaraz@gmail.com.\n\n"
                "In the meantime, if any of your members would benefit from a free listing on the "
                "AskAdil solicitor directory, the self-serve form is here: {{signup_link}}\n\n"
                "Jazakallah Khair,\n"
                "Muazam Sarfaraz\n"
                "AskAdil (MCB)"
            ),
        },
    },
    "cadence": [
        {"day": 0, "action": "send_initial"},
        {"day": 5, "action": "follow_up", "template": "follow_up_1"},
        {"day": 12, "action": "follow_up", "template": "follow_up_2"},
        {"day": 21, "action": "follow_up", "template": "final"},
        {"day": 28, "action": "close"},
    ],
    "llm_config": {
        "provider": "anthropic",
        "model": "claude-haiku-4-5",
        "temperature": 0.3,
        "personalisation": "low",
        "tone": "respectful-peer",
    },
    "contacts_signup_path": "/solicitor-signup",
}


def load_targets(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_contacts(targets: list[dict]) -> list[dict]:
    contacts = []
    for t in targets:
        contacts.append(
            {
                "name": t["name"],
                "email": t.get("contact_email_guess"),
                "organisation": t["name"],
                "role": t.get("target_role", "Leadership"),
                "website": t.get("website"),
                "contact_url": t.get("contact_url"),
                "metadata": {
                    "entity_id": t["id"],
                    "entity_type": t.get("type", "network"),
                    "estimated_members": t.get("estimated_members"),
                    "rationale": t.get("rationale"),
                    "org_name": t["name"],
                },
            }
        )
    return contacts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", default=DEFAULT_JSON_PATH)
    parser.add_argument("--api-url", default=os.getenv("OUTREACH_API_URL", "http://localhost:8001"))
    parser.add_argument("--api-key", default=os.getenv("OUTREACH_API_KEY", ""))
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    targets = load_targets(args.json)
    contacts = build_contacts(targets)

    payload = {
        "campaign": CAMPAIGN_DATA,
        "contacts": contacts,
    }

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        print(f"\n[dry-run] Would create campaign with {len(contacts)} contacts.")
        return 0

    if not args.api_key:
        print("ERROR: --api-key required (or set OUTREACH_API_KEY env var)")
        return 2

    resp = httpx.post(
        f"{args.api_url}/api/v1/campaigns/bulk-seed",
        json=payload,
        headers={"X-API-Key": args.api_key},
        timeout=60,
    )
    print(f"Status: {resp.status_code}")
    print(resp.text[:1000])
    return 0 if resp.status_code < 300 else 1


if __name__ == "__main__":
    sys.exit(main())
