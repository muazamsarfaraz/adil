"""OG-RAG extraction pass 1: regex + structural split.

Splits a judgment's ``clean_text`` into paragraphs via blank-line boundaries
(numbered legal paragraphs typically already sit on their own line in TNA XML
output), then runs a spaCy sentencizer per paragraph for sentence-level spans.

Mines structural references via regex only:
  * Neutral citation (court + year + number) → ``CaseNode``
  * Section / subsection references → ``SectionRefCandidate``
  * EHRC code references → ``SectionRefCandidate`` against the EHRC code
  * Statute short titles (lookup from ``UK_STATUTE_SHORT_TITLES``) → ``StatuteRefCandidate``

Outputs are pure dataclasses with deterministic UUIDv5 ``node_id`` fields so
that re-running on the same judgment produces the same identifiers — required
for the writer in Architecture B to UPSERT idempotently.

Zero LLM cost. Tested against 5 hand-curated fixtures.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable

import spacy
from spacy.language import Language

# ---------------------------------------------------------------------------
# Deterministic ID namespace
# ---------------------------------------------------------------------------

# Stable namespace UUID for OG-RAG ontology node IDs. Generated once via
# uuid5(uuid.NAMESPACE_URL, "adil:ograg:ontology"); hard-coded so the value
# is reproducible across machines and python versions.
OGRAG_NAMESPACE = uuid.UUID("c4dc7c0c-2b91-5b0a-94d1-7e4cc1c33adf")


def _node_id(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(OGRAG_NAMESPACE, f"{kind}:{key}")


# ---------------------------------------------------------------------------
# Statute lookup table
# ---------------------------------------------------------------------------

# Mirror of UK_LEGISLATION_URLS keys in adil-rag-api/rag_service.py. Kept as a
# local table to avoid a cross-service import (the uploader and rag-api ship
# as independent Railway services). P1.5's acts fetcher seeds canonical
# Statute nodes for the same titles, so the ``slug`` here doubles as the
# stable lookup key the writer joins on.
UK_STATUTE_SHORT_TITLES: dict[str, str] = {
    "Equality Act 2010": "equality-act-2010",
    "Public Order Act 1986": "public-order-act-1986",
    "Crime and Disorder Act 1998": "crime-and-disorder-act-1998",
    "Online Safety Act 2023": "online-safety-act-2023",
    "Human Rights Act 1998": "human-rights-act-1998",
    "Employment Rights Act 1996": "employment-rights-act-1996",
    "Racial and Religious Hatred Act 2006": "racial-and-religious-hatred-act-2006",
    "Hate Crime and Public Order (Scotland) Act 2021": "hate-crime-and-public-order-scotland-act-2021",
    "Fair Employment and Treatment (Northern Ireland) Order 1998": "fair-employment-and-treatment-ni-order-1998",
    "Race Relations (Northern Ireland) Order 1997": "race-relations-ni-order-1997",
    "Disability Discrimination Act 1995": "disability-discrimination-act-1995",
    "Mental Capacity Act 2005": "mental-capacity-act-2005",
    "Adults with Incapacity (Scotland) Act 2000": "adults-with-incapacity-scotland-act-2000",
    "Mental Capacity Act (Northern Ireland) 2016": "mental-capacity-act-ni-2016",
}

# Sorted longest-first so "Mental Capacity Act 2005" matches before any
# hypothetical shorter prefix; protects against overlapping titles.
_STATUTE_TITLE_PATTERN = re.compile(
    "|".join(re.escape(title) for title in sorted(UK_STATUTE_SHORT_TITLES, key=len, reverse=True))
)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Neutral citation: [2021] UKSC 15, [2019] EWCA Civ 1374, [2015] EWHC 2493 (Admin)
# Court tokens we accept up front (UKSC, UKHL, EWCA, EWHC, UKEAT). Optional
# division (Civ/Crim/Admin/Comm/Ch/Fam/TCC/Pat/QB/KB) follows the number for
# EWCA/EWHC.
_NEUTRAL_CITATION = re.compile(
    r"\[(?P<year>\d{4})\]\s+"
    r"(?P<court>UKSC|UKHL|EWCA|EWHC|UKEAT)"
    r"(?:\s+(?P<division>Civ|Crim|Admin|Comm|Ch|Fam|TCC|Pat|QB|KB))?"
    r"\s+(?P<number>\d+)"
    r"(?:\s*\((?P<paren_div>Admin|Comm|Ch|Fam|TCC|Pat|QB|KB)\))?"
)

# Section reference: s.13, s 13, s.13(1), s.13(1A), section 13, section 13(2)(a)
_SECTION_REF = re.compile(
    r"\b(?:s(?:ection)?\.?)\s*" r"(?P<section>\d+[A-Z]?)" r"(?P<subsection>(?:\s*\(\s*[\dA-Za-z]+\s*\))*)",
    re.IGNORECASE,
)

# EHRC code paragraph: EHRC §3.5, EHRC § 3.5.2
_EHRC_REF = re.compile(r"EHRC\s*§\s*(?P<paragraph>\d+(?:\.\d+)*)")

# Paragraph split: blank lines OR start-of-line numbered markers like "1." / "12."
_PARA_SPLIT = re.compile(r"\n\s*\n+")
_NUM_PARA = re.compile(r"^\s*(\d{1,4})\.\s+(.*)", re.MULTILINE | re.DOTALL)


# ---------------------------------------------------------------------------
# spaCy sentencizer
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def _sentencizer() -> Language:
    """Lazy-built blank English pipeline with a sentencizer.

    ``spacy.blank("en")`` ships with the library — no model download — and
    the sentencizer adds only sentence boundary detection (no NER/POS/etc),
    which keeps cold-start cheap enough for an arq worker.
    """
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    return nlp


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CaseNode:
    node_id: uuid.UUID
    neutral_citation: str
    case_name: str
    court: str
    year: int

    @property
    def kind(self) -> str:
        return "Case"


@dataclass(frozen=True)
class ParagraphNode:
    node_id: uuid.UUID
    case_id: uuid.UUID
    index: int  # 0-based position within the judgment
    number: int | None  # legal paragraph number when detected (e.g., "12." → 12)
    text: str
    sentence_count: int

    @property
    def kind(self) -> str:
        return "Paragraph"


@dataclass(frozen=True)
class StatuteRefCandidate:
    """Mention of a statute short title inside a paragraph.

    ``resolved_node_id`` is filled by a caller-supplied lookup (P1.5's acts
    fetcher provides the canonical Statute node IDs); when None, the writer
    falls back to ``candidate_node_id`` which is deterministic on slug.
    """

    candidate_node_id: uuid.UUID
    paragraph_id: uuid.UUID
    short_title: str
    slug: str
    resolved_node_id: uuid.UUID | None = None

    @property
    def kind(self) -> str:
        return "StatuteRef"


@dataclass(frozen=True)
class SectionRefCandidate:
    """Mention of a section inside a paragraph.

    ``statute_slug`` is None when the section reference is bare ("s.13" with
    no nearby statute mention); Pass 2 (Haiku) resolves these via context.
    """

    candidate_node_id: uuid.UUID
    paragraph_id: uuid.UUID
    section: str  # e.g., "13" or "13A"
    subsection: str | None  # e.g., "(1)(a)" — verbatim chain
    statute_slug: str | None
    resolved_node_id: uuid.UUID | None = None

    @property
    def kind(self) -> str:
        return "SectionRef"


@dataclass(frozen=True)
class CourtNode:
    """Deterministic node derived from the case neutral citation (UKSC / EWCA / ...).

    No LLM involved — Pass 2 emits one of these per case via ``court_node_for``.
    """

    node_id: uuid.UUID
    code: str  # e.g. "UKSC", "EWCA", "UKEAT", "EWHC", "UKHL"
    division: str | None = None  # e.g. "Civ", "Admin" for EWCA/EWHC

    @property
    def kind(self) -> str:
        return "Court"


@dataclass(frozen=True)
class TopicNode:
    """Closed-vocabulary topic. ``slug`` is the canonical key joined on by
    the rag-api retriever; the full vocabulary lives in ``pass2_haiku``.
    """

    node_id: uuid.UUID
    slug: str

    @property
    def kind(self) -> str:
        return "Topic"


@dataclass(frozen=True)
class PartyNode:
    node_id: uuid.UUID
    name: str
    role: str  # "appellant" | "respondent" | "claimant" | "defendant" | "intervener" | "other"

    @property
    def kind(self) -> str:
        return "Party"


@dataclass(frozen=True)
class JudgeNode:
    node_id: uuid.UUID
    name: str

    @property
    def kind(self) -> str:
        return "Judge"


@dataclass(frozen=True)
class Edge:
    """Generic edge between two ontology nodes.

    Pass 2 emits ``has_topic``, ``decided_in_court``, ``judged_by``,
    ``heard_party``. ``paragraph_id`` is non-None for paragraph-attributed
    relations (e.g. ``has_topic``); None for case-level edges (e.g.
    ``decided_in_court``).
    """

    kind: str
    source_id: uuid.UUID
    target_id: uuid.UUID
    paragraph_id: uuid.UUID | None = None


@dataclass
class ExtractionResult:
    case: CaseNode
    paragraphs: list[ParagraphNode] = field(default_factory=list)
    statute_refs: list[StatuteRefCandidate] = field(default_factory=list)
    section_refs: list[SectionRefCandidate] = field(default_factory=list)
    # ---- Pass 2 (Haiku) ----
    court: CourtNode | None = None
    topics: list[TopicNode] = field(default_factory=list)
    parties: list[PartyNode] = field(default_factory=list)
    judges: list[JudgeNode] = field(default_factory=list)
    edges: list[Edge] = field(default_factory=list)
    # ---- Pass 3 (Flash cross-refs) ----
    # Lightweight Case nodes for judgments this one cites but we may not
    # have ingested ourselves. ``case_name`` stays blank until/unless the
    # cited case is itself extracted in a later run.
    referenced_cases: list[CaseNode] = field(default_factory=list)
    # Populated by ``build_hyperedges`` after pass 3. Held as ``Any`` here
    # to avoid a forward-import cycle with ``pass3_flash``; the concrete
    # type is ``pass3_flash.HyperedgeNode``.
    hyperedges: list[Any] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Paragraph splitter
# ---------------------------------------------------------------------------


def _split_paragraphs(clean_text: str) -> list[tuple[int | None, str]]:
    """Return ``[(paragraph_number_or_None, text), ...]`` in source order.

    Two-stage: first split on blank lines, then for each block detect a
    leading ``N.`` marker so we can carry the legal paragraph number through
    to the node. Blocks with no leading number get ``None`` (typical for
    case headers, headnotes, judge introductions).
    """
    blocks = [b.strip() for b in _PARA_SPLIT.split(clean_text) if b.strip()]
    out: list[tuple[int | None, str]] = []
    for block in blocks:
        m = _NUM_PARA.match(block)
        if m:
            try:
                out.append((int(m.group(1)), m.group(2).strip()))
                continue
            except ValueError:
                pass
        out.append((None, block))
    return out


# ---------------------------------------------------------------------------
# Reference miners
# ---------------------------------------------------------------------------


def _mine_statute_refs(
    *,
    paragraph: ParagraphNode,
    text: str,
    resolver: Callable[[str], uuid.UUID | None] | None,
) -> list[StatuteRefCandidate]:
    out: list[StatuteRefCandidate] = []
    seen: set[str] = set()
    for m in _STATUTE_TITLE_PATTERN.finditer(text):
        title = m.group(0)
        slug = UK_STATUTE_SHORT_TITLES[title]
        if slug in seen:
            continue
        seen.add(slug)
        out.append(
            StatuteRefCandidate(
                candidate_node_id=_node_id("statute", slug),
                paragraph_id=paragraph.node_id,
                short_title=title,
                slug=slug,
                resolved_node_id=resolver(slug) if resolver else None,
            )
        )
    return out


def _mine_section_refs(
    *,
    paragraph: ParagraphNode,
    text: str,
    running_statute_slug: str | None,
    resolver: Callable[[str, str], uuid.UUID | None] | None,
) -> list[SectionRefCandidate]:
    """Mine s.N / section N references and the EHRC code's paragraph refs.

    ``running_statute_slug`` is the most-recently-mentioned statute carried
    across paragraphs (best-effort attribution). It's None when ambiguous
    (multiple statutes named in a paragraph) or before any statute mention.
    """
    out: list[SectionRefCandidate] = []
    statute_slug = running_statute_slug

    seen: set[tuple[str, str | None, str | None]] = set()

    for m in _SECTION_REF.finditer(text):
        section = m.group("section")
        subsection = m.group("subsection") or ""
        subsection_norm = re.sub(r"\s+", "", subsection) or None
        key = (section, subsection_norm, statute_slug)
        if key in seen:
            continue
        seen.add(key)
        section_key = f"{statute_slug or 'unknown'}#{section}{subsection_norm or ''}"
        out.append(
            SectionRefCandidate(
                candidate_node_id=_node_id("section", section_key),
                paragraph_id=paragraph.node_id,
                section=section,
                subsection=subsection_norm,
                statute_slug=statute_slug,
                resolved_node_id=(resolver(statute_slug, section) if resolver and statute_slug else None),
            )
        )

    # EHRC code paragraphs are modelled as SectionRefs against the special
    # "ehrc-employment-code" pseudo-statute so the same join table can hold
    # them. P1.5's acts fetcher seeds the EHRC node under this slug.
    for m in _EHRC_REF.finditer(text):
        paragraph_ref = m.group("paragraph")
        key = (paragraph_ref, None, "ehrc-employment-code")
        if key in seen:
            continue
        seen.add(key)
        out.append(
            SectionRefCandidate(
                candidate_node_id=_node_id("section", f"ehrc-employment-code#{paragraph_ref}"),
                paragraph_id=paragraph.node_id,
                section=paragraph_ref,
                subsection=None,
                statute_slug="ehrc-employment-code",
                resolved_node_id=(resolver("ehrc-employment-code", paragraph_ref) if resolver else None),
            )
        )

    return out


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------


def _normalise_citation(year: str, court: str, division: str | None, number: str) -> str:
    if division:
        return f"[{year}] {court} {division} {number}"
    return f"[{year}] {court} {number}"


def extract_pass1(
    judgment: Any,
    *,
    statute_resolver: Callable[[str], uuid.UUID | None] | None = None,
    section_resolver: Callable[[str, str], uuid.UUID | None] | None = None,
) -> ExtractionResult:
    """Run pass 1 extraction on a Judgment ORM row (or duck-typed object).

    Required attributes on ``judgment``: ``neutral_citation``, ``case_name``,
    ``court``, ``judgment_date``, ``clean_text``. The ``judgment_date`` is
    optional and only used for the case year; falls back to a regex-mined
    year from the neutral citation.

    ``statute_resolver(slug) -> UUID | None`` and
    ``section_resolver(statute_slug, section) -> UUID | None`` are optional
    callbacks that let the caller swap candidate IDs for canonical P1.5
    Statute/Section node IDs. When omitted, candidates carry their own
    deterministic IDs and the writer can resolve at insert time.
    """
    neutral_citation = judgment.neutral_citation.strip()
    case_name = judgment.case_name.strip()
    court = (judgment.court or "").strip()

    # Pull year from neutral citation; fall back to judgment_date.
    nc_match = _NEUTRAL_CITATION.search(neutral_citation)
    if nc_match:
        year = int(nc_match.group("year"))
    elif judgment.judgment_date is not None:
        year = judgment.judgment_date.year
    else:
        raise ValueError(f"cannot determine year for judgment {neutral_citation!r}")

    case = CaseNode(
        node_id=_node_id("case", neutral_citation),
        neutral_citation=neutral_citation,
        case_name=case_name,
        court=court,
        year=year,
    )

    nlp = _sentencizer()
    result = ExtractionResult(case=case)

    blocks = _split_paragraphs(judgment.clean_text or "")
    running_statute_slug: str | None = None
    for idx, (number, text) in enumerate(blocks):
        doc = nlp(text)
        sentence_count = sum(1 for _ in doc.sents)

        # Stable ID even when paragraph numbering is missing: prefer the
        # legal paragraph number when present (so node IDs survive small
        # cosmetic edits to header text), else use positional index.
        para_key = f"{neutral_citation}#para-{number}" if number is not None else f"{neutral_citation}#idx-{idx}"
        paragraph = ParagraphNode(
            node_id=_node_id("paragraph", para_key),
            case_id=case.node_id,
            index=idx,
            number=number,
            text=text,
            sentence_count=sentence_count,
        )
        result.paragraphs.append(paragraph)

        statute_refs = _mine_statute_refs(paragraph=paragraph, text=text, resolver=statute_resolver)
        result.statute_refs.extend(statute_refs)

        # Update running statute: exactly-one named in this paragraph → use it;
        # multiple → ambiguous, clear; zero → carry the previous one.
        slugs_here = [ref.slug for ref in statute_refs]
        if len(slugs_here) == 1:
            running_statute_slug = slugs_here[0]
        elif len(slugs_here) > 1:
            running_statute_slug = None

        result.section_refs.extend(
            _mine_section_refs(
                paragraph=paragraph,
                text=text,
                running_statute_slug=running_statute_slug,
                resolver=section_resolver,
            )
        )

    return result
