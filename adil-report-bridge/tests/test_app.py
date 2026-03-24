"""Tests for the bridge FastAPI app."""

import os
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

os.environ["BRIDGE_API_KEY"] = "test-bridge-key"
os.environ["GOOGLE_API_KEY"] = "test-google-key"

from app import app

client = TestClient(app)
HEADERS = {"X-Bridge-Key": "test-bridge-key"}


def test_health():
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "healthy"


def test_targets():
    resp = client.get("/targets", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert "police-uk" in data


def test_submit_no_auth():
    resp = client.post("/submit", json={"target": "police-uk", "data": {}})
    assert resp.status_code == 403


def test_submit_invalid_target():
    resp = client.post(
        "/submit",
        headers=HEADERS,
        json={"target": "nonexistent", "data": {}},
    )
    assert resp.status_code == 400


def test_submit_missing_fields():
    resp = client.post(
        "/submit",
        headers=HEADERS,
        json={"target": "police-uk", "data": {"first_name": "Ahmad"}},
    )
    assert resp.status_code == 422


@patch("app._submit_report", new_callable=AsyncMock)
def test_submit_success(mock_submit):
    mock_submit.return_value = {
        "success": True,
        "target": "police-uk",
        "reference_number": "HC-2026-99999",
        "confirmation_screenshot": "base64data",
        "confirmation_text": "Your report has been submitted.",
        "submitted_at": "2026-03-22T19:30:00Z",
    }
    resp = client.post(
        "/submit",
        headers=HEADERS,
        json={
            "target": "police-uk",
            "data": {
                "first_name": "Ahmad",
                "surname": "Hassan",
                "dob": {"day": "15", "month": "06", "year": "1990"},
                "gender": "male",
                "email": "ahmad@example.com",
                "incident_details": "Hate incident occurred",
                "location": "London E1",
                "date_time": "10 March 2026",
            },
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["success"] is True
    assert data["reference_number"] == "HC-2026-99999"
