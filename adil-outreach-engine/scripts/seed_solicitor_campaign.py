#!/usr/bin/env python3
"""Seed script: reads solicitor-directory-comprehensive.json and creates a campaign with bulk contacts.

Usage:
    python scripts/seed_solicitor_campaign.py
    python scripts/seed_solicitor_campaign.py --dry-run
    python scripts/seed_solicitor_campaign.py --api-url http://localhost:8001 --api-key my-key
    python scripts/seed_solicitor_campaign.py --wave 1
"""

import argparse
import json
import os
import sys
from pathlib import Path

import httpx

DEFAULT_JSON_PATH = str(
    Path(__file__).resolve().parent.parent.parent
    / "adil-rag-api"
    / "docs"
    / "plans"
    / "solicitor-directory-comprehensive.json"
)

CAMPAIGN_DATA = {
    "name": "Solicitor Directory Outreach - Wave 1",
    "slug": "solicitor-wave1",
    "goal": "signup",
    "templates": {
        "initial": {
            "subject": "AskAdil \u2014 Free AI Legal Guidance for British Muslims | Directory Listing",
            "body": (
                "Assalamu Alaikum {{contact_name}},\n\n"
                "{{personalised_intro}}\n\n"
                "I\u2019m reaching out from AskAdil, a free AI-powered legal guidance platform "
                "designed specifically for the British Muslim community. We\u2019re building a trusted "
                "solicitor directory to connect our users with qualified legal professionals.\n\n"
                "We\u2019d love to include {{firm_name}} in our directory. Listing is completely free "
                "and takes just 15 minutes to set up.\n\n"
                "Benefits include:\n"
                "- Direct referrals from users seeking legal help in your practice areas\n"
                "- Enhanced online visibility within the Muslim community\n"
                "- A profile showcasing your specialisms and languages spoken\n\n"
                "Would you be available for a brief call this week to discuss?\n\n"
                "Jazakallah Khair,\nAskAdil Team"
            ),
        },
        "follow_up_1": {
            "subject": "Re: AskAdil Solicitor Directory \u2014 Quick Follow-Up",
            "body": (
                "Assalamu Alaikum {{contact_name}},\n\n"
                "I wanted to follow up on my previous email about listing {{firm_name}} "
                "in the AskAdil solicitor directory.\n\n"
                "{{personalised_intro}}\n\n"
                "As a reminder, listing is completely free and takes just 15 minutes to set up.\n\n"
                "Would you be available for a brief call this week?\n\n"
                "Jazakallah Khair,\nAskAdil Team"
            ),
        },
        "follow_up_2": {
            "subject": "Re: AskAdil Directory \u2014 Final Note",
            "body": (
                "Hi {{contact_name}},\n\n"
                "Just a final note \u2014 we\u2019d love to include {{firm_name}} in the AskAdil "
                "solicitor directory. If you\u2019re interested, you can sign up directly here:\n\n"
                "{{signup_link}}\n\n"
                "No obligation, and listing is free.\n\n"
                "Best regards,\nAskAdil Team"
            ),
        },
    },
    "cadence": [
        {"day": 0, "action": "send_initial"},
        {"day": 3, "action": "follow_up", "template": "follow_up_1"},
        {"day": 7, "action": "follow_up", "template": "follow_up_2"},
        {"day": 14, "action": "close"},
    ],
    "llm_config": {
        "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
        "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
        "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
    },
    "research_instructions": (
        "Visit the firm's website and find: the best contact person for partnership enquiries "
        "(ideally a senior partner or business development lead), their key practice areas relevant "
        "to British Muslims, any recent news or awards, and their SRA registration status. "
        "Summarise personalisation hooks."
    ),
    "compose_instructions": (
        "Write a warm, professional outreach email to a solicitor firm. Use the research data to "
        "personalise the opening paragraph. Reference specific details about their firm (awards, "
        "specialisms, team members). The tone should be respectful and community-oriented. "
        "Use 'Assalamu Alaikum' for Muslim-focused firms."
    ),
    "classify_instructions": (
        "Classify the reply as one of: interested (wants to be listed/learn more), "
        "declined (not interested), question (asking for more info), out_of_office (auto-reply), "
        "bounce (delivery failure). Extract any specific concerns or questions mentioned."
    ),
    "conversion_config": {
        "type": "signup",
        "signup_fields": [
            {"name": "firm_name", "type": "text", "required": True},
            {
                "name": "specialisms",
                "type": "multi_select",
                "required": True,
                "options": [
                    "islamic_family_law",
                    "islamic_wills",
                    "islamic_finance",
                    "discrimination",
                    "immigration",
                    "employment",
                    "criminal",
                    "personal_injury",
                    "conveyancing",
                    "commercial",
                ],
            },
            {"name": "free_consultation", "type": "boolean", "required": True},
            {"name": "legal_aid", "type": "boolean", "required": True},
            {
                "name": "languages",
                "type": "multi_select",
                "required": False,
                "options": [
                    "English",
                    "Arabic",
                    "Urdu",
                    "Hindi",
                    "Bengali",
                    "Punjabi",
                    "Somali",
                    "Turkish",
                    "Farsi",
                    "French",
                ],
            },
            {
                "name": "preferred_referral_method",
                "type": "select",
                "required": True,
                "options": ["email", "phone", "form", "any"],
            },
        ],
        "confirmation_email": True,
        "webhook_on_conversion": "https://api.askadil.org/api/v1/solicitors",
    },
    "auto_send": False,
    "sender_name": "AskAdil Team",
    "sender_email": "outreach@askadil.org",
    "reply_to": "outreach@askadil.org",
}


def firm_to_contact(firm: dict) -> dict:
    """Map a firm from the JSON to a contact payload."""
    return {
        "name": firm.get("contact_person") or firm.get("name", firm.get("firm_name", "")),
        "email": firm.get("email", ""),
        "firm_name": firm.get("name", firm.get("firm_name", "")),
        "phone": firm.get("phone"),
        "website": firm.get("website"),
        "metadata": {
            "specialisms": firm.get("specialisms", []),
            "location": ", ".join(firm.get("locations", []))
            if isinstance(firm.get("locations"), list)
            else firm.get("location", ""),
            "source": "solicitor-directory-comprehensive.json",
            "sra_number": firm.get("sra_number"),
            "priority": firm.get("priority", "standard"),
            "wave": firm.get("wave", 1),
            "languages": firm.get("languages", []),
            "notes": firm.get("notable", firm.get("notes", "")),
            "category": firm.get("category", ""),
            "muslim_focus": firm.get("muslim_focus", False),
        },
    }


def main():
    parser = argparse.ArgumentParser(description="Seed the solicitor directory campaign")
    parser.add_argument("--api-url", default="http://localhost:8001", help="Base API URL")
    parser.add_argument(
        "--api-key", default=os.environ.get("OUTREACH_API_KEY", os.environ.get("API_KEY", "")), help="API key"
    )
    parser.add_argument("--json-path", default=DEFAULT_JSON_PATH, help="Path to solicitor JSON")
    parser.add_argument("--dry-run", action="store_true", help="Print plan without making API calls")
    parser.add_argument("--wave", type=int, choices=[1, 2, 3, 4], help="Only seed firms from a specific wave")
    args = parser.parse_args()

    # Load JSON
    json_path = Path(args.json_path)
    if not json_path.exists():
        print(f"ERROR: JSON file not found at {json_path}")
        sys.exit(1)

    with open(json_path) as f:
        data = json.load(f)

    firms = data.get("firms", data.get("directory", []))
    if not firms:
        print("ERROR: No firms found in JSON")
        sys.exit(1)

    # Filter by wave if specified
    if args.wave:
        firms = [f for f in firms if f.get("wave", 1) == args.wave]
        print(f"Filtered to wave {args.wave}: {len(firms)} firms")

    # Map firms to contacts
    contacts = []
    skipped = []
    for firm in firms:
        contact = firm_to_contact(firm)
        if not contact["email"]:
            skipped.append(firm.get("name", firm.get("firm_name", "unknown")))
            continue
        contacts.append(contact)

    print(f"Total firms in JSON: {len(firms)}")
    print(f"Contacts to import: {len(contacts)}")
    if skipped:
        print(f"Skipped (no email): {len(skipped)}")
        for name in skipped:
            print(f"  WARNING: Skipping '{name}' — no email address")

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(f"Would create campaign: {CAMPAIGN_DATA['name']} (slug: {CAMPAIGN_DATA['slug']})")
        print(f"Would import {len(contacts)} contacts")
        for c in contacts[:5]:
            print(f"  - {c['name']} <{c['email']}> ({c['firm_name']})")
        if len(contacts) > 5:
            print(f"  ... and {len(contacts) - 5} more")
        return

    if not args.api_key:
        print("ERROR: No API key provided. Set OUTREACH_API_KEY env var or use --api-key")
        sys.exit(1)

    headers = {"X-API-Key": args.api_key, "Content-Type": "application/json"}
    base = args.api_url.rstrip("/")

    with httpx.Client(timeout=30) as client:
        # Check if campaign already exists
        resp = client.get(f"{base}/api/v1/outreach/campaigns", headers=headers)
        resp.raise_for_status()
        existing = resp.json()
        for item in existing.get("items", []):
            if item.get("slug") == CAMPAIGN_DATA["slug"]:
                print(f"Campaign '{CAMPAIGN_DATA['slug']}' already exists (id: {item['id']}). Skipping creation.")
                campaign_id = item["id"]
                break
        else:
            # Create campaign
            print(f"Creating campaign: {CAMPAIGN_DATA['name']}...")
            resp = client.post(f"{base}/api/v1/outreach/campaigns", headers=headers, json=CAMPAIGN_DATA)
            resp.raise_for_status()
            campaign_id = resp.json()["id"]
            print(f"Campaign created: {campaign_id}")

        # Bulk import contacts (API expects {"contacts": [...]})
        if contacts:
            print(f"Importing {len(contacts)} contacts...")
            resp = client.post(
                f"{base}/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk",
                headers=headers,
                json={"contacts": contacts},
            )
            resp.raise_for_status()
            result = resp.json()
            print(f"Created: {result.get('created', 'unknown')} contacts")
            if result.get("errors"):
                print(f"Errors: {len(result['errors'])}")
                for err in result["errors"]:
                    print(f"  - {err}")

    print("\nDone! Campaign is ready for review.")
    print(f"  Campaign ID: {campaign_id}")
    print(f"  View stats:  curl -H 'X-API-Key: KEY' {base}/api/v1/outreach/campaigns/{campaign_id}/stats")
    print(f"  Launch:       curl -X POST -H 'X-API-Key: KEY' {base}/api/v1/outreach/campaigns/{campaign_id}/launch")


if __name__ == "__main__":
    main()
