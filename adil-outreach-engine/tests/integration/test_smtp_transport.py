"""Integration test for the SMTP email transport against the local mailbox stack.

Auto-skips when:
  * The mailbox docker container is not healthy.
  * No agent is provisioned in mailbox's roster (so we have no real
    SMTP account to authenticate as).

This test is the proof that EmailService can be flipped from SendGrid to
SMTP via the EMAIL_TRANSPORT env var without touching any caller code.
"""

from __future__ import annotations

import asyncio
import email
import ssl
import subprocess
from email.utils import parseaddr
from pathlib import Path

import pytest


MAILBOX_REPO = Path(r"E:\dev\experiments\mailbox")
MAILBOX_ROSTER = MAILBOX_REPO / "data" / "config" / "roster.yaml"


def _container_healthy() -> bool:
    try:
        r = subprocess.run(
            ["docker", "inspect", "-f", "{{.State.Health.Status}}", "mailserver"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return r.returncode == 0 and r.stdout.strip() == "healthy"
    except Exception:
        return False


def _load_roster() -> tuple[str, list[str]]:
    """Return (password, [emails]) from mailbox's roster.yaml."""
    if not MAILBOX_ROSTER.exists():
        return ("", [])
    import yaml

    data = yaml.safe_load(MAILBOX_ROSTER.read_text())
    return data.get("password", "agentpass"), [a["email"] for a in data.get("agents", [])]


_HEALTHY = _container_healthy()
_PASSWORD, _AGENTS = _load_roster()


pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(not _HEALTHY, reason="mailbox container not healthy"),
    pytest.mark.skipif(len(_AGENTS) < 2, reason="mailbox needs at least 2 provisioned agents"),
]


def _expunge(email_addr: str) -> None:
    subprocess.run(
        ["docker", "exec", "mailserver", "doveadm", "expunge", "-u", email_addr, "mailbox", "INBOX", "all"],
        capture_output=True,
        check=False,
        timeout=10,
    )


@pytest.fixture
def smtp_settings(monkeypatch):
    """Flip EmailService to SMTP mode, pointed at the mailbox stack."""
    from app.config import settings

    sender = _AGENTS[0]
    monkeypatch.setattr(settings, "email_transport", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "localhost")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", sender)
    monkeypatch.setattr(settings, "smtp_password", _PASSWORD)
    monkeypatch.setattr(settings, "smtp_use_starttls", True)
    monkeypatch.setattr(settings, "smtp_verify_certs", False)
    return sender


async def _read_inbox(inbox: str, password: str, *, subject_filter: str, timeout: float = 15.0) -> bytes | None:
    """IMAP-poll the inbox until we see a message with the given subject."""
    import aioimaplib

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    client = aioimaplib.IMAP4_SSL("localhost", 993, ssl_context=ctx)
    await client.wait_hello_from_server()
    await client.login(inbox, password)
    await client.select("INBOX")
    try:
        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            _, raw = await client.search("ALL")
            for mid in (raw[0] or b"").split():
                _, data = await client.fetch(mid.decode(), "(RFC822)")
                if len(data) < 2:
                    continue
                if subject_filter.encode() in data[1]:
                    return data[1]
            await asyncio.sleep(0.5)
        return None
    finally:
        try:
            await asyncio.wait_for(client.logout(), timeout=2)
        except Exception:
            pass


@pytest.mark.asyncio
async def test_smtp_transport_delivers_to_mailbox(smtp_settings):
    """EmailService.send_email with EMAIL_TRANSPORT=smtp → real delivery."""
    from app.services.email import EmailService

    sender = smtp_settings
    recipient = _AGENTS[1]
    _expunge(recipient)

    svc = EmailService()
    result = await svc.send_email(
        to_email=recipient,
        from_email=sender,
        from_name="Adil Outreach (test)",
        subject="adil-smtp-transport-test",
        html_body="<p>Hello — proving the SMTP transport works.</p>",
    )

    assert result["status"] == "sent"
    assert result["sendgrid_message_id"], "expected a message id back"

    raw = await _read_inbox(recipient, _PASSWORD, subject_filter="adil-smtp-transport-test")
    assert raw is not None, "message did not land in the recipient's inbox"

    parsed = email.message_from_bytes(raw)
    assert parsed["Subject"] == "adil-smtp-transport-test"
    _, addr = parseaddr(parsed["From"])
    assert addr == sender


@pytest.mark.asyncio
async def test_smtp_transport_preserves_threading_headers(smtp_settings):
    """initial_message_id → In-Reply-To + References preserved."""
    from app.services.email import EmailService

    sender = smtp_settings
    recipient = _AGENTS[1]
    _expunge(recipient)

    parent_id = "parent-msg-12345@adil.test"
    svc = EmailService()
    await svc.send_email(
        to_email=recipient,
        from_email=sender,
        from_name="Adil",
        subject="adil-smtp-thread-test",
        html_body="<p>Follow-up.</p>",
        initial_message_id=parent_id,
    )

    raw = await _read_inbox(recipient, _PASSWORD, subject_filter="adil-smtp-thread-test")
    assert raw is not None
    parsed = email.message_from_bytes(raw)
    assert f"<{parent_id}>" in (parsed["In-Reply-To"] or "")
    assert f"<{parent_id}>" in (parsed["References"] or "")


@pytest.mark.asyncio
async def test_smtp_transport_custom_args_become_x_headers(smtp_settings):
    """custom_args → X-Custom-* headers (mirror of SendGrid metadata)."""
    from app.services.email import EmailService

    sender = smtp_settings
    recipient = _AGENTS[1]
    _expunge(recipient)

    svc = EmailService()
    await svc.send_email(
        to_email=recipient,
        from_email=sender,
        from_name="Adil",
        subject="adil-smtp-customargs-test",
        html_body="<p>x</p>",
        custom_args={"contact_id": "contact-abc", "campaign_id": "camp-xyz"},
    )

    raw = await _read_inbox(recipient, _PASSWORD, subject_filter="adil-smtp-customargs-test")
    assert raw is not None
    parsed = email.message_from_bytes(raw)
    assert parsed["X-Custom-contact_id"] == "contact-abc"
    assert parsed["X-Custom-campaign_id"] == "camp-xyz"


@pytest.mark.asyncio
async def test_smtp_transport_writes_list_unsubscribe_header(smtp_settings):
    """List-Unsubscribe header lands on the message when unsubscribe targets are passed."""
    from app.services.email import EmailService

    sender = smtp_settings
    recipient = _AGENTS[1]
    _expunge(recipient)

    svc = EmailService()
    await svc.send_email(
        to_email=recipient,
        from_email=sender,
        from_name="Adil",
        subject="adil-smtp-listunsub-test",
        html_body="<p>x</p>",
        unsubscribe_mailto="unsub@example.test",
        unsubscribe_url="https://example.test/unsub?cid=abc",
    )

    raw = await _read_inbox(recipient, _PASSWORD, subject_filter="adil-smtp-listunsub-test")
    assert raw is not None
    parsed = email.message_from_bytes(raw)
    lu = parsed["List-Unsubscribe"] or ""
    assert "<https://example.test/unsub?cid=abc>" in lu
    assert "<mailto:unsub@example.test>" in lu
    # One-Click is signalled by a second header when a URL is provided
    assert parsed["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"


@pytest.mark.asyncio
async def test_smtp_transport_bad_auth_raises_permanent_error(monkeypatch):
    """Wrong password → SendGridPermanentError (legacy name, transport-agnostic)."""
    from app.config import settings
    from app.services.email import EmailService, SendGridPermanentError

    sender = _AGENTS[0]
    monkeypatch.setattr(settings, "email_transport", "smtp")
    monkeypatch.setattr(settings, "smtp_host", "localhost")
    monkeypatch.setattr(settings, "smtp_port", 587)
    monkeypatch.setattr(settings, "smtp_username", sender)
    monkeypatch.setattr(settings, "smtp_password", "definitely-not-the-password")
    monkeypatch.setattr(settings, "smtp_use_starttls", True)
    monkeypatch.setattr(settings, "smtp_verify_certs", False)

    svc = EmailService()
    with pytest.raises(SendGridPermanentError):
        await svc.send_email(
            to_email=_AGENTS[1],
            from_email=sender,
            from_name="x",
            subject="adil-smtp-bad-auth",
            html_body="<p>x</p>",
        )
