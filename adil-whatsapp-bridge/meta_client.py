"""
meta_client.py — Meta WhatsApp Business Cloud Graph API wrapper.

Endpoints documented at https://developers.facebook.com/docs/whatsapp/cloud-api.
This module is intentionally thin: HTTP I/O only. Higher-level policy
(consent, rate limits, cost caps) lives in handler.py.
"""

from __future__ import annotations

import hmac
import logging
import os
from hashlib import sha256
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GRAPH_BASE = "https://graph.facebook.com"


def _graph_url(phone_number_id: str) -> str:
    version = os.environ.get("META_GRAPH_VERSION", "v20.0")
    return f"{GRAPH_BASE}/{version}/{phone_number_id}/messages"


def verify_signature(raw_body: bytes, header_value: str | None, app_secret: str | None) -> bool:
    """Verify Meta's X-Hub-Signature-256 HMAC.

    Header format is ``sha256=<hex>``. Uses ``hmac.compare_digest`` to avoid
    timing leaks. Returns False on any missing input or mismatch.
    """
    if not header_value or not app_secret:
        return False
    if not header_value.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), raw_body, sha256).hexdigest()
    provided = header_value.split("=", 1)[1].strip()
    return hmac.compare_digest(expected, provided)


class MetaClient:
    """Async client for the WhatsApp Cloud API."""

    def __init__(
        self,
        phone_number_id: str,
        access_token: str,
        *,
        timeout: float = 15.0,
    ) -> None:
        self.phone_number_id = phone_number_id
        self.access_token = access_token
        self._timeout = timeout

    async def _post(self, payload: dict[str, Any]) -> dict[str, Any]:
        url = _graph_url(self.phone_number_id)
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            logger.warning("Meta Graph API error %s: %s", resp.status_code, resp.text[:500])
            resp.raise_for_status()
        return resp.json()

    async def send_text(self, to_e164: str, text: str, *, preview_url: bool = False) -> dict[str, Any]:
        """Send a plain-text WhatsApp message. ``to_e164`` must omit the leading +."""
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": to_e164.lstrip("+"),
            "type": "text",
            "text": {"body": text, "preview_url": preview_url},
        }
        return await self._post(payload)

    async def mark_read(self, message_id: str) -> dict[str, Any]:
        payload = {
            "messaging_product": "whatsapp",
            "status": "read",
            "message_id": message_id,
        }
        return await self._post(payload)


def from_env() -> MetaClient | None:
    """Build a client from env, or return None if not configured (dev/test)."""
    pid = os.environ.get("META_PHONE_NUMBER_ID")
    tok = os.environ.get("META_ACCESS_TOKEN")
    if not pid or not tok:
        return None
    return MetaClient(pid, tok)
