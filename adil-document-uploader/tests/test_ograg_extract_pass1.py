"""Tests for OG-RAG extraction pass 1 (structural / regex).

Five hand-curated judgment fixtures cover the regex patterns required by
the spec: neutral citations across UKSC/UKHL/EWCA/EWHC/UKEAT, section
references with subsections, EHRC code references, and statute short
title lookups.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

import pytest

from app.services.ograg_extract import (
    CaseNode,
    extract_pass1,
)
from app.services.ograg_extract.pass1_structural import (
    OGRAG_NAMESPACE,
    UK_STATUTE_SHORT_TITLES,
    _NEUTRAL_CITATION,
)


@dataclass
class _FakeJudgment:
    """Duck-typed stand-in for the Judgment ORM row."""

    neutral_citation: str
    case_name: str
    court: str
    judgment_date: date | None
    clean_text: str


# ---------------------------------------------------------------------------
# Fixtures: 5 hand-curated judgments
# ---------------------------------------------------------------------------


@pytest.fixture
def fixture_uksc_lee_ashers() -> _FakeJudgment:
    """UKSC religious-discrimination judgment with section refs to Equality Act."""
    return _FakeJudgment(
        neutral_citation="[2018] UKSC 49",
        case_name="Lee v Ashers Baking Co Ltd",
        court="UKSC",
        judgment_date=date(2018, 10, 10),
        clean_text=(
            "1. This appeal concerns alleged discrimination under the Equality Act 2010.\n\n"
            "2. The appellant relied on section 13 and section 19 of that Act.\n\n"
            "3. The court considered s.29(1) and s.29(2)(a) in detail.\n\n"
            "4. Reference was also made to the Human Rights Act 1998, in particular s.6.\n"
        ),
    )


@pytest.fixture
def fixture_ewca_employment() -> _FakeJudgment:
    """EWCA Civ employment judgment citing EHRC employment code paragraphs."""
    return _FakeJudgment(
        neutral_citation="[2021] EWCA Civ 1374",
        case_name="Higgs v Farmor's School",
        court="EWCA",
        judgment_date=date(2021, 9, 30),
        clean_text=(
            "1. The Claimant brought claims under the Equality Act 2010.\n\n"
            "2. The Employment Tribunal had regard to EHRC §3.5 and EHRC §3.5.2 of the "
            "employment code when applying section 26 of the Act.\n\n"
            "3. Section 26(4) was also considered.\n"
        ),
    )


@pytest.fixture
def fixture_ewhc_admin() -> _FakeJudgment:
    """EWHC Admin judgment with the parenthesised division form."""
    return _FakeJudgment(
        neutral_citation="[2015] EWHC 2493 (Admin)",
        case_name="R (on the application of X) v Secretary of State",
        court="EWHC",
        judgment_date=date(2015, 8, 28),
        clean_text=(
            "1. The Crime and Disorder Act 1998 is relevant to this appeal.\n\n"
            "2. Section 28 of that Act defines racial and religious aggravation.\n\n"
            "3. The Public Order Act 1986 was also invoked at trial; section 4A.\n"
        ),
    )


@pytest.fixture
def fixture_ukeat_no_paragraphs() -> _FakeJudgment:
    """UKEAT judgment with no numbered paragraph markers — header-style text."""
    return _FakeJudgment(
        neutral_citation="[2019] UKEAT 0044",
        case_name="Doe v Acme Ltd",
        court="UKEAT",
        judgment_date=date(2019, 6, 14),
        clean_text=(
            "JUDGMENT\n\n"
            "The Employment Appeal Tribunal heard this matter on 1 May 2019. "
            "The relevant statute is the Employment Rights Act 1996, particularly "
            "section 98 and section 98(4).\n\n"
            "The appeal is dismissed."
        ),
    )


@pytest.fixture
def fixture_ukhl_human_rights() -> _FakeJudgment:
    """UKHL judgment exercising the Human Rights Act statute lookup."""
    return _FakeJudgment(
        neutral_citation="[2004] UKHL 56",
        case_name="A v Secretary of State for the Home Department",
        court="UKHL",
        judgment_date=date(2004, 12, 16),
        clean_text=(
            "1. This case concerns the Human Rights Act 1998.\n\n"
            "2. The detention regime was challenged under section 23.\n\n"
            "3. Reference is made to the Equality Act 2010 in passing.\n"
        ),
    )


# ---------------------------------------------------------------------------
# Smoke / sanity tests
# ---------------------------------------------------------------------------


def test_namespace_is_stable() -> None:
    # Hard-coded value protects callers that persist node_ids in Postgres.
    assert OGRAG_NAMESPACE == uuid.UUID("c4dc7c0c-2b91-5b0a-94d1-7e4cc1c33adf")


def test_neutral_citation_regex_matches_all_court_tokens() -> None:
    cases = [
        "[2018] UKSC 49",
        "[2021] EWCA Civ 1374",
        "[2015] EWHC 2493 (Admin)",
        "[2019] UKEAT 0044",
        "[2004] UKHL 56",
    ]
    for c in cases:
        assert _NEUTRAL_CITATION.search(c) is not None, c


# ---------------------------------------------------------------------------
# Fixture 1: UKSC + Equality Act sections
# ---------------------------------------------------------------------------


def test_fixture1_extracts_case_and_paragraphs(fixture_uksc_lee_ashers: _FakeJudgment) -> None:
    result = extract_pass1(fixture_uksc_lee_ashers)
    assert isinstance(result.case, CaseNode)
    assert result.case.year == 2018
    assert result.case.court == "UKSC"
    assert len(result.paragraphs) == 4
    # Numbered paragraphs preserved.
    assert [p.number for p in result.paragraphs] == [1, 2, 3, 4]


def test_fixture1_extracts_statute_refs(fixture_uksc_lee_ashers: _FakeJudgment) -> None:
    result = extract_pass1(fixture_uksc_lee_ashers)
    slugs = sorted({r.slug for r in result.statute_refs})
    assert "equality-act-2010" in slugs
    assert "human-rights-act-1998" in slugs


def test_fixture1_extracts_section_refs_with_subsection(
    fixture_uksc_lee_ashers: _FakeJudgment,
) -> None:
    result = extract_pass1(fixture_uksc_lee_ashers)
    sections = [(r.section, r.subsection) for r in result.section_refs]
    assert ("13", None) in sections
    assert ("19", None) in sections
    assert ("29", "(1)") in sections
    assert ("29", "(2)(a)") in sections
    assert ("6", None) in sections


# ---------------------------------------------------------------------------
# Fixture 2: EWCA + EHRC code
# ---------------------------------------------------------------------------


def test_fixture2_extracts_ehrc_paragraphs(fixture_ewca_employment: _FakeJudgment) -> None:
    result = extract_pass1(fixture_ewca_employment)
    ehrc_refs = [r for r in result.section_refs if r.statute_slug == "ehrc-employment-code"]
    ehrc_sections = sorted(r.section for r in ehrc_refs)
    assert ehrc_sections == ["3.5", "3.5.2"]


def test_fixture2_case_division_parsed(fixture_ewca_employment: _FakeJudgment) -> None:
    result = extract_pass1(fixture_ewca_employment)
    assert result.case.year == 2021
    assert result.case.court == "EWCA"


# ---------------------------------------------------------------------------
# Fixture 3: EWHC (Admin)
# ---------------------------------------------------------------------------


def test_fixture3_admin_division_parsed(fixture_ewhc_admin: _FakeJudgment) -> None:
    result = extract_pass1(fixture_ewhc_admin)
    assert result.case.year == 2015
    slugs = {r.slug for r in result.statute_refs}
    assert "crime-and-disorder-act-1998" in slugs
    assert "public-order-act-1986" in slugs


def test_fixture3_section_attribution_when_single_statute_per_para(
    fixture_ewhc_admin: _FakeJudgment,
) -> None:
    """If one statute is named in a paragraph, sections in that paragraph
    are attributed to it (best-effort)."""
    result = extract_pass1(fixture_ewhc_admin)
    s28 = next(r for r in result.section_refs if r.section == "28")
    assert s28.statute_slug == "crime-and-disorder-act-1998"
    s4a = next(r for r in result.section_refs if r.section == "4A")
    assert s4a.statute_slug == "public-order-act-1986"


# ---------------------------------------------------------------------------
# Fixture 4: UKEAT without numbered paragraphs
# ---------------------------------------------------------------------------


def test_fixture4_unnumbered_paragraphs_get_none_number(
    fixture_ukeat_no_paragraphs: _FakeJudgment,
) -> None:
    result = extract_pass1(fixture_ukeat_no_paragraphs)
    assert all(p.number is None for p in result.paragraphs)
    assert len(result.paragraphs) == 3  # JUDGMENT, body, dismissed


def test_fixture4_finds_employment_rights_act(
    fixture_ukeat_no_paragraphs: _FakeJudgment,
) -> None:
    result = extract_pass1(fixture_ukeat_no_paragraphs)
    slugs = {r.slug for r in result.statute_refs}
    assert "employment-rights-act-1996" in slugs


# ---------------------------------------------------------------------------
# Fixture 5: UKHL + Human Rights Act
# ---------------------------------------------------------------------------


def test_fixture5_ukhl_parses(fixture_ukhl_human_rights: _FakeJudgment) -> None:
    result = extract_pass1(fixture_ukhl_human_rights)
    assert result.case.court == "UKHL"
    assert result.case.year == 2004


def test_fixture5_statute_refs_dedupe_per_paragraph(
    fixture_ukhl_human_rights: _FakeJudgment,
) -> None:
    """Statute mentions are deduped within a paragraph, not across the case."""
    result = extract_pass1(fixture_ukhl_human_rights)
    slugs = sorted(r.slug for r in result.statute_refs)
    assert slugs == ["equality-act-2010", "human-rights-act-1998"]


# ---------------------------------------------------------------------------
# Idempotency: same judgment in → same node IDs out
# ---------------------------------------------------------------------------


def test_idempotent_node_ids(fixture_uksc_lee_ashers: _FakeJudgment) -> None:
    r1 = extract_pass1(fixture_uksc_lee_ashers)
    r2 = extract_pass1(fixture_uksc_lee_ashers)
    assert r1.case.node_id == r2.case.node_id
    assert [p.node_id for p in r1.paragraphs] == [p.node_id for p in r2.paragraphs]
    assert [r.candidate_node_id for r in r1.statute_refs] == [r.candidate_node_id for r in r2.statute_refs]
    assert [r.candidate_node_id for r in r1.section_refs] == [r.candidate_node_id for r in r2.section_refs]


def test_different_judgments_produce_different_case_ids(
    fixture_uksc_lee_ashers: _FakeJudgment,
    fixture_ewca_employment: _FakeJudgment,
) -> None:
    r1 = extract_pass1(fixture_uksc_lee_ashers)
    r2 = extract_pass1(fixture_ewca_employment)
    assert r1.case.node_id != r2.case.node_id


# ---------------------------------------------------------------------------
# Resolver callbacks integrate with P1.5's acts fetcher output
# ---------------------------------------------------------------------------


def test_statute_resolver_substitutes_canonical_node_id(
    fixture_uksc_lee_ashers: _FakeJudgment,
) -> None:
    canonical = uuid.UUID("11111111-1111-1111-1111-111111111111")

    def resolver(slug: str) -> uuid.UUID | None:
        return canonical if slug == "equality-act-2010" else None

    result = extract_pass1(fixture_uksc_lee_ashers, statute_resolver=resolver)
    ea = next(r for r in result.statute_refs if r.slug == "equality-act-2010")
    assert ea.resolved_node_id == canonical
    hr = next(r for r in result.statute_refs if r.slug == "human-rights-act-1998")
    assert hr.resolved_node_id is None  # resolver said no — Pass 2 / writer resolves


def test_section_resolver_invoked_only_when_statute_slug_known(
    fixture_ewhc_admin: _FakeJudgment,
) -> None:
    calls: list[tuple[str, str]] = []

    def resolver(slug: str, section: str) -> uuid.UUID | None:
        calls.append((slug, section))
        return None

    extract_pass1(fixture_ewhc_admin, section_resolver=resolver)
    # Both attributed sections in fixture 3 should reach the resolver.
    assert ("crime-and-disorder-act-1998", "28") in calls
    assert ("public-order-act-1986", "4A") in calls


# ---------------------------------------------------------------------------
# Statute table sanity
# ---------------------------------------------------------------------------


def test_statute_short_titles_table_nonempty() -> None:
    # Guard against an accidental empty dict — would silently disable
    # statute extraction.
    assert len(UK_STATUTE_SHORT_TITLES) >= 10
    assert "Equality Act 2010" in UK_STATUTE_SHORT_TITLES
