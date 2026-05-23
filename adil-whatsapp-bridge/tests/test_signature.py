from __future__ import annotations

import hmac
import sys
from hashlib import sha256
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from meta_client import verify_signature  # noqa: E402


def _sign(body: bytes, secret: str) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, sha256).hexdigest()


def test_valid_signature_accepted():
    body = b'{"hello":"world"}'
    secret = "topsecret"
    assert verify_signature(body, _sign(body, secret), secret) is True


def test_wrong_signature_rejected():
    assert verify_signature(b"x", "sha256=deadbeef", "topsecret") is False


def test_missing_header_rejected():
    assert verify_signature(b"x", None, "topsecret") is False


def test_missing_secret_rejected():
    assert verify_signature(b"x", "sha256=anything", "") is False


def test_wrong_prefix_rejected():
    body = b"x"
    secret = "topsecret"
    raw = hmac.new(secret.encode(), body, sha256).hexdigest()
    assert verify_signature(body, "sha1=" + raw, secret) is False


def test_tampered_body_rejected():
    secret = "topsecret"
    sig = _sign(b"original", secret)
    assert verify_signature(b"tampered", sig, secret) is False
