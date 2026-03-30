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

Reply text:
{reply_text}

Previous outreach context:
{outreach_context}

Return a JSON object:
{{
  "category": "<one of the categories above>",
  "confidence": <0.0-1.0>,
  "extracted_data": {{<any relevant extracted info like return date for OOO, specific questions, etc.>}}
}}
"""


def _parse_classification(text: str) -> dict:
    """Parse classification JSON from LLM response with fallbacks."""
    # Try direct JSON parse
    try:
        result = json.loads(text)
        if isinstance(result, dict) and result.get("category") in VALID_CATEGORIES:
            return result
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting JSON from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group(1).strip())
            if isinstance(result, dict) and result.get("category") in VALID_CATEGORIES:
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    # Try finding first { ... } block
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            result = json.loads(text[brace_start : brace_end + 1])
            if isinstance(result, dict) and result.get("category") in VALID_CATEGORIES:
                return result
        except (json.JSONDecodeError, TypeError):
            pass

    # String matching fallback
    text_lower = text.lower()
    for category in VALID_CATEGORIES:
        if category in text_lower:
            return {
                "category": category,
                "confidence": 0.5,
                "extracted_data": {"parse_method": "string_match"},
            }

    # Ultimate fallback — safest default routes to human review
    return {
        "category": "question",
        "confidence": 0.0,
        "extracted_data": {"parse_method": "fallback", "raw_response": text[:200]},
    }


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
        }

    except Exception as e:
        logger.error("Classify node failed: %s", e, exc_info=True)
        # Default to "question" — safest fallback, routes to human review
        return {
            "classification": "question",
            "current_step": "classify",
            "error": f"Classify failed: {e}",
        }
