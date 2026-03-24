"""Tests for report generation Pydantic models."""

import pytest
from pydantic import ValidationError

from models import (
    ConversationTurn,
    GenerateReportRequest,
    GenerateReportResponse,
    ReportSection,
    ReportType,
)


class TestReportType:
    def test_incident_summary_value(self):
        assert ReportType.INCIDENT_SUMMARY == "incident_summary"

    def test_solicitor_pack_value(self):
        assert ReportType.SOLICITOR_PACK == "solicitor_pack"


class TestGenerateReportRequest:
    def test_valid_incident_summary(self):
        req = GenerateReportRequest(
            conversation_history=[
                ConversationTurn(role="user", content="I was harassed at work for wearing hijab"),
                ConversationTurn(role="model", content="I understand. Let me help."),
            ],
            report_type=ReportType.INCIDENT_SUMMARY,
        )
        assert req.report_type == ReportType.INCIDENT_SUMMARY
        assert len(req.conversation_history) == 2

    def test_valid_solicitor_pack_with_jurisdiction(self):
        req = GenerateReportRequest(
            conversation_history=[
                ConversationTurn(role="user", content="My employer denied me prayer breaks"),
            ],
            report_type=ReportType.SOLICITOR_PACK,
            jurisdiction="Scotland",
        )
        assert req.report_type == ReportType.SOLICITOR_PACK
        assert req.jurisdiction == "Scotland"

    def test_rejects_empty_history(self):
        with pytest.raises(ValidationError):
            GenerateReportRequest(
                conversation_history=[],
                report_type=ReportType.INCIDENT_SUMMARY,
            )

    def test_defaults_to_incident_summary(self):
        req = GenerateReportRequest(
            conversation_history=[
                ConversationTurn(role="user", content="test"),
            ],
        )
        assert req.report_type == ReportType.INCIDENT_SUMMARY

    def test_jurisdiction_optional(self):
        req = GenerateReportRequest(
            conversation_history=[
                ConversationTurn(role="user", content="test"),
            ],
        )
        assert req.jurisdiction is None


class TestReportSection:
    def test_valid_section(self):
        section = ReportSection(heading="WHAT HAPPENED", content="Someone shouted abuse.")
        assert section.heading == "WHAT HAPPENED"
        assert section.content == "Someone shouted abuse."


class TestGenerateReportResponse:
    def test_valid_response(self):
        resp = GenerateReportResponse(
            report_text="--- INCIDENT REPORT ---\nTest",
            report_type=ReportType.INCIDENT_SUMMARY,
            sections=[ReportSection(heading="WHAT HAPPENED", content="Test")],
        )
        assert resp.report_type == ReportType.INCIDENT_SUMMARY
        assert len(resp.sections) == 1
        assert resp.generated_at is not None

    def test_generated_at_auto_set(self):
        resp = GenerateReportResponse(
            report_text="test",
            report_type=ReportType.SOLICITOR_PACK,
        )
        assert "T" in resp.generated_at  # ISO format contains T
