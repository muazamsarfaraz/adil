"""Strict API-key verification + client IP resolution for adil-rag-api.

Every protected endpoint must reject requests without a valid X-API-Key with HTTP 401.
When the key is valid, the caller is trusted to supply the real client IP via
`X-AskAdil-Client-IP` (used for rate-limit bucketing). Without a valid key, the
socket peer address is used.
"""

from __future__ import annotations

import os

from fastapi import HTTPException, Request, Security
from fastapi.security import APIKeyHeader

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str | None = Security(api_key_header)) -> str:
    """FastAPI Security dependency. Returns the key on success, raises 401 otherwise."""
    expected = os.getenv("ADIL_API_KEY")
    if not expected:
        # Fail closed — misconfiguration is an outage, not a free pass
        raise HTTPException(status_code=500, detail="ADIL_API_KEY not configured")
    if not api_key or api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing X-API-Key")
    return api_key


def resolve_client_ip(request: Request, api_key_valid: bool) -> str:
    """Return the client IP used for rate-limit bucketing.

    When api_key_valid is True (a trusted caller — our Next.js proxy),
    prefer the X-AskAdil-Client-IP header. Otherwise use the socket peer.
    """
    if api_key_valid:
        trusted = request.headers.get("X-AskAdil-Client-IP")
        if trusted:
            return trusted.strip()
    client = request.client
    return client.host if client else "unknown"
