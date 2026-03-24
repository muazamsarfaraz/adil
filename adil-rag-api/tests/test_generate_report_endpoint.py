"""Tests for POST /api/v1/generate-report endpoint."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app import app
    return TestClient(app)


@pytest.fixture
def api_key():
    return os.environ.get("ADIL_API_KEY", "test-key")


class TestGenerateReportEndpoint:
    def test_rejects_empty_history(self, client, api_key):
        resp = client.post(
            "/api/v1/generate-report",
            json={"conversation_history": [], "report_type": "incident_summary"},
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_rejects_invalid_report_type(self, client, api_key):
        resp = client.post(
            "/api/v1/generate-report",
            json={
                "conversation_history": [{"role": "user", "content": "test"}],
                "report_type": "invalid_type",
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 422

    def test_endpoint_exists(self, client, api_key):
        """Smoke test: endpoint exists and accepts valid input."""
        resp = client.post(
            "/api/v1/generate-report",
            json={
                "conversation_history": [
                    {"role": "user", "content": "I was harassed at work"},
                    {"role": "model", "content": "That sounds like it could be direct discrimination."},
                ],
                "report_type": "incident_summary",
                "jurisdiction": "England and Wales",
            },
            headers={"X-API-Key": api_key},
        )
        # Not 404 (exists), not 422 (valid input)
        # May be 200 (Gemini configured) or 500/503 (Gemini not configured)
        assert resp.status_code in (200, 500, 503)

    def test_accepts_solicitor_pack_type(self, client, api_key):
        resp = client.post(
            "/api/v1/generate-report",
            json={
                "conversation_history": [
                    {"role": "user", "content": "My employer denied prayer breaks"},
                ],
                "report_type": "solicitor_pack",
            },
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code in (200, 500, 503)
