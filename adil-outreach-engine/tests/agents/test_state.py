"""Tests for OutreachState TypedDict."""

from app.agents.state import OutreachState


def test_outreach_state_can_be_instantiated():
    """OutreachState can be created with all fields."""
    state: OutreachState = {
        "contact_id": "c-123",
        "campaign_id": "camp-456",
        "contact": {"name": "John Smith", "email": "john@example.com"},
        "campaign": {"name": "Test Campaign"},
        "research_data": {},
        "draft_subject": "",
        "draft_body": "",
        "reply_text": "",
        "classification": "",
        "current_step": "research",
        "error": "",
    }
    assert state["contact_id"] == "c-123"
    assert state["campaign_id"] == "camp-456"
    assert state["current_step"] == "research"


def test_outreach_state_has_all_expected_keys():
    """OutreachState has all keys defined in the spec."""
    expected_keys = {
        "contact_id",
        "campaign_id",
        "contact",
        "campaign",
        "research_data",
        "draft_subject",
        "draft_body",
        "reply_text",
        "classification",
        "current_step",
        "error",
    }
    # TypedDict __annotations__ has all declared keys
    assert set(OutreachState.__annotations__.keys()) == expected_keys


def test_outreach_state_key_access():
    """OutreachState values are accessible by key."""
    state: OutreachState = {
        "contact_id": "c-1",
        "campaign_id": "camp-1",
        "contact": {"name": "Jane"},
        "campaign": {"name": "Outreach 1"},
        "research_data": {"hooks": ["award winner"]},
        "draft_subject": "Hello",
        "draft_body": "Dear Jane...",
        "reply_text": "Thanks for your email",
        "classification": "interested",
        "current_step": "classify",
        "error": "",
    }
    assert state["research_data"]["hooks"] == ["award winner"]
    assert state["draft_subject"] == "Hello"
    assert state["classification"] == "interested"
