"""Research agent node — enriches contact data using scraper, SRA, and web search tools."""

from __future__ import annotations

import json
import logging

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import DEFAULT_LLM_CONFIG, get_llm
from app.agents.state import OutreachState
from app.agents.tools.scraper import scrape_website
from app.agents.tools.sra import search_sra_register
from app.agents.tools.web_search import search_web

logger = logging.getLogger(__name__)

_TOOLS = [scrape_website, search_sra_register, search_web]

_SYSTEM_PROMPT = """\
You are a thorough legal research agent. Your job is to deeply research the following \
solicitor firm and gather SPECIFIC, DISTINCTIVE personalisation hooks for an outreach email.

Contact: {contact_info}

Instructions from campaign manager:
{research_instructions}

Use the available tools to:
1. Scrape the firm's website (if provided) — start with the homepage, then follow links \
to "About Us", "Our Team", "Practice Areas", and "Services" pages to get full coverage
2. Check the SRA register for regulatory status and accreditations
3. Search the web for recent news, awards, rankings, or notable mentions

You MUST extract the following where available:
- **Specialisms & practice areas**: List ALL practice areas, especially niche ones like \
discrimination law, hate crime, Islamophobia cases, Islamic finance (Sharia-compliant), \
Islamic wills & inheritance, immigration, asylum, human rights, mental health, housing
- **Awards & rankings**: Legal 500 rankings, Chambers & Partners rankings, Law Society \
accreditations (e.g. Lexcel, CQS), SRA accreditations, any "Firm of the Year" awards
- **Notable cases or achievements**: High-profile cases, landmark rulings, pro bono work, \
community impact, any published case studies
- **Team members**: Key partners, senior solicitors, specialists — especially anyone with \
relevant cultural or language expertise
- **Languages spoken**: Arabic, Urdu, Hindi, Bengali, Punjabi, Somali, Turkish, Farsi, etc.
- **Community engagement**: Work with Muslim communities, mosques, Islamic organisations, \
legal aid provision, free consultations
- **The SINGLE MOST DISTINCTIVE thing about this firm**: What makes them stand out from \
every other solicitor? This is the #1 priority for personalisation — it could be a rare \
specialism, a groundbreaking case, a unique community role, an exceptional award, or a \
niche they dominate

IMPORTANT: Do NOT be generic. Dig deep. If the website mentions discrimination law, hate \
crime work, or community-specific services, those are MORE valuable than generic practice \
areas like conveyancing or personal injury. Niche specialisms are gold for personalisation.

Return a JSON object with:
- "personalisation_hooks": list of 3-5 SPECIFIC hooks (not generic — each must reference \
a concrete fact about the firm)
- "most_distinctive": the single most distinctive/impressive thing about this firm (1 sentence)
- "firm_description": brief description of the firm and what they're known for
- "specialisms": list of all practice areas/specialisms found
- "awards_and_rankings": list of any awards, rankings, or accreditations
- "sra_status": SRA registration details (or "not checked")
- "key_people": list of key people identified with their roles
- "languages": list of languages spoken at the firm
- "recent_news": any recent news or notable mentions
- "community_engagement": any community-focused work or affiliations
- "best_contact_email": the best email to reach the contact (from website if different)
"""


def _build_contact_info(contact: dict) -> str:
    """Format contact dict into a readable string for the system prompt."""
    parts = []
    if contact.get("name"):
        parts.append(f"Name: {contact['name']}")
    if contact.get("email"):
        parts.append(f"Email: {contact['email']}")
    if contact.get("firm_name"):
        parts.append(f"Firm: {contact['firm_name']}")
    if contact.get("website"):
        parts.append(f"Website: {contact['website']}")
    if contact.get("metadata") and isinstance(contact["metadata"], dict):
        location = contact["metadata"].get("location")
        if location:
            parts.append(f"Location: {location}")
    return "\n".join(parts) if parts else "No contact details available"


def _parse_research_json(text: str) -> dict:
    """Best-effort extraction of JSON from LLM text response."""
    # Try direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        pass

    # Try extracting JSON from markdown code block
    import re

    match = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except (json.JSONDecodeError, TypeError):
            pass

    # Try finding first { ... } block
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])
        except (json.JSONDecodeError, TypeError):
            pass

    # Fallback: return raw text as a hook
    return {
        "personalisation_hooks": [],
        "most_distinctive": "",
        "firm_description": text[:500] if text else "",
        "specialisms": [],
        "awards_and_rankings": [],
        "sra_status": "not checked",
        "key_people": [],
        "languages": [],
        "recent_news": "",
        "community_engagement": "",
        "best_contact_email": "",
        "raw_response": text,
    }


async def research_node(state: OutreachState) -> dict:
    """
    Research agent node. Uses tools to enrich contact data.

    Reads: state["contact"], state["campaign"]
    Writes: state["research_data"], state["current_step"]
    """
    try:
        contact = state["contact"]
        campaign = state["campaign"]

        # Resolve LLM config
        llm_config = campaign.get("llm_config", {}).get("research") or DEFAULT_LLM_CONFIG["research"]
        llm = get_llm(llm_config, temperature=0.2)

        # Bind tools for ReAct-style calling
        llm_with_tools = llm.bind_tools(_TOOLS)

        # Build messages
        contact_info = _build_contact_info(contact)
        research_instructions = campaign.get("research_instructions", "Research this contact thoroughly.")

        system_msg = SystemMessage(
            content=_SYSTEM_PROMPT.format(
                contact_info=contact_info,
                research_instructions=research_instructions,
            )
        )
        human_msg = HumanMessage(content="Please research this contact and return the JSON research data.")

        messages = [system_msg, human_msg]

        # ReAct loop: invoke LLM, execute tool calls, feed results back
        max_iterations = 8
        for _ in range(max_iterations):
            response = await llm_with_tools.ainvoke(messages)
            messages.append(response)

            # Check if there are tool calls
            if not response.tool_calls:
                break

            # Execute each tool call
            from langchain_core.messages import ToolMessage

            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]

                # Find and execute the matching tool
                tool_fn = {t.name: t for t in _TOOLS}.get(tool_name)
                if tool_fn:
                    try:
                        result = await tool_fn.ainvoke(tool_args)
                        # Guard against non-string results
                        if isinstance(result, list):
                            result = "\n".join(str(item) for item in result)
                        elif not isinstance(result, str):
                            result = str(result)
                    except Exception as tool_err:
                        logger.warning(
                            "Tool %s failed for %s: %s — continuing with remaining tools",
                            tool_name,
                            contact.get("name", "unknown"),
                            tool_err,
                        )
                        result = (
                            f"Tool '{tool_name}' encountered an error: {tool_err}. "
                            f"Please continue with the remaining tools and data you have."
                        )
                else:
                    result = f"Unknown tool: {tool_name}"

                messages.append(ToolMessage(content=str(result), tool_call_id=tool_call["id"]))

        # Parse the final response — content may be str or list of content blocks
        raw_content = response.content if hasattr(response, "content") else str(response)
        if isinstance(raw_content, list):
            final_text = " ".join(str(c) for c in raw_content)
        else:
            final_text = str(raw_content)
        research_data = _parse_research_json(final_text)

        logger.info(
            "Research completed for contact %s — found %d personalisation hooks",
            contact.get("name", "unknown"),
            len(research_data.get("personalisation_hooks", [])),
        )

        return {"research_data": research_data, "current_step": "research"}

    except Exception as e:
        logger.error("Research node failed: %s", e, exc_info=True)
        return {
            "research_data": {
                "error": str(e),
                "personalisation_hooks": [],
            },
            "current_step": "research",
            "error": f"Research failed: {e}",
        }
