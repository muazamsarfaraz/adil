import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("ADIL_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("FILE_SEARCH_STORE_ID", "fake")
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL not set — skipping DB integration test")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])


@pytest.fixture
def client(env):
    import importlib

    import app as app_module

    importlib.reload(app_module)
    return TestClient(app_module.app)


async def test_record_upload_success(client):
    conv_id = str(uuid.uuid4())
    upload_id = str(uuid.uuid4())
    resp = client.post(
        "/api/v1/uploads/record",
        headers={"X-API-Key": "test-key"},
        json={
            "id": upload_id,
            "conversation_id": conv_id,
            "object_key": f"uploads/{conv_id}/{upload_id}.png",
            "content_type": "image/png",
            "size_bytes": 1234,
        },
    )
    assert resp.status_code == 201
    assert resp.json()["id"] == upload_id


async def test_record_upload_rejects_invalid_content_type(client):
    conv_id = str(uuid.uuid4())
    upload_id = str(uuid.uuid4())
    resp = client.post(
        "/api/v1/uploads/record",
        headers={"X-API-Key": "test-key"},
        json={
            "id": upload_id,
            "conversation_id": conv_id,
            "object_key": f"uploads/{conv_id}/{upload_id}.exe",
            "content_type": "application/x-msdownload",
            "size_bytes": 1234,
        },
    )
    assert resp.status_code == 422


async def test_record_upload_rejects_oversize(client):
    conv_id = str(uuid.uuid4())
    upload_id = str(uuid.uuid4())
    resp = client.post(
        "/api/v1/uploads/record",
        headers={"X-API-Key": "test-key"},
        json={
            "id": upload_id,
            "conversation_id": conv_id,
            "object_key": f"uploads/{conv_id}/{upload_id}.png",
            "content_type": "image/png",
            "size_bytes": 20 * 1024 * 1024,
        },
    )
    assert resp.status_code == 422


async def test_record_upload_requires_api_key(client):
    conv_id = str(uuid.uuid4())
    upload_id = str(uuid.uuid4())
    resp = client.post(
        "/api/v1/uploads/record",
        json={
            "id": upload_id,
            "conversation_id": conv_id,
            "object_key": f"uploads/{conv_id}/{upload_id}.png",
            "content_type": "image/png",
            "size_bytes": 1234,
        },
    )
    assert resp.status_code == 401
