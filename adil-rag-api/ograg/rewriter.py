"""Multi-turn query rewriter — collapses the last ~4 turns + the current
question into a single standalone retrieval query.

Called by ``ograg.retriever.retrieve`` whenever conversation_history is
non-empty. Uses Gemini Flash (cheap: ~$0.0001/call). Falls back to the
original question on any failure so retrieval never blocks on rewrite.
"""

from __future__ import annotations

import asyncio
import logging
import os

from google import genai

logger = logging.getLogger(__name__)

REWRITE_MODEL = os.environ.get("OGRAG_REWRITE_MODEL", "gemini-2.5-flash")
MAX_TURNS = 4

_PROMPT = (
    "You rewrite the user's CURRENT question into a single standalone "
    "retrieval query for a UK legal knowledge base. Inline anything from "
    "the recent conversation needed for the question to be self-contained: "
    "subject (e.g. 'my employer'), jurisdiction, statute names, dates. "
    "Output ONLY the rewritten query as a single line — no quotes, no "
    "preface, no explanation. If the current question is already "
    "self-contained, return it unchanged.\n\n"
    "--- RECENT TURNS ---\n{turns}\n--- END TURNS ---\n\n"
    "CURRENT QUESTION: {question}\n"
    "REWRITTEN QUERY:"
)


def _client() -> genai.Client:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is not set")
    return genai.Client(api_key=api_key)


def _format_turns(history: list[dict[str, str]]) -> str:
    lines: list[str] = []
    for turn in history[-MAX_TURNS:]:
        role = (turn.get("role") or "user").lower()
        role = "USER" if role == "user" else "ASSISTANT"
        text = (turn.get("content") or turn.get("text") or "").strip()
        if not text:
            continue
        # Trim each turn so a single long answer can't dominate the prompt.
        if len(text) > 600:
            text = text[:600].rstrip() + "…"
        lines.append(f"{role}: {text}")
    return "\n".join(lines) if lines else "(no prior turns)"


async def rewrite_query(history: list[dict[str, str]], question: str) -> str:
    """Return a standalone query. Falls back to ``question`` on any error."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    if not history:
        return question.strip()

    prompt = _PROMPT.format(turns=_format_turns(history), question=question.strip())

    def _call() -> str:
        client = _client()
        resp = client.models.generate_content(
            model=REWRITE_MODEL,
            contents=prompt,
            config={
                # Keep it tight — a query, not an essay.
                "temperature": 0.0,
                "max_output_tokens": 200,
            },
        )
        text = getattr(resp, "text", None) or ""
        return text.strip()

    try:
        rewritten = await asyncio.to_thread(_call)
    except Exception as e:
        logger.warning("query rewrite failed (%s); using original", e)
        return question.strip()

    if not rewritten:
        return question.strip()
    # Strip surrounding quotes the model sometimes adds despite instructions.
    rewritten = rewritten.strip().strip('"').strip("'").strip()
    # Single line only — collapse newlines.
    rewritten = " ".join(rewritten.split())
    return rewritten or question.strip()
