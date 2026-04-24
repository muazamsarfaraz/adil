"""Thin Telegram Bot API client for platform-health notifications.

Mirrors adil-document-uploader/app/services/telegram.py so both services
speak to the same @MCB_Adil_Bot chat. Reads TELEGRAM_BOT_TOKEN and
TELEGRAM_CHAT_ID from the environment; send() is a no-op if either is
missing so local dev doesn't spam the group.
"""

from __future__ import annotations

import logging
import os
from typing import Final

import httpx

logger = logging.getLogger(__name__)

_MAX_LEN: Final[int] = 3800  # Telegram caps text at 4096; leave headroom for our wrapper


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
    """Format and send a compact error alert."""
    msg = f"🚨 *{service}* error\n" f"`{endpoint}`\n" f"{type(exc).__name__}: {str(exc)[:400]}"
    return await notify(msg)
