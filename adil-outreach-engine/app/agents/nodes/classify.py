"""Classify agent node — classifies reply text into categories."""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import DEFAULT_LLM_CONFIG, get_llm
from app.agents.state import OutreachState

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"interested", "declined", "question", "out_of_office", "bounce"}

_SYSTEM_PROMPT = """\
You are an email reply classification agent.

Instructions from campaign manager:
{classify_instructions}

Classify the following reply into exactly one of these categories:
- interested: The contact is interested and wants to proceed
- declined: The contact explicitly declines or opts out
- question: The contact has questions and needs more information
- out_of_office: Auto-reply / out of office message
- bounce: Delivery failure / invalid email

In addition, the Wave-1 outreach to UK Muslim solicitors asks TWO things:
  Q1) Would you like a free listing in the AskAdil solicitor directory?
  Q2) Would you also be willing to sponsor / support AskAdil financially?

Independently of the main `category`, detect whether the contact has
affirmatively answered Q2 (sponsorship). Examples that COUNT as Q2-yes:
"happy to sponsor", "yes I'd donate", "we can support you", "send me payment
details", "willing to contribute". Examples that DO NOT count: "interested
in the listing" (that's Q1, not Q2), "I'll think about sponsoring later"
(uncertain), "depends on the cost" (uncertain).

Default `sponsorship_interest` to false unless the affirmative is clear.

Reply text:
{reply_text}

Previous outreach context:
{outreach_context}

Return a JSON object:
{{
  "category": "<one of the categories above>",
  "confidence": <0.0-1.0>,
  "sponsorship_interest": <true or false>,
  "extracted_data": {{<any relevant extracted info like return date for OOO, specific questions, etc.>}}
}}
"""


def _normalise(result: dict) -> dict:
    """Guarantee `sponsorship_interest` exists and is bool. Default False.

    The LLM may omit the field or return a truthy string. Force the type so
    downstream callers don't have to guard.
    """
    raw = result.get("sponsorship_interest", False)
    if isinstance(raw, str):
        result["sponsorship_interest"] = raw.strip().lower() in {"true", "yes", "1"}
    else:
        result["sponsorship_interest"] = bool(raw)
    return result


def _parse_classification(text: str) -> dict:
    """Parse classification JSON from LLM response with fallbacks."""
    # Try direct JSON parse
    try:
        result = json.loads(text)
        if isinstance(result, dict) and result.get("category") in VALID_CATEGORIES:
            return _normalise(result)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting JSON from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, dict) and result.get("category") in VALID_CATEGORIES:
                return _normalise(result)
        except (json.JSONDecodeError, TypeError):
            pass

    # Try finding first { ... } block
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            result = json.loads(text[brace_start : brace_end + 1])
            if isinstance(result, dict) and result.get("category") in VALID_CATEGORIES:
                return _normalise(result)
        except (json.JSONDecodeError, TypeError):
            pass

    # String matching fallback — never claims sponsorship_interest in this
    # path (we'd need to actually understand the text to be confident).
    text_lower = text.lower()
    for category in VALID_CATEGORIES:
        if category in text_lower:
            return _normalise(
                {
                    "category": category,
                    "confidence": 0.5,
                    "extracted_data": {"parse_method": "string_match"},
                }
            )

    # Ultimate fallback — safest default routes to human review.
    return _normalise(
        {
            "category": "question",
            "confidence": 0.0,
            "extracted_data": {"parse_method": "fallback", "raw_response": text[:200]},
        }
    )


async def classify_node(state: OutreachState) -> dict:
    """
    Classify agent node. Classifies reply text into categories.

    Reads: state["reply_text"], state["campaign"]
    Writes: state["classification"], state["current_step"]
    """
    try:
        reply_text = state.get("reply_text", "")
        campaign = state.get("campaign", {})

        if not reply_text:
            logger.warning("Classify node called with empty reply_text")
            return {
                "classification": "question",
                "current_step": "classify",
            }

        # Resolve LLM config
        llm_config = campaign.get("llm_config", {}).get("classify") or DEFAULT_LLM_CONFIG["classify"]
        llm = get_llm(llm_config, temperature=0.0)

        # Build outreach context summary
        contact = state.get("contact", {})
        outreach_context = "No previous context."
        events = contact.get("outreach_events", [])
        if events:
            ctx_parts = []
            for evt in events[-3:]:
                ctx_parts.append(f"- {evt.get('event_type', 'unknown')}: {evt.get('summary', 'no summary')}")
            outreach_context = "\n".join(ctx_parts)

        classify_instructions = campaign.get(
            "classify_instructions",
            "Classify the reply accurately based on the content.",
        )

        system_msg = SystemMessage(
            content=_SYSTEM_PROMPT.format(
                classify_instructions=classify_instructions,
                reply_text=reply_text,
                outreach_context=outreach_context,
            )
        )
        human_msg = HumanMessage(content="Please classify this reply.")

        response = await llm.ainvoke([system_msg, human_msg])
        raw_content = response.content if hasattr(response, "content") else str(response)
        response_text = " ".join(str(c) for c in raw_content) if isinstance(raw_content, list) else str(raw_content)

        parsed = _parse_classification(response_text)
        category = parsed["category"]

        logger.info(
            "Reply classified as '%s' (confidence: %.2f) for contact %s",
            category,
            parsed.get("confidence", 0.0),
            contact.get("name", "unknown"),
        )

        return {
            "classification": category,
            "current_step": "classify",
            # Wave-1 Q2 sponsorship signal — surfaced separately from the main
            # `classification` enum so it can route to the sponsorship_interest
            # table without disturbing the existing graph branches.
            "sponsorship_interest": bool(parsed.get("sponsorship_interest", False)),
        }

    except Exception as e:
        logger.error("Classify node failed: %s", e, exc_info=True)
        # Default to "question" — safest fallback, routes to human review
        return {
            "classification": "question",
            "current_step": "classify",
            "sponsorship_interest": False,
            "error": f"Classify failed: {e}",
        }
