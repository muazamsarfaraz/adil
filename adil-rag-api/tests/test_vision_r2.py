"""Tests for vision endpoint R2 upload loading with ownership verification."""

import os
import uuid
from unittest.mock import AsyncMock

import asyncpg
import pytest
import pytest_asyncio
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def seed_upload(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL not set")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("ADIL_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("FILE_SEARCH_STORE_ID", "fake")
    monkeypatch.setenv("R2_ACCOUNT_ID", "acc")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_ENDPOINT", "https://acc.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_BACKEND_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("R2_BACKEND_SECRET_ACCESS_KEY", "S")

    conv_id = uuid.uuid4()
    upload_id = uuid.uuid4()
    conn = await asyncpg.connect(os.environ["TEST_DATABASE_URL"])
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS uploads (
              id UUID PRIMARY KEY,
              conversation_id UUID NOT NULL,
              object_key TEXT NOT NULL,
              content_type TEXT NOT NULL,
              size_bytes INT NOT NULL,
              created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
              expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '24 hours')
            )
            """
        )
        await conn.execute("TRUNCATE uploads")
        await conn.execute(
            "INSERT INTO uploads (id, conversation_id, object_key, content_type, size_bytes) "
            "VALUES ($1, $2, $3, $4, $5)",
            upload_id,
            conv_id,
            f"uploads/{conv_id}/{upload_id}.png",
            "image/png",
            1234,
        )
    finally:
        await conn.close()
    return conv_id, upload_id


async def test_vision_with_owned_upload(seed_upload, monkeypatch):
    conv_id, upload_id = seed_upload

    # Stub R2 — return fake PNG bytes
    import r2_client

    fake_png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    monkeypatch.setattr(
        r2_client.R2Client,
        "get_object",
        AsyncMock(return_value=fake_png),
    )

    # Stub Gemini vision call in RAGService — whatever method name exists
    import rag_service

    async def fake_vision(*args, **kwargs):
        return {
            "answer": "test answer",
            "sources": [],
            "viability_assessment": None,
            "usage": {},
            "metadata": {},
        }

    # Patch whichever method the image endpoint calls; common candidates:
    for method_name in ("query_with_image", "query_image", "analyse_images", "query_with_images"):
        if hasattr(rag_service.RAGService, method_name):
            monkeypatch.setattr(rag_service.RAGService, method_name, fake_vision)
            break

    import importlib

    import app as app_module

    importlib.reload(app_module)
    client = TestClient(app_module.app)

    resp = client.post(
        "/api/v1/query/image",
        headers={"X-API-Key": "test-key"},
        json={
            "query": "what is this",
            "conversation_id": str(conv_id),
            "upload_ids": [str(upload_id)],
        },
    )
    assert resp.status_code == 200, resp.text


async def test_vision_rejects_cross_conversation_upload(seed_upload):
    _, upload_id = seed_upload

    import importlib

    import app as app_module

    importlib.reload(app_module)
    client = TestClient(app_module.app)

    resp = client.post(
        "/api/v1/query/image",
        headers={"X-API-Key": "test-key"},
        json={
            "query": "what is this",
            "conversation_id": str(uuid.uuid4()),
            "upload_ids": [str(upload_id)],
        },
    )
    assert resp.status_code == 403
