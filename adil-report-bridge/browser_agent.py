"""Browser automation agent for form submission.

Uses browser-use with Gemini Flash to fill multi-step web forms.
The AI agent reads form labels semantically, adapting to UI changes.
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Any

from browser_use import Agent, Browser, ChatGoogle
from screenshot import compress_screenshot
from targets import get_target

logger = logging.getLogger(__name__)

# Concurrency: max 1 Chromium session to avoid OOM
_semaphore = asyncio.Semaphore(1)
SEMAPHORE_TIMEOUT = 30  # seconds to wait before returning 503


def _is_dry_run() -> bool:
    """Whether to skip the final Submit click. Controlled by BRIDGE_DRY_RUN env."""
    return os.getenv("BRIDGE_DRY_RUN", "false").strip().lower() in ("1", "true", "yes", "on")


def _build_task_prompt(target_config: dict[str, Any], data: dict[str, Any]) -> str:
    """Build the agent task prompt from target instructions and user data."""
    instructions = target_config["instructions"]

    data_lines = []
    for key, value in data.items():
        if value is None or value == "" or value == []:
            continue
        if isinstance(value, dict):
            formatted = ", ".join(f"{k}: {v}" for k, v in value.items())
            data_lines.append(f"- {key}: {formatted}")
        elif isinstance(value, list):
            data_lines.append(f"- {key}: {', '.join(str(v) for v in value)}")
        else:
            data_lines.append(f"- {key}: {value}")

    data_block = "\n".join(data_lines)

    base = (
        f"{instructions}\n\n"
        f"DATA TO FILL IN THE FORM:\n{data_block}\n\n"
        f"IMPORTANT:\n"
        f"- If a field is not in the data above, leave it blank or skip it.\n"
        f"- For 'additional_info' or free-text fields, include: "
        f"'Submitted via AskAdil (askadil.org) on behalf of the reporter.'\n"
    )
    if _is_dry_run():
        return base + (
            "- DRY RUN MODE: walk through every step and fill every field, BUT "
            "WHEN YOU REACH THE FINAL REVIEW / SUBMIT PAGE, DO NOT CLICK THE "
            "SUBMIT, SEND, FILE, or CONFIRM BUTTON. Stop on the review page and "
            "report back the page contents. This is a pre-launch validation "
            "and any actual submission would be logged as a false police report.\n"
            "- Treat the run as successful once you reach (but do not interact "
            "with) the final Submit button.\n"
        )
    return base + (
        "- After submitting, DO NOT close the page. Stay on the confirmation page.\n"
        "- Report the confirmation text and any reference number you see.\n"
    )


async def submit_report(
    target_id: str,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Submit a report using AI browser automation."""
    target_config = get_target(target_id)
    if not target_config:
        return {
            "success": False,
            "error": f"Unknown target: {target_id}",
            "target": target_id,
        }

    # Acquire semaphore with timeout
    try:
        await asyncio.wait_for(_semaphore.acquire(), timeout=SEMAPHORE_TIMEOUT)
    except TimeoutError:
        return {
            "success": False,
            "error": "Service busy — another submission is in progress. Please try again shortly.",
            "target": target_id,
        }

    browser = None
    try:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        # Use browser-use's native ChatGoogle (drops langchain dependency).
        # Reads GOOGLE_API_KEY / GEMINI_API_KEY from env.
        llm = ChatGoogle(model=model)

        browser = Browser(headless=True)
        task_prompt = _build_task_prompt(target_config, data)

        agent = Agent(
            task=task_prompt,
            llm=llm,
            browser=browser,
            initial_actions=[
                {"go_to_url": {"url": target_config["url"]}},
            ],
        )

        logger.info("Starting form submission for target=%s", target_id)
        history = await asyncio.wait_for(agent.run(max_steps=50), timeout=60)

        final_result = history.final_result() or ""
        is_successful = history.is_successful()

        # Take screenshot of final page
        screenshot_b64 = None
        try:
            page = await agent.browser_context.get_current_page()
            if page:
                png_bytes = await asyncio.wait_for(page.screenshot(full_page=False), timeout=10)
                screenshot_b64 = compress_screenshot(png_bytes)
        except Exception as e:
            logger.warning("Screenshot capture failed: %s", e)

        if is_successful:
            reference = _extract_reference(final_result)
            dry_run = _is_dry_run()
            screenshot_size = len(screenshot_b64) if screenshot_b64 else 0
            logger.info(
                "Submit OK target=%s dry_run=%s ref=%s screenshot_bytes=%s",
                target_id,
                dry_run,
                reference,
                screenshot_size,
            )
            message = (
                "DRY RUN — form was filled and the review page was reached, but "
                "no Submit button was clicked. No report was filed."
                if dry_run
                else None
            )
            return {
                "success": True,
                "target": target_id,
                "reference_number": (f"DRY-RUN-{int(datetime.now(UTC).timestamp())}" if dry_run else reference),
                "confirmation_screenshot": screenshot_b64,
                "confirmation_text": final_result[:500],
                "submitted_at": datetime.now(UTC).isoformat(),
                "message": message,
                "dry_run": dry_run,
            }
        else:
            logger.warning(
                "Submit unsuccessful target=%s screenshot_bytes=%s result=%s",
                target_id,
                len(screenshot_b64) if screenshot_b64 else 0,
                final_result[:200],
            )
            return {
                "success": False,
                "target": target_id,
                "error": f"Form submission did not complete successfully. Agent result: {final_result[:200]}",
                "confirmation_screenshot": screenshot_b64,
                "target_url": target_config["url"],
            }

    except TimeoutError:
        logger.error("Form submission timed out for target=%s", target_id)
        return {
            "success": False,
            "target": target_id,
            "error": "Form submission timed out after 60 seconds.",
            "target_url": target_config["url"],
        }
    except Exception as e:
        logger.error("Form submission error for target=%s: %s", target_id, e)
        return {
            "success": False,
            "target": target_id,
            "error": f"Form submission failed: {str(e)}",
            "target_url": target_config["url"],
        }
    finally:
        if browser:
            try:
                await browser.close()
            except Exception:
                pass
        _semaphore.release()
        del data


def _extract_reference(text: str) -> str | None:
    """Try to extract a reference number from the agent's final result text.

    Patterns ordered most-to-least specific so a portal-specific format wins
    over the generic 'reference: XYZ' fallback. Anchors avoid swallowing
    common false positives like 'AskAdil' (capital + 5 alphanums).
    """
    import re

    patterns = [
        # Police UK / Met format: HC-2026-12345
        r"\b(HC-\d{4}-\d{3,})\b",
        # Tell MAMA: TM-12345
        r"\b(TM-\d{4,})\b",
        # IRU: IRU/12345 or IRU-2026-001
        r"\b(IRU[-/][A-Z0-9-]{4,})\b",
        # Generic 'crime reference number 1234567/26'
        r"crime\s+reference(?:\s+number)?[:\s]*#?\s*([A-Z0-9/]{6,})",
        # Generic '(your )?reference[:\s] XYZ' — only match alphanumeric refs
        # with at least one digit so we don't catch words like 'AskAdil'.
        r"(?:your\s+)?ref(?:erence)?(?:\s+number)?[:\s]*#?\s*([A-Z0-9-]{4,}\d[A-Z0-9-]{0,})",
        # Confirmation/case number labels
        r"(?:confirmation|case)\s+number[:\s]*#?\s*([A-Z0-9-]{5,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None
