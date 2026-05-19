"""Pure-logic tests for MCA inline → ontology promotion.

These tests don't touch the database. The DB write path (``promote_to_db``)
is exercised by the integration test in ``test_ograg_store.py``-style
fixtures once the ontology migration ships in prod; for the half-day
deliverable, the deterministic node/edge generation is what matters.
"""

from ograg.mca_promote import (
    MCA_ACT_REFS,
    MCA_CASE_NAMES,
    Edge,
    Node,
    _case_id,
    _section_id,
    _statute_id,
    build_nodes_and_edges,
)

from rag_service import LEGISLATION_SNIPPETS, UK_CASE_LAW, UK_LEGISLATION_URLS


def _build():
    return build_nodes_and_edges(LEGISLATION_SNIPPETS, UK_CASE_LAW, UK_LEGISLATION_URLS)


def test_emits_statute_section_and_case_node_types():
    nodes, _ = _build()
    types = {n.type for n in nodes}
    assert {"Statute", "Section", "Case"}.issubset(types)


def test_all_three_mca_statutes_present():
    nodes, _ = _build()
    statute_names = {n.attrs["name"] for n in nodes if n.type == "Statute"}
    assert statute_names == set(MCA_ACT_REFS.keys())


def test_mca_2005_statute_attrs_match_legislation_gov_uk():
    nodes, _ = _build()
    mca = next(n for n in nodes if n.type == "Statute" and n.attrs["name"] == "Mental Capacity Act 2005")
    assert mca.attrs["leg_type"] == "ukpga"
    assert mca.attrs["year"] == 2005
    assert mca.attrs["leg_number"] == 9
    assert mca.attrs["url"] == "https://www.legislation.gov.uk/ukpga/2005/9"


def test_all_inline_mca_sections_promoted():
    nodes, _ = _build()
    mca_statute = _statute_id("ukpga", 2005, 9)
    sections = {
        n.attrs["number"] for n in nodes if n.type == "Section" and n.attrs.get("statute_id") == str(mca_statute)
    }
    expected = set(LEGISLATION_SNIPPETS["Mental Capacity Act 2005"].keys())
    assert sections == expected


def test_section_text_preserved_from_inline_snippet():
    nodes, _ = _build()
    mca_statute = _statute_id("ukpga", 2005, 9)
    s3 = next(
        n
        for n in nodes
        if n.type == "Section" and n.attrs.get("statute_id") == str(mca_statute) and n.attrs["number"] == "3"
    )
    assert s3.attrs["text"] == LEGISLATION_SNIPPETS["Mental Capacity Act 2005"]["3"]


def test_all_curated_cop_cases_promoted():
    nodes, _ = _build()
    case_names = {n.attrs["name"] for n in nodes if n.type == "Case"}
    assert case_names == MCA_CASE_NAMES


def test_statute_contains_section_edges_match_section_count():
    nodes, edges = _build()
    mca_statute = _statute_id("ukpga", 2005, 9)
    contains = [e for e in edges if e.relation == "contains" and e.source_id == mca_statute]
    mca_sections = [n for n in nodes if n.type == "Section" and n.attrs.get("statute_id") == str(mca_statute)]
    assert len(contains) == len(mca_sections)


def test_every_cop_case_interprets_mca_2005():
    nodes, edges = _build()
    mca_statute = _statute_id("ukpga", 2005, 9)
    case_ids = {n.id for n in nodes if n.type == "Case"}
    interprets_targets = {e.source_id for e in edges if e.relation == "interprets" and e.target_id == mca_statute}
    assert interprets_targets == case_ids


def test_jb_case_cites_section_3_specifically():
    _, edges = _build()
    mca_statute = _statute_id("ukpga", 2005, 9)
    s3 = _section_id(mca_statute, "3")
    jb = _case_id("[2021] UKSC 52")
    cites_s3 = [e for e in edges if e.relation == "cites" and e.source_id == jb and e.target_id == s3]
    assert len(cites_s3) == 1


def test_node_ids_are_deterministic_across_runs():
    a_nodes, a_edges = _build()
    b_nodes, b_edges = _build()
    assert sorted(str(n.id) for n in a_nodes) == sorted(str(n.id) for n in b_nodes)
    assert sorted(str(e.id) for e in a_edges) == sorted(str(e.id) for e in b_edges)


def test_statute_id_matches_uploader_namespace():
    """The MCA Statute UUID must match what ontology_writer in
    adil-document-uploader would generate, so the legislation.gov.uk
    re-ingest merges on the same row (not creates a duplicate).
    """
    from uuid import UUID, uuid5

    # Replicates _NS in both modules (single source of truth would be
    # nicer, but the two services ship independently).
    ns = UUID("d8e8a8e8-1d0c-4b87-9d76-1f7e1fa1ad11")
    expected = uuid5(ns, "statute:ukpga/2005/9")
    assert _statute_id("ukpga", 2005, 9) == expected


def test_dataclasses_are_immutable():
    """Frozen dataclasses guarantee callers can't accidentally mutate
    a generated node/edge between build and write.
    """
    import pytest

    nodes, edges = _build()
    with pytest.raises(dataclasses_FrozenInstanceError()):
        nodes[0].type = "Other"  # type: ignore[misc]
    with pytest.raises(dataclasses_FrozenInstanceError()):
        edges[0].relation = "other"  # type: ignore[misc]


def dataclasses_FrozenInstanceError():  # helper to keep the import local
    import dataclasses

    return dataclasses.FrozenInstanceError


def test_node_and_edge_are_exported():
    """Smoke test that the public dataclasses are importable for callers."""
    assert Node is not None
    assert Edge is not None
