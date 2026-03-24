"""Tests for smart form guide generation."""

from report_generator import (
    _build_police_scotland_guide_prompt,
    _build_police_uk_guide_prompt,
    _build_tell_mama_guide_prompt,
    get_report_prompt,
)


class TestPoliceUKGuide:
    def test_contains_form_url(self):
        prompt = _build_police_uk_guide_prompt("England and Wales")
        assert "police.uk" in prompt

    def test_contains_step_by_step(self):
        prompt = _build_police_uk_guide_prompt()
        assert "Step" in prompt or "step" in prompt

    def test_is_instruction_not_conversation(self):
        prompt = _build_police_uk_guide_prompt()
        assert "NOT having a conversation" in prompt


class TestTellMAMAGuide:
    def test_contains_form_url(self):
        prompt = _build_tell_mama_guide_prompt()
        assert "tellmamauk.org" in prompt

    def test_contains_step_by_step(self):
        prompt = _build_tell_mama_guide_prompt()
        assert "Step" in prompt or "step" in prompt


class TestPoliceScotlandGuide:
    def test_contains_form_url(self):
        prompt = _build_police_scotland_guide_prompt()
        assert "scotland.police.uk" in prompt

    def test_contains_step_by_step(self):
        prompt = _build_police_scotland_guide_prompt()
        assert "Step" in prompt or "step" in prompt


class TestGetReportPromptGuides:
    def test_police_uk_guide_type(self):
        prompt = get_report_prompt("police_uk_guide")
        assert "police.uk" in prompt

    def test_tell_mama_guide_type(self):
        prompt = get_report_prompt("tell_mama_guide")
        assert "tellmamauk.org" in prompt

    def test_police_scotland_guide_type(self):
        prompt = get_report_prompt("police_scotland_guide")
        assert "scotland.police.uk" in prompt
