"""OG-RAG ontology extraction passes for case-law judgments.

Pass 1 (structural, this module): regex + spaCy sentencizer — zero LLM cost.
Pass 2 (Claude Haiku): topics, parties, relations.
Pass 3 (Gemini Flash): cross-references.
"""

from app.services.ograg_extract.pass1_structural import (
    CaseNode,
    CourtNode,
    Edge,
    ExtractionResult,
    JudgeNode,
    ParagraphNode,
    PartyNode,
    SectionRefCandidate,
    StatuteRefCandidate,
    TopicNode,
    extract_pass1,
)
from app.services.ograg_extract.pass2_haiku import (
    CLOSED_TOPIC_VOCAB,
    HaikuExtractionError,
    extract_pass2,
    make_pass2_runner,
)

__all__ = [
    "CaseNode",
    "CourtNode",
    "Edge",
    "ExtractionResult",
    "JudgeNode",
    "ParagraphNode",
    "PartyNode",
    "SectionRefCandidate",
    "StatuteRefCandidate",
    "TopicNode",
    "extract_pass1",
    "CLOSED_TOPIC_VOCAB",
    "HaikuExtractionError",
    "extract_pass2",
    "make_pass2_runner",
]
