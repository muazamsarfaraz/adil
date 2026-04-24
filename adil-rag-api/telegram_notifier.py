"""Thin Telegram Bot API client for platform-health notifications.

Mirrors adil-document-uploader/app/services/telegram.py so both services
speak to the same @MCB_Adil_Bot chat. Reads TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID from the environment; send() is a no-op if either is
missing so local dev doesn't spam the group.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Final

import httpx

logger = logging.getLogger(__name__)

_MAX_LEN: Final[int] = 3800  # Telegram caps text at 4096; leave headroom for our wrapper

# Dedup: fingerprint -> last-sent epoch. Prevents alert floods during a 429 storm.
_ALERT_COOLDOWN_SECONDS: Final[int] = 600  # 10 minutes
_recent_alerts: dict[str, float] = {}


def _env() -> tuple[str | None, str | None]:
    return os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")


async def notify(text: str, *, parse_mode: str = "Markdown") -> bool:
    """Fire-and-forget Telegram send. Never raises.

    Returns True if the message reached the API, False otherwise (missing
    credentials, network error, API rejection). Truncates overlong text.
    """
    token, chat_id = _env()
    if not token or not chat_id:
        return False
    payload = {
        "chat_id": chat_id,
        "text": text[:_MAX_LEN],
        "parse_mode": parse_mode,
        "disable_web_page_preview": True,
    }
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            resp = await client.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload)
            ok = resp.status_code == 200 and resp.json().get("ok") is True
            if not ok:
                logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text[:200])
            return ok
    except Exception:
        logger.exception("Telegram notifier raised")
        return False


async def notify_error(service: str, endpoint: str, exc: BaseException) -> bool:
    """Format and send a compact error alert.

    Deduplicates identical errors within a 10-minute window so a sustained
    upstream outage (e.g. Gemini monthly spending cap hit) produces one
    alert, not one per user request.
    """
    fp = f"{service}|{endpoint}|{type(exc).__name__}|{str(exc)[:120]}"
    now = time.time()
    last = _recent_alerts.get(fp, 0.0)
    if now - last < _ALERT_COOLDOWN_SECONDS:
        return False
    _recent_alerts[fp] = now
    # Opportunistic GC — keep the dict bounded.
    if len(_recent_alerts) > 256:
        cutoff = now - _ALERT_COOLDOWN_SECONDS
        for k in [k for k, v in _recent_alerts.items() if v < cutoff]:
            _recent_alerts.pop(k, None)

    msg = f"🚨 *{service}* error\n`{endpoint}`\n{type(exc).__name__}: {str(exc)[:400]}"
    return await notify(msg)
