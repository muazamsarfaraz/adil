"""Shared fixtures for integration tests."""

from __future__ import annotations

import os
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.campaign import Campaign, CampaignGoal, CampaignStatus
from app.models.contact import Contact, ContactStatus

# ---------------------------------------------------------------------------
# Skip helpers
# ---------------------------------------------------------------------------

HAS_DATABASE_URL = bool(os.environ.get("DATABASE_URL"))
HAS_GEMINI_KEY = bool(os.environ.get("GEMINI_API_KEY"))
HAS_STAGING = bool(os.environ.get("OUTREACH_BASE_URL") and os.environ.get("OUTREACH_API_KEY"))

skip_no_postgres = pytest.mark.skipif(not HAS_DATABASE_URL, reason="DATABASE_URL not set — skipping Postgres tests")
skip_no_gemini = pytest.mark.skipif(not HAS_GEMINI_KEY, reason="GEMINI_API_KEY not set — skipping LLM tests")
skip_no_staging = pytest.mark.skipif(not HAS_STAGING, reason="OUTREACH_BASE_URL / OUTREACH_API_KEY not set")


# ---------------------------------------------------------------------------
# Async Postgres session fixture
# ---------------------------------------------------------------------------


def _async_url(raw: str) -> str:
    """Convert postgresql:// to postgresql+asyncpg:// if needed."""
    if raw.startswith("postgresql://"):
        return raw.replace("postgresql://", "postgresql+asyncpg://", 1)
    if raw.startswith("postgres://"):
        return raw.replace("postgres://", "postgresql+asyncpg://", 1)
    return raw


@pytest.fixture
async def pg_session():
    """Yield an async Postgres session, creating tables before and dropping after."""
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        pytest.skip("DATABASE_URL not set")

    engine = create_async_engine(_async_url(database_url), echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with session_factory() as session:
        yield session

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)

    await engine.dispose()


# ---------------------------------------------------------------------------
# Campaign + contact factory fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def make_campaign():
    """Factory to create a Campaign ORM object (not yet committed)."""

    def _make(**overrides) -> Campaign:
        defaults = {
            "name": f"Integration Test Campaign {uuid.uuid4().hex[:6]}",
            "slug": f"int-test-{uuid.uuid4().hex[:8]}",
            "goal": CampaignGoal.signup,
            "status": CampaignStatus.draft,
            "templates": {
                "initial": {
                    "subject": "Introducing AskAdil — Islamic wills made simple",
                    "body": (
                        "Dear {{contact_name}},\n\n"
                        "{{personalised_intro}}\n\n"
                        "AskAdil is a Sharia-compliant will-writing platform. "
                        "We'd love to partner with {{firm_name}}.\n\n"
                        "Best regards,\nMuazam Ali"
                    ),
                }
            },
            "cadence": [{"step": 0, "delay_days": 0}, {"step": 1, "delay_days": 3}],
            "llm_config": {
                "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
                "compose": {"provider": "gemini", "model": "gemini-2.5-flash"},
                "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
            },
            "sender_name": "Muazam Ali",
            "sender_email": "muazam@askadil.com",
            "auto_send": False,
        }
        defaults.update(overrides)
        return Campaign(**defaults)

    return _make


@pytest.fixture
def make_contact():
    """Factory to create a Contact ORM object (not yet committed)."""

    def _make(campaign_id: uuid.UUID, **overrides) -> Contact:
        defaults = {
            "campaign_id": campaign_id,
            "name": f"Test Contact {uuid.uuid4().hex[:6]}",
            "email": f"test-{uuid.uuid4().hex[:6]}@example.com",
            "firm_name": "Test Firm",
            "website": "https://example.com",
            "status": ContactStatus.pending,
        }
        defaults.update(overrides)
        return Contact(**defaults)

    return _make
