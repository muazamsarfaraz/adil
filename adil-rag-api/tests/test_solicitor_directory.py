"""Tests for the solicitor directory endpoint."""

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


class TestSolicitorDirectoryEndpoint:
    def test_endpoint_exists(self, client, api_key):
        resp = client.get("/api/v1/solicitors", headers={"X-API-Key": api_key})
        assert resp.status_code == 200

    def test_returns_list(self, client, api_key):
        resp = client.get("/api/v1/solicitors", headers={"X-API-Key": api_key})
        data = resp.json()
        assert "solicitors" in data
        assert isinstance(data["solicitors"], list)
        assert len(data["solicitors"]) > 0

    def test_filter_by_jurisdiction(self, client, api_key):
        resp = client.get("/api/v1/solicitors?jurisdiction=scotland", headers={"X-API-Key": api_key})
        data = resp.json()
        for firm in data["solicitors"]:
            assert "scotland" in firm.get("jurisdiction", "").lower() or "uk" in firm.get("jurisdiction", "").lower()

    def test_filter_by_specialism(self, client, api_key):
        resp = client.get("/api/v1/solicitors?specialism=employment", headers={"X-API-Key": api_key})
        data = resp.json()
        assert len(data["solicitors"]) > 0

    def test_includes_disclaimer(self, client, api_key):
        resp = client.get("/api/v1/solicitors", headers={"X-API-Key": api_key})
        data = resp.json()
        assert "disclaimer" in data

    def test_all_firms_show_outreach_pending(self, client, api_key):
        resp = client.get("/api/v1/solicitors", headers={"X-API-Key": api_key})
        data = resp.json()
        for firm in data["solicitors"]:
            assert firm.get("outreach_status") in ("not_contacted", "pending")

    def test_filter_by_location(self, client, api_key):
        resp = client.get("/api/v1/solicitors?location=london", headers={"X-API-Key": api_key})
        data = resp.json()
        assert len(data["solicitors"]) > 0
        for firm in data["solicitors"]:
            locations_lower = [loc.lower() for loc in firm.get("locations", [])]
            assert any("london" in loc for loc in locations_lower)

    def test_firm_has_required_fields(self, client, api_key):
        resp = client.get("/api/v1/solicitors", headers={"X-API-Key": api_key})
        data = resp.json()
        required_fields = {"name", "locations", "specialisms", "jurisdiction", "website", "outreach_status", "category"}
        for firm in data["solicitors"]:
            for field in required_fields:
                assert field in firm, f"Missing field '{field}' in firm {firm.get('name', '?')}"

    def test_returns_total_count(self, client, api_key):
        resp = client.get("/api/v1/solicitors", headers={"X-API-Key": api_key})
        data = resp.json()
        assert "total" in data
        assert data["total"] == len(data["solicitors"])

    def test_no_results_filter(self, client, api_key):
        resp = client.get("/api/v1/solicitors?specialism=nonexistent_specialism_xyz", headers={"X-API-Key": api_key})
        data = resp.json()
        assert data["solicitors"] == []
        assert data["total"] == 0
