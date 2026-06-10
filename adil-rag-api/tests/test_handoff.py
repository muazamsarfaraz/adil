"""P6-02 — tests for the MCB Mental Health cross-link (reverse direction).

Pure-unit: imports only `handoff`, no app / network / DB. Run from the
`adil-rag-api` directory: `python -m pytest tests/test_handoff.py -q`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import handoff  # noqa: E402

# ---------------------------------------------------------------------------
# Clinical / wellbeing / crisis messages arriving at AskAdil must hand off.
# ---------------------------------------------------------------------------
POSITIVE = {
    "acute_risk": [
        "I feel suicidal and don't know what to do.",
        "Sometimes I want to die.",
        "I've been self-harming again.",
        "I keep thinking about killing myself.",
    ],
    "treatment_seeking": [
        "Can you recommend a Muslim counsellor near me?",
        "I need therapy for my anxiety.",
        "Where can I find a therapist who understands my faith?",
        "Is there mental health support available in my area?",
    ],
    "emotional_distress": [
        "I feel really depressed and hopeless lately.",
        "I'm struggling with my mental health and can't cope.",
        "I keep having panic attacks at night.",
        "I feel so overwhelmed and numb.",
    ],
}

# ---------------------------------------------------------------------------
# Genuine *legal* queries (AskAdil's own job) must NEVER hand off, even when
# they mention a mental-health condition or statute.
# ---------------------------------------------------------------------------
NEGATIVE = [
    "My brother was sectioned under the Mental Health Act, can he appeal?",
    "Can my employer sack me because of my depression?",
    "Does my dad lack the mental capacity to manage his money?",
    "How do I become a deputy through the Court of Protection?",
    "My employer refused reasonable adjustments for my anxiety — is that discrimination?",
    "What is a Deprivation of Liberty Safeguard?",
    "How do I make a safeguarding referral for a vulnerable adult?",
    "What are my rights under the Equality Act 2010 at work?",
]


def test_each_category_detected():
    for expected_key, queries in POSITIVE.items():
        for q in queries:
            cat = handoff.detect(q)
            assert cat is not None, f"expected handoff for: {q!r}"
            assert cat.key == expected_key, f"{q!r} -> {cat.key}, expected {expected_key}"


def test_legal_queries_do_not_hand_off():
    for q in NEGATIVE:
        assert handoff.detect(q) is None, f"false handoff on legal query: {q!r}"
        assert handoff.clinical_handoff_suffix(q) == ""


def test_suffix_text_and_url():
    q = "I feel suicidal."
    suffix = handoff.clinical_handoff_suffix(q)
    assert suffix == handoff.HANDOFF_TEXT
    assert handoff.MCB_MH_URL in suffix
    assert "mental-health" in suffix.lower()


def test_apply_handoff_appends_to_answer():
    answer = "Under the Equality Act 2010 you may have protections..."
    out = handoff.apply_handoff(answer, "I'm struggling with my mental health.")
    assert handoff.MCB_MH_URL in out
    assert out.startswith("Under the Equality Act 2010")


def test_apply_handoff_is_idempotent():
    q = "I need therapy for my anxiety."
    once = handoff.apply_handoff("Legal answer.", q)
    twice = handoff.apply_handoff(once, q)
    assert once == twice
    assert twice.count(handoff.MCB_MH_URL) == 1


def test_apply_handoff_noop_for_legal():
    answer = "You may bring a claim in the Employment Tribunal."
    out = handoff.apply_handoff(answer, "Can I be sacked for my depression?")
    assert out == answer


def test_apply_handoff_handles_empty_answer():
    out = handoff.apply_handoff("", "I feel hopeless and depressed.")
    assert out == handoff.HANDOFF_TEXT
