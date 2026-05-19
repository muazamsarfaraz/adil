"""Heuristic PII-stripping for eval queries.

Used both by ``extract_queries.py`` (to pre-filter shadow-table rows before a
human reviews them) and as a unit-testable function. NOT a substitute for the
manual anonymisation pass — flag-and-redact, never trust silently.
"""

from __future__ import annotations

import re

# Common UK first names + surnames that appear in conversation logs.
# Deliberately tiny — we want the regex below (capitalised-word triggers) to do
# most of the work; this is a backup for very common cases that aren't
# capitalised.
_NAME_HINTS = (r"\b(my name is|i am|i'm|this is|call me)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+)?",)

# Email + phone + UK postcode.
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?:\+?44|0)\s?\d{2,4}[\s-]?\d{3,4}[\s-]?\d{3,4}")
_UK_POSTCODE = re.compile(r"\b[A-Z]{1,2}[0-9][A-Z0-9]?\s?[0-9][A-Z]{2}\b", re.IGNORECASE)

# Address-fragment patterns ("12 High Street", "Flat 3").
_STREET = re.compile(
    r"\b\d{1,4}\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,3}\s+"
    r"(?:Street|Road|Lane|Avenue|Drive|Close|Way|Court|Place|Square|Crescent)\b"
)

_NAME_RE = re.compile("|".join(_NAME_HINTS), re.IGNORECASE)


def anonymise(text: str) -> str:
    """Return ``text`` with PII patterns replaced by placeholders.

    Best-effort. A human still needs to skim every output before commit — this
    only catches the easy 80%.
    """
    out = text
    out = _EMAIL.sub("[EMAIL]", out)
    out = _PHONE.sub("[PHONE]", out)
    out = _UK_POSTCODE.sub("[POSTCODE]", out)
    out = _STREET.sub("[ADDRESS]", out)
    out = _NAME_RE.sub(_redact_name, out)
    return out


def _redact_name(match: re.Match[str]) -> str:
    """Replace a "my name is X" capture with the trigger phrase + [NAME]."""
    trigger = match.group(0).split(None, 1)[0]
    # Preserve the original casing of the trigger word.
    if trigger.lower() in {"my", "i", "this", "call"}:
        # The trigger is multi-word — take everything up to the first capital.
        head = re.match(r"^[^A-Z]+", match.group(0))
        return (head.group(0) if head else "") + "[NAME]"
    return f"{trigger} [NAME]"


def looks_like_pii(text: str) -> bool:
    """Return True if any of the high-confidence PII regexes match."""
    return bool(_EMAIL.search(text) or _PHONE.search(text) or _UK_POSTCODE.search(text) or _STREET.search(text))
