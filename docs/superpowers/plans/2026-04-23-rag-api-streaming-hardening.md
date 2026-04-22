# adil-rag-api Streaming + Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an SSE streaming chat endpoint to adil-rag-api, enforce strict API-key auth with trusted client-IP propagation, add Postgres rate limiting, R2 object storage for image uploads, and an SSRF filter for URL extraction.

**Architecture:** New endpoints land as FastAPI routes in `app.py`. Rate limiting moves from `slowapi` (in-memory) to a Postgres `rate_limit_counters` table for cross-replica correctness. Uploads are referenced by object key in Cloudflare R2 (S3-compatible), with backend credentials scoped to `GetObject`/`DeleteObject`. A new `app/ssrf_filter.py` module blocks RFC1918 + link-local ranges for all outbound URL fetches.

**Tech Stack:** FastAPI, asyncpg, aioboto3 (R2 via S3 API), google-genai (streaming), pytest + pytest-asyncio

**Spec:** `docs/superpowers/specs/2026-04-22-rag-api-streaming-hardening.md`

**Prerequisite for:** `docs/superpowers/plans/2026-04-23-frontend-nextjs-rewrite.md` (the frontend plan can proceed against non-streaming `/api/v1/query` until this lands, so these can run in parallel).

---

## File Map

All paths relative to `adil-rag-api/`.

| File | Responsibility |
|------|----------------|
| `migrations/001_rate_limit_counters.sql` | Postgres DDL for rate-limit table |
| `migrations/002_uploads.sql` | Postgres DDL for uploads metadata |
| `rate_limit.py` | Postgres fixed-window counter helper + FastAPI dependency |
| `auth.py` | Extracted strict `verify_api_key` (401 on missing) + `resolve_client_ip` |
| `ssrf_filter.py` | Block RFC1918 + link-local + loopback + IPv6 equivalents |
| `content_extractor.py` | Existing — wire up SSRF filter on all outbound fetches |
| `r2_client.py` | Async R2 S3 client (GetObject, DeleteObject) |
| `app.py` | Existing — add streaming endpoint, upload record endpoint, auth hardening, CORS gating |
| `models.py` | Existing — add `StreamEvent`, `UploadRecordRequest`, `UploadRecordResponse` |
| `tests/test_rate_limit.py` | Unit + integration tests for counter logic + 429 behaviour |
| `tests/test_auth.py` | 401 on missing key, trusted IP header only with key |
| `tests/test_ssrf_filter.py` | Parametrised tests for each blocked CIDR |
| `tests/test_uploads.py` | Upload record + query/image ownership check |
| `tests/test_streaming.py` | SSE events order + Retry-After on 429 |
| `docs/api/streaming-events.md` | Client-facing event schema reference |

Migrations: the backend currently has no Alembic setup (the document-uploader service does). For this plan we use plain SQL files executed at startup via a small idempotent runner in `app.py`'s `lifespan`. Alembic can be retrofitted later.

---

## Task 1: Add SQL migrations for rate_limit_counters and uploads

**Files:**
- Create: `adil-rag-api/migrations/001_rate_limit_counters.sql`
- Create: `adil-rag-api/migrations/002_uploads.sql`
- Create: `adil-rag-api/db_migrate.py` (idempotent runner)
- Modify: `adil-rag-api/app.py` (call runner in `lifespan`)
- Create: `adil-rag-api/tests/test_migrations.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_migrations.py`:

```python
import os
import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set — skipping DB integration test",
)
async def test_migrations_create_tables():
    from db_migrate import run_migrations

    db_url = os.getenv("TEST_DATABASE_URL")
    await run_migrations(db_url)

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' "
            "AND table_name IN ('rate_limit_counters', 'uploads')"
        )
        names = {r["table_name"] for r in rows}
        assert names == {"rate_limit_counters", "uploads"}
    finally:
        await conn.close()


@pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"),
    reason="TEST_DATABASE_URL not set",
)
async def test_migrations_idempotent():
    from db_migrate import run_migrations

    db_url = os.getenv("TEST_DATABASE_URL")
    # Run twice — must not raise
    await run_migrations(db_url)
    await run_migrations(db_url)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd adil-rag-api
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_migrations.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'db_migrate'`.

If you don't have a local Postgres, set `TEST_DATABASE_URL=""` and the tests will skip — you can still proceed, but verify on CI or dev Postgres before moving on.

- [ ] **Step 3: Create the SQL migrations**

Create `migrations/001_rate_limit_counters.sql`:

```sql
CREATE TABLE IF NOT EXISTS rate_limit_counters (
  bucket_key   TEXT        NOT NULL,
  bucket_start TIMESTAMPTZ NOT NULL,
  count        INT         NOT NULL DEFAULT 0,
  PRIMARY KEY (bucket_key, bucket_start)
);

CREATE INDEX IF NOT EXISTS rate_limit_counters_bucket_start_idx
  ON rate_limit_counters (bucket_start);
```

Create `migrations/002_uploads.sql`:

```sql
CREATE TABLE IF NOT EXISTS uploads (
  id              UUID         PRIMARY KEY,
  conversation_id UUID         NOT NULL,
  object_key      TEXT         NOT NULL,
  content_type    TEXT         NOT NULL CHECK (content_type IN ('image/png','image/jpeg','image/webp')),
  size_bytes      INT          NOT NULL CHECK (size_bytes BETWEEN 1 AND 10485760),
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  expires_at      TIMESTAMPTZ  NOT NULL DEFAULT (now() + interval '24 hours')
);

CREATE INDEX IF NOT EXISTS uploads_conversation_id_idx ON uploads (conversation_id);
CREATE INDEX IF NOT EXISTS uploads_expires_at_idx ON uploads (expires_at);
```

- [ ] **Step 4: Implement the runner**

Create `db_migrate.py`:

```python
"""Idempotent SQL migration runner for adil-rag-api.

Reads migrations/*.sql in filename order and executes them inside a transaction.
All DDL uses IF NOT EXISTS so re-running is safe.
"""

from __future__ import annotations

import logging
from pathlib import Path

import asyncpg

logger = logging.getLogger(__name__)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def run_migrations(database_url: str) -> None:
    """Apply all .sql files in migrations/ in filename order. Idempotent."""
    files = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not files:
        logger.info("No migrations to run")
        return

    conn = await asyncpg.connect(database_url)
    try:
        async with conn.transaction():
            for sql_file in files:
                logger.info("Applying migration %s", sql_file.name)
                sql = sql_file.read_text(encoding="utf-8")
                await conn.execute(sql)
    finally:
        await conn.close()

    logger.info("Applied %d migration(s)", len(files))
```

- [ ] **Step 5: Wire into app lifespan**

In `app.py`, replace the existing `lifespan` (or add to it) so migrations run on startup:

```python
from db_migrate import run_migrations

@asynccontextmanager
async def lifespan(app: FastAPI):
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        await run_migrations(database_url)
    else:
        logger.warning("DATABASE_URL not set — skipping migrations")
    yield
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_migrations.py -v
```

Expected: both tests PASS (or SKIP if no DB available).

- [ ] **Step 7: Commit**

```bash
git add adil-rag-api/migrations/ adil-rag-api/db_migrate.py adil-rag-api/app.py adil-rag-api/tests/test_migrations.py
git commit -m "feat(rag-api): add SQL migrations for rate_limit + uploads tables"
```

---

## Task 2: Postgres rate-limit helper

**Files:**
- Create: `adil-rag-api/rate_limit.py`
- Create: `adil-rag-api/tests/test_rate_limit.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rate_limit.py`:

```python
import os
from datetime import timedelta

import asyncpg
import pytest

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db_pool():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    pool = await asyncpg.create_pool(url, min_size=1, max_size=4)
    # Ensure table exists
    async with pool.acquire() as conn:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rate_limit_counters (
              bucket_key   TEXT        NOT NULL,
              bucket_start TIMESTAMPTZ NOT NULL,
              count        INT         NOT NULL DEFAULT 0,
              PRIMARY KEY (bucket_key, bucket_start)
            )
            """
        )
        await conn.execute("TRUNCATE rate_limit_counters")
    yield pool
    await pool.close()


async def test_increment_returns_running_count(db_pool):
    from rate_limit import increment_and_count

    key = "chat:ip:1.2.3.4"
    c1 = await increment_and_count(db_pool, key, window=timedelta(minutes=1))
    c2 = await increment_and_count(db_pool, key, window=timedelta(minutes=1))
    c3 = await increment_and_count(db_pool, key, window=timedelta(minutes=1))

    assert c1 == 1
    assert c2 == 2
    assert c3 == 3


async def test_different_keys_isolated(db_pool):
    from rate_limit import increment_and_count

    a = await increment_and_count(db_pool, "chat:ip:1.2.3.4", window=timedelta(minutes=1))
    b = await increment_and_count(db_pool, "chat:ip:5.6.7.8", window=timedelta(minutes=1))

    assert a == 1
    assert b == 1


async def test_check_rate_limit_raises_on_exceed(db_pool):
    from rate_limit import check_rate_limit, RateLimitExceeded

    key = "chat:ip:1.2.3.4"
    # 3 allowed
    for _ in range(3):
        await check_rate_limit(db_pool, key, limit=3, window=timedelta(minutes=1))

    # 4th raises
    with pytest.raises(RateLimitExceeded) as exc:
        await check_rate_limit(db_pool, key, limit=3, window=timedelta(minutes=1))
    assert exc.value.retry_after_seconds > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_rate_limit.py -v
```

Expected: `ModuleNotFoundError: No module named 'rate_limit'`.

- [ ] **Step 3: Implement rate_limit.py**

Create `rate_limit.py`:

```python
"""Postgres-backed fixed-window rate limiter.

Each (bucket_key, bucket_start) row counts requests in a fixed window.
The window is determined by rounding `now()` down to the window boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import asyncpg


class RateLimitExceeded(Exception):
    def __init__(self, limit: int, window: timedelta, retry_after_seconds: int):
        self.limit = limit
        self.window = window
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit {limit}/{window} exceeded")


def _bucket_start(window: timedelta, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    seconds = int(now.timestamp())
    window_s = int(window.total_seconds())
    bucket_epoch = (seconds // window_s) * window_s
    return datetime.fromtimestamp(bucket_epoch, tz=timezone.utc)


async def increment_and_count(
    pool: asyncpg.Pool, key: str, window: timedelta
) -> int:
    """Atomically increment the counter for (key, current window) and return the new count."""
    bucket_start = _bucket_start(window)
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO rate_limit_counters (bucket_key, bucket_start, count)
            VALUES ($1, $2, 1)
            ON CONFLICT (bucket_key, bucket_start)
            DO UPDATE SET count = rate_limit_counters.count + 1
            RETURNING count
            """,
            key,
            bucket_start,
        )
    return row["count"]


async def check_rate_limit(
    pool: asyncpg.Pool, key: str, limit: int, window: timedelta
) -> int:
    """Increment counter and raise RateLimitExceeded if it passes `limit`."""
    count = await increment_and_count(pool, key, window)
    if count > limit:
        # Seconds remaining until the window ends
        now = datetime.now(timezone.utc)
        bucket_end = _bucket_start(window, now) + window
        retry_after = max(1, int((bucket_end - now).total_seconds()))
        raise RateLimitExceeded(limit=limit, window=window, retry_after_seconds=retry_after)
    return count


@dataclass(frozen=True)
class Limit:
    key_prefix: str
    limit: int
    window: timedelta


async def check_limits(pool: asyncpg.Pool, limits: list[Limit], identity: str) -> None:
    """Apply a list of limits sequentially. Raises RateLimitExceeded on first hit."""
    for limit in limits:
        key = f"{limit.key_prefix}:{identity}"
        await check_rate_limit(pool, key, limit.limit, limit.window)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_rate_limit.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add adil-rag-api/rate_limit.py adil-rag-api/tests/test_rate_limit.py
git commit -m "feat(rag-api): postgres-backed fixed-window rate limiter"
```

---

## Task 3: Auth hardening — strict 401 + trusted client IP

**Files:**
- Create: `adil-rag-api/auth.py`
- Modify: `adil-rag-api/app.py` (replace inline `verify_api_key` with import)
- Create: `adil-rag-api/tests/test_auth.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_auth.py`:

```python
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient


def build_app(api_key: str = "test-key"):
    import os
    os.environ["ADIL_API_KEY"] = api_key
    # Reload module to pick up env
    import importlib
    import auth
    importlib.reload(auth)
    app = FastAPI()

    @app.get("/protected")
    async def protected(_key: str = pytest.importorskip("fastapi").Security(auth.verify_api_key)):
        return {"ok": True}

    @app.get("/echo-ip")
    async def echo_ip(request: pytest.importorskip("fastapi").Request):
        return {"ip": auth.resolve_client_ip(request, api_key_valid=True)}

    return app


def test_protected_endpoint_rejects_missing_key():
    app = build_app()
    client = TestClient(app)
    resp = client.get("/protected")
    assert resp.status_code == 401


def test_protected_endpoint_rejects_wrong_key():
    app = build_app()
    client = TestClient(app)
    resp = client.get("/protected", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_protected_endpoint_accepts_valid_key():
    app = build_app()
    client = TestClient(app)
    resp = client.get("/protected", headers={"X-API-Key": "test-key"})
    assert resp.status_code == 200


def test_client_ip_trusts_header_when_api_key_valid():
    app = build_app()
    client = TestClient(app)
    resp = client.get(
        "/echo-ip",
        headers={"X-API-Key": "test-key", "X-AskAdil-Client-IP": "9.9.9.9"},
    )
    assert resp.status_code == 200
    assert resp.json()["ip"] == "9.9.9.9"


def test_client_ip_ignores_header_when_api_key_missing():
    # Using `api_key_valid=False` path — falls back to socket
    import auth
    from starlette.requests import Request

    scope = {
        "type": "http",
        "client": ("1.1.1.1", 12345),
        "headers": [(b"x-askadil-client-ip", b"9.9.9.9")],
    }
    request = Request(scope)
    ip = auth.resolve_client_ip(request, api_key_valid=False)
    assert ip == "1.1.1.1"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_auth.py -v
```

Expected: `ModuleNotFoundError: No module named 'auth'`.

- [ ] **Step 3: Implement auth.py**

Create `auth.py`:

```python
"""Strict API-key verification + client IP resolution for adil-rag-api.

Every protected endpoint must reject requests without a valid X-API-Key with HTTP 401.
When the key is valid, the caller is trusted to supply the real client IP via
`X-AskAdil-Client-IP` (used for rate-limit bucketing). Without a valid key, the
socket peer address is used — but since the backend only runs on Railway's
internal private network, this path is rare.
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
```

- [ ] **Step 4: Replace inline verify_api_key in app.py**

In `app.py`, find the existing:

```python
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=True)

async def verify_api_key(api_key: str = Security(api_key_header)) -> str:
    ...
```

Replace with:

```python
from auth import verify_api_key, resolve_client_ip  # noqa: E402
```

Leave every `Security(verify_api_key)` call site unchanged.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_auth.py -v
```

Expected: all 5 tests PASS.

- [ ] **Step 6: Run the full test suite to catch regressions**

```bash
pytest tests/ -v
```

Expected: existing tests continue to pass. Any test that previously used `auto_error=True` semantics should still get 401, not 403, because `HTTPException(401)` is now raised explicitly.

- [ ] **Step 7: Commit**

```bash
git add adil-rag-api/auth.py adil-rag-api/app.py adil-rag-api/tests/test_auth.py
git commit -m "feat(rag-api): strict 401 on missing API key + trusted client IP header"
```

---

## Task 4: SSRF egress filter

**Files:**
- Create: `adil-rag-api/ssrf_filter.py`
- Create: `adil-rag-api/tests/test_ssrf_filter.py`
- Modify: `adil-rag-api/content_extractor.py` (wire filter into all outbound fetches)

- [ ] **Step 1: Write the failing test**

Create `tests/test_ssrf_filter.py`:

```python
import pytest

from ssrf_filter import is_blocked, BLOCKED_CIDRS


@pytest.mark.parametrize(
    "ip",
    [
        "127.0.0.1",          # loopback
        "127.255.255.255",
        "10.0.0.1",           # RFC1918
        "172.16.0.1",
        "172.31.255.255",
        "192.168.1.1",
        "169.254.169.254",    # link-local / cloud metadata
        "169.254.0.1",
        "::1",                # IPv6 loopback
        "fe80::1",            # IPv6 link-local
        "fc00::1",            # IPv6 unique-local
    ],
)
def test_blocked_ips_are_rejected(ip):
    assert is_blocked(ip) is True


@pytest.mark.parametrize(
    "ip",
    [
        "1.1.1.1",            # Cloudflare DNS
        "8.8.8.8",            # Google DNS
        "93.184.216.34",      # example.com
        "2606:4700:4700::1111",
    ],
)
def test_public_ips_are_allowed(ip):
    assert is_blocked(ip) is False


def test_invalid_ip_is_blocked_conservatively():
    # An unparseable address must be treated as unsafe
    assert is_blocked("not-an-ip") is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_ssrf_filter.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement ssrf_filter.py**

Create `ssrf_filter.py`:

```python
"""Block outbound fetches to private/internal IP ranges (SSRF protection).

Usage:
    from ssrf_filter import is_blocked, resolve_and_check

    if is_blocked("10.0.0.1"):
        raise ValueError("blocked")

    # Or, for a URL (resolves DNS + checks all answers):
    await resolve_and_check("http://example.com")  # raises on block
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

BLOCKED_CIDRS: list[ipaddress._BaseNetwork] = [
    # IPv4
    ipaddress.ip_network("127.0.0.0/8"),      # loopback
    ipaddress.ip_network("10.0.0.0/8"),       # RFC1918
    ipaddress.ip_network("172.16.0.0/12"),    # RFC1918
    ipaddress.ip_network("192.168.0.0/16"),   # RFC1918
    ipaddress.ip_network("169.254.0.0/16"),   # link-local + cloud metadata
    ipaddress.ip_network("0.0.0.0/8"),        # "this network"
    # IPv6
    ipaddress.ip_network("::1/128"),          # loopback
    ipaddress.ip_network("fc00::/7"),         # unique-local
    ipaddress.ip_network("fe80::/10"),        # link-local
]


def is_blocked(ip: str) -> bool:
    """Return True if the IP is in any blocked range. Unparseable IPs are blocked."""
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        logger.warning("Unparseable IP treated as blocked: %r", ip)
        return True
    return any(addr in cidr for cidr in BLOCKED_CIDRS)


async def resolve_and_check(url: str) -> None:
    """Resolve the URL's hostname and raise if any answer is blocked.

    Prevents DNS rebinding by checking every resolved address.
    """
    parsed = urlparse(url)
    host = parsed.hostname
    if not host:
        raise ValueError(f"URL has no host: {url!r}")

    loop = asyncio.get_running_loop()
    try:
        addrinfo = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"DNS resolution failed for {host!r}: {exc}")

    for family, _type, _proto, _canon, sockaddr in addrinfo:
        ip = sockaddr[0]
        if is_blocked(ip):
            raise ValueError(f"URL resolves to blocked IP {ip} ({host})")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_ssrf_filter.py -v
```

Expected: all 13 cases PASS.

- [ ] **Step 5: Wire into content_extractor.py**

In `content_extractor.py`, find the class that does URL fetching. Before every outbound `httpx.get` / `httpx.AsyncClient` call that uses a user-supplied URL, add a call to `resolve_and_check`. Example pattern — for each existing public method that takes a URL:

```python
from ssrf_filter import resolve_and_check

class ContentExtractor:
    async def extract(self, url: str) -> ExtractedContent:
        await resolve_and_check(url)   # NEW — raises on private/internal
        # existing logic unchanged
        ...
```

If any method constructs intermediate URLs (e.g. redirect handling), wrap each hop with `resolve_and_check`. `httpx` follows redirects by default; set `follow_redirects=False` and handle them manually so each hop can be SSRF-checked.

- [ ] **Step 6: Run full suite**

```bash
pytest tests/ -v
```

Expected: all existing tests still pass; any test that uses private IPs in URLs will now fail — update those tests to use public hostnames or mock the extractor.

- [ ] **Step 7: Commit**

```bash
git add adil-rag-api/ssrf_filter.py adil-rag-api/content_extractor.py adil-rag-api/tests/test_ssrf_filter.py
git commit -m "feat(rag-api): SSRF egress filter on content extractor"
```

---

## Task 5: R2 client wrapper

**Files:**
- Create: `adil-rag-api/r2_client.py`
- Modify: `adil-rag-api/requirements.txt` (add `aioboto3`)
- Create: `adil-rag-api/tests/test_r2_client.py`

- [ ] **Step 1: Add aioboto3 to requirements**

Edit `requirements.txt`, add:

```
aioboto3>=13.0.0
```

Install:

```bash
pip install aioboto3
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_r2_client.py`:

```python
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

    # Replace the internal _make_client with a stub
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


async def test_from_env_raises_when_incomplete(monkeypatch):
    from r2_client import R2Client, R2ConfigError

    for k in ("R2_ACCOUNT_ID", "R2_BUCKET", "R2_ENDPOINT",
              "R2_BACKEND_ACCESS_KEY_ID", "R2_BACKEND_SECRET_ACCESS_KEY"):
        monkeypatch.delenv(k, raising=False)

    with pytest.raises(R2ConfigError):
        R2Client.from_env()
```

- [ ] **Step 3: Run test to verify it fails**

```bash
pytest tests/test_r2_client.py -v
```

Expected: `ModuleNotFoundError`.

- [ ] **Step 4: Implement r2_client.py**

Create `r2_client.py`:

```python
"""Async Cloudflare R2 client for backend reads/deletes.

R2 is S3-compatible — we use aioboto3 pointed at the R2 endpoint. Backend
credentials are scoped to GetObject + DeleteObject only.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

import aioboto3


class R2ConfigError(Exception):
    pass


@dataclass(frozen=True)
class R2Config:
    account_id: str
    bucket: str
    endpoint_url: str
    access_key_id: str
    secret_access_key: str

    @classmethod
    def from_env(cls) -> "R2Config":
        required = {
            "R2_ACCOUNT_ID": None,
            "R2_BUCKET": None,
            "R2_ENDPOINT": None,
            "R2_BACKEND_ACCESS_KEY_ID": None,
            "R2_BACKEND_SECRET_ACCESS_KEY": None,
        }
        values: dict[str, str] = {}
        missing: list[str] = []
        for name in required:
            v = os.getenv(name)
            if not v:
                missing.append(name)
            else:
                values[name] = v
        if missing:
            raise R2ConfigError(f"Missing R2 env vars: {', '.join(missing)}")
        return cls(
            account_id=values["R2_ACCOUNT_ID"],
            bucket=values["R2_BUCKET"],
            endpoint_url=values["R2_ENDPOINT"],
            access_key_id=values["R2_BACKEND_ACCESS_KEY_ID"],
            secret_access_key=values["R2_BACKEND_SECRET_ACCESS_KEY"],
        )


class R2Client:
    def __init__(self, config: R2Config):
        self.config = config
        self._session = aioboto3.Session()

    @classmethod
    def from_env(cls) -> "R2Client":
        return cls(R2Config.from_env())

    def _make_client(self):
        return self._session.client(
            "s3",
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key_id,
            aws_secret_access_key=self.config.secret_access_key,
            region_name="auto",
        )

    async def get_object(self, object_key: str) -> bytes:
        """Fetch bytes from R2. Raises on missing object or access error."""
        async with self._make_client() as s3:
            resp = await s3.get_object(Bucket=self.config.bucket, Key=object_key)
            body = resp["Body"]
            return await body.read()

    async def delete_object(self, object_key: str) -> None:
        async with self._make_client() as s3:
            await s3.delete_object(Bucket=self.config.bucket, Key=object_key)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_r2_client.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add adil-rag-api/r2_client.py adil-rag-api/requirements.txt adil-rag-api/tests/test_r2_client.py
git commit -m "feat(rag-api): R2 client for backend GetObject/DeleteObject"
```

---

## Task 6: Upload models + `/api/v1/uploads/record` endpoint

**Files:**
- Modify: `adil-rag-api/models.py` (add request/response models)
- Modify: `adil-rag-api/app.py` (add endpoint)
- Create: `adil-rag-api/tests/test_uploads_record.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_uploads_record.py`:

```python
import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv("ADIL_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("FILE_SEARCH_STORE_ID", "fake")
    # DB must be available for the test — skip if not
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL not set")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])


async def test_record_upload_success(client: TestClient):
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
    data = resp.json()
    assert data["id"] == upload_id


async def test_record_upload_rejects_invalid_content_type(client: TestClient):
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


async def test_record_upload_rejects_oversize(client: TestClient):
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
            "size_bytes": 20 * 1024 * 1024,  # 20MB
        },
    )
    assert resp.status_code == 422


async def test_record_upload_requires_api_key(client: TestClient):
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
```

Add `conftest.py` fixture if not present:

```python
# tests/conftest.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    import importlib
    import app as app_module

    importlib.reload(app_module)
    return TestClient(app_module.app)
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_uploads_record.py -v
```

Expected: tests fail — endpoint doesn't exist yet.

- [ ] **Step 3: Add models**

In `models.py`, add:

```python
from typing import Literal


class UploadRecordRequest(BaseModel):
    id: uuid.UUID
    conversation_id: uuid.UUID
    object_key: str = Field(..., min_length=1, max_length=512)
    content_type: Literal["image/png", "image/jpeg", "image/webp"]
    size_bytes: int = Field(..., ge=1, le=10_485_760)  # 1 byte to 10MB


class UploadRecordResponse(BaseModel):
    id: uuid.UUID
```

Also add `import uuid` if not already present.

- [ ] **Step 4: Add endpoint to app.py**

In `app.py`, import models and add the endpoint:

```python
from models import UploadRecordRequest, UploadRecordResponse

@app.post(
    "/api/v1/uploads/record",
    response_model=UploadRecordResponse,
    status_code=201,
    tags=["Uploads"],
)
async def record_upload(
    request: Request,
    body: UploadRecordRequest,
    _api_key: str = Security(verify_api_key),
):
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise HTTPException(status_code=500, detail="DATABASE_URL not configured")

    conn = await asyncpg.connect(db_url)
    try:
        await conn.execute(
            """
            INSERT INTO uploads (id, conversation_id, object_key, content_type, size_bytes)
            VALUES ($1, $2, $3, $4, $5)
            """,
            body.id,
            body.conversation_id,
            body.object_key,
            body.content_type,
            body.size_bytes,
        )
    finally:
        await conn.close()

    return UploadRecordResponse(id=body.id)
```

Add `import asyncpg` at the top if not already present.

- [ ] **Step 5: Run tests to verify they pass**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_uploads_record.py -v
```

Expected: all 4 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add adil-rag-api/models.py adil-rag-api/app.py adil-rag-api/tests/test_uploads_record.py adil-rag-api/tests/conftest.py
git commit -m "feat(rag-api): POST /api/v1/uploads/record endpoint"
```

---

## Task 7: Vision endpoint — R2 fetch + ownership check

**Files:**
- Modify: `adil-rag-api/app.py` (update `/api/v1/query/image` to accept `upload_ids` and read from R2)
- Modify: `adil-rag-api/models.py` (extend `ImageQueryRequest` with `upload_ids`)
- Create: `adil-rag-api/tests/test_vision_r2.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_vision_r2.py`:

```python
import os
import uuid
from unittest.mock import AsyncMock

import asyncpg
import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture
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
            upload_id, conv_id, f"uploads/{conv_id}/{upload_id}.png", "image/png", 1234,
        )
    finally:
        await conn.close()
    return conv_id, upload_id


async def test_vision_with_owned_upload(seed_upload, monkeypatch):
    conv_id, upload_id = seed_upload

    # Stub R2
    import r2_client
    stub_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    monkeypatch.setattr(
        r2_client.R2Client, "get_object",
        AsyncMock(return_value=stub_bytes),
    )

    # Stub Gemini call inside RAGService.query_with_image
    import rag_service
    async def fake_query_with_image(self, query, images, **kw):
        return {"answer": "test", "sources": [], "viability_assessment": None,
                "usage": {}, "metadata": {}}
    monkeypatch.setattr(rag_service.RAGService, "query_with_image", fake_query_with_image)

    import importlib, app as app_module
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
    assert resp.status_code == 200


async def test_vision_rejects_cross_conversation_upload(seed_upload, monkeypatch):
    conv_id, upload_id = seed_upload

    import importlib, app as app_module
    importlib.reload(app_module)
    client = TestClient(app_module.app)

    # Use a different conversation_id — must 403
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
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_vision_r2.py -v
```

Expected: fails (endpoint doesn't support `upload_ids` yet).

- [ ] **Step 3: Update ImageQueryRequest model**

In `models.py`, update `ImageQueryRequest`:

```python
class ImageQueryRequest(BaseModel):
    query: str
    conversation_id: uuid.UUID | None = None
    conversation_history: list[ConversationTurn] | None = None
    # New: references to uploads recorded in the uploads table
    upload_ids: list[uuid.UUID] = Field(default_factory=list)
    # Legacy inline images (base64) — kept for backward compatibility
    images: list[ImageData] = Field(default_factory=list)
    max_sources: int = 10
    include_viability_score: bool = True
```

- [ ] **Step 4: Update /api/v1/query/image endpoint in app.py**

Locate the existing `@app.post("/api/v1/query/image")` handler. Before the call that forwards images to the RAG service, add:

```python
from r2_client import R2Client
from models import ImageData

async def _load_uploads_from_r2(
    conversation_id: uuid.UUID,
    upload_ids: list[uuid.UUID],
) -> list[ImageData]:
    if not upload_ids:
        return []
    db_url = os.getenv("DATABASE_URL")
    if not db_url:
        raise HTTPException(500, "DATABASE_URL not configured")

    conn = await asyncpg.connect(db_url)
    try:
        rows = await conn.fetch(
            "SELECT id, object_key, content_type FROM uploads "
            "WHERE id = ANY($1::uuid[]) AND conversation_id = $2",
            upload_ids, conversation_id,
        )
    finally:
        await conn.close()

    found_ids = {r["id"] for r in rows}
    missing = set(upload_ids) - found_ids
    if missing:
        raise HTTPException(
            status_code=403,
            detail=f"Upload(s) not found for this conversation: {sorted(str(m) for m in missing)}",
        )

    r2 = R2Client.from_env()
    images: list[ImageData] = []
    for row in rows:
        data = await r2.get_object(row["object_key"])
        images.append(ImageData(
            data=base64.b64encode(data).decode("ascii"),
            mime_type=row["content_type"],
        ))
    return images
```

Then, inside the `/api/v1/query/image` handler, merge R2-loaded images with any inline `images`:

```python
r2_images = await _load_uploads_from_r2(body.conversation_id, body.upload_ids)
all_images = r2_images + body.images
# ... pass `all_images` to the existing RAGService call ...
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_vision_r2.py -v
```

Expected: both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add adil-rag-api/models.py adil-rag-api/app.py adil-rag-api/tests/test_vision_r2.py
git commit -m "feat(rag-api): vision endpoint loads uploads from R2 with ownership check"
```

---

## Task 8: Rate-limit FastAPI dependency + wire to endpoints

**Files:**
- Modify: `adil-rag-api/app.py`
- Create: `adil-rag-api/tests/test_rate_limit_endpoints.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_rate_limit_endpoints.py`:

```python
import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL not set")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("ADIL_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("FILE_SEARCH_STORE_ID", "fake")


async def test_report_endpoint_rate_limits_at_3_per_hour(monkeypatch):
    # 4th call in the same hour from same IP must 429 with Retry-After
    import importlib, app as app_module, rag_service
    async def fake_submit(*a, **kw):
        return {"ok": True, "reference": "ABC"}
    monkeypatch.setattr(rag_service.RAGService, "submit_report", fake_submit, raising=False)
    importlib.reload(app_module)
    client = TestClient(app_module.app)

    payload = {
        "reporter": {"name": "T", "email": "t@t.com"},
        "incident": {"target_org": "bmt", "summary": "test"},
    }
    headers = {"X-API-Key": "test-key", "X-AskAdil-Client-IP": "5.5.5.5"}

    # 3 allowed
    for _ in range(3):
        r = client.post("/api/v1/report/submit", headers=headers, json=payload)
        assert r.status_code in (200, 201, 202)
    # 4th rejected
    r = client.post("/api/v1/report/submit", headers=headers, json=payload)
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_rate_limit_endpoints.py -v
```

Expected: fails (no rate limiting applied yet).

- [ ] **Step 3: Add rate-limit dependency to app.py**

In `app.py`, add:

```python
from datetime import timedelta

import asyncpg

from rate_limit import Limit, check_limits, RateLimitExceeded

_db_pool: asyncpg.Pool | None = None


async def _get_pool() -> asyncpg.Pool:
    global _db_pool
    if _db_pool is None:
        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise HTTPException(500, "DATABASE_URL not configured")
        _db_pool = await asyncpg.create_pool(db_url, min_size=1, max_size=10)
    return _db_pool


def enforce(limits: list[Limit]):
    """Return a FastAPI dependency that enforces the given rate limits."""
    async def _dep(request: Request, _api_key: str = Security(verify_api_key)):
        identity = resolve_client_ip(request, api_key_valid=True)
        pool = await _get_pool()
        try:
            await check_limits(pool, limits, identity)
        except RateLimitExceeded as exc:
            raise HTTPException(
                status_code=429,
                detail=f"rate limit exceeded ({exc.limit}/{exc.window})",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            )
    return _dep


CHAT_LIMITS = [
    Limit("chat:ip", 30, timedelta(minutes=1)),
    Limit("chat:ip", 200, timedelta(hours=1)),
]
CHAT_IMAGE_LIMITS = [
    Limit("chat-image:ip", 10, timedelta(minutes=1)),
    Limit("chat-image:ip", 50, timedelta(hours=1)),
]
REPORT_LIMITS = [
    Limit("report:ip", 3, timedelta(hours=1)),
    Limit("report:ip", 10, timedelta(hours=24)),
]
EXTRACT_URL_LIMITS = [
    Limit("extract-url:ip", 20, timedelta(minutes=1)),
]
UPLOAD_LIMITS = [
    Limit("upload:ip", 10, timedelta(hours=1)),
]
```

Attach to each protected endpoint by adding `dependencies=[Depends(enforce(X_LIMITS))]`:

```python
from fastapi import Depends

@app.post("/api/v1/query", ..., dependencies=[Depends(enforce(CHAT_LIMITS))])
async def query(...): ...

@app.post("/api/v1/query/image", ..., dependencies=[Depends(enforce(CHAT_IMAGE_LIMITS))])
async def query_image(...): ...

@app.post("/api/v1/report/submit", ..., dependencies=[Depends(enforce(REPORT_LIMITS))])
async def submit_report(...): ...

@app.post("/api/v1/extract-url", ..., dependencies=[Depends(enforce(EXTRACT_URL_LIMITS))])
async def extract_url(...): ...

@app.post("/api/v1/uploads/record", ..., dependencies=[Depends(enforce(UPLOAD_LIMITS))])
async def record_upload(...): ...
```

- [ ] **Step 4: Run tests**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_rate_limit_endpoints.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add adil-rag-api/app.py adil-rag-api/tests/test_rate_limit_endpoints.py
git commit -m "feat(rag-api): Postgres rate limits on chat / report / upload endpoints"
```

---

## Task 9: SSE streaming endpoint `/api/v1/query/stream`

**Files:**
- Modify: `adil-rag-api/app.py`
- Modify: `adil-rag-api/rag_service.py` (add `stream_query` method)
- Modify: `adil-rag-api/models.py` (add `StreamEvent` types for documentation)
- Create: `adil-rag-api/tests/test_streaming.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_streaming.py`:

```python
import os

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.asyncio


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    if not os.getenv("TEST_DATABASE_URL"):
        pytest.skip("TEST_DATABASE_URL not set")
    monkeypatch.setenv("DATABASE_URL", os.environ["TEST_DATABASE_URL"])
    monkeypatch.setenv("ADIL_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_API_KEY", "fake")
    monkeypatch.setenv("FILE_SEARCH_STORE_ID", "fake")


async def test_stream_emits_token_source_viability_done(monkeypatch):
    # Stub the streaming generator on RAGService
    import importlib, app as app_module, rag_service

    async def fake_stream(self, query, **kw):
        yield {"event": "token", "data": "Based "}
        yield {"event": "token", "data": "in England"}
        yield {"event": "source", "data": {"type": "statute", "title": "EA 2010 §10", "url": "https://…", "citation": "[1]"}}
        yield {"event": "viability", "data": {"score": 75, "vento_band": "Middle", "statutory_footing": True,
                                              "case_law_precedent": True, "quantum_potential": "moderate",
                                              "evidence_checklist": []}}
        yield {"event": "done", "data": {"conversation_id": "x", "sources_count": 1, "tokens_used": 42}}

    monkeypatch.setattr(rag_service.RAGService, "stream_query", fake_stream, raising=False)
    importlib.reload(app_module)
    client = TestClient(app_module.app)

    resp = client.post(
        "/api/v1/query/stream",
        headers={"X-API-Key": "test-key", "X-AskAdil-Client-IP": "7.7.7.7"},
        json={"query": "what is indirect discrimination?"},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")

    body = resp.text
    assert "event: token" in body
    assert "data: \"Based \"" in body or 'data: "Based "' in body
    assert "event: source" in body
    assert "event: viability" in body
    assert "event: done" in body
```

- [ ] **Step 2: Run test to verify it fails**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_streaming.py -v
```

Expected: fails (endpoint doesn't exist).

- [ ] **Step 3: Add `stream_query` to RAGService**

In `rag_service.py`, add an async generator:

```python
async def stream_query(self, query: str, *, conversation_history=None,
                       jurisdiction=None, max_sources=10,
                       include_viability_score=True, conversation_id=None):
    """Yield SSE-shaped events from a Gemini streaming call.

    Each yielded item is {"event": str, "data": Any}.
    """
    # Reuse the same request construction as existing `query()`
    contents, system_instruction = self._build_prompt(
        query=query,
        conversation_history=conversation_history or [],
        jurisdiction=jurisdiction,
    )

    stream = self.client.models.generate_content_stream(
        model=self.model_name,
        contents=contents,
        config={
            "system_instruction": system_instruction,
            "tools": [{"file_search": {"file_search_store_names": [self.file_search_store_id]}}],
        },
    )

    full_text = ""
    usage_metadata = None
    for chunk in stream:
        if getattr(chunk, "text", None):
            full_text += chunk.text
            yield {"event": "token", "data": chunk.text}
        if getattr(chunk, "usage_metadata", None):
            usage_metadata = chunk.usage_metadata

    # After generation completes, parse sources + viability from full_text
    sources = self._extract_sources(full_text)
    for s in sources[:max_sources]:
        yield {"event": "source", "data": s.model_dump() if hasattr(s, "model_dump") else s}

    if include_viability_score:
        viability = self._extract_viability(full_text, sources)
        if viability:
            yield {"event": "viability",
                   "data": viability.model_dump() if hasattr(viability, "model_dump") else viability}

    yield {
        "event": "done",
        "data": {
            "conversation_id": str(conversation_id) if conversation_id else None,
            "sources_count": len(sources),
            "tokens_used": getattr(usage_metadata, "total_token_count", 0) if usage_metadata else 0,
        },
    }
```

If `_build_prompt`, `_extract_sources`, `_extract_viability` don't exist with these exact names, adapt to the existing method names in `rag_service.py`.

- [ ] **Step 4: Add streaming endpoint to app.py**

```python
import json
import asyncio
from fastapi.responses import StreamingResponse

@app.post(
    "/api/v1/query/stream",
    tags=["Query"],
    dependencies=[Depends(enforce(CHAT_LIMITS))],
)
async def query_stream(
    request: Request,
    body: QueryRequest,
    _api_key: str = Security(verify_api_key),
):
    async def event_source():
        # Heartbeat task to keep proxies from closing idle streams
        heartbeat_stop = asyncio.Event()

        async def heartbeat():
            while not heartbeat_stop.is_set():
                try:
                    await asyncio.wait_for(heartbeat_stop.wait(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"

        # We cannot trivially merge generators; emit heartbeats inline between chunks instead.
        try:
            last_send = asyncio.get_event_loop().time()
            async for event in rag_service.stream_query(
                query=body.query,
                conversation_history=body.conversation_history,
                jurisdiction=getattr(body, "jurisdiction", None),
                max_sources=body.max_sources,
                include_viability_score=body.include_viability_score,
                conversation_id=getattr(body, "conversation_id", None),
            ):
                data_json = json.dumps(event["data"], default=str) if not isinstance(event["data"], str) else json.dumps(event["data"])
                yield f"event: {event['event']}\ndata: {data_json}\n\n"
                last_send = asyncio.get_event_loop().time()
        except RateLimitExceeded as exc:
            yield f"event: error\ndata: {json.dumps({'code':'RATE_LIMIT','message':str(exc)})}\n\n"
        except Exception as exc:
            logger.exception("stream error")
            yield f"event: error\ndata: {json.dumps({'code':'INTERNAL','message':str(exc)[:200]})}\n\n"

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable proxy buffering
        },
    )
```

- [ ] **Step 5: Run tests**

```bash
TEST_DATABASE_URL=postgresql://localhost/adil_test pytest tests/test_streaming.py -v
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add adil-rag-api/app.py adil-rag-api/rag_service.py adil-rag-api/tests/test_streaming.py
git commit -m "feat(rag-api): SSE streaming endpoint /api/v1/query/stream"
```

---

## Task 10: CORS gating — dev-only

**Files:**
- Modify: `adil-rag-api/app.py`

- [ ] **Step 1: Update the CORSMiddleware registration**

Find the existing:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    ...
)
```

Replace with:

```python
enable_dev_cors = os.getenv("ENABLE_DEV_CORS", "false").lower() == "true"
cors_origins = ["http://localhost:3000"] if enable_dev_cors else []

if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
```

In production (Railway private network), `ENABLE_DEV_CORS` is unset → no CORS middleware at all. Local dev sets `ENABLE_DEV_CORS=true` → `localhost:3000` is allowed.

- [ ] **Step 2: Run full suite**

```bash
pytest tests/ -v
```

Expected: everything still passes. No CORS test changes needed because the existing tests don't depend on CORS headers.

- [ ] **Step 3: Commit**

```bash
git add adil-rag-api/app.py
git commit -m "feat(rag-api): gate CORS behind ENABLE_DEV_CORS env flag"
```

---

## Task 11: Streaming events documentation

**Files:**
- Create: `adil-rag-api/docs/api/streaming-events.md`

- [ ] **Step 1: Write the doc**

```markdown
# Streaming Event Schema

`POST /api/v1/query/stream` emits Server-Sent Events (SSE) with the following event types.

Each event is framed as:

```
event: <type>
data: <json-or-string>

```

(blank line terminates the event)

## Event types

### `token`
A text chunk from the model. `data` is a JSON-encoded string.

```
event: token
data: "Based "
```

### `source`
A citation. `data` is a JSON object.

| Field | Type | Notes |
|-------|------|-------|
| `type` | `"statute" \| "case_law" \| "echr_judgment"` | enum |
| `title` | string | e.g. "Equality Act 2010 §10" |
| `url` | string | link to legislation.gov.uk or caselaw.nationalarchives.gov.uk |
| `citation` | string | e.g. `"[1]"` |
| `excerpt` | string (optional) | short quote |

### `viability`
A structured viability assessment. Emitted at most once.

| Field | Type |
|-------|------|
| `score` | int 0-100 |
| `vento_band` | `"Lower" \| "Middle" \| "Upper" \| "Exceptional"` |
| `statutory_footing` | bool |
| `case_law_precedent` | bool |
| `quantum_potential` | `"low" \| "moderate" \| "high"` |
| `evidence_checklist` | string[] |

### `done`
Terminal event. The stream will close after this.

| Field | Type |
|-------|------|
| `conversation_id` | string (UUID) |
| `sources_count` | int |
| `tokens_used` | int |

### `error`
Terminal event on failure.

| Field | Type |
|-------|------|
| `message` | string (human-readable) |
| `code` | `"RATE_LIMIT" \| "AUTH" \| "INTERNAL" \| "VALIDATION" \| "UPSTREAM"` |

## Keepalive

Between token bursts, the server may send SSE comments:

```
: keepalive

```

Clients should ignore comment lines.
```

- [ ] **Step 2: Commit**

```bash
git add adil-rag-api/docs/api/streaming-events.md
git commit -m "docs(rag-api): streaming event schema reference"
```

---

## Task 12: Rate-limit cleanup cron in document-uploader

**Files:**
- Modify: `adil-document-uploader/app/workers/tasks.py`
- Modify: `adil-document-uploader/app/workers/settings.py`

- [ ] **Step 1: Add cleanup task**

Append to `adil-document-uploader/app/workers/tasks.py`:

```python
async def rate_limit_cleanup(ctx: dict) -> dict:
    """Remove rate-limit counter rows older than 48 hours and expired upload rows.

    Runs against the adil-rag-api Postgres database. Assumes DATABASE_URL is set
    to that backend's database (shared across services).
    """
    import asyncpg

    settings = get_settings()
    rag_db_url = os.getenv("RAG_API_DATABASE_URL") or settings.database_url
    if not rag_db_url:
        logger.warning("No DB URL for rate_limit_cleanup; skipping")
        return {"deleted_counters": 0, "deleted_uploads": 0}

    conn = await asyncpg.connect(rag_db_url)
    try:
        deleted_c = await conn.fetchval(
            "WITH d AS (DELETE FROM rate_limit_counters "
            "WHERE bucket_start < now() - interval '48 hours' RETURNING 1) "
            "SELECT count(*) FROM d"
        )
        deleted_u = await conn.fetchval(
            "WITH d AS (DELETE FROM uploads WHERE expires_at < now() RETURNING 1) "
            "SELECT count(*) FROM d"
        )
    finally:
        await conn.close()

    logger.info("rate_limit_cleanup: removed %s counters, %s uploads", deleted_c, deleted_u)
    return {"deleted_counters": int(deleted_c or 0), "deleted_uploads": int(deleted_u or 0)}
```

Add `import os` at the top if not already present.

- [ ] **Step 2: Register the cron**

In `adil-document-uploader/app/workers/settings.py`, update `WorkerSettings`:

```python
from app.workers.tasks import (
    fetch_case_law,
    upload_pending,
    heartbeat,
    heartbeat_alert_only,
    rate_limit_cleanup,
)

class WorkerSettings:
    functions = [fetch_case_law, upload_pending, heartbeat, heartbeat_alert_only, rate_limit_cleanup]
    redis_settings = RedisSettings.from_dsn(_settings.redis_url)

    cron_jobs = [
        cron(fetch_case_law, hour=3, minute=0),
        cron(upload_pending, hour=3, minute=30),
        cron(heartbeat, hour={0, 6, 12, 18}, minute=0),
        cron(heartbeat_alert_only, minute=0),
        cron(rate_limit_cleanup, minute=15),   # hourly at :15
    ]
```

- [ ] **Step 3: Add Railway env var**

In the `adil-document-uploader` Railway service, add:

```
RAG_API_DATABASE_URL=<same Postgres URL used by adil-rag-api>
```

This is the new env var the worker uses to connect to the backend's DB for cleanup. Document it in `adil-document-uploader/.env.example`.

- [ ] **Step 4: Commit**

```bash
git add adil-document-uploader/app/workers/tasks.py adil-document-uploader/app/workers/settings.py adil-document-uploader/.env.example
git commit -m "feat(document-uploader): hourly cleanup of rate-limit counters + expired uploads"
```

---

## Parallel execution map

```
Task 1 (migrations)
  └─> Task 2 (rate_limit helper)   ──┐
  └─> Task 3 (auth hardening)      ──┤  All of 4-7 can start in parallel
  └─> Task 4 (SSRF filter)         ──┤  once their prerequisites are met
  └─> Task 5 (R2 client)           ──┤
        └─> Task 6 (uploads endpoint) ─┤
        └─> Task 7 (vision R2)        ─┤
              └─> Task 8 (rate limits on endpoints)
                    └─> Task 9 (SSE streaming)
                          └─> Task 10 (CORS gate)
                                └─> Task 11 (docs)
                                      └─> Task 12 (cleanup cron)
```

Tasks 4 and 5 are fully independent of each other. Tasks 2 and 3 only need Task 1. Dispatch them in parallel for fastest completion.

---

## Self-review

Spec coverage (Spec 1 `docs/superpowers/specs/2026-04-22-rag-api-streaming-hardening.md`):

| Spec section | Task |
|--------------|------|
| 1. Streaming endpoint | Task 9 |
| 2. Rate limiting (table + middleware) | Tasks 1, 2, 8 |
| 3. Authentication + client IP | Task 3 |
| 4. Upload metadata + R2 | Tasks 5, 6, 7 |
| 5. SSRF filter | Task 4 |
| 6. Viability + source schema docs | Task 11 |
| 7. Remove CORS / dev gate | Task 10 |
| 8. Gemini ZDR prerequisite | (not code — documentation in privacy notice, tracked in Spec 2) |
| Cleanup cron | Task 12 |

All spec sections covered.
