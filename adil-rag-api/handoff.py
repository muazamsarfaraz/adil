"""Cross-link handoff contract with the MCB Mental Health signpost (reverse).

AskAdil answers UK **legal** questions. Some messages that arrive here are really
about *clinical / wellbeing* mental health — someone in distress, looking for
counselling, or expressing acute risk. Those belong to the MCB Mental Health
signpost (the sister service), which carries a vetted UK provider directory and a
hard-coded crisis card.

This is the mirror of `mh-rag-api/handoff.py` (MCB MH → AskAdil for legal topics).
When a clinical / help-seeking / risk signal is detected we **append a one-line
handoff link** to the MCB MH signpost — additive, never blocking the legal answer.

Detection is deliberately intent-bound: it fires on help-seeking and risk
phrasing, NOT on bare condition words. So a *legal* query that merely mentions a
mental-health condition — e.g. "can I be sacked for my depression?", "my dad lacks
mental capacity", "he was sectioned under the Mental Health Act" — stays with
AskAdil and does **not** hand off.

Pure-stdlib, no I/O — safe to import anywhere and trivially unit-testable.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MCB_MH_URL = "https://mcb-mental-health-production.up.railway.app"

# Equivalent, mirrored phrasing to mh-rag-api's forward handoff line.
HANDOFF_TEXT = (
    "For the mental-health and wellbeing side of this — counselling, emotional "
    "support, or someone to talk to — the MCB Mental Health signpost can help: "
    f"[mcb-mental-health]({MCB_MH_URL})."
)


@dataclass(frozen=True)
class HandoffCategory:
    """A clinical / wellbeing topic AskAdil hands off to the MCB MH signpost for."""

    key: str
    label: str
    pattern: re.Pattern[str]


def _p(*alts: str) -> re.Pattern[str]:
    return re.compile("|".join(alts), re.IGNORECASE)


# Ordered most-urgent → least. First match wins. Every pattern requires
# help-seeking or risk *intent*, not just a diagnosis noun.
HANDOFF_CATEGORIES: tuple[HandoffCategory, ...] = (
    HandoffCategory(
        key="acute_risk",
        label="Acute mental-health risk (crisis)",
        pattern=_p(
            r"\bsuicid\w*",
            r"\bkill(?:ing)? (?:myself|himself|herself|themsel\w*)\b",
            r"\bend (?:my|his|her|their) (?:own )?life\b",
            r"\bself[\s-]?harm\w*",
            r"\bharm(?:ing)? (?:myself|himself|herself)\b",
            r"\bwant(?:ed|ing)? to die\b",
            r"\bdon'?t want to (?:be here|live|wake up)\b",
            r"\boverdos\w*",
        ),
    ),
    HandoffCategory(
        key="treatment_seeking",
        label="Seeking counselling / therapy",
        pattern=_p(
            r"\b(?:find|finding|need|needs|want|wanting|looking for|recommend|see|seeing|access(?:ing)?)\b"
            r"[^.]{0,40}\b(therapist|counsell?ors?|counsell?ing|therapy|psychologist|psychiatrist|talking therap\w*)\b",
            r"\bmuslim (?:therapist|counsell?or|counsell?ing|therapy)\b",
            r"\bmental health (?:support|services?|help|helpline)\b",
            r"\b(CBT|cognitive behavioural therapy)\b",
        ),
    ),
    HandoffCategory(
        key="emotional_distress",
        label="Emotional distress / wellbeing support",
        pattern=_p(
            r"\b(?:feel|feeling|felt|i'?m)\b"
            r"[^.]{0,30}\b(depress\w*|anxious|anxiety|hopeless|empty|worthless|numb|overwhelmed|suicidal)\b",
            r"\bstruggl\w*\b[^.]{0,30}\b(mental health|emotionally|to cope|depress\w*|anxiety)\b",
            r"\bcan'?t cope\b",
            r"\bmental breakdown\b",
            r"\bburn(?:t|ed) out\b",
            r"\bpanic attacks?\b",
        ),
    ),
)


def detect(text: str | None) -> HandoffCategory | None:
    """Return the first clinical handoff category matched in ``text``, or ``None``."""
    if not text:
        return None
    for category in HANDOFF_CATEGORIES:
        if category.pattern.search(text):
            return category
    return None


def clinical_handoff_suffix(text: str | None) -> str:
    """Return the handoff sentence to append, or ``""`` when no category matches."""
    return HANDOFF_TEXT if detect(text) is not None else ""


def apply_handoff(answer: str | None, text: str | None) -> str:
    """Return ``answer`` with the handoff sentence appended when ``text`` is clinical.

    Idempotent: a no-op when the query isn't clinical, or when the MCB MH link is
    already present in ``answer``.
    """
    answer = answer or ""
    suffix = clinical_handoff_suffix(text)
    if not suffix or MCB_MH_URL in answer:
        return answer
    body = answer.rstrip()
    return f"{body}\n\n{suffix}" if body else suffix
