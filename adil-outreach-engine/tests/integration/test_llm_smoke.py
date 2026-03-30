"""
LLM smoke tests — make real API calls to Gemini.

Verify that agent nodes work with real LLM responses, not mocks.
Skipped when GEMINI_API_KEY is not set.
"""

from __future__ import annotations


import pytest

from app.agents.nodes.classify import classify_node
from app.agents.nodes.compose import compose_node
from app.agents.nodes.research import research_node
from app.agents.state import OutreachState

from tests.integration.conftest import skip_no_gemini

pytestmark = [pytest.mark.integration, skip_no_gemini]

# All tests use Gemini to avoid needing multiple API keys for smoke tests
_LLM_CONFIG = {
    "research": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "compose": {"provider": "gemini", "model": "gemini-2.5-flash"},
    "classify": {"provider": "gemini", "model": "gemini-2.5-flash"},
}


def _make_state(**overrides) -> OutreachState:
    """Build a minimal OutreachState dict with defaults."""
    defaults: dict = {
        "contact_id": "test-contact-id",
        "campaign_id": "test-campaign-id",
        "contact": {
            "name": "Test Contact",
            "email": "test@example.com",
            "firm_name": "Test Firm",
            "website": "https://example.com",
        },
        "campaign": {
            "name": "Integration Test Campaign",
            "slug": "int-test",
            "goal": "signup",
            "llm_config": _LLM_CONFIG,
            "research_instructions": "Research this solicitor firm thoroughly.",
            "compose_instructions": "Write a warm, professional outreach email.",
            "classify_instructions": "Classify the reply accurately.",
            "templates": {
                "initial": {
                    "subject": "Introducing AskAdil to {{firm_name}}",
                    "body": (
                        "Dear {{contact_name}},\n\n"
                        "{{personalised_intro}}\n\n"
                        "AskAdil helps solicitors offer Sharia-compliant wills.\n\n"
                        "Best regards,\nMuazam Ali"
                    ),
                }
            },
            "sender_name": "Muazam Ali",
            "auto_send": False,
        },
        "research_data": {},
        "draft_subject": "",
        "draft_body": "",
        "reply_text": "",
        "classification": "",
        "current_step": "",
        "error": "",
    }
    defaults.update(overrides)
    return defaults


# ---------------------------------------------------------------------------
# Research node tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(90)
async def test_research_node_real_llm():
    """Run research node against I Will Solicitors with real Gemini call."""
    state = _make_state(
        contact={
            "name": "Haroon Rashid",
            "email": "info@iwillsolicitors.com",
            "firm_name": "I Will Solicitors",
            "website": "https://www.iwillsolicitors.com",
        },
    )

    result = await research_node(state)

    assert "research_data" in result
    research = result["research_data"]

    # Verify we got meaningful content, not empty or error
    assert research, "research_data should not be empty"
    assert "error" not in research or research.get(
        "personalisation_hooks"
    ), f"Research returned error without hooks: {research}"

    # Should have at least some content
    has_content = (
        research.get("personalisation_hooks") or research.get("firm_description") or research.get("key_people")
    )
    assert has_content, f"Research data has no meaningful content: {research}"


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(60)
async def test_research_node_bad_website():
    """Run against a nonexistent domain, verify graceful fallback."""
    state = _make_state(
        contact={
            "name": "Nobody Real",
            "email": "nobody@example.com",
            "firm_name": "Nonexistent Firm",
            "website": "https://thisdomaindoesnotexist12345.com",
        },
    )

    # Should NOT crash — should return fallback data
    result = await research_node(state)

    assert "research_data" in result
    assert result["current_step"] == "research"
    # The research may contain an error field but the node itself should not throw


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(60)
async def test_research_javascript_site():
    """Run against a JavaScript-heavy site, verify it doesn't crash."""
    state = _make_state(
        contact={
            "name": "Test User",
            "email": "test@example.com",
            "firm_name": "React App Firm",
            "website": "https://landaulaw.co.uk",
        },
    )

    result = await research_node(state)

    assert "research_data" in result
    assert result["current_step"] == "research"


# ---------------------------------------------------------------------------
# Compose node tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(60)
async def test_compose_node_real_llm():
    """Run compose node with sample research data and template."""
    state = _make_state(
        contact={
            "name": "Haroon Rashid",
            "email": "info@iwillsolicitors.com",
            "firm_name": "I Will Solicitors",
            "website": "https://www.iwillsolicitors.com",
            "metadata": {"location": "Birmingham"},
        },
        research_data={
            "personalisation_hooks": [
                "I Will Solicitors specialise in Islamic wills and inheritance planning",
                "Founded by Haroon Rashid, a solicitor passionate about serving the Muslim community",
                "They offer fixed-fee services for Sharia-compliant wills",
            ],
            "firm_description": (
                "I Will Solicitors is a Birmingham-based law firm specialising in "
                "Islamic wills, inheritance planning, and Sharia-compliant legal services."
            ),
            "sra_status": "Regulated by SRA",
            "key_people": ["Haroon Rashid — Founder"],
            "recent_news": "Expanded services to include online will-writing in 2024",
        },
    )

    result = await compose_node(state)

    assert result["current_step"] == "compose"
    assert result["draft_subject"], "Subject should not be empty"
    assert result["draft_body"], "Body should not be empty"
    assert len(result["draft_body"]) > 50, "Body is too short to be a real email"

    # Verify no leftover placeholders
    body = result["draft_body"]
    subject = result["draft_subject"]
    for placeholder in ["[Your Name]", "[Your Name/AskAdil Team]", "{{contact_name}}", "{{firm_name}}"]:
        assert placeholder not in body, f"Placeholder {placeholder!r} found in body"
        assert placeholder not in subject, f"Placeholder {placeholder!r} found in subject"


# ---------------------------------------------------------------------------
# Classify node tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio(loop_scope="session")
@pytest.mark.timeout(60)
async def test_classify_node_real_llm():
    """Classify sample replies and verify correct categories."""
    test_cases = [
        (
            "Yes I'm interested, this sounds great! Can we set up a call next week?",
            "interested",
        ),
        (
            "No thank you, we're not looking for any new services at the moment. "
            "Please remove us from your mailing list.",
            "declined",
        ),
        (
            "I'm out of the office until next week Monday 7th April. "
            "I will respond to your email on my return. "
            "For urgent matters please contact reception.",
            "out_of_office",
        ),
    ]

    for reply_text, expected_category in test_cases:
        state = _make_state(reply_text=reply_text)
        result = await classify_node(state)

        assert result["current_step"] == "classify"
        actual = result["classification"]
        assert (
            actual == expected_category
        ), f"Reply {reply_text[:40]!r}... classified as {actual!r}, expected {expected_category!r}"
