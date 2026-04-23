from unittest.mock import AsyncMock, MagicMock

import pytest

pytestmark = pytest.mark.asyncio


async def test_get_object_returns_bytes(monkeypatch):
    from r2_client import R2Client

    monkeypatch.setenv("R2_ACCOUNT_ID", "acc")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_ENDPOINT", "https://acc.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_BACKEND_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("R2_BACKEND_SECRET_ACCESS_KEY", "SECRET")

    client = R2Client.from_env()

    stub_s3 = MagicMock()
    body = AsyncMock()
    body.read = AsyncMock(return_value=b"image-bytes")
    stub_s3.get_object = AsyncMock(return_value={"Body": body})

    class FakeCtx:
        async def __aenter__(self_inner):
            return stub_s3

        async def __aexit__(self_inner, *a):
            return None

    client._make_client = lambda: FakeCtx()

    result = await client.get_object("uploads/conv/abc.png")
    assert result == b"image-bytes"
    stub_s3.get_object.assert_awaited_once_with(Bucket="bucket", Key="uploads/conv/abc.png")


async def test_delete_object_calls_s3(monkeypatch):
    from r2_client import R2Client

    monkeypatch.setenv("R2_ACCOUNT_ID", "acc")
    monkeypatch.setenv("R2_BUCKET", "bucket")
    monkeypatch.setenv("R2_ENDPOINT", "https://acc.r2.cloudflarestorage.com")
    monkeypatch.setenv("R2_BACKEND_ACCESS_KEY_ID", "AKIA")
    monkeypatch.setenv("R2_BACKEND_SECRET_ACCESS_KEY", "SECRET")

    client = R2Client.from_env()
    stub_s3 = MagicMock()
    stub_s3.delete_object = AsyncMock(return_value={})

    class FakeCtx:
        async def __aenter__(self_inner):
            return stub_s3

        async def __aexit__(self_inner, *a):
            return None

    client._make_client = lambda: FakeCtx()
    await client.delete_object("uploads/conv/xyz.jpg")
    stub_s3.delete_object.assert_awaited_once_with(Bucket="bucket", Key="uploads/conv/xyz.jpg")


async def test_from_env_raises_when_incomplete(monkeypatch):
    from r2_client import R2Client, R2ConfigError

    for k in ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ENDPOINT", "R2_BACKEND_ACCESS_KEY_ID", "R2_BACKEND_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(R2ConfigError):
        R2Client.from_env()
