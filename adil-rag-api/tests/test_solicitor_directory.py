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


class TestSolicitorSearchEndpoint:
    """Tests for /api/v1/solicitors/search (LegalScraper landing data)."""

    def test_search_returns_envelope(self, client, api_key):
        resp = client.get("/api/v1/solicitors/search?limit=5", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        data = resp.json()
        assert "solicitors" in data
        assert "total" in data
        assert "disclaimer" in data
        assert isinstance(data["solicitors"], list)

    def test_search_default_limit_respected(self, client, api_key):
        resp = client.get("/api/v1/solicitors/search?limit=5", headers={"X-API-Key": api_key})
        data = resp.json()
        assert len(data["solicitors"]) <= 5
        assert data["total"] == len(data["solicitors"])

    def test_search_filter_by_language(self, client, api_key):
        resp = client.get(
            "/api/v1/solicitors/search?language=Urdu&limit=20",
            headers={"X-API-Key": api_key},
        )
        data = resp.json()
        assert len(data["solicitors"]) > 0
        for s in data["solicitors"]:
            assert any("urdu" in (lg or "").lower() for lg in s.get("languages") or [])

    def test_search_filter_by_area(self, client, api_key):
        resp = client.get(
            "/api/v1/solicitors/search?area=Family&limit=20",
            headers={"X-API-Key": api_key},
        )
        data = resp.json()
        assert len(data["solicitors"]) > 0
        for s in data["solicitors"]:
            assert any("family" in (a or "").lower() for a in s.get("areas") or [])

    def test_search_filter_muslim_only(self, client, api_key):
        resp = client.get(
            "/api/v1/solicitors/search?muslim_only=true&limit=20",
            headers={"X-API-Key": api_key},
        )
        data = resp.json()
        assert len(data["solicitors"]) > 0
        for s in data["solicitors"]:
            assert s.get("muslim_language") is True

    def test_search_filter_postcode_prefix(self, client, api_key):
        resp = client.get(
            "/api/v1/solicitors/search?postcode=M&limit=20",
            headers={"X-API-Key": api_key},
        )
        data = resp.json()
        for s in data["solicitors"]:
            pc = (s.get("postcode") or "").upper().replace(" ", "")
            assert pc.startswith("M")

    def test_search_limit_capped_at_200(self, client, api_key):
        resp = client.get(
            "/api/v1/solicitors/search?limit=9999",
            headers={"X-API-Key": api_key},
        )
        data = resp.json()
        assert len(data["solicitors"]) <= 200

    def test_search_requires_api_key(self, client):
        resp = client.get("/api/v1/solicitors/search")
        assert resp.status_code in (401, 403)

    def test_search_record_has_public_fields(self, client, api_key):
        resp = client.get("/api/v1/solicitors/search?limit=1", headers={"X-API-Key": api_key})
        data = resp.json()
        if not data["solicitors"]:
            pytest.skip("No solicitor records loaded")
        rec = data["solicitors"][0]
        for field in ("sra_id", "name"):
            assert field in rec

    def test_search_no_results_returns_empty(self, client, api_key):
        resp = client.get(
            "/api/v1/solicitors/search?name=ZZZZZNoSuchSolicitor&limit=10",
            headers={"X-API-Key": api_key},
        )
        data = resp.json()
        assert data["solicitors"] == []
        assert data["total"] == 0


class TestSolicitorFacetsEndpoint:
    def test_facets_lists(self, client, api_key):
        resp = client.get("/api/v1/solicitors/facets", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data.get("areas"), list)
        assert isinstance(data.get("languages"), list)

    def test_facets_includes_area_groups(self, client, api_key):
        resp = client.get("/api/v1/solicitors/facets", headers={"X-API-Key": api_key})
        data = resp.json()
        groups = data.get("area_groups")
        assert isinstance(groups, list) and len(groups) > 0
        for g in groups:
            assert set(g) >= {"group", "wave", "count"}
            assert g["count"] > 0  # zero-count groups are omitted
        labels = {g["group"] for g in groups}
        # Wave-1 categories must be present (data carries immigration + wills areas)
        assert "Immigration & Asylum" in labels
        assert "Wills, Probate & Inheritance" in labels
        wave1 = {g["group"]: g["wave"] for g in groups}
        assert wave1["Immigration & Asylum"] == 1
        assert wave1["Wills, Probate & Inheritance"] == 1


class TestPracticeAreaGroups:
    """Direct unit tests for the curated practice-area groups."""

    def test_list_groups_curated_order_preserved(self):
        from solicitor_directory import PRACTICE_AREA_GROUPS, list_practice_area_groups

        present = list_practice_area_groups()
        curated_order = [g["group"] for g in PRACTICE_AREA_GROUPS]
        returned_order = [g["group"] for g in present]
        # Returned labels appear in the same relative order as the curated tuple.
        assert returned_order == [g for g in curated_order if g in set(returned_order)]

    def test_group_label_search_expands_matchers(self):
        from solicitor_directory import search_solicitors

        out = search_solicitors(area="Immigration & Asylum", limit=200)
        assert len(out) > 0
        for s in out:
            assert any(
                "immigration" in (a or "").lower() or "asylum" in (a or "").lower() for a in s.get("areas") or []
            )

    def test_group_search_superset_of_single_substring(self):
        from solicitor_directory import search_solicitors

        # The "Immigration & Asylum" group rolls up every "immigration" raw
        # string, so it must return at least as many as a bare substring search.
        grouped = search_solicitors(area="Immigration & Asylum", limit=200)
        substring = search_solicitors(area="immigration", limit=200)
        assert len(grouped) >= len(substring)

    def test_wills_group_includes_probate(self):
        from solicitor_directory import search_solicitors

        out = search_solicitors(area="Wills, Probate & Inheritance", limit=200)
        assert len(out) > 0
        # At least one matched solicitor should be a probate (not wills) record,
        # proving the group rolls up multiple raw strings.
        assert any(any("probate" in (a or "").lower() for a in s.get("areas") or []) for s in out)

    def test_unknown_area_falls_back_to_substring(self):
        from solicitor_directory import search_solicitors

        # A non-group string still behaves as a plain substring filter.
        out = search_solicitors(area="employment", limit=20)
        for s in out:
            assert any("employment" in (a or "").lower() for a in s.get("areas") or [])


class TestSolicitorVerifyEndpoint:
    def test_verify_known_sra_id(self, client, api_key):
        from solicitor_directory import _ensure_solicitors_loaded

        rows = _ensure_solicitors_loaded()
        if not rows:
            pytest.skip("No solicitor records loaded")
        sra_id = rows[0]["sra_id"]
        resp = client.get(f"/api/v1/solicitors/verify/{sra_id}", headers={"X-API-Key": api_key})
        assert resp.status_code == 200
        data = resp.json()
        assert data["solicitor"]["sra_id"] == sra_id

    def test_verify_unknown_sra_id_404(self, client, api_key):
        resp = client.get("/api/v1/solicitors/verify/0", headers={"X-API-Key": api_key})
        assert resp.status_code == 404


class TestSearchFunction:
    """Direct unit tests for search_solicitors() (no HTTP layer)."""

    def test_returns_list_of_dicts(self):
        from solicitor_directory import search_solicitors

        out = search_solicitors(limit=3)
        assert isinstance(out, list)
        assert all(isinstance(r, dict) for r in out)

    def test_postcode_prefix_outward_match(self):
        from solicitor_directory import search_solicitors

        out = search_solicitors(postcode_prefix="EC", limit=50)
        for s in out:
            pc = (s.get("postcode") or "").upper().replace(" ", "")
            assert pc.startswith("EC")

    def test_muslim_only_flag_filters(self):
        from solicitor_directory import search_solicitors

        out = search_solicitors(muslim_only=True, limit=20)
        for s in out:
            assert s.get("muslim_language") is True

    def test_verify_by_sra_id_returns_none_for_unknown(self):
        from solicitor_directory import verify_solicitor_by_sra_id

        assert verify_solicitor_by_sra_id("definitely-not-a-real-sra-id") is None
