"""Tests for target configuration."""

from targets import TARGETS, get_target, validate_data_for_target


def test_police_uk_target_exists():
    assert "police-uk" in TARGETS


def test_police_uk_has_required_keys():
    t = TARGETS["police-uk"]
    assert "name" in t
    assert "url" in t
    assert "instructions" in t
    assert "required_fields" in t
    assert "optional_fields" in t
    assert "coverage" in t


def test_police_uk_url():
    t = TARGETS["police-uk"]
    assert "police.uk" in t["url"]


def test_get_target_valid():
    t = get_target("police-uk")
    assert t["name"] == "Police UK — National Hate Crime Report"


def test_get_target_invalid():
    assert get_target("nonexistent") is None


def test_validate_data_all_required_present():
    data = {
        "first_name": "Ahmad",
        "surname": "Hassan",
        "dob": {"day": "15", "month": "06", "year": "1990"},
        "gender": "male",
        "email": "ahmad@example.com",
        "incident_details": "Something happened",
        "location": "London",
        "date_time": "10 March 2026",
    }
    missing = validate_data_for_target("police-uk", data)
    assert missing == []


def test_validate_data_missing_fields():
    data = {"first_name": "Ahmad"}
    missing = validate_data_for_target("police-uk", data)
    assert "surname" in missing
    assert "email" in missing
    assert "incident_details" in missing


def test_tell_mama_target_exists():
    assert "tell-mama" in TARGETS
    t = TARGETS["tell-mama"]
    assert "tellmamauk.org" in t["url"]
    assert t["coverage"] == "United Kingdom"
    assert "incident_type" in t["required_fields"]


def test_police_scotland_target_exists():
    assert "police-scotland" in TARGETS
    t = TARGETS["police-scotland"]
    assert "scotland.police.uk" in t["url"]
    assert t["coverage"] == "Scotland"


def test_british_muslim_trust_target_exists():
    assert "british-muslim-trust" in TARGETS
    t = TARGETS["british-muslim-trust"]
    assert "britishmuslimtrust.co.uk/report-hate" in t["url"]
    assert t["adapter_type"] == "browser"
    assert t["coverage"] == "United Kingdom"
    assert "instructions" in t
    assert "city" in t["required_fields"]


def test_muslim_safety_net_target_exists():
    assert "muslim-safety-net" in TARGETS
    t = TARGETS["muslim-safety-net"]
    assert "muslimsafetynet.org.uk/report" in t["url"]
    assert t["adapter_type"] == "browser"
    assert t["coverage"] == "United Kingdom"


def test_prevent_watch_target_exists():
    assert "prevent-watch" in TARGETS
    t = TARGETS["prevent-watch"]
    assert "preventwatch.org" in t["url"]
    assert t["adapter_type"] == "email"
    assert t["email_to"] == "contact@preventwatch.org"
    assert t["coverage"] == "United Kingdom"


def test_all_targets_have_required_keys():
    common_keys = {"name", "url", "required_fields", "optional_fields", "coverage", "adapter_type"}
    for tid, tcfg in TARGETS.items():
        for key in common_keys:
            assert key in tcfg, f"Target '{tid}' missing key '{key}'"
        if tcfg["adapter_type"] == "browser":
            assert "instructions" in tcfg, f"Browser target '{tid}' missing 'instructions'"
        elif tcfg["adapter_type"] == "email":
            assert "email_to" in tcfg, f"Email target '{tid}' missing 'email_to'"
        else:
            raise AssertionError(f"Target '{tid}' has unknown adapter_type '{tcfg['adapter_type']!r}'")


def test_email_targets_have_recipients():
    email_targets = {tid: t for tid, t in TARGETS.items() if t.get("adapter_type") == "email"}
    assert len(email_targets) >= 3
    for tid, t in email_targets.items():
        assert "@" in t["email_to"], f"Email target '{tid}' has invalid email_to"
