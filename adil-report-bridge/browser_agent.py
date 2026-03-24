"""Browser automation agent for form submission.

Uses browser-use with Gemini Flash to fill multi-step web forms.
The AI agent reads form labels semantically, adapting to UI changes.
"""
import os
import logging
import asyncio
from typing import Dict, Any, Optional
from datetime import datetime, timezone

from browser_use import Agent, Browser
from langchain_google_genai import ChatGoogleGenerativeAI

from targets import get_target
from screenshot import compress_screenshot

logger = logging.getLogger(__name__)

# Concurrency: max 1 Chromium session to avoid OOM
_semaphore = asyncio.Semaphore(1)
SEMAPHORE_TIMEOUT = 30  # seconds to wait before returning 503


def _build_task_prompt(target_config: Dict[str, Any], data: Dict[str, Any]) -> str:
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

    return (
        f"{instructions}\n\n"
        f"DATA TO FILL IN THE FORM:\n{data_block}\n\n"
        f"IMPORTANT:\n"
        f"- If a field is not in the data above, leave it blank or skip it.\n"
        f"- For 'additional_info' or free-text fields, include: "
        f"'Submitted via AskAdil (askadil.org) on behalf of the reporter.'\n"
        f"- After submitting, DO NOT close the page. Stay on the confirmation page.\n"
        f"- Report the confirmation text and any reference number you see."
    )


async def submit_report(
    target_id: str,
    data: Dict[str, Any],
) -> Dict[str, Any]:
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
    except asyncio.TimeoutError:
        return {
            "success": False,
            "error": "Service busy — another submission is in progress. Please try again shortly.",
            "target": target_id,
        }

    browser = None
    try:
        model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        llm = ChatGoogleGenerativeAI(model=model)

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
                png_bytes = await asyncio.wait_for(
                    page.screenshot(full_page=False), timeout=10
                )
                screenshot_b64 = compress_screenshot(png_bytes)
        except Exception as e:
            logger.warning("Screenshot capture failed: %s", e)

        if is_successful:
            reference = _extract_reference(final_result)
            return {
                "success": True,
                "target": target_id,
                "reference_number": reference,
                "confirmation_screenshot": screenshot_b64,
                "confirmation_text": final_result[:500],
                "submitted_at": datetime.now(timezone.utc).isoformat(),
            }
        else:
            return {
                "success": False,
                "target": target_id,
                "error": f"Form submission did not complete successfully. Agent result: {final_result[:200]}",
                "confirmation_screenshot": screenshot_b64,
                "target_url": target_config["url"],
            }

    except asyncio.TimeoutError:
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


def _extract_reference(text: str) -> Optional[str]:
    """Try to extract a reference number from the agent's final result text."""
    import re
    patterns = [
        r"(?:ref(?:erence)?[\s:]*#?\s*)([A-Z0-9-]{5,})",
        r"(HC-\d{4}-\d+)",
        r"(?:number[\s:]*#?\s*)([A-Z0-9-]{5,})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None
