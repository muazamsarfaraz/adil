"""Send node (placeholder) — actual SendGrid integration in Plan 3."""

from __future__ import annotations

import logging

from app.agents.state import OutreachState

logger = logging.getLogger(__name__)


async def send_node(state: OutreachState) -> dict:
    """
    Send node (placeholder). Actual SendGrid integration in Plan 3.

    In production, this node:
    1. Calls SendGrid API to send the email
    2. Logs an outreach_event (email_sent)
    3. Updates contact status to "emailed"
    4. Schedules the first evaluate task via arq

    For now, logs the draft and returns.

    Reads: state["draft_subject"], state["draft_body"], state["contact"]
    Writes: state["current_step"]
    """
    logger.info(
        "[SEND PLACEHOLDER] Would send email to %s: Subject: %s",
        state["contact"].get("email", "unknown"),
        state.get("draft_subject", "N/A"),
    )

    return {"current_step": "send"}
