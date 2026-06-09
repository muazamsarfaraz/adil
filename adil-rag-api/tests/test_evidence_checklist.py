"""Tests for evidence checklist parsing."""

from rag_service import RAGService


class TestParseEvidenceChecklist:
    def test_parses_checklist_block(self):
        text = (
            "Legal analysis here.\n\n"
            "---EVIDENCE_CHECKLIST---\n"
            "- Save screenshots of the discriminatory messages\n"
            "- Note the exact date, time, and location of the incident\n"
            "- Get contact details of any witnesses\n"
            "- Keep copies of any formal complaints you have made\n"
            "---END_CHECKLIST---"
        )
        items = RAGService._parse_evidence_checklist(text)
        assert len(items) == 4
        assert "screenshots" in items[0].lower()
        assert "witnesses" in items[2].lower()

    def test_returns_empty_when_no_block(self):
        text = "Just a normal response."
        items = RAGService._parse_evidence_checklist(text)
        assert items == []

    def test_strips_checklist_block_from_answer(self):
        text = "Analysis.\n\n---EVIDENCE_CHECKLIST---\n- Item 1\n- Item 2\n---END_CHECKLIST---\n\nMore text."
        cleaned = RAGService._strip_evidence_checklist(text)
        assert "---EVIDENCE_CHECKLIST---" not in cleaned
        assert "Analysis." in cleaned
        assert "More text." in cleaned

    def test_handles_items_without_dashes(self):
        text = "---EVIDENCE_CHECKLIST---\nSave screenshots\nNote dates\n---END_CHECKLIST---"
        items = RAGService._parse_evidence_checklist(text)
        assert len(items) == 2
