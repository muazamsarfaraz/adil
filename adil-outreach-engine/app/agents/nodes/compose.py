"""Compose agent node — generates personalised email from template + research data."""

from __future__ import annotations

import json
import logging
import re

from langchain_core.messages import HumanMessage, SystemMessage

from app.agents.llm import DEFAULT_LLM_CONFIG, get_llm
from app.agents.state import OutreachState

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are an expert email composition agent. Write a highly personalised email using the \
template and research data provided. The email must feel like a human researched this \
firm specifically — never generic.

Instructions from campaign manager:
{compose_instructions}

Template:
Subject: {template_subject}
Body: {template_body}

Research data:
{research_data}

Contact details:
Name: {contact_name}
Firm: {firm_name}
Location: {location}

Sender details:
Sender name: {sender_name}

Outreach history:
{outreach_history}

Rules:
- Replace all {{{{variable}}}} placeholders with appropriate content
- {{{{personalised_intro}}}} MUST lead with the firm's most distinctive achievement, \
specialism, or award — the thing that makes them unique. This is the opening hook.
- If research found awards or rankings (Legal 500, Chambers, Law Society accreditations), \
mention them by name — e.g. "Congratulations on your Legal 500 ranking in immigration law"
- If research found specific case types or niche specialisms (discrimination, hate crime, \
Islamic finance, Islamic wills), reference them directly — e.g. "Your work in discrimination \
and hate crime cases is exactly the kind of specialism our users need"
- If research found languages spoken, mention the community connection — e.g. "The fact that \
your team speaks Urdu and Arabic means you can serve our users in their preferred language"
- NEVER be generic. Do NOT write vague praise like "your excellent reputation" or "your \
well-established firm". Every compliment must reference a SPECIFIC fact from the research.
- If research data is thin (few hooks found), be honest — say "Based on your website..." \
rather than inventing vague praise. A short, honest email beats a long, generic one.
- Keep the email under 200 words. Brevity shows respect for the reader's time.
- Do not invent facts not present in the research data
- Sign off using the sender name "{sender_name}" — never use placeholders like [Your Name] or [Your Name/AskAdil Team]
- Return ONLY the email in this format:
  SUBJECT: <subject line>
  BODY: <email body>
"""


def _resolve_template(campaign: dict, contact: dict) -> tuple[str, str]:
    """Pick the right template based on cadence step."""
    templates = campaign.get("templates", {})
    cadence_step = contact.get("current_cadence_step", 0)

    if cadence_step == 0:
        template = templates.get("initial", {})
    else:
        template = templates.get(f"follow_up_{cadence_step}", templates.get("follow_up", {}))

    subject = template.get("subject", "Introduction from {{sender_name}}")
    body = template.get("body", "Hello {{contact_name}},\n\n{{personalised_intro}}\n\n{{main_content}}")
    return subject, body


def _format_research_data(research_data: dict) -> str:
    """Format research data dict into readable text for the LLM."""
    if not research_data:
        return "No research data available."

    parts = []
    if research_data.get("most_distinctive"):
        parts.append(f"MOST DISTINCTIVE THING ABOUT THIS FIRM: {research_data['most_distinctive']}")
    if research_data.get("personalisation_hooks"):
        hooks = research_data["personalisation_hooks"]
        if isinstance(hooks, list):
            parts.append("Personalisation hooks:\n" + "\n".join(f"- {h}" for h in hooks))
    if research_data.get("firm_description"):
        parts.append(f"Firm description: {research_data['firm_description']}")
    if research_data.get("specialisms"):
        specs = research_data["specialisms"]
        if isinstance(specs, list):
            parts.append("Specialisms & practice areas: " + ", ".join(str(s) for s in specs))
        else:
            parts.append(f"Specialisms & practice areas: {specs}")
    if research_data.get("awards_and_rankings"):
        awards = research_data["awards_and_rankings"]
        if isinstance(awards, list):
            parts.append("Awards & rankings:\n" + "\n".join(f"- {a}" for a in awards))
        else:
            parts.append(f"Awards & rankings: {awards}")
    if research_data.get("sra_status"):
        parts.append(f"SRA status: {research_data['sra_status']}")
    if research_data.get("recent_news"):
        parts.append(f"Recent news: {research_data['recent_news']}")
    if research_data.get("key_people"):
        kp = research_data["key_people"]
        if isinstance(kp, list):
            parts.append("Key people: " + ", ".join(str(p) for p in kp))
        else:
            parts.append(f"Key people: {kp}")
    if research_data.get("languages"):
        langs = research_data["languages"]
        if isinstance(langs, list):
            parts.append("Languages spoken: " + ", ".join(str(lang) for lang in langs))
        else:
            parts.append(f"Languages spoken: {langs}")
    if research_data.get("community_engagement"):
        parts.append(f"Community engagement: {research_data['community_engagement']}")

    return "\n\n".join(parts) if parts else json.dumps(research_data, indent=2)


def _parse_email_response(text: str) -> tuple[str, str]:
    """Parse SUBJECT: ... BODY: ... from the LLM response."""
    subject = ""
    body = ""

    # Try structured parse
    subject_match = re.search(r"SUBJECT:\s*(.+?)(?:\n|$)", text, re.IGNORECASE)
    if subject_match:
        subject = subject_match.group(1).strip()

    body_match = re.search(r"BODY:\s*(.+)", text, re.IGNORECASE | re.DOTALL)
    if body_match:
        body = body_match.group(1).strip()

    # Fallback: if parsing failed, use the whole response
    if not subject and not body:
        lines = text.strip().splitlines()
        if lines:
            subject = lines[0][:100]  # First line as subject
            body = "\n".join(lines[1:]).strip() if len(lines) > 1 else text

    return subject, body


async def compose_node(state: OutreachState) -> dict:
    """
    Compose agent node. Generates personalised email from template + research data.

    Reads: state["contact"], state["campaign"], state["research_data"]
    Writes: state["draft_subject"], state["draft_body"], state["current_step"]
    """
    try:
        contact = state["contact"]
        campaign = state["campaign"]
        research_data = state.get("research_data", {})

        # Resolve LLM config
        llm_config = campaign.get("llm_config", {}).get("compose") or DEFAULT_LLM_CONFIG["compose"]
        llm = get_llm(llm_config, temperature=0.7)

        # Resolve template
        template_subject, template_body = _resolve_template(campaign, contact)

        # Format inputs
        formatted_research = _format_research_data(research_data)

        contact_name = contact.get("name", "")
        firm_name = contact.get("firm_name", "")
        location = ""
        if contact.get("metadata") and isinstance(contact["metadata"], dict):
            location = contact["metadata"].get("location", "")

        # Build outreach history summary
        outreach_history = "No previous outreach."
        events = contact.get("outreach_events", [])
        if events:
            history_parts = []
            for evt in events[-5:]:  # Last 5 events
                history_parts.append(f"- {evt.get('event_type', 'unknown')} on {evt.get('created_at', 'unknown date')}")
            outreach_history = "\n".join(history_parts)

        compose_instructions = campaign.get(
            "compose_instructions",
            "Write a warm, professional outreach email.",
        )

        sender_name = campaign.get("sender_name") or campaign.get("name", "AskAdil Team")

        system_msg = SystemMessage(
            content=_SYSTEM_PROMPT.format(
                compose_instructions=compose_instructions,
                template_subject=template_subject,
                template_body=template_body,
                research_data=formatted_research,
                contact_name=contact_name,
                firm_name=firm_name,
                location=location,
                sender_name=sender_name,
                outreach_history=outreach_history,
            )
        )
        human_msg = HumanMessage(content="Please compose the personalised email now.")

        response = await llm.ainvoke([system_msg, human_msg])
        raw_content = response.content if hasattr(response, "content") else str(response)
        response_text = " ".join(str(c) for c in raw_content) if isinstance(raw_content, list) else str(raw_content)

        subject, body = _parse_email_response(response_text)

        logger.info(
            "Email composed for %s — subject: %s",
            contact_name or "unknown",
            subject[:60],
        )

        return {
            "draft_subject": subject,
            "draft_body": body,
            "current_step": "compose",
        }

    except Exception as e:
        logger.error("Compose node failed: %s", e, exc_info=True)
        return {
            "draft_subject": "",
            "draft_body": "",
            "current_step": "compose",
            "error": f"Compose failed: {e}",
        }
