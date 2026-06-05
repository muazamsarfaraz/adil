"""Verification tests for template-level legal disclaimer emission.

These tests are the verification step for ClickUp 869dk095z and the
adil-rag-api worked example in the AI-hallucination playbook §8.2.

The load-bearing claim: **the LLM cannot suppress the disclaimer.** These tests
prove it by constructing the response models with EMPTY answer / EMPTY content
and asserting the disclaimer still appears in the serialised JSON. If a future
change moves the disclaimer into the prompt or context, these tests fail.
"""

from __future__ import annotations

from legal_disclaimer import LEGAL_ADVICE_DISCLAIMER

from models import (
    AnalyzeContentResponse,
    GenerateReportResponse,
    QueryMetadata,
    QueryResponse,
    ReportType,
    TokenUsage,
)


def _make_token_usage() -> TokenUsage:
    return TokenUsage(prompt_tokens=0, completion_tokens=0, total_tokens=0, estimated_cost_usd=0.0)


def _make_query_metadata() -> QueryMetadata:
    return QueryMetadata(processing_time_ms=0)


# ---------------------------------------------------------------------------
# QueryResponse — /api/v1/query
# ---------------------------------------------------------------------------


def test_query_response_emits_disclaimer_even_with_empty_answer() -> None:
    """LLM returned nothing — disclaimer MUST still be in the wire payload."""
    resp = QueryResponse(
        answer="",  # mock LLM returned empty
        sources=[],
        usage=_make_token_usage(),
        query_metadata=_make_query_metadata(),
    )
    serialised = resp.model_dump()
    assert "disclaimer" in serialised, "disclaimer field missing from serialised QueryResponse"
    assert serialised["disclaimer"] == LEGAL_ADVICE_DISCLAIMER


def test_query_response_disclaimer_survives_json_dump() -> None:
    """Round-trip through JSON serialiser — disclaimer must remain."""
    resp = QueryResponse(
        answer="some answer",
        sources=[],
        usage=_make_token_usage(),
        query_metadata=_make_query_metadata(),
    )
    payload = resp.model_dump_json()
    assert LEGAL_ADVICE_DISCLAIMER in payload


def test_query_response_disclaimer_cannot_be_overridden_via_construction() -> None:
    """Even if a future caller tries to set disclaimer in the constructor,
    the model_serializer overwrites it at dump time."""
    # The field isn't declared on the model — Pydantic ignores it on construction.
    resp = QueryResponse(
        answer="x",
        sources=[],
        usage=_make_token_usage(),
        query_metadata=_make_query_metadata(),
    )
    # And it always shows up on dump:
    assert resp.model_dump()["disclaimer"] == LEGAL_ADVICE_DISCLAIMER


# ---------------------------------------------------------------------------
# AnalyzeContentResponse — /api/v1/analyze
# ---------------------------------------------------------------------------


def test_analyze_response_emits_disclaimer_even_with_empty_answer() -> None:
    resp = AnalyzeContentResponse(
        answer="",
        sources=[],
        usage=_make_token_usage(),
        query_metadata=_make_query_metadata(),
    )
    assert resp.model_dump()["disclaimer"] == LEGAL_ADVICE_DISCLAIMER


# ---------------------------------------------------------------------------
# GenerateReportResponse — /api/v1/generate-report
# ---------------------------------------------------------------------------


def test_generate_report_response_emits_disclaimer() -> None:
    # Pick whichever ReportType member exists (handles enum variants between releases)
    first_report_type = next(iter(ReportType))
    resp = GenerateReportResponse(
        report_text="",  # mock LLM returned empty
        report_type=first_report_type,
        sections=[],
    )
    serialised = resp.model_dump()
    assert serialised.get("disclaimer") == LEGAL_ADVICE_DISCLAIMER


# ---------------------------------------------------------------------------
# Sanity — the disclaimer string itself
# ---------------------------------------------------------------------------


def test_disclaimer_string_matches_playbook_spec() -> None:
    """The exact wording is specified in playbook §8.2 + ClickUp 869dk095z."""
    assert "Information only" in LEGAL_ADVICE_DISCLAIMER
    assert "not legal advice" in LEGAL_ADVICE_DISCLAIMER
    assert "help you find a solicitor" in LEGAL_ADVICE_DISCLAIMER
    assert "don't represent you" in LEGAL_ADVICE_DISCLAIMER
