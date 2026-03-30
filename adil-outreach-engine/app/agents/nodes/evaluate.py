"""Evaluate node — checks for replies and decides next action (follow-up vs close)."""

from __future__ import annotations

import logging

from app.agents.state import OutreachState

logger = logging.getLogger(__name__)


async def evaluate_node(state: OutreachState) -> dict:
    """
    Evaluate node. Checks for replies and decides next action.

    This node is the decision point after the "wait" period.
    It determines routing via the return value which conditional edges read.

    Reads: state["contact"], state["campaign"], state["reply_text"]
    Writes: state["current_step"], and routing hints ("has_reply", "action")
    """
    reply_text = state.get("reply_text", "")
    contact = state.get("contact", {})
    campaign = state.get("campaign", {})

    if reply_text:
        logger.info(
            "Evaluate: reply received from %s — routing to classify",
            contact.get("name", "unknown"),
        )
        return {
            "current_step": "evaluate",
            "has_reply": True,
        }

    # No reply — check cadence
    current_step = contact.get("current_cadence_step", 0)
    cadence = campaign.get("cadence", [])
    total_steps = len(cadence) if isinstance(cadence, list) else 0

    if current_step < total_steps - 1:
        logger.info(
            "Evaluate: no reply from %s — cadence step %d/%d — routing to follow_up",
            contact.get("name", "unknown"),
            current_step + 1,
            total_steps,
        )
        return {
            "current_step": "evaluate",
            "has_reply": False,
            "action": "follow_up",
        }

    logger.info(
        "Evaluate: no reply from %s — cadence exhausted — routing to close",
        contact.get("name", "unknown"),
    )
    return {
        "current_step": "evaluate",
        "has_reply": False,
        "action": "close",
    }


def evaluate_router(state: dict) -> str:
    """Route from evaluate node based on reply status and cadence."""
    if state.get("has_reply"):
        return "classify"
    elif state.get("action") == "follow_up":
        return "compose"  # loops back to compose with follow-up template
    else:
        return "close"
