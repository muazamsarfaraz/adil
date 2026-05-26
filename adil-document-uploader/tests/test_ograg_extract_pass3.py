"""Unit tests for OG-RAG extraction pass 3 (Gemini Flash cross-references)
and the hyperedge build step.

All tests are offline — the Gemini client and embedder are stubbed.
"""

from __future__ import annotations

import json
import uuid

import pytest

from app.services.ograg_extract import (
    CaseNode,
    Edge,
    ExtractionResult,
    ParagraphNode,
    SectionRefCandidate,
    StatuteRefCandidate,
    build_hyperedges,
    extract_pass3,
    make_pass3_runner,
)
from app.services.ograg_extract import pass3_flash as p3
from app.services.ograg_extract.pass3_flash import FlashExtractionError


pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_case(citation: str = "[2023] UKSC 15", name: str = "Smith v Jones") -> CaseNode:
    return CaseNode(
        node_id=uuid.uuid5(uuid.NAMESPACE_URL, citation),
        neutral_citation=citation,
        case_name=name,
        court="UKSC",
        year=2023,
    )


def _make_paragraph(case: CaseNode, idx: int, text: str) -> ParagraphNode:
    return ParagraphNode(
        node_id=uuid.uuid5(uuid.NAMESPACE_URL, f"{case.neutral_citation}#p{idx}"),
        case_id=case.node_id,
        index=idx,
        number=idx + 1,
        text=text,
        sentence_count=1,
    )


def _make_result() -> ExtractionResult:
    case = _make_case()
    p0 = _make_paragraph(case, 0, "The leading authority is [2019] EWCA Civ 1374 on this question.")
    p1 = _make_paragraph(
        case,
        1,
        "We are not bound by [2015] EWHC 2493 (Admin) which was decided on different facts; "
        "and [2021] UKSC 12 overruled [2010] UKHL 3 entirely.",
    )
    return ExtractionResult(case=case, paragraphs=[p0, p1])


# ---------------------------------------------------------------------------
# Fake Gemini client
# ---------------------------------------------------------------------------


class _FakeUsage:
    def __init__(self, p_in: int = 1000, p_out: int = 200):
        self.prompt_token_count = p_in
        self.candidates_token_count = p_out


class _FakeResponse:
    def __init__(self, text: str, *, usage: _FakeUsage | None = None):
        self.text = text
        self.usage_metadata = usage or _FakeUsage()


class _FakeFlashClient:
    """Mocks google-genai's client.models.generate_content."""

    def __init__(self, responses: list[_FakeResponse | Exception]):
        self._responses = list(responses)
        self.calls: list[dict] = []
        outer = self

        class _Models:
            @staticmethod
            def generate_content(**kwargs):
                outer.calls.append(kwargs)
                r = outer._responses.pop(0)
                if isinstance(r, Exception):
                    raise r
                return r

        self.models = _Models()


# ---------------------------------------------------------------------------
# 1. extract_pass3 — happy path
# ---------------------------------------------------------------------------


async def test_pass3_classifies_cross_refs_into_edges():
    result = _make_result()
    payload = json.dumps(
        {
            "refs": [
                {"cited_citation": "[2019] EWCA Civ 1374", "relation": "cites", "paragraph_index": 0},
                {
                    "cited_citation": "[2015] EWHC 2493 (Admin)",
                    "relation": "distinguished_by",
                    "paragraph_index": 1,
                },
                {"cited_citation": "[2010] UKHL 3", "relation": "overrules", "paragraph_index": 1},
            ]
        }
    )
    client = _FakeFlashClient([_FakeResponse(payload)])

    stats = await extract_pass3(judgment=None, result=result, client=client)

    assert stats.classified == 3
    # 4 candidates are discovered by the regex pre-pass: the three the
    # model returns, plus [2021] UKSC 12 which appears in the text but the
    # model declined to classify.
    assert stats.candidates == 4
    kinds = [e.kind for e in result.edges]
    assert sorted(kinds) == ["cites", "distinguished_by", "overrules"]
    # All three cited cases got a CaseNode appended.
    cited_citations = {c.neutral_citation for c in result.referenced_cases}
    assert cited_citations == {"[2019] EWCA Civ 1374", "[2015] EWHC 2493 (Admin)", "[2010] UKHL 3"}
    # Paragraph attribution forwarded from the model.
    by_kind = {e.kind: e for e in result.edges}
    assert by_kind["cites"].paragraph_id == result.paragraphs[0].node_id
    assert by_kind["overrules"].paragraph_id == result.paragraphs[1].node_id


# ---------------------------------------------------------------------------
# 2. extract_pass3 — self-citation skipped, hallucinations dropped
# ---------------------------------------------------------------------------


async def test_pass3_skips_self_citation_and_drops_hallucinations():
    result = _make_result()
    # The model invents a citation that was not in CANDIDATES.
    payload = json.dumps(
        {
            "refs": [
                {"cited_citation": "[2023] UKSC 15", "relation": "cites"},  # self
                {"cited_citation": "[1999] EWHC 999", "relation": "cites"},  # hallucinated
                {"cited_citation": "[2019] EWCA Civ 1374", "relation": "cites"},  # real
            ]
        }
    )
    client = _FakeFlashClient([_FakeResponse(payload)])

    stats = await extract_pass3(judgment=None, result=result, client=client)

    assert stats.classified == 1
    assert len(result.edges) == 1
    assert result.edges[0].kind == "cites"
    assert result.edges[0].target_id != result.case.node_id  # not a self-edge


# ---------------------------------------------------------------------------
# 3. extract_pass3 — invalid relations dropped
# ---------------------------------------------------------------------------


async def test_pass3_drops_invalid_relations():
    result = _make_result()
    payload = json.dumps(
        {
            "refs": [
                {"cited_citation": "[2019] EWCA Civ 1374", "relation": "applies"},  # invalid
                {"cited_citation": "[2021] UKSC 12", "relation": "cites"},
            ]
        }
    )
    client = _FakeFlashClient([_FakeResponse(payload)])

    stats = await extract_pass3(judgment=None, result=result, client=client)

    assert stats.classified == 1
    assert [e.kind for e in result.edges] == ["cites"]


# ---------------------------------------------------------------------------
# 4. extract_pass3 — no candidates → no LLM call
# ---------------------------------------------------------------------------


async def test_pass3_skips_llm_when_no_candidates():
    case = _make_case()
    para = _make_paragraph(case, 0, "Plain text with zero neutral citations.")
    result = ExtractionResult(case=case, paragraphs=[para])

    class _ShouldNotCall:
        class models:
            @staticmethod
            def generate_content(**kwargs):
                raise AssertionError("LLM call must not happen when there are no candidates")

    stats = await extract_pass3(judgment=None, result=result, client=_ShouldNotCall())

    assert stats.candidates == 0
    assert stats.classified == 0
    assert stats.cost_usd == 0.0
    assert result.edges == []
    assert result.referenced_cases == []


# ---------------------------------------------------------------------------
# 5. extract_pass3 — idempotency: re-running emits no duplicate edges
# ---------------------------------------------------------------------------


async def test_pass3_idempotent_on_rerun():
    result = _make_result()
    payload = json.dumps(
        {
            "refs": [
                {"cited_citation": "[2019] EWCA Civ 1374", "relation": "cites"},
            ]
        }
    )

    # First run.
    client1 = _FakeFlashClient([_FakeResponse(payload)])
    await extract_pass3(judgment=None, result=result, client=client1)
    edges_after_first = list(result.edges)
    refs_after_first = list(result.referenced_cases)

    # Second run on a *fresh* result for the same case yields identical
    # node_ids — proving idempotency of the deterministic UUIDs.
    result2 = _make_result()
    client2 = _FakeFlashClient([_FakeResponse(payload)])
    await extract_pass3(judgment=None, result=result2, client=client2)

    assert [e.target_id for e in result2.edges] == [e.target_id for e in edges_after_first]
    assert [c.node_id for c in result2.referenced_cases] == [c.node_id for c in refs_after_first]


# ---------------------------------------------------------------------------
# 6. extract_pass3 — bad JSON raises FlashExtractionError
# ---------------------------------------------------------------------------


async def test_pass3_raises_on_non_json_response():
    result = _make_result()
    client = _FakeFlashClient([_FakeResponse("totally not json at all")])

    with pytest.raises(FlashExtractionError):
        await extract_pass3(judgment=None, result=result, client=client)


# ---------------------------------------------------------------------------
# 7. extract_pass3 — retryable 503 then success
# ---------------------------------------------------------------------------


async def test_pass3_retries_on_503_then_succeeds(monkeypatch):
    # Make backoff instant for tests.
    monkeypatch.setattr(p3, "_BASE_BACKOFF_S", 0.0)

    payload = json.dumps({"refs": [{"cited_citation": "[2019] EWCA Civ 1374", "relation": "cites"}]})
    result = _make_result()
    client = _FakeFlashClient(
        [
            RuntimeError("503 UNAVAILABLE"),
            _FakeResponse(payload),
        ]
    )

    stats = await extract_pass3(judgment=None, result=result, client=client)

    assert stats.classified == 1
    assert len(client.calls) == 2


# ---------------------------------------------------------------------------
# 8. extract_pass3 — non-retryable error fails fast
# ---------------------------------------------------------------------------


async def test_pass3_non_retryable_error_fails_fast(monkeypatch):
    monkeypatch.setattr(p3, "_BASE_BACKOFF_S", 0.0)
    result = _make_result()
    client = _FakeFlashClient([RuntimeError("400 INVALID_ARGUMENT")])

    with pytest.raises(FlashExtractionError):
        await extract_pass3(judgment=None, result=result, client=client)

    # Only one attempt because the error isn't retryable.
    assert len(client.calls) == 1


# ---------------------------------------------------------------------------
# 9. build_hyperedges — happy path
# ---------------------------------------------------------------------------


async def _fake_embedder(text: str) -> list[float]:
    # Deterministic, no real model needed. 768 floats so the shape matches
    # gemini-embedding-001 / the pgvector(768) column.
    return [float(len(text) % 100) / 100.0] * 768


async def test_build_hyperedges_collects_entities_and_embeds_each_paragraph():
    result = _make_result()

    # Seed paragraph 0 with one statute_ref and one section_ref.
    statute_id = uuid.uuid5(uuid.NAMESPACE_URL, "statute:equality-act-2010")
    section_id = uuid.uuid5(uuid.NAMESPACE_URL, "section:equality-act-2010/13")
    result.statute_refs.append(
        StatuteRefCandidate(
            candidate_node_id=statute_id,
            paragraph_id=result.paragraphs[0].node_id,
            short_title="Equality Act 2010",
            slug="equality-act-2010",
        )
    )
    result.section_refs.append(
        SectionRefCandidate(
            candidate_node_id=section_id,
            paragraph_id=result.paragraphs[0].node_id,
            section="13",
            subsection="(1)",
            statute_slug="equality-act-2010",
        )
    )
    # Seed paragraph 1 with a pass3-style edge.
    cited_case_id = uuid.uuid5(uuid.NAMESPACE_URL, "[2019] EWCA Civ 1374")
    result.edges.append(
        Edge(
            kind="cites",
            source_id=result.case.node_id,
            target_id=cited_case_id,
            paragraph_id=result.paragraphs[1].node_id,
        )
    )

    stats = await build_hyperedges(result, embedder=_fake_embedder)

    assert stats.hyperedges_built == 2  # both paragraphs have entities
    assert len(result.hyperedges) == 2

    h0 = next(h for h in result.hyperedges if h.paragraph_id == result.paragraphs[0].node_id)
    assert statute_id in h0.node_ids
    assert section_id in h0.node_ids
    assert result.case.node_id in h0.node_ids  # Case is always anchor
    assert len(h0.embedding) == 768

    h1 = next(h for h in result.hyperedges if h.paragraph_id == result.paragraphs[1].node_id)
    assert cited_case_id in h1.node_ids


async def test_build_hyperedges_skips_paragraphs_with_no_domain_entities():
    """A paragraph that only has the Case anchor (no statute/section/case
    references and no pass-2/3 edges) is skipped by default — adds no
    structural signal to the index.
    """
    result = _make_result()  # paragraphs have neutral citations only; without
    # the pass-3 edges seeded below, neither paragraph has any "domain entity"
    # — they only carry the Case anchor.

    stats = await build_hyperedges(result, embedder=_fake_embedder)

    assert stats.hyperedges_built == 0
    assert result.hyperedges == []


async def test_build_hyperedges_skip_empty_false_keeps_all_paragraphs():
    result = _make_result()
    stats = await build_hyperedges(result, embedder=_fake_embedder, skip_empty=False)

    assert stats.hyperedges_built == 2
    assert len(result.hyperedges) == 2
    # Each hyperedge has at least the Case anchor.
    for h in result.hyperedges:
        assert result.case.node_id in h.node_ids


# ---------------------------------------------------------------------------
# 12. make_pass3_runner — orchestrator-friendly tuple shape
# ---------------------------------------------------------------------------


async def test_make_pass3_runner_returns_orchestrator_tuple():
    payload = json.dumps({"refs": [{"cited_citation": "[2019] EWCA Civ 1374", "relation": "cites"}]})
    client = _FakeFlashClient([_FakeResponse(payload)])

    runner = make_pass3_runner(
        client=client,
        embedder=_fake_embedder,
        skip_empty_hyperedges=False,  # ensure hyperedges get built so the
        # cost component is non-zero and stable for the assertion.
    )

    result = _make_result()
    cost, model, in_tok, out_tok, note = await runner(judgment=None, result=result)

    assert isinstance(cost, float) and cost > 0
    assert model == "gemini-2.5-flash"
    assert in_tok == 1000
    assert out_tok == 200
    assert "candidates=" in note
    assert "classified=1" in note
    assert "hyperedges=" in note
