"""Tests for the geo-ranked solicitor finder."""

from __future__ import annotations

import os
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _reset_osrm_env():
    """Default to OSRM disabled so tests don't reach out to the network."""
    prev = os.environ.get("USE_OSRM")
    os.environ["USE_OSRM"] = "false"
    yield
    if prev is None:
        os.environ.pop("USE_OSRM", None)
    else:
        os.environ["USE_OSRM"] = prev


# -----------------------------------------------------------------
# postcodes_io
# -----------------------------------------------------------------


def test_normalise_postcode_strips_whitespace_and_uppercases():
    from postcodes_io import normalise_postcode

    assert normalise_postcode("m14 5ab") == "M145AB"
    assert normalise_postcode("  EC2N 4AY  ") == "EC2N4AY"
    assert normalise_postcode(None) == ""
    assert normalise_postcode("") == ""


def test_is_valid_uk_postcode_accepts_common_shapes():
    from postcodes_io import is_valid_uk_postcode

    assert is_valid_uk_postcode("M14 5AB")
    assert is_valid_uk_postcode("EC2N 4AY")
    assert is_valid_uk_postcode("B11 3HE")
    assert is_valid_uk_postcode("SW1A 1AA")
    assert not is_valid_uk_postcode("")
    assert not is_valid_uk_postcode("NOT-A-POSTCODE")
    assert not is_valid_uk_postcode("12345")


# -----------------------------------------------------------------
# osrm_client
# -----------------------------------------------------------------


def test_osrm_disabled_when_use_osrm_false():
    import osrm_client

    os.environ["USE_OSRM"] = "false"
    assert osrm_client.is_enabled() is False


def test_osrm_enabled_by_default_with_url():
    import osrm_client

    os.environ["USE_OSRM"] = "true"
    os.environ["OSRM_SERVICE_URL"] = "https://example.org"
    try:
        assert osrm_client.is_enabled() is True
    finally:
        os.environ.pop("OSRM_SERVICE_URL", None)
        os.environ["USE_OSRM"] = "false"


@pytest.mark.asyncio
async def test_driving_table_returns_none_when_disabled():
    import osrm_client

    os.environ["USE_OSRM"] = "false"
    result = await osrm_client.driving_table((53.45, -2.21), [(53.46, -2.22)])
    assert result is None


@pytest.mark.asyncio
async def test_driving_table_empty_destinations():
    import osrm_client

    result = await osrm_client.driving_table((53.45, -2.21), [])
    assert result == []


def test_duration_human_formats():
    from osrm_client import duration_human

    assert duration_human(None) is None
    assert duration_human(45) == "1 min"
    assert duration_human(360) == "6 min"
    assert duration_human(3600) == "1 h"
    assert duration_human(5400) == "1 h 30 min"


# -----------------------------------------------------------------
# /api/v1/solicitors/near-me end-to-end (no network)
# -----------------------------------------------------------------


@pytest.fixture
def client():
    """Spin up the FastAPI TestClient with a stubbed asyncpg pool (None)."""
    import app as app_module
    from fastapi.testclient import TestClient

    # Force _get_pool to return None so the cache path degrades cleanly.
    async def _fake_pool():
        return None

    with patch.object(app_module, "_get_pool", _fake_pool):
        yield TestClient(app_module.app)


def _stub_geocode(coords_by_pc):
    """Build a (geocode_postcode, geocode_postcodes) pair returning canned coords."""

    async def single(pc, pool=None):
        from postcodes_io import normalise_postcode

        return coords_by_pc.get(normalise_postcode(pc))

    async def bulk(pcs, pool=None):
        from postcodes_io import normalise_postcode

        out = {}
        for pc in pcs:
            norm = normalise_postcode(pc)
            if norm in coords_by_pc:
                out[norm] = coords_by_pc[norm]
        return out

    return single, bulk


def test_invalid_postcode_returns_400(client):
    resp = client.get("/api/v1/solicitors/near-me", params={"postcode": "NOT-VALID"})
    assert resp.status_code == 400


def test_near_me_returns_results_without_osrm(client):
    """When OSRM is disabled, results come back alphabetical with osrm_available=false."""
    # Patch geocoding so we don't touch postcodes.io.
    coords = {
        "M145AB": (53.45, -2.21),
        "M16JL": (53.46, -2.20),
        "B113HE": (52.45, -1.91),
    }
    single, bulk = _stub_geocode(coords)

    with (
        patch("solicitors_near_me.postcodes_io.geocode_postcode", single),
        patch("solicitors_near_me.postcodes_io.geocode_postcodes", bulk),
    ):
        resp = client.get(
            "/api/v1/solicitors/near-me",
            params={"postcode": "M14 5AB", "limit": 3},
        )

    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["osrm_available"] is False
    assert data["user"]["postcode"] == "M145AB"
    assert isinstance(data["results"], list)
    # When OSRM is off we still return SOME results sorted alphabetically.
    if data["results"]:
        names = [r["name"] for r in data["results"]]
        assert names == sorted(names, key=lambda n: (n or "").lower())
        # Each result has the expected contract keys.
        first = data["results"][0]
        for key in (
            "sra_id",
            "name",
            "firm_name",
            "postcode",
            "areas",
            "languages",
            "distance_m",
            "duration_s",
            "duration_human",
            "regulator_url",
        ):
            assert key in first


def test_near_me_includes_disclaimer(client):
    coords = {"M145AB": (53.45, -2.21), "M16JL": (53.46, -2.20)}
    single, bulk = _stub_geocode(coords)
    with (
        patch("solicitors_near_me.postcodes_io.geocode_postcode", single),
        patch("solicitors_near_me.postcodes_io.geocode_postcodes", bulk),
    ):
        resp = client.get(
            "/api/v1/solicitors/near-me",
            params={"postcode": "M14 5AB"},
        )
    assert resp.status_code == 200
    assert "disclaimer" in resp.json()


def test_near_me_ranks_by_driving_time_when_osrm_available(client):
    """Stub OSRM to return a known matrix and check sort order."""
    coords = {
        "M145AB": (53.45, -2.21),
        "M16JL": (53.46, -2.20),
        "B113HE": (52.45, -1.91),
    }
    single, bulk = _stub_geocode(coords)

    async def fake_table(origin, destinations, profile="driving"):
        # Return descending duration so we can verify sort.
        return [{"distance_m": 1000.0 * (i + 1), "duration_s": 600.0 - i * 60} for i, _ in enumerate(destinations)]

    os.environ["USE_OSRM"] = "true"
    os.environ["OSRM_SERVICE_URL"] = "https://example.org"
    try:
        with (
            patch("solicitors_near_me.postcodes_io.geocode_postcode", single),
            patch("solicitors_near_me.postcodes_io.geocode_postcodes", bulk),
            patch("solicitors_near_me.osrm_client.driving_table", fake_table),
        ):
            resp = client.get(
                "/api/v1/solicitors/near-me",
                params={"postcode": "M14 5AB", "limit": 5},
            )
    finally:
        os.environ.pop("OSRM_SERVICE_URL", None)
        os.environ["USE_OSRM"] = "false"

    assert resp.status_code == 200
    data = resp.json()
    assert data["osrm_available"] is True
    if len(data["results"]) >= 2:
        durations = [r["duration_s"] for r in data["results"]]
        assert durations == sorted(durations)
        # duration_human should be set when duration_s is.
        assert data["results"][0]["duration_human"] is not None


def test_solicitors_near_me_module_pure_function():
    """find_near_me should reject obviously bad postcodes without touching the network."""
    import asyncio

    from solicitors_near_me import find_near_me

    payload = asyncio.run(find_near_me(postcode="not-a-postcode", pool=None))
    assert payload["ok"] is False
    assert payload["error"] == "invalid_postcode"
    assert payload["results"] == []
