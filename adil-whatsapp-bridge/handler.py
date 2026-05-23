"""
handler.py — inbound WhatsApp message dispatch + onboarding flow.

Pipeline:
  1. Parse Meta webhook payload, find user message(s).
  2. Per phone: enforce daily cost cap, then per-phone rate limit.
  3. Privacy/consent gate — on first contact, ask for YES.
  4. Jurisdiction gate — ask for 1/2/3 if not set.
  5. Slash-like keywords: ``reset``, ``delete me``, ``report``, ``help``.
  6. Otherwise dispatch to adil-rag-api and reply with formatted answer.

The dispatch never raises out; every branch sends a reply and persists state.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

import asyncpg
import httpx
import session as sess
from formatter import (
    format_sources,
    format_viability,
    split_for_whatsapp,
    to_whatsapp,
)
from meta_client import MetaClient
from rag_client import RagClient

logger = logging.getLogger(__name__)

PRIVACY_NOTICE_URL_DEFAULT = "https://askadil.org/privacy"


@dataclass
class InboundMessage:
    """Single inbound message extracted from a Meta webhook payload."""

    phone: str
    message_id: str
    text: str
    msg_type: str  # "text", "image", "audio", "interactive", "other"
    image_id: str | None = None


def parse_inbound(payload: dict[str, Any]) -> list[InboundMessage]:
    """Extract inbound user messages from a Meta webhook payload.

    Meta sends a deeply nested structure. We tolerate variations and skip
    statuses (delivery/read receipts) — those are echoed back to us but
    don't represent new user input.
    """
    out: list[InboundMessage] = []
    entries = payload.get("entry") or []
    for entry in entries:
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            messages = value.get("messages") or []
            for m in messages:
                phone = (m.get("from") or "").strip()
                msg_id = m.get("id") or ""
                if not phone or not msg_id:
                    continue
                mtype = m.get("type") or "other"
                if mtype == "text":
                    text = (m.get("text") or {}).get("body") or ""
                    out.append(InboundMessage(phone, msg_id, text, "text"))
                elif mtype == "image":
                    img = m.get("image") or {}
                    caption = img.get("caption") or ""
                    out.append(InboundMessage(phone, msg_id, caption, "image", image_id=img.get("id")))
                elif mtype == "interactive":
                    interactive = m.get("interactive") or {}
                    btn = interactive.get("button_reply") or interactive.get("list_reply") or {}
                    text = btn.get("title") or btn.get("id") or ""
                    out.append(InboundMessage(phone, msg_id, text, "interactive"))
                else:
                    out.append(InboundMessage(phone, msg_id, "", mtype))
    return out


WELCOME = (
    "❃ Welcome to AskAdil — free UK legal guidance for British Muslims.\n\n"
    "I cover discrimination, hate crime, deputyship and Court of Protection.\n\n"
    "*I am an educational tool, not a law firm.* Always consult a qualified "
    "solicitor before taking action.\n\n"
    "By continuing you accept our privacy notice: {url}\n\n"
    "Reply *YES* to continue, or *delete me* to remove your data."
)

JURISDICTION_PROMPT = (
    "Thanks. To give you the right answer, which jurisdiction are you in?\n\n"
    "  *1* — England & Wales\n"
    "  *2* — Scotland\n"
    "  *3* — Northern Ireland"
)

HELP = (
    "Send me a legal question in plain English. I'll search UK statute and case "
    "law and reply with an answer plus sources.\n\n"
    "Keywords:\n"
    "  *report* — file a hate-crime report formally\n"
    "  *reset*  — start a new conversation\n"
    "  *delete me* — wipe all data I hold for you\n"
    "  *help*   — show this message"
)


def _classify_jurisdiction_reply(text: str) -> str | None:
    t = text.strip().lower()
    if t in {"1", "ew", "england", "wales", "england & wales", "england and wales"}:
        return "EW"
    if t in {"2", "sco", "scotland"}:
        return "SCO"
    if t in {"3", "ni", "northern ireland", "n. ireland", "n ireland"}:
        return "NI"
    return None


def _is_consent(text: str) -> bool:
    return text.strip().lower() in {"yes", "y", "i agree", "agree", "accept"}


def _is_delete(text: str) -> bool:
    return text.strip().lower() in {"delete me", "delete my data", "forget me", "remove me"}


def _is_reset(text: str) -> bool:
    return text.strip().lower() in {"reset", "start over", "restart", "new"}


def _is_report(text: str) -> bool:
    return text.strip().lower() in {"report", "file report", "submit report"}


def _is_help(text: str) -> bool:
    return text.strip().lower() in {"help", "?", "menu"}


@dataclass
class Dispatcher:
    """Holds the wired dependencies for a single bridge service process."""

    pool: asyncpg.Pool
    meta: MetaClient
    rag: RagClient
    per_minute: int = 20
    per_day: int = 200
    daily_cost_cap_cents: int = 5000
    privacy_url: str = PRIVACY_NOTICE_URL_DEFAULT

    async def _send(self, phone: str, text: str) -> None:
        for chunk in split_for_whatsapp(text):
            try:
                await self.meta.send_text(phone, chunk, preview_url=False)
                await sess.record_outbound(self.pool, cost_cents=1)
            except httpx.HTTPError:
                logger.exception("send_text failed phone=%s", phone)
                return

    async def _cost_cap_open(self) -> bool:
        spent = await sess.daily_outbound_spend_cents(self.pool)
        return spent < self.daily_cost_cap_cents

    async def handle(self, msg: InboundMessage) -> None:
        if not await self._cost_cap_open():
            logger.warning("Daily cost cap hit; dropping outbound for %s", msg.phone)
            return

        s = await sess.load(self.pool, msg.phone)

        rate = await sess.check_rate(self.pool, msg.phone, per_minute=self.per_minute, per_day=self.per_day)
        if not rate.allowed:
            await self._send(
                msg.phone,
                "You're sending messages a bit fast — please try again in " f"~{rate.retry_after_seconds}s.",
            )
            return

        try:
            await self.meta.mark_read(msg.message_id)
        except httpx.HTTPError:
            pass

        text = (msg.text or "").strip()

        if _is_delete(text):
            await sess.delete(self.pool, msg.phone)
            await self._send(
                msg.phone,
                "Done — I've deleted everything I held about you. "
                "Reply *YES* at any time to start a fresh conversation.",
            )
            return

        if not s.has_consent:
            if _is_consent(text):
                await sess.set_consent(self.pool, msg.phone)
                await self._send(msg.phone, JURISDICTION_PROMPT)
            else:
                await self._send(msg.phone, WELCOME.format(url=self.privacy_url))
            return

        if _is_help(text):
            await self._send(msg.phone, HELP)
            return

        if _is_reset(text):
            await sess.reset(self.pool, msg.phone)
            await self._send(
                msg.phone,
                "Conversation cleared. " + JURISDICTION_PROMPT,
            )
            return

        if not s.has_jurisdiction:
            choice = _classify_jurisdiction_reply(text)
            if choice:
                await sess.set_jurisdiction(self.pool, msg.phone, choice)
                label = {
                    "EW": "England & Wales",
                    "SCO": "Scotland",
                    "NI": "Northern Ireland",
                }[choice]
                await self._send(
                    msg.phone,
                    f"Got it — {label}. Ask me anything about your situation.",
                )
            else:
                await self._send(msg.phone, JURISDICTION_PROMPT)
            return

        if _is_report(text):
            await self._send(
                msg.phone,
                "To file a formal hate-crime report, please use the secure form at "
                "https://askadil.org/report — it's wired to the same reporting bridge "
                "as our chat, but needs a few extra fields we can't safely collect "
                "over WhatsApp.",
            )
            return

        if msg.msg_type == "image" and not text:
            await self._send(
                msg.phone,
                "Thanks for the image. Image analysis over WhatsApp is coming soon — "
                "for now, please send a short description of what the image shows and "
                "your question about it.",
            )
            return

        if not text:
            await self._send(
                msg.phone,
                "I didn't catch a question there. Reply *help* to see what I can do.",
            )
            return

        await sess.append_turn(self.pool, msg.phone, "user", text)

        await self._send(msg.phone, "_… looking that up …_")

        history = await sess.history_for_rag(self.pool, msg.phone)
        prefix = f"[user jurisdiction: {s.jurisdiction}]\n"

        try:
            resp = await self.rag.query(prefix + text, history=history[:-1])
        except httpx.HTTPError:
            logger.exception("rag-api call failed")
            await self._send(
                msg.phone,
                "Sorry — I'm having trouble reaching the knowledge base. Please try " "again in a minute.",
            )
            return

        answer_md: str = resp.get("answer") or ""
        sources: list[dict[str, Any]] = resp.get("sources") or []
        viability = resp.get("viability")

        body = to_whatsapp(answer_md)
        tail_parts = [format_sources(sources), format_viability(viability)]
        tail = "\n\n".join(p for p in tail_parts if p)
        if tail:
            body = f"{body}\n\n{tail}"
        body = f"{body}\n\n_Type *report* to file formally, *reset* to start over._"

        await self._send(msg.phone, body)
        await sess.append_turn(self.pool, msg.phone, "model", answer_md)


def build_dispatcher(pool: asyncpg.Pool, meta: MetaClient, rag: RagClient) -> Dispatcher:
    return Dispatcher(
        pool=pool,
        meta=meta,
        rag=rag,
        per_minute=int(os.environ.get("WA_RATE_PER_MINUTE", "20")),
        per_day=int(os.environ.get("WA_RATE_PER_DAY", "200")),
        daily_cost_cap_cents=int(float(os.environ.get("WA_DAILY_COST_CAP_USD", "50")) * 100),
        privacy_url=os.environ.get("PRIVACY_NOTICE_URL", PRIVACY_NOTICE_URL_DEFAULT),
    )
