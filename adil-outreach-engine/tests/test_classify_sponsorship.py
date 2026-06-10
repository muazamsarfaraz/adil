"""Unit tests for sponsorship_interest extraction in the classify node.

Pure-unit — no DB, no LLM call. Tests the parser only.
"""

from __future__ import annotations

import pytest

from app.agents.nodes.classify import _normalise, _parse_classification


# ---------------------------------------------------------------------------
# _normalise — type guarantees for the new sponsorship_interest field
# ---------------------------------------------------------------------------


def test_normalise_defaults_missing_field_to_false():
    out = _normalise({"category": "interested", "confidence": 0.9})
    assert out["sponsorship_interest"] is False


def test_normalise_passes_bool_through():
    out = _normalise({"category": "interested", "sponsorship_interest": True})
    assert out["sponsorship_interest"] is True


def test_normalise_coerces_truthy_string():
    for v in ("true", "yes", "1", "True", "YES"):
        out = _normalise({"category": "interested", "sponsorship_interest": v})
        assert out["sponsorship_interest"] is True, f"expected True for {v!r}"


def test_normalise_coerces_falsy_string():
    for v in ("false", "no", "0", "", "maybe"):
        out = _normalise({"category": "interested", "sponsorship_interest": v})
        assert out["sponsorship_interest"] is False, f"expected False for {v!r}"


# ---------------------------------------------------------------------------
# _parse_classification — JSON parse paths preserve the new field
# ---------------------------------------------------------------------------


def test_parser_direct_json_preserves_sponsorship_true():
    raw = '{"category": "interested", "confidence": 0.95, "sponsorship_interest": true}'
    result = _parse_classification(raw)
    assert result["category"] == "interested"
    assert result["sponsorship_interest"] is True


def test_parser_direct_json_defaults_when_field_omitted():
    raw = '{"category": "interested", "confidence": 0.95}'
    result = _parse_classification(raw)
    assert result["sponsorship_interest"] is False


def test_parser_markdown_codeblock_preserves_sponsorship():
    raw = """Here is my analysis:
```json
{"category": "interested", "confidence": 0.9, "sponsorship_interest": true}
```
"""
    result = _parse_classification(raw)
    assert result["sponsorship_interest"] is True


def test_parser_brace_fallback_preserves_sponsorship():
    raw = 'Some prose. {"category": "interested", "sponsorship_interest": true} trailing.'
    result = _parse_classification(raw)
    assert result["sponsorship_interest"] is True


def test_parser_string_match_fallback_defaults_to_false():
    """When we can only string-match the category, we lack confidence in any
    Q2-yes signal — default to False."""
    raw = "The user seems interested in proceeding."
    result = _parse_classification(raw)
    assert result["category"] == "interested"
    assert result["sponsorship_interest"] is False


def test_parser_ultimate_fallback_defaults_to_false():
    raw = "totally unparseable response"
    result = _parse_classification(raw)
    assert result["category"] == "question"
    assert result["sponsorship_interest"] is False


# ---------------------------------------------------------------------------
# Realistic LLM-output samples (acceptance-style)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "reply_label,raw,want_sponsorship",
    [
        (
            "happy-to-sponsor",
            '{"category": "interested", "confidence": 0.95, "sponsorship_interest": true, "extracted_data": {}}',
            True,
        ),
        (
            "just-listing-not-sponsor",
            '{"category": "interested", "confidence": 0.9, "sponsorship_interest": false, "extracted_data": {"notes": "Q1 yes, Q2 silent"}}',
            False,
        ),
        (
            "declined-everything",
            '{"category": "declined", "confidence": 0.85, "sponsorship_interest": false, "extracted_data": {}}',
            False,
        ),
        (
            "out-of-office",
            '{"category": "out_of_office", "confidence": 0.99, "sponsorship_interest": false, "extracted_data": {"return_date": "2026-06-20"}}',
            False,
        ),
    ],
)
def test_realistic_llm_outputs(reply_label: str, raw: str, want_sponsorship: bool):
    result = _parse_classification(raw)
    assert result["sponsorship_interest"] is want_sponsorship, f"failed for {reply_label}"
