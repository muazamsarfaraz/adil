"""Tests for the image query endpoint (/api/v1/query/image)."""

import base64

import pytest
from pydantic import ValidationError

from models import ALLOWED_IMAGE_MIMES, ImageData, ImageQueryRequest


class TestImageModels:
    """Validate image-related Pydantic models."""

    def test_allowed_image_mimes_contains_png(self):
        assert "image/png" in ALLOWED_IMAGE_MIMES

    def test_allowed_image_mimes_contains_jpeg(self):
        assert "image/jpeg" in ALLOWED_IMAGE_MIMES

    def test_allowed_image_mimes_contains_gif(self):
        assert "image/gif" in ALLOWED_IMAGE_MIMES

    def test_allowed_image_mimes_contains_webp(self):
        assert "image/webp" in ALLOWED_IMAGE_MIMES

    def test_allowed_image_mimes_excludes_svg(self):
        assert "image/svg+xml" not in ALLOWED_IMAGE_MIMES

    def test_image_data_valid(self):
        img = ImageData(
            mime_type="image/png",
            data=base64.b64encode(b"fakepngdata").decode(),
        )
        assert img.mime_type == "image/png"

    def test_image_query_request_rejects_empty_images(self):
        with pytest.raises(ValidationError):
            ImageQueryRequest(images=[], include_viability_score=False)

    def test_image_query_request_rejects_over_5_images(self):
        with pytest.raises(ValidationError):
            ImageQueryRequest(
                images=[ImageData(mime_type="image/png", data="dGVzdA==") for _ in range(6)],
                include_viability_score=False,
            )

    def test_image_query_request_valid_single_image(self):
        req = ImageQueryRequest(
            query="Is this discriminatory?",
            images=[ImageData(mime_type="image/png", data="dGVzdA==")],
            include_viability_score=False,
        )
        assert req.query == "Is this discriminatory?"
        assert len(req.images) == 1

    def test_image_query_request_optional_query(self):
        req = ImageQueryRequest(
            images=[ImageData(mime_type="image/jpeg", data="dGVzdA==")],
            include_viability_score=False,
        )
        assert req.query is None

    def test_image_query_request_max_5_images(self):
        req = ImageQueryRequest(
            images=[ImageData(mime_type="image/png", data="dGVzdA==") for _ in range(5)],
            include_viability_score=False,
        )
        assert len(req.images) == 5


API_KEY_VALUE = "test-secret-key-12345"


class TestImageEndpointContract:
    """Test the /api/v1/query/image endpoint contract."""

    @pytest.fixture(autouse=True)
    def _set_api_key(self, monkeypatch):
        """Ensure a deterministic API key is configured for every test.

        We patch the module-level ``API_KEY`` directly so that
        ``verify_api_key`` sees it without needing an ``importlib.reload``.
        """
        import app as app_mod

        monkeypatch.setenv("ADIL_API_KEY", API_KEY_VALUE)
        monkeypatch.setattr(app_mod, "API_KEY", API_KEY_VALUE)

    @pytest.fixture
    def client(self):
        import app as app_mod
        from fastapi.testclient import TestClient

        return TestClient(app_mod.app)

    @property
    def auth_headers(self):
        return {"X-API-Key": API_KEY_VALUE}

    def test_image_endpoint_requires_auth(self, client):
        """Endpoint rejects requests without API key when auth is enabled."""
        resp = client.post(
            "/api/v1/query/image",
            json={
                "images": [{"mime_type": "image/png", "data": "dGVzdA=="}],
            },
            # No X-API-Key header
        )
        assert resp.status_code in (401, 403)

    def test_image_endpoint_wrong_key_rejected(self, client):
        """Endpoint rejects requests with wrong API key."""
        resp = client.post(
            "/api/v1/query/image",
            json={
                "images": [{"mime_type": "image/png", "data": "dGVzdA=="}],
            },
            headers={"X-API-Key": "wrong-key"},
        )
        assert resp.status_code in (401, 403)

    def test_image_endpoint_rejects_empty_images(self, client):
        """Endpoint should reject request with no images (422 validation)."""
        resp = client.post(
            "/api/v1/query/image",
            json={"images": []},
            headers=self.auth_headers,
        )
        assert resp.status_code == 422

    def test_image_endpoint_exists(self, client):
        """Smoke test: the endpoint exists (not 404)."""
        resp = client.post(
            "/api/v1/query/image",
            json={
                "images": [{"mime_type": "image/png", "data": "dGVzdA=="}],
            },
            headers=self.auth_headers,
        )
        # Not 404 — endpoint exists. May be 400/500 depending on Gemini config.
        assert resp.status_code != 404

    def test_image_endpoint_rejects_too_many_images(self, client):
        """Endpoint should reject request with more than 5 images."""
        resp = client.post(
            "/api/v1/query/image",
            json={
                "images": [{"mime_type": "image/png", "data": "dGVzdA=="} for _ in range(6)],
            },
            headers=self.auth_headers,
        )
        assert resp.status_code == 422
