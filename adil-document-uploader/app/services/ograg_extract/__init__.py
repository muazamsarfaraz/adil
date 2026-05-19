"""OG-RAG ontology extraction passes for case-law judgments.

Pass 1 (structural, this module): regex + spaCy sentencizer — zero LLM cost.
Pass 2 (Claude Haiku): topics, parties, relations.
Pass 3 (Gemini Flash): cross-references.
"""

from app.services.ograg_extract.pass1_structural import (
    CaseNode,
    ExtractionResult,
    ParagraphNode,
    SectionRefCandidate,
    StatuteRefCandidate,
    extract_pass1,
)

__all__ = [
    "CaseNode",
    "ExtractionResult",
    "ParagraphNode",
    "SectionRefCandidate",
    "StatuteRefCandidate",
    "extract_pass1",
]
