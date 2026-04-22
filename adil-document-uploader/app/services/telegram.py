from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Sends messages to a Telegram chat via the Bot API."""

    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._base = f"https://api.telegram.org/bot{bot_token}"

    async def send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Send a message. Returns True on success, False on failure."""
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._base}/sendMessage",
                    json={"chat_id": self.chat_id, "text": text, "parse_mode": parse_mode},
                )
                ok = resp.status_code == 200 and resp.json().get("ok") is True
                if not ok:
                    logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text[:200])
                return ok
        except Exception:
            logger.exception("Telegram send exception")
            return False
