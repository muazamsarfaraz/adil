import pytest
from fastapi import FastAPI, Request, Security
from fastapi.testclient import TestClient
from starlette.requests import Request as StarletteRequest


@pytest.fixture
def app_with_auth(monkeypatch):
    monkeypatch.setenv("ADIL_API_KEY", "test-key")
    import importlib

    import auth

    importlib.reload(auth)

    app = FastAPI()

    @app.get("/protected")
    async def protected(_key: str = Security(auth.verify_api_key)):
        return {"ok": True}

    @app.get("/echo-ip-trusted")
    async def echo_ip_trusted(request: Request, _key: str = Security(auth.verify_api_key)):
        return {"ip": auth.resolve_client_ip(request, api_key_valid=True)}

    return app, auth


def test_protected_endpoint_rejects_missing_key(app_with_auth):
    app, _ = app_with_auth
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_protected_endpoint_rejects_wrong_key(app_with_auth):
    app, _ = app_with_auth
    client = TestClient(app)
    resp = client.get("/protected", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_protected_endpoint_accepts_valid_key(app_with_auth):
    app, _ = app_with_auth
    client = TestClient(app)
    resp = client.get("/protected", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200


def test_client_ip_trusts_header_when_api_key_valid(app_with_auth):
    app, _ = app_with_auth
    client = TestClient(app)
    resp = client.get(
        "/echo-ip-trusted",
        headers={"X-API-Key": "test-key", "X-AskAdil-Client-IP": "9.9.9.9"},
    )
    assert resp.status_code == 200
    assert resp.json()["ip"] == "9.9.9.9"


def test_client_ip_ignores_header_when_api_key_not_valid(app_with_auth):
    _, auth = app_with_auth
    scope = {
        "type": "http",
        "client": ("1.1.1.1", 12345),
        "headers": [(b"x-askadil-client-ip", b"9.9.9.9")],
        "method": "GET",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "scheme": "http",
        "server": ("testserver", 80),
    }
    request = StarletteRequest(scope)
    ip = auth.resolve_client_ip(request, api_key_valid=False)
    assert ip == "1.1.1.1"
