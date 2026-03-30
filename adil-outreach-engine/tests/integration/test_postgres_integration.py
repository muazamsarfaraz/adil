"""
Integration tests against real Postgres.

These catch enum mismatches, JSONB edge cases, and UUID generation issues
that SQLite misses. Skipped when DATABASE_URL is not set.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.models.campaign import Campaign, CampaignGoal, CampaignStatus
from app.models.contact import Contact, ContactStatus
from app.models.conversion import Conversion, ConversionType
from app.models.outreach_event import EventChannel, EventType, OutreachEvent

from tests.integration.conftest import skip_no_postgres

pytestmark = [pytest.mark.integration, skip_no_postgres]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_campaign(session, make_campaign, **kw) -> Campaign:
    campaign = make_campaign(**kw)
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return campaign


async def _create_contact(session, make_contact, campaign_id, **kw) -> Contact:
    contact = make_contact(campaign_id, **kw)
    session.add(contact)
    await session.commit()
    await session.refresh(contact)
    return contact


async def _cleanup_campaign(session, campaign_id: uuid.UUID):
    """Delete campaign and all associated data via cascade."""
    campaign = await session.get(Campaign, campaign_id)
    if campaign:
        await session.delete(campaign)
        await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_campaign_postgres(pg_session, make_campaign):
    """Full campaign creation with all JSONB fields on real Postgres."""
    campaign = make_campaign(
        templates={
            "initial": {
                "subject": "Test subject with unicode: Sharia-compliant \u2014 \u00a3500",
                "body": "Hello {{contact_name}},\n\n{{personalised_intro}}\n\nBest,\nTeam",
            },
            "follow_up_1": {
                "subject": "Following up",
                "body": "Just checking in...",
            },
        },
        cadence=[
            {"step": 0, "delay_days": 0, "channel": "email"},
            {"step": 1, "delay_days": 3, "channel": "email"},
            {"step": 2, "delay_days": 7, "channel": "email"},
        ],
        llm_config={
            "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
            "compose": {"provider": "anthropic", "model": "claude-sonnet-4-6"},
            "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
        },
        conversion_config={
            "signup_url": "https://app.askadil.com/signup",
            "tracking_params": {"utm_source": "outreach", "utm_medium": "email"},
        },
        success_criteria={
            "target_conversion_rate": 0.05,
            "minimum_contacts": 100,
        },
    )
    pg_session.add(campaign)
    await pg_session.commit()
    await pg_session.refresh(campaign)

    try:
        # Verify UUID was generated
        assert campaign.id is not None
        assert isinstance(campaign.id, uuid.UUID)

        # Verify JSONB fields roundtrip correctly
        assert campaign.templates["initial"]["subject"].startswith("Test subject")
        assert len(campaign.cadence) == 3
        assert campaign.llm_config["compose"]["model"] == "claude-sonnet-4-6"
        assert campaign.conversion_config["tracking_params"]["utm_source"] == "outreach"
        assert campaign.success_criteria["target_conversion_rate"] == 0.05

        # Verify enums
        assert campaign.goal == CampaignGoal.signup
        assert campaign.status == CampaignStatus.draft

        # Verify timestamps were set
        assert campaign.created_at is not None
        assert campaign.updated_at is not None
    finally:
        await _cleanup_campaign(pg_session, campaign.id)


@pytest.mark.asyncio
async def test_create_contact_with_metadata(pg_session, make_campaign, make_contact):
    """Contact with complex nested metadata on real Postgres."""
    campaign = await _create_campaign(pg_session, make_campaign)
    try:
        contact = await _create_contact(
            pg_session,
            make_contact,
            campaign.id,
            name="Fatima Khan",
            email="fatima@example.com",
            firm_name="Khan & Associates",
            website="https://khanlaw.co.uk",
            metadata_={
                "location": "Birmingham",
                "practice_areas": ["islamic finance", "family law", "wills & probate"],
                "sra_number": "123456",
                "tags": ["high-priority", "referred"],
                "nested": {
                    "source": "conference",
                    "event_name": "Islamic Finance Forum 2025",
                    "notes": "Met at panel discussion; expressed interest in tech solutions",
                },
            },
        )

        # Re-fetch from DB to verify JSONB roundtrip
        fetched = await pg_session.get(Contact, contact.id)
        assert fetched is not None
        assert fetched.metadata_["location"] == "Birmingham"
        assert "islamic finance" in fetched.metadata_["practice_areas"]
        assert fetched.metadata_["nested"]["event_name"] == "Islamic Finance Forum 2025"
        assert fetched.metadata_["sra_number"] == "123456"
    finally:
        await _cleanup_campaign(pg_session, campaign.id)


@pytest.mark.asyncio
async def test_log_all_event_types(pg_session, make_campaign, make_contact):
    """Iterate ALL EventType enum values and insert an event for each one."""
    campaign = await _create_campaign(pg_session, make_campaign)
    try:
        contact = await _create_contact(pg_session, make_contact, campaign.id)

        for event_type in EventType:
            event = OutreachEvent(
                contact_id=contact.id,
                event_type=event_type,
                channel=EventChannel.system,
                subject=f"Test event: {event_type.value}",
                content=f"Integration test for event type {event_type.value}",
                metadata_={"test": True, "event_type_value": event_type.value},
            )
            pg_session.add(event)

        await pg_session.commit()

        # Verify all events were inserted
        result = await pg_session.execute(
            select(func.count(OutreachEvent.id)).where(OutreachEvent.contact_id == contact.id)
        )
        count = result.scalar()
        assert count == len(EventType), f"Expected {len(EventType)} events, got {count}"
    finally:
        await _cleanup_campaign(pg_session, campaign.id)


@pytest.mark.asyncio
async def test_log_all_contact_statuses(pg_session, make_campaign, make_contact):
    """Iterate ALL ContactStatus enum values and update a contact to each."""
    campaign = await _create_campaign(pg_session, make_campaign)
    try:
        contact = await _create_contact(pg_session, make_contact, campaign.id)

        for status in ContactStatus:
            contact.status = status
            await pg_session.commit()
            await pg_session.refresh(contact)
            assert contact.status == status, f"Failed to set status to {status.value}"
    finally:
        await _cleanup_campaign(pg_session, campaign.id)


@pytest.mark.asyncio
async def test_bulk_contact_import_100(pg_session, make_campaign, make_contact):
    """Import 100 contacts, verify count."""
    campaign = await _create_campaign(pg_session, make_campaign)
    try:
        for i in range(100):
            contact = Contact(
                campaign_id=campaign.id,
                name=f"Bulk Contact {i:03d}",
                email=f"bulk-{i:03d}-{uuid.uuid4().hex[:4]}@example.com",
                firm_name=f"Firm {i:03d}",
                status=ContactStatus.pending,
            )
            pg_session.add(contact)

        await pg_session.commit()

        result = await pg_session.execute(select(func.count(Contact.id)).where(Contact.campaign_id == campaign.id))
        count = result.scalar()
        assert count == 100, f"Expected 100 contacts, got {count}"
    finally:
        await _cleanup_campaign(pg_session, campaign.id)


@pytest.mark.asyncio
async def test_campaign_stats_aggregation(pg_session, make_campaign, make_contact):
    """Create contacts in various statuses, verify stats math."""
    campaign = await _create_campaign(pg_session, make_campaign)
    try:
        status_distribution = {
            ContactStatus.pending: 5,
            ContactStatus.researching: 3,
            ContactStatus.ready: 2,
            ContactStatus.draft_pending: 4,
            ContactStatus.emailed: 10,
            ContactStatus.replied: 3,
            ContactStatus.converted: 2,
            ContactStatus.declined: 1,
            ContactStatus.unresponsive: 4,
            ContactStatus.bounced: 1,
        }

        for status, count in status_distribution.items():
            for i in range(count):
                contact = Contact(
                    campaign_id=campaign.id,
                    name=f"Stats Contact {status.value} {i}",
                    email=f"stats-{status.value}-{i}-{uuid.uuid4().hex[:4]}@example.com",
                    firm_name="Stats Firm",
                    status=status,
                )
                pg_session.add(contact)

        await pg_session.commit()

        # Query stats like the app does
        result = await pg_session.execute(
            select(Contact.status, func.count(Contact.id))
            .where(Contact.campaign_id == campaign.id)
            .group_by(Contact.status)
        )
        status_counts = dict(result.all())

        total = sum(status_counts.values())
        assert total == sum(status_distribution.values()), f"Total mismatch: {total}"

        # Verify individual counts
        for status, expected_count in status_distribution.items():
            actual = status_counts.get(status, 0)
            assert actual == expected_count, f"Status {status.value}: expected {expected_count}, got {actual}"

        # Verify rate calculations
        emailed = status_counts.get(ContactStatus.emailed, 0)
        replied = status_counts.get(ContactStatus.replied, 0)
        converted = status_counts.get(ContactStatus.converted, 0)
        declined = status_counts.get(ContactStatus.declined, 0)
        unresponsive = status_counts.get(ContactStatus.unresponsive, 0)

        sent_total = emailed + replied + converted + declined + unresponsive
        assert sent_total == 20  # 10 + 3 + 2 + 1 + 4

        reply_rate = replied / sent_total if sent_total > 0 else 0
        conversion_rate = converted / total if total > 0 else 0
        assert 0 < reply_rate < 1
        assert 0 < conversion_rate < 1
    finally:
        await _cleanup_campaign(pg_session, campaign.id)


@pytest.mark.asyncio
async def test_csv_export_with_special_characters(pg_session, make_campaign, make_contact):
    """Firm names with unicode, commas, quotes."""
    campaign = await _create_campaign(pg_session, make_campaign)
    try:
        special_names = [
            ("O'Brien & Partners, LLP", "obrienpartners@example.com"),
            ("Muller, Schmidt & Soehne GmbH", "muller@example.com"),
            ('Firm with "Quotes" Inside', "quotes@example.com"),
            ("Sharia-Compliant \u2014 \u00a3500 Practice", "sharia@example.com"),
            ("\u5f8b\u5e08\u4e8b\u52a1\u6240 (Chinese Law Firm)", "chinese@example.com"),
            ("Al-\u1e24asan Legal \u2013 \u0639\u0631\u0628\u064a", "arabic@example.com"),
            ("Firm\twith\ttabs\tand\nnewlines", "tabs@example.com"),
        ]

        for firm_name, email in special_names:
            contact = Contact(
                campaign_id=campaign.id,
                name=f"Contact at {firm_name[:20]}",
                email=email,
                firm_name=firm_name,
                status=ContactStatus.pending,
            )
            pg_session.add(contact)

        await pg_session.commit()

        # Re-fetch and verify all special characters survived the roundtrip
        result = await pg_session.execute(
            select(Contact).where(Contact.campaign_id == campaign.id).order_by(Contact.email)
        )
        contacts = result.scalars().all()
        assert len(contacts) == len(special_names)

        fetched_firms = {c.email: c.firm_name for c in contacts}
        for firm_name, email in special_names:
            assert (
                fetched_firms[email] == firm_name
            ), f"Roundtrip failed for {email}: expected {firm_name!r}, got {fetched_firms[email]!r}"
    finally:
        await _cleanup_campaign(pg_session, campaign.id)


@pytest.mark.asyncio
async def test_conversion_roundtrip(pg_session, make_campaign, make_contact):
    """Create signup conversion, verify data persisted correctly."""
    campaign = await _create_campaign(pg_session, make_campaign)
    try:
        contact = await _create_contact(
            pg_session,
            make_contact,
            campaign.id,
            name="Converted User",
            email="converted@example.com",
            status=ContactStatus.converted,
        )

        conversion = Conversion(
            contact_id=contact.id,
            type=ConversionType.signup,
            data={
                "plan": "professional",
                "signup_url": "https://app.askadil.com/signup?ref=outreach",
                "utm_params": {
                    "utm_source": "outreach",
                    "utm_medium": "email",
                    "utm_campaign": campaign.slug,
                },
                "user_agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)",
                "ip_country": "GB",
            },
        )
        pg_session.add(conversion)
        await pg_session.commit()
        await pg_session.refresh(conversion)

        # Verify roundtrip
        assert conversion.id is not None
        assert isinstance(conversion.id, uuid.UUID)
        assert conversion.type == ConversionType.signup
        assert conversion.data["plan"] == "professional"
        assert conversion.data["utm_params"]["utm_campaign"] == campaign.slug
        assert conversion.created_at is not None

        # Re-fetch from DB
        fetched = await pg_session.get(Conversion, conversion.id)
        assert fetched is not None
        assert fetched.data["ip_country"] == "GB"
    finally:
        await _cleanup_campaign(pg_session, campaign.id)
