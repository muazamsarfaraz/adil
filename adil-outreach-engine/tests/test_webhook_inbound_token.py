"""Pure-unit tests for SendGrid Inbound Parse bearer-token verification.

No DB, no FastAPI app — just the verifier function with a stubbed Request.
The DB-backed integration tests in tests/test_webhooks.py exercise the same
verifier via the FastAPI dependency wiring; this file makes sure the core
logic is gated even when Postgres isn't available.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _fake_request(query: str = "", auth_header: str | None = None):
    """Build the minimum surface `verify_sendgrid_inbound_token` reads."""
    qp = {}
    if query:
        for kv in query.split("&"):
            if "=" in kv:
                k, v = kv.split("=", 1)
                qp[k] = v
    headers = {}
    if auth_header is not None:
        headers["authorization"] = auth_header
    return SimpleNamespace(query_params=qp, headers=headers)


@pytest.mark.asyncio
async def test_verifier_returns_true_when_disabled():
    from app.auth.webhook_verify import verify_sendgrid_inbound_token

    with patch("app.auth.webhook_verify.settings") as s:
        s.sendgrid_inbound_verify_enabled = False
        s.sendgrid_inbound_token = ""
        assert await verify_sendgrid_inbound_token(_fake_request()) is True


@pytest.mark.asyncio
async def test_verifier_refuses_when_enabled_but_unconfigured():
    """Empty `sendgrid_inbound_token` with verify enabled → reject. This is
    the secure-by-default posture for a misconfigured deploy."""
    from app.auth.webhook_verify import verify_sendgrid_inbound_token

    with patch("app.auth.webhook_verify.settings") as s:
        s.sendgrid_inbound_verify_enabled = True
        s.sendgrid_inbound_token = ""
        assert await verify_sendgrid_inbound_token(_fake_request(query="token=anything")) is False


@pytest.mark.asyncio
async def test_verifier_rejects_missing_token():
    from app.auth.webhook_verify import verify_sendgrid_inbound_token

    with patch("app.auth.webhook_verify.settings") as s:
        s.sendgrid_inbound_verify_enabled = True
        s.sendgrid_inbound_token = "secret"
        assert await verify_sendgrid_inbound_token(_fake_request()) is False


@pytest.mark.asyncio
async def test_verifier_rejects_wrong_token():
    from app.auth.webhook_verify import verify_sendgrid_inbound_token

    with patch("app.auth.webhook_verify.settings") as s:
        s.sendgrid_inbound_verify_enabled = True
        s.sendgrid_inbound_token = "secret"
        assert await verify_sendgrid_inbound_token(_fake_request(query="token=wrong")) is False


@pytest.mark.asyncio
async def test_verifier_accepts_correct_token_in_query():
    from app.auth.webhook_verify import verify_sendgrid_inbound_token

    with patch("app.auth.webhook_verify.settings") as s:
        s.sendgrid_inbound_verify_enabled = True
        s.sendgrid_inbound_token = "secret"
        assert await verify_sendgrid_inbound_token(_fake_request(query="token=secret")) is True


@pytest.mark.asyncio
async def test_verifier_accepts_correct_token_in_authorization_header():
    from app.auth.webhook_verify import verify_sendgrid_inbound_token

    with patch("app.auth.webhook_verify.settings") as s:
        s.sendgrid_inbound_verify_enabled = True
        s.sendgrid_inbound_token = "secret"
        assert await verify_sendgrid_inbound_token(_fake_request(auth_header="Bearer secret")) is True


@pytest.mark.asyncio
async def test_verifier_uses_constant_time_compare():
    """Sanity check that hmac.compare_digest is used (defence-in-depth: the
    compare itself is constant-time, so an attacker can't time-attack the
    token char by char). We assert the import was called when the token is
    wrong — the failure path still goes through compare_digest."""
    import hmac

    from app.auth.webhook_verify import verify_sendgrid_inbound_token

    with (
        patch("app.auth.webhook_verify.settings") as s,
        patch.object(hmac, "compare_digest", wraps=hmac.compare_digest) as spy,
    ):
        s.sendgrid_inbound_verify_enabled = True
        s.sendgrid_inbound_token = "secret"
        await verify_sendgrid_inbound_token(_fake_request(query="token=wrong"))
        assert spy.called, "Expected hmac.compare_digest to gate the token comparison"
