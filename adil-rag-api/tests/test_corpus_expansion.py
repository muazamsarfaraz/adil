"""Tests for jurisdiction-specific legislation corpus."""

from rag_service import LEGISLATION_SNIPPETS, UK_CASE_LAW


class TestScotlandCorpus:
    def test_hate_crime_act_2021_present(self):
        assert any("Hate Crime" in key for key in LEGISLATION_SNIPPETS)

    def test_hate_crime_act_has_sections(self):
        key = [k for k in LEGISLATION_SNIPPETS if "Hate Crime" in k][0]
        snippet = LEGISLATION_SNIPPETS[key]
        assert "stirring up hatred" in str(snippet).lower() or "aggravation" in str(snippet).lower()


class TestNorthernIrelandCorpus:
    def test_feto_1998_present(self):
        assert any("FETO" in key or "Fair Employment" in key for key in LEGISLATION_SNIPPETS)

    def test_race_relations_order_present(self):
        assert any("Race Relations" in key and ("NI" in key or "1997" in key) for key in LEGISLATION_SNIPPETS)


class TestCaseLawExpansion:
    def test_scottish_case_present(self):
        """At least one Scottish-jurisdiction case should exist."""
        scottish_cases = [
            name
            for name, info in UK_CASE_LAW.items()
            if "scotland" in info.get("court", "").lower()
            or "scottish" in info.get("court", "").lower()
            or "sheriff" in info.get("court", "").lower()
        ]
        # If no Scottish cases exist yet, check for Scotland in jurisdiction field
        if not scottish_cases:
            scottish_cases = [name for name, info in UK_CASE_LAW.items() if "scotland" in str(info).lower()]
        assert len(scottish_cases) >= 1
