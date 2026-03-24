"""Tests for viability scoring extraction."""

from rag_service import RAGService


class TestParseViability:
    """Test the viability parser extracts structured data from Gemini text."""

    def test_parses_viability_block(self):
        text = (
            "Some legal analysis here.\n\n"
            "---VIABILITY_ASSESSMENT---\n"
            "SCORE: 72\n"
            "VENTO_BAND: middle\n"
            "VENTO_RANGE: £12,000 – £36,500\n"
            "STATUTORY_FOOTING: true\n"
            "CASE_LAW_PRECEDENT: true\n"
            "QUANTUM_POTENTIAL: true\n"
            "REASONING: Strong statutory basis under s.13 Equality Act 2010.\n"
            "---END_VIABILITY---"
        )
        result = RAGService._parse_viability(text)
        assert result is not None
        assert result.score == 72
        assert result.vento_band.value == "middle"
        assert result.statutory_footing is True
        assert result.case_law_precedent is True
        assert result.quantum_potential is True
        assert "s.13" in result.reasoning

    def test_parses_lower_band(self):
        text = (
            "---VIABILITY_ASSESSMENT---\n"
            "SCORE: 35\n"
            "VENTO_BAND: lower\n"
            "VENTO_RANGE: £1,200 – £12,000\n"
            "STATUTORY_FOOTING: true\n"
            "CASE_LAW_PRECEDENT: false\n"
            "QUANTUM_POTENTIAL: false\n"
            "REASONING: Some basis but weak evidence.\n"
            "---END_VIABILITY---"
        )
        result = RAGService._parse_viability(text)
        assert result is not None
        assert result.score == 35
        assert result.vento_band.value == "lower"
        assert result.case_law_precedent is False

    def test_parses_upper_band(self):
        text = (
            "---VIABILITY_ASSESSMENT---\n"
            "SCORE: 85\n"
            "VENTO_BAND: upper\n"
            "VENTO_RANGE: £36,500 – £61,000\n"
            "STATUTORY_FOOTING: true\n"
            "CASE_LAW_PRECEDENT: true\n"
            "QUANTUM_POTENTIAL: true\n"
            "REASONING: Sustained campaign of harassment with strong evidence.\n"
            "---END_VIABILITY---"
        )
        result = RAGService._parse_viability(text)
        assert result is not None
        assert result.score == 85
        assert result.vento_band.value == "upper"

    def test_parses_exceptional_band(self):
        text = (
            "---VIABILITY_ASSESSMENT---\n"
            "SCORE: 95\n"
            "VENTO_BAND: exceptional\n"
            "VENTO_RANGE: £61,000+\n"
            "STATUTORY_FOOTING: true\n"
            "CASE_LAW_PRECEDENT: true\n"
            "QUANTUM_POTENTIAL: true\n"
            "REASONING: Multiple protected characteristics, extreme and prolonged abuse.\n"
            "---END_VIABILITY---"
        )
        result = RAGService._parse_viability(text)
        assert result is not None
        assert result.score == 95
        assert result.vento_band.value == "exceptional"

    def test_returns_none_when_no_block(self):
        text = "Just a normal response without viability data."
        result = RAGService._parse_viability(text)
        assert result is None

    def test_strips_viability_block_from_answer(self):
        text = (
            "Legal analysis here.\n\n"
            "---VIABILITY_ASSESSMENT---\n"
            "SCORE: 50\n"
            "VENTO_BAND: middle\n"
            "REASONING: Test.\n"
            "---END_VIABILITY---\n\n"
            "More text after."
        )
        cleaned = RAGService._strip_viability_block(text)
        assert "---VIABILITY_ASSESSMENT---" not in cleaned
        assert "Legal analysis here." in cleaned
        assert "More text after." in cleaned

    def test_handles_malformed_score(self):
        text = (
            "---VIABILITY_ASSESSMENT---\n"
            "SCORE: not_a_number\n"
            "VENTO_BAND: middle\n"
            "REASONING: Test.\n"
            "---END_VIABILITY---"
        )
        result = RAGService._parse_viability(text)
        # Should either return None or handle gracefully
        assert result is None or isinstance(result.score, int)

    def test_clamps_score_to_valid_range(self):
        text = (
            "---VIABILITY_ASSESSMENT---\n"
            "SCORE: 150\n"
            "VENTO_BAND: upper\n"
            "REASONING: Over the top.\n"
            "---END_VIABILITY---"
        )
        result = RAGService._parse_viability(text)
        assert result is not None
        assert result.score <= 100

    def test_requires_hitl_always_true(self):
        text = (
            "---VIABILITY_ASSESSMENT---\n"
            "SCORE: 50\n"
            "VENTO_BAND: middle\n"
            "REASONING: Test.\n"
            "---END_VIABILITY---"
        )
        result = RAGService._parse_viability(text)
        assert result is not None
        assert result.requires_hitl is True

    def test_handles_missing_optional_fields(self):
        text = "---VIABILITY_ASSESSMENT---\n" "SCORE: 40\n" "REASONING: Minimal info.\n" "---END_VIABILITY---"
        result = RAGService._parse_viability(text)
        assert result is not None
        assert result.score == 40
        assert result.vento_band is None
        assert result.vento_range is None
