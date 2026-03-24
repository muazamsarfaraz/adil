"""Tests for bridge Pydantic models."""

import pytest
from pydantic import ValidationError

from models import DOB, SubmitRequest, SubmitResponse


def test_submit_request_valid():
    req = SubmitRequest(
        target="police-uk",
        data={
            "first_name": "Ahmad",
            "surname": "Hassan",
            "dob": {"day": "15", "month": "06", "year": "1990"},
            "gender": "male",
            "email": "ahmad@example.com",
            "incident_details": "Hate incident occurred outside station",
            "location": "London E1",
            "date_time": "10 March 2026, 5:30pm",
        },
    )
    assert req.target == "police-uk"
    assert req.data["first_name"] == "Ahmad"


def test_submit_request_missing_target():
    with pytest.raises(ValidationError):
        SubmitRequest(data={"first_name": "Test"})


def test_submit_response_success():
    resp = SubmitResponse(
        success=True,
        target="police-uk",
        reference_number="HC-2026-12345",
        confirmation_screenshot="base64data",
        confirmation_text="Report submitted.",
    )
    assert resp.success is True
    assert resp.reference_number == "HC-2026-12345"


def test_submit_response_failure():
    resp = SubmitResponse(
        success=False,
        target="police-uk",
        error="Site unreachable",
        fallback_report="--- INCIDENT REPORT ---",
        target_url="https://www.police.uk/ro/report/hate-crime/forms/v1/hate-crime-online2/",
    )
    assert resp.success is False
    assert resp.error == "Site unreachable"


def test_dob_model():
    dob = DOB(day="15", month="06", year="1990")
    assert dob.day == "15"
