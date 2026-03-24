"""Tests for the analytics endpoint."""

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


class TestAnalyticsEndpoint:
    def test_endpoint_exists(self, client, api_key):
        resp = client.get("/api/v1/analytics", headers={"X-API-Key": api_key})
        # 200 if Postgres configured, 503 if not
        assert resp.status_code in (200, 503)

    def test_returns_expected_structure(self, client, api_key):
        resp = client.get("/api/v1/analytics", headers={"X-API-Key": api_key})
        if resp.status_code == 200:
            data = resp.json()
            assert "total_conversations" in data
            assert "topics" in data
            assert "jurisdictions" in data

    def test_requires_auth(self, client):
        resp = client.get("/api/v1/analytics")
        assert resp.status_code in (401, 403)
