#!/usr/bin/env python3
"""
AskAdil (عادل) — AI Legal Assistant
UK Discrimination Law Educational Platform

"Educate First, Litigate Second"
askadil.org — A Muslim Council of Britain Initiative
"""

import base64
import os
import re

import chainlit as cl
import httpx
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- Configuration ---
RAG_API_URL = os.environ.get("RAG_API_URL", "http://localhost:8000")
ADIL_API_KEY = os.environ.get("ADIL_API_KEY", "")

# URL pattern for detection
URL_PATTERN = re.compile(r'https?://[^\s<>"{}|\\^`\[\]]+', re.IGNORECASE)


def has_urls(text: str) -> bool:
    """Check if text contains URLs"""
    return bool(URL_PATTERN.search(text))


# Image upload constraints
ALLOWED_IMAGE_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp"}
MAX_IMAGES = 5
MAX_IMAGE_SIZE_MB = int(os.environ.get("MAX_IMAGE_SIZE_MB", "10"))


@cl.on_chat_start
async def start_chat():
    """Initialize chat session with conversation history and jurisdiction selection"""
    cl.user_session.set("message_count", 0)
    cl.user_session.set("viability_requested", False)
    cl.user_session.set("conversation_history", [])
    cl.user_session.set("jurisdiction", None)

    # Send welcome message with jurisdiction selector
    actions = [
        cl.Action(
            name="select_jurisdiction",
            payload={"jurisdiction": "England & Wales"},
            label="🏴󠁧󠁢󠁥󠁮󠁧󠁿 England & Wales",
        ),
        cl.Action(
            name="select_jurisdiction",
            payload={"jurisdiction": "Scotland"},
            label="🏴󠁧󠁢󠁳󠁣󠁴󠁿 Scotland",
        ),
        cl.Action(
            name="select_jurisdiction",
            payload={"jurisdiction": "Northern Ireland"},
            label="🇬🇧 Northern Ireland",
        ),
    ]

    await cl.Message(
        content=(
            "⚖️ **Welcome to AskAdil (عادل)**\n\n"
            "I'm a free legal education assistant specialising in **UK discrimination law**, "
            "particularly cases affecting British Muslims.\n\n"
            "🇬🇧 **Please select your jurisdiction to get started:**"
        ),
        actions=actions,
    ).send()


@cl.action_callback("select_jurisdiction")
async def on_select_jurisdiction(action: cl.Action):
    """Handle jurisdiction selection at chat start"""
    jurisdiction = action.payload.get("jurisdiction", "")
    cl.user_session.set("jurisdiction", jurisdiction)

    await cl.Message(
        content=(
            f"✅ **Jurisdiction set to: {jurisdiction}**\n\n"
            "📋 **To give you the best guidance, I'll start by asking a few "
            "questions** — like when the incident happened and the details.\n\n"
            "💡 **You can also:**\n"
            "- Upload **screenshots or photos** of messages, letters, or documents for legal analysis\n"
            "- Paste **YouTube / Facebook video / Twitter / Instagram / news article links** for legal analysis (video transcripts extracted automatically)\n"
            "- Ask **follow-up questions** — I remember our conversation\n"
            "- Get **actionable next steps** with real links to organisations like Tell MAMA, ACAS, Citizens Advice, and more\n"
            "- Type **report** to submit a hate crime report to **Police UK**, **Tell MAMA**, **Police Scotland**, **IRU**, **Islamophobia UK**, **EASS**, or **Stop Hate UK** — I'll fill in the forms for you\n"
            "- Get a **confirmation email** with your reference number after submitting a report\n\n"
            "> ⚠️ **AskAdil is an educational tool, not a law firm.** "
            "Always consult a qualified solicitor before taking legal action.\n\n"
            "*Tell me what happened and I'll help you understand your rights.*"
        )
    ).send()


async def _send_query(user_text: str, images: list = None):
    """Core query logic shared by direct messages and action callbacks.

    Sends the user text (with conversation history) to the RAG API,
    displays the answer, sources, suggested follow-ups, and updates
    the session history.
    """
    msg = cl.Message(content="")
    await msg.send()

    try:
        # Retrieve conversation history from session
        history = cl.user_session.get("conversation_history") or []

        # Prepend jurisdiction context to the query
        jurisdiction = cl.user_session.get("jurisdiction")
        if jurisdiction:
            query_with_context = f"[Jurisdiction: {jurisdiction}] {user_text}"
        else:
            query_with_context = user_text

        # Check for URLs
        contains_urls = has_urls(user_text)

        # Show processing indicator for content extraction
        if contains_urls:
            await msg.stream_token("*🔗 Extracting content from URL(s)...*\n\n")

        # Show processing indicator for images
        if images:
            count = len(images)
            await msg.stream_token(f"*📸 Analysing {count} image{'s' if count > 1 else ''}...*\n\n")

        # Check if user is asking about case viability
        viability_keywords = [
            "can i sue",
            "do i have a case",
            "should i take legal action",
            "worth pursuing",
            "viability",
            "compensation",
            "how much",
        ]
        include_viability = any(kw in user_text.lower() for kw in viability_keywords)

        # Build conversation history payload
        history_payload = [{"role": turn["role"], "content": turn["content"]} for turn in history] if history else None

        # Choose endpoint based on content type
        api_headers = {"X-API-Key": ADIL_API_KEY} if ADIL_API_KEY else {}
        async with httpx.AsyncClient(timeout=120.0) as client:
            if images:
                response = await client.post(
                    f"{RAG_API_URL}/api/v1/query/image",
                    headers=api_headers,
                    json={
                        "query": query_with_context or None,
                        "images": images,
                        "include_viability_score": include_viability,
                        "conversation_history": history_payload,
                    },
                )
            elif contains_urls:
                response = await client.post(
                    f"{RAG_API_URL}/api/v1/analyze",
                    headers=api_headers,
                    json={
                        "content": query_with_context,
                        "include_viability_score": include_viability,
                        "conversation_history": history_payload,
                    },
                )
            else:
                response = await client.post(
                    f"{RAG_API_URL}/api/v1/query",
                    headers=api_headers,
                    json={
                        "query": query_with_context,
                        "max_sources": 10,
                        "include_viability_score": include_viability,
                        "conversation_history": history_payload,
                    },
                )
            response.raise_for_status()
            data = response.json()

        # Display answer
        answer = data.get("answer", "")
        await msg.stream_token(answer)

        # Add viability assessment if present
        viability = data.get("viability")
        if viability:
            viability_text = "\n\n---\n📊 **Preliminary Viability Assessment**\n"
            viability_text += f"- Score: {viability.get('score', 'N/A')}/100\n"
            if viability.get("vento_band"):
                viability_text += (
                    f"- Estimated Band: {viability.get('vento_band').title()} ({viability.get('vento_range', '')})\n"
                )
            viability_text += f"\n⚠️ *This is a preliminary assessment. {viability.get('reasoning', '')}*\n"
            if viability.get("requires_hitl"):
                viability_text += "\n🔔 **This case may benefit from professional legal review.**"
            await msg.stream_token(viability_text)

        # Add sources if available
        sources = data.get("sources", [])
        if sources:
            sources_text = "\n\n---\n📚 **Legal Sources:**\n"
            for i, source in enumerate(sources, 1):
                title = source.get("title", "Unknown")
                citation = source.get("neutral_citation", "")
                section = source.get("section", "")
                url = source.get("url", "")
                excerpt = source.get("excerpt", "")

                if section and source.get("act_name"):
                    source_title = f"{section} {source.get('act_name')}"
                elif citation:
                    source_title = f"{title} `{citation}`"
                else:
                    source_title = title

                if url:
                    sources_text += f"\n**{i}. [{source_title}]({url})**\n"
                else:
                    sources_text += f"\n**{i}. {source_title}**\n"

                if excerpt and excerpt != source_title:
                    sources_text += f"> {excerpt}\n"

            await msg.stream_token(sources_text)

        # Add platform-specific advice if present (from analyze endpoint)
        platform_advice = data.get("platform_specific_advice")
        if platform_advice:
            await msg.stream_token(f"\n\n---\n{platform_advice}")

        # Add content summary if present
        content_summary = data.get("content_summary")
        if content_summary:
            await msg.stream_token(f"\n\n📋 *{content_summary}*")

        # Report to police call-to-action (visible in message body)
        report_cta = "\n\n---\n"
        report_cta += "🚨 **Want to report this?**\n"
        report_cta += "Type **report** and I'll submit a report on your behalf to **Police UK**, **Tell MAMA**, **Police Scotland**, or the **IRU** — I'll fill in the form for you."
        await msg.stream_token(report_cta)

        # Persistent legal disclaimer on every response
        disclaimer = "\n\n---\n⚠️ *AskAdil is an educational tool, not a law firm. "
        disclaimer += "This is not legal advice. Always consult a "
        disclaimer += "[qualified solicitor](https://solicitors.lawsociety.org.uk/) "
        disclaimer += "before taking action.*"
        await msg.stream_token(disclaimer)

        # Build suggested-question action buttons
        suggested = data.get("suggested_questions") or []
        actions = []
        for i, question in enumerate(suggested[:3]):
            actions.append(
                cl.Action(
                    name="suggested_question",
                    payload={"question": question},
                    label=question,
                )
            )
        # Add "Report to Police" action button (prominent)
        actions.append(
            cl.Action(
                name="start_report",
                icon="shield-alert",
                payload={"target": "police-uk"},
                label="🚨 Report to Police UK",
                description="Submit a hate crime report to police.uk — AskAdil will fill in the form for you",
            )
        )
        if actions:
            msg.actions = actions

        await msg.update()

        # --- Update conversation history in session ---
        # Use a placeholder for image-only messages (empty content fails
        # ConversationTurn min_length=1 validation on subsequent requests)
        user_content = user_text if user_text.strip() else "[User uploaded image(s) for analysis]"
        history.append({"role": "user", "content": user_content})
        # Store a trimmed version of the answer (without sources/disclaimer)
        history.append({"role": "model", "content": answer})
        # Keep last 20 turns (10 exchanges) to avoid token bloat
        if len(history) > 20:
            history = history[-20:]
        cl.user_session.set("conversation_history", history)

        # Update message count
        count = cl.user_session.get("message_count") or 0
        cl.user_session.set("message_count", count + 1)

    except httpx.TimeoutException:
        await msg.stream_token("⏳ The request timed out. Please try again with a shorter question.")
        await msg.update()
    except httpx.HTTPStatusError as e:
        await msg.stream_token(f"❌ Error connecting to the legal knowledge base: {e.response.status_code}")
        await msg.update()
    except Exception as e:
        await msg.stream_token(f"❌ An unexpected error occurred: {str(e)}")
        await msg.update()


@cl.on_message
async def main(message: cl.Message):
    """Handle incoming messages with URL, image, and conversation memory support"""
    # Check if we're collecting PII for a report
    if await _handle_report_pii(message.content):
        return
    if await _handle_report_consent(message.content):
        return

    # Trigger report flow when user types "report"
    # Trigger report flow — show target selection or start directly
    msg_lower = message.content.strip().lower()
    if msg_lower in ("report", "report to police", "submit report"):
        cl.user_session.set("awaiting_report_target", True)
        await cl.Message(
            content=(
                "📋 **Where would you like to submit your report?**\n\n"
                "Type the number of the organisation:\n\n"
                "**1.** 🚔 **Police UK** — National hate crime report (England & Wales)\n"
                "**2.** 🕌 **Tell MAMA** — Anti-Muslim hate incident report (UK-wide)\n"
                "**3.** 🏴󠁧󠁢󠁳󠁣󠁴󠁿 **Police Scotland** — Hate crime report (Scotland only)\n"
                "**4.** 🛡️ **IRU** — Islamophobia Response Unit (UK-wide)\n"
                "**5.** 📍 **Islamophobia UK** — Anonymous incident tracker (UK-wide, no personal details needed)\n"
                "**6.** 📧 **EASS** — Equality Advisory Support Service (email report)\n"
                "**7.** 📧 **Stop Hate UK** — 24/7 hate crime support (email report)\n\n"
                "Or type **cancel** to go back."
            )
        ).send()
        return

    # Handle target selection
    if cl.user_session.get("awaiting_report_target"):
        cl.user_session.set("awaiting_report_target", False)
        target_map = {
            "1": "police-uk",
            "2": "tell-mama",
            "3": "police-scotland",
            "4": "iru",
            "5": "islamophobia-uk",
            "6": "eass",
            "7": "stop-hate-uk",
        }
        target_names = {
            "police-uk": "Police UK",
            "tell-mama": "Tell MAMA",
            "police-scotland": "Police Scotland",
            "iru": "IRU (Islamophobia Response Unit)",
            "islamophobia-uk": "Islamophobia UK",
            "eass": "EASS",
            "stop-hate-uk": "Stop Hate UK",
        }
        target = target_map.get(msg_lower)
        if not target:
            if msg_lower in ("cancel", "stop", "quit", "no"):
                await cl.Message(content="Report cancelled.").send()
                return
            await cl.Message(content="Please type **1** to **7** to select, or **cancel** to go back.").send()
            cl.user_session.set("awaiting_report_target", True)
            return

        # Targets that don't need PII (anonymous reporting)
        NO_PII_TARGETS = {"islamophobia-uk"}

        cl.user_session.set("report_target", target)
        cl.user_session.set("report_data", {})

        if target in NO_PII_TARGETS:
            # Skip PII collection — go straight to consent with conversation data only
            cl.user_session.set("awaiting_report_consent", True)
            history = cl.user_session.get("conversation_history") or []
            incident_text = "\n".join(turn["content"] for turn in history if turn["role"] == "user")
            consent_msg = (
                f"📋 **Report Submission — {target_names[target]}**\n\n"
                "This form is **anonymous** — no personal details are needed.\n\n"
                "**The following will be submitted from our conversation:**\n"
                f"- Incident summary and description\n"
                "- Location and date/time (if mentioned)\n\n"
                "Type **yes** to submit or **no** to cancel."
            )
            await cl.Message(content=consent_msg).send()
            return

        cl.user_session.set("report_field_index", 0)
        cl.user_session.set("collecting_report_pii", True)
        field_name, prompt, required = REPORT_PII_FIELDS[0]
        await cl.Message(
            content=(
                f"📋 **Report Submission — {target_names[target]}**\n\n"
                "I'll need a few personal details to fill in the reporting form on your behalf.\n\n"
                "**How your data is handled:**\n"
                f"- Your details are sent directly to {target_names[target]} and **immediately discarded** from our system\n"
                "- AskAdil **does not store** your personal information\n"
                "- You will review everything before I submit\n"
                "- You can cancel at any time by typing **cancel**\n\n"
                f"{prompt}"
            )
        ).send()
        return

    images = None

    # Check for image attachments
    if message.elements:
        image_elements = [el for el in message.elements if el.mime and el.mime in ALLOWED_IMAGE_MIMES and el.path]
        if image_elements:
            if len(image_elements) > MAX_IMAGES:
                await cl.Message(content=f"Please upload a maximum of {MAX_IMAGES} images at a time.").send()
                return

            images = []
            for el in image_elements:
                # Check file size
                file_size = os.path.getsize(el.path)
                if file_size > MAX_IMAGE_SIZE_MB * 1024 * 1024:
                    await cl.Message(content=f"Image '{el.name}' exceeds {MAX_IMAGE_SIZE_MB}MB limit.").send()
                    return

                # Read and base64 encode
                with open(el.path, "rb") as f:
                    image_bytes = f.read()
                images.append(
                    {
                        "mime_type": el.mime,
                        "data": base64.b64encode(image_bytes).decode("utf-8"),
                    }
                )

    await _send_query(message.content, images=images)


@cl.action_callback("suggested_question")
async def on_suggested_question(action: cl.Action):
    """Handle clicks on suggested follow-up question buttons"""
    question = action.payload.get("question", "")
    if question:
        await _send_query(question)


# --- Report Submission Flow ---

REPORT_PII_FIELDS = [
    ("first_name", "What is your **first name**?", True),
    ("surname", "What is your **surname**?", True),
    ("dob_str", "What is your **date of birth**? (DD/MM/YYYY)", True),
    ("gender", "What is your **gender**? (Male / Female / Self-describe)", True),
    ("email", "What is your **email address**?", True),
    ("phone", "What is your **phone number**? (optional — press Enter to skip)", False),
]


@cl.action_callback("start_report")
async def on_start_report(action: cl.Action):
    """Handle clicks on 'Report to Police' action button."""
    target = action.payload.get("target", "police-uk")
    cl.user_session.set("report_target", target)
    cl.user_session.set("report_data", {})
    cl.user_session.set("report_field_index", 0)
    cl.user_session.set("collecting_report_pii", True)

    field_name, prompt, required = REPORT_PII_FIELDS[0]
    await cl.Message(
        content=(
            "📋 **Report Submission — Police UK**\n\n"
            "I'll need a few personal details to fill in the police hate crime reporting form on your behalf.\n\n"
            "**How your data is handled:**\n"
            "- Your details are sent directly to police.uk and **immediately discarded** from our system\n"
            "- AskAdil **does not store** your personal information\n"
            "- You will review everything before I submit\n"
            "- You can cancel at any time by typing **cancel**\n\n"
            f"{prompt}"
        )
    ).send()


async def _handle_report_pii(message_text: str):
    """Process PII collection during report flow. Returns True if still collecting."""
    if not cl.user_session.get("collecting_report_pii"):
        return False

    idx = cl.user_session.get("report_field_index", 0)
    data = cl.user_session.get("report_data", {})
    field_name, prompt, required = REPORT_PII_FIELDS[idx]

    value = message_text.strip()

    # Allow cancel at any point
    if value.lower() in ("cancel", "stop", "quit", "no"):
        cl.user_session.set("collecting_report_pii", False)
        cl.user_session.set("report_data", {})
        await cl.Message(content="Report submission cancelled. Your information has been discarded.").send()
        return True

    if not value and not required:
        value = None
    elif not value and required:
        await cl.Message(content=f"This field is required. {prompt}").send()
        return True

    data[field_name] = value
    cl.user_session.set("report_data", data)

    next_idx = idx + 1
    if next_idx < len(REPORT_PII_FIELDS):
        cl.user_session.set("report_field_index", next_idx)
        _, next_prompt, _ = REPORT_PII_FIELDS[next_idx]
        await cl.Message(content=next_prompt).send()
        return True

    # All fields collected — show consent summary
    cl.user_session.set("collecting_report_pii", False)
    cl.user_session.set("awaiting_report_consent", True)

    consent_msg = (
        "📋 **Please review the information below before I submit your report.**\n\n"
        "**Your details (sent to police.uk):**\n"
        f"- **Name:** {data.get('first_name')} {data.get('surname')}\n"
        f"- **Date of Birth:** {data.get('dob_str')}\n"
        f"- **Gender:** {data.get('gender')}\n"
        f"- **Email:** {data.get('email')}\n"
    )
    if data.get("phone"):
        consent_msg += f"- **Phone:** {data.get('phone')}\n"

    consent_msg += (
        "\n**Incident details** from our conversation will be included in the report.\n\n"
        "**By confirming you consent to the following:**\n"
        "- A hate crime report will be submitted to **police.uk** on your behalf\n"
        "- Your personal details above will be shared with the police\n"
        "- AskAdil will **not store** any of your personal information after submission\n"
        "- Once submitted, the report **cannot be recalled** by AskAdil\n\n"
        "Type **yes** to submit or **no** to cancel."
    )
    await cl.Message(content=consent_msg).send()
    return True


async def _handle_report_consent(message_text: str):
    """Handle the consent confirmation for report submission."""
    if not cl.user_session.get("awaiting_report_consent"):
        return False

    cl.user_session.set("awaiting_report_consent", False)
    response = message_text.strip().lower()

    if response not in ("yes", "y", "confirm"):
        await cl.Message(content="Report submission cancelled. Your information has been discarded.").send()
        cl.user_session.set("report_data", {})
        return True

    data = cl.user_session.get("report_data", {})
    target = cl.user_session.get("report_target", "police-uk")
    history = cl.user_session.get("conversation_history") or []
    target_names = {
        "police-uk": "Police UK",
        "tell-mama": "Tell MAMA",
        "police-scotland": "Police Scotland",
        "iru": "IRU",
        "islamophobia-uk": "Islamophobia UK",
    }

    incident_text = "\n".join(turn["content"] for turn in history if turn["role"] == "user")

    # Anonymous targets (no PII) — use direct bridge call format
    NO_PII_TARGETS = {"islamophobia-uk"}

    if target in NO_PII_TARGETS:
        payload = {
            "target": target,
            "consent_confirmed": True,
            "reporter": {
                "first_name": "Anonymous",
                "surname": "Reporter",
                "dob": {"day": "01", "month": "01", "year": "2000"},
                "gender": "Unknown",
                "email": "anonymous@askadil.org",
            },
            "incident": {
                "details": incident_text or "Hate crime incident reported via AskAdil.",
                "location": "Provided in conversation",
                "date_time": "Provided in conversation",
                "role": "victim",
            },
            "evidence_urls": [],
            "conversation_history": [{"role": t["role"], "content": t["content"]} for t in history]
            if history
            else None,
        }
    else:
        dob_parts = data.get("dob_str", "01/01/1990").split("/")
        dob = (
            {"day": dob_parts[0], "month": dob_parts[1], "year": dob_parts[2]}
            if len(dob_parts) == 3
            else {"day": "01", "month": "01", "year": "1990"}
        )

        payload = {
            "target": target,
            "consent_confirmed": True,
            "reporter": {
                "first_name": data.get("first_name"),
                "surname": data.get("surname"),
                "dob": dob,
                "gender": data.get("gender"),
                "email": data.get("email"),
                "phone": data.get("phone"),
            },
            "incident": {
                "details": incident_text or "Hate crime incident reported via AskAdil.",
                "location": "Provided in conversation",
                "date_time": "Provided in conversation",
                "role": "victim",
            },
            "evidence_urls": [],
            "conversation_history": [{"role": t["role"], "content": t["content"]} for t in history]
            if history
            else None,
        }

    msg = cl.Message(content=f"*⏳ Submitting your report to {target_names.get(target, target)}...*")
    await msg.send()

    try:
        api_headers = {"X-API-Key": ADIL_API_KEY} if ADIL_API_KEY else {}
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{RAG_API_URL}/api/v1/submit-report",
                headers=api_headers,
                json=payload,
            )
            resp.raise_for_status()
            result = resp.json()
    except Exception as e:
        await msg.stream_token(f"\n\n❌ Failed to connect to the reporting service: {str(e)}")
        await msg.update()
        cl.user_session.set("report_data", {})
        return True

    cl.user_session.set("report_data", {})

    if result.get("success"):
        ref = result.get("reference_number", "N/A")
        response_text = f"✅ **Report submitted successfully!**\n\n**Reference Number:** `{ref}`\n\n"
        if result.get("message"):
            response_text += f"{result['message']}\n\n"
        response_text += (
            "⚠️ **Please save this reference number now.** "
            "AskAdil does not store your personal information after submission.\n\n"
            "Police may contact you at the email/phone you provided. "
            "If you don't hear back within 7 days, call **101** and quote your reference number."
        )

        if result.get("confirmation_screenshot"):
            response_text += "\n\n📸 **Confirmation screenshot saved below.**"

        msg.content = response_text
        await msg.update()
    else:
        error_text = "❌ **Automated submission was not successful.**\n\n"
        if result.get("error"):
            error_text += f"{result['error']}\n\n"

        if result.get("fallback_report"):
            error_text += (
                "📋 **Here is your incident report — you can submit it manually:**\n\n"
                f"```\n{result['fallback_report']}\n```\n\n"
            )

        if result.get("target_url"):
            error_text += f"🔗 **Submit manually here:** [{result['target_url']}]({result['target_url']})\n"

        msg.content = error_text
        await msg.update()

    return True
