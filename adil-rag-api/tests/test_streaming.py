"""Tests for the SSE streaming endpoint (/api/v1/query/stream)."""

import re

import pytest
from fastapi.testclient import TestClient

API_KEY_VALUE = "test-secret-key-12345"


@pytest.fixture(autouse=True)
def _setup(monkeypatch):
    """Configure auth key and stub out rate-limit DB check for all tests in this module."""
    import app as app_mod

    monkeypatch.setenv("ADIL_API_KEY", API_KEY_VALUE)
    monkeypatch.setattr(app_mod, "API_KEY", API_KEY_VALUE)

    # Bypass the Postgres-backed rate limiter (no DB in unit-test env)
    async def _no_check(pool, limits, identity):  # noqa: ARG001
        return None

    monkeypatch.setattr(app_mod, "check_limits", _no_check)

    # Provide a no-op pool accessor so enforce() dependency resolves cleanly
    async def _fake_pool():
        return None

    monkeypatch.setattr(app_mod, "_get_pool", _fake_pool)


@pytest.fixture
def client():
    import app as app_mod

    return TestClient(app_mod.app)


@pytest.fixture
def auth_headers():
    return {"X-API-Key": API_KEY_VALUE, "X-AskAdil-Client-IP": "7.7.7.7"}


def _install_fake_stream(monkeypatch):
    """Install a fake RAGService.stream_query that yields deterministic SSE events."""
    import app as app_mod

    import rag_service as rag_service_mod

    # Ensure rag_service module global is populated with something (service is created
    # during lifespan; in tests it may be None). Set a sentinel truthy placeholder.
    # The fake stream_query ignores `self`, so a simple object works.
    class _FakeService:
        pass

    monkeypatch.setattr(app_mod, "rag_service", _FakeService())

    async def fake_stream(self, query_text, **kwargs):  # noqa: ARG001
        yield {"event": "token", "data": "Based "}
        yield {"event": "token", "data": "in England"}
        yield {
            "event": "source",
            "data": {
                "type": "statute",
                "title": "Equality Act 2010 §10",
                "url": "https://www.legislation.gov.uk/ukpga/2010/15/section/10",
                "citation": "[1]",
            },
        }
        yield {
            "event": "viability",
            "data": {
                "score": 75,
                "vento_band": "Middle",
                "statutory_footing": True,
                "case_law_precedent": True,
                "quantum_potential": "moderate",
                "evidence_checklist": ["payslips", "grievance letters"],
            },
        }
        yield {
            "event": "done",
            "data": {"conversation_id": None, "sources_count": 1, "tokens_used": 42},
        }

    # Bind the fake as a method on the real class so `rag_service.stream_query(...)` works
    # regardless of the concrete service instance type.
    monkeypatch.setattr(rag_service_mod.RAGService, "stream_query", fake_stream, raising=False)
    # Also attach to the FakeService instance so `app_mod.rag_service.stream_query` works
    monkeypatch.setattr(type(app_mod.rag_service), "stream_query", fake_stream, raising=False)


def test_stream_endpoint_exists(client, auth_headers, monkeypatch):
    """Smoke: endpoint is registered."""
    _install_fake_stream(monkeypatch)
    resp = client.post(
        "/api/v1/query/stream",
        headers=auth_headers,
        json={"query": "test"},
    )
    assert resp.status_code != 404


def test_stream_requires_auth(client):
    """Missing API key is rejected."""
    resp = client.post(
        "/api/v1/query/stream",
        json={"query": "what is indirect discrimination?"},
    )
    assert resp.status_code in (401, 403)


def test_stream_emits_token_source_viability_done(client, auth_headers, monkeypatch):
    """Verify the endpoint emits SSE frames in the expected order."""
    _install_fake_stream(monkeypatch)

    resp = client.post(
        "/api/v1/query/stream",
        headers=auth_headers,
        json={"query": "what is indirect discrimination?"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/event-stream")

    body = resp.text
    # Verify each event type appears at least once, in order
    events_in_order = [m.group(1) for m in re.finditer(r"event: (\w+)", body)]
    assert "token" in events_in_order
    assert "source" in events_in_order
    assert "viability" in events_in_order
    assert "done" in events_in_order
    assert events_in_order.index("token") < events_in_order.index("source")
    assert events_in_order.index("source") < events_in_order.index("viability")
    assert events_in_order.index("viability") < events_in_order.index("done")

    # Verify token payload is JSON-encoded string ("Based " with surrounding quotes)
    tok_match = re.search(r'event: token\ndata: "Based "', body)
    assert tok_match is not None, f"expected JSON-encoded token; got: {body[:500]}"
