# adil-document-uploader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI microservice that fetches UK case law from The National Archives API and uploads it to the existing Gemini File Search Tool Store.

**Architecture:** FastAPI + arq worker pattern (mirroring adil-outreach-engine). TNA Atom API for case law search/download, Postgres for dedup/audit, Gemini genai SDK for FST store uploads. Single Dockerfile with SERVICE_ROLE env var for API vs worker mode.

**Tech Stack:** FastAPI, uvicorn, arq, Redis, SQLAlchemy async, asyncpg, Alembic, httpx, lxml, google-genai, pydantic-settings

**Spec:** `docs/superpowers/specs/2026-04-04-document-uploader-design.md`

**Existing pattern to follow:** `adil-outreach-engine/` (same Dockerfile, railway.toml, arq worker, SQLAlchemy async, API key auth patterns)

---

## File Map

All paths relative to `adil-document-uploader/`.

| File | Responsibility |
|------|---------------|
| `pyproject.toml` | Dependencies, project metadata, tool config |
| `.env.example` | Environment variable template |
| `.dockerignore` | Docker build exclusions |
| `railway.toml` | Railway deployment config |
| `Dockerfile` | Multi-stage build, SERVICE_ROLE pattern |
| `docker-compose.yml` | Local dev (api + worker + postgres + redis) |
| `alembic.ini` | Alembic config pointing to app.database |
| `alembic/env.py` | Async Alembic environment |
| `app/__init__.py` | Package marker |
| `app/config.py` | pydantic-settings Settings + SearchDomain definitions |
| `app/database.py` | Async SQLAlchemy engine + session factory |
| `app/auth/__init__.py` | Package marker |
| `app/auth/api_key.py` | FastAPI dependency: validate ADMIN_API_KEY header |
| `app/models/__init__.py` | Package marker, re-export Judgment |
| `app/models/judgment.py` | SQLAlchemy Judgment model |
| `app/schemas/__init__.py` | Package marker |
| `app/schemas/judgment.py` | Pydantic schemas for API request/response |
| `app/services/__init__.py` | Package marker |
| `app/services/tna_client.py` | TNA Atom API: search + download judgments |
| `app/services/xml_parser.py` | Akoma Ntoso XML to clean text + metadata |
| `app/services/gemini_uploader.py` | Upload documents to Gemini FST store |
| `app/api/__init__.py` | Package marker |
| `app/api/judgments.py` | GET /judgments, GET /judgments/{id} |
| `app/api/admin.py` | POST /fetch, POST /upload, GET /stats |
| `app/main.py` | FastAPI app, lifespan, router includes, health |
| `app/workers/__init__.py` | Package marker |
| `app/workers/settings.py` | arq WorkerSettings + cron schedule |
| `app/workers/tasks.py` | fetch_case_law + upload_pending task functions |
| `tests/__init__.py` | Package marker |
| `tests/conftest.py` | Shared fixtures (async DB, httpx test client) |
| `tests/test_tna_client.py` | TNA client unit tests with mocked HTTP |
| `tests/test_xml_parser.py` | XML parser tests with sample Akoma Ntoso |
| `tests/test_gemini_uploader.py` | Gemini uploader tests with mocked SDK |
| `tests/test_judgments_api.py` | API endpoint tests |
| `tests/test_workers.py` | Worker task tests |
| `README.md` | Service documentation |

---

## Task 1: Project Scaffold

**Files:**
- Create: `adil-document-uploader/pyproject.toml`
- Create: `adil-document-uploader/.env.example`
- Create: `adil-document-uploader/.dockerignore`
- Create: `adil-document-uploader/railway.toml`
- Create: `adil-document-uploader/Dockerfile`
- Create: `adil-document-uploader/docker-compose.yml`
- Create: `adil-document-uploader/app/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

```toml
[project]
name = "adil-document-uploader"
version = "0.1.0"
description = "Case law fetcher and Gemini FST store uploader for AskAdil"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.34.0",
    "sqlalchemy[asyncio]>=2.0.36",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",
    "pydantic>=2.10.0",
    "pydantic-settings>=2.7.0",
    "python-dotenv>=1.0.1",
    "httpx>=0.28.0",
    "lxml>=5.0.0",
    "google-genai>=0.4.0",
    "arq>=0.26.0",
    "redis>=5.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.25.0",
    "httpx>=0.28.0",
    "aiosqlite>=0.20.0",
    "ruff>=0.8.0",
    "respx>=0.22.0",
    "fakeredis>=2.21.0",
]

[tool.setuptools.packages.find]
include = ["app*"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 120
```

- [ ] **Step 2: Create .env.example**

```env
# TNA API (no auth needed)
TNA_BASE_URL=https://caselaw.nationalarchives.gov.uk

# Gemini
GEMINI_API_KEY=your_gemini_api_key
FILE_SEARCH_STORE_ID=fileSearchStores/your_store_id

# Database
DATABASE_URL=postgresql+asyncpg://uploader:uploader_dev@localhost:5434/document_uploader

# Redis
REDIS_URL=redis://localhost:6381

# Auth
ADMIN_API_KEY=your_admin_api_key

# Service
PORT=8002
SERVICE_ROLE=api
```

- [ ] **Step 3: Create .dockerignore**

```
.git
.env
.venv
__pycache__
*.pyc
.pytest_cache
.ruff_cache
tests/
docker-compose.yml
*.md
```

- [ ] **Step 4: Create railway.toml**

```toml
[build]
builder = "DOCKERFILE"
dockerfilePath = "Dockerfile"

[deploy]
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 3
```

- [ ] **Step 5: Create Dockerfile**

```dockerfile
# Stage 1 — Builder
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libxml2-dev libxslt1-dev \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
RUN pip install --no-cache-dir --prefix=/install .

# Stage 2 — Runtime
FROM python:3.11-slim AS runtime

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    libxml2 libxslt1.1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY --from=builder /install /usr/local
COPY . .

RUN adduser --disabled-password --no-create-home appuser
USER appuser

EXPOSE 8002

ENV SERVICE_ROLE=api

CMD ["sh", "-c", "if [ \"$SERVICE_ROLE\" = 'worker' ]; then echo 'Starting arq worker...' && arq app.workers.settings.WorkerSettings; else alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8002}; fi"]
```

- [ ] **Step 6: Create docker-compose.yml**

```yaml
services:
  api:
    build: .
    ports:
      - "8002:8002"
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      sh -c "alembic upgrade head &&
             uvicorn app.main:app --host 0.0.0.0 --port 8002 --reload"
    volumes:
      - .:/app

  worker:
    build: .
    env_file: .env
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: arq app.workers.settings.WorkerSettings

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: document_uploader
      POSTGRES_USER: uploader
      POSTGRES_PASSWORD: uploader_dev
    ports:
      - "5434:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U uploader"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6381:6379"
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 5s
      retries: 5

volumes:
  pgdata:
```

- [ ] **Step 7: Create app/__init__.py**

Empty file.

- [ ] **Step 8: Commit**

```bash
cd adil-document-uploader
git add -A
git commit -m "feat(document-uploader): project scaffold with Dockerfile, Railway, docker-compose"
```

---

## Task 2: Config + Database + Alembic Setup

**Files:**
- Create: `adil-document-uploader/app/config.py`
- Create: `adil-document-uploader/app/database.py`
- Create: `adil-document-uploader/alembic.ini`
- Create: `adil-document-uploader/alembic/env.py`

- [ ] **Step 1: Create app/config.py**

```python
from __future__ import annotations

from dataclasses import dataclass
from pydantic_settings import BaseSettings


@dataclass(frozen=True)
class SearchDomain:
    """A predefined case law search domain."""

    name: str
    queries: list[str]
    courts: list[str]


SEARCH_DOMAINS: list[SearchDomain] = [
    SearchDomain(
        name="religious_discrimination_employment",
        queries=['"religious discrimination"', '"Equality Act" religion belief'],
        courts=["eat", "ewca/civ"],
    ),
    SearchDomain(
        name="hate_crime_religious_hatred",
        queries=['"religiously aggravated"', '"religious hatred"', '"racially aggravated"'],
        courts=["ewca/crim", "ewhc/admin"],
    ),
    SearchDomain(
        name="goods_services_discrimination",
        queries=['"discrimination" "provision of services"', '"Equality Act" "section 29"'],
        courts=["ewca/civ", "ewhc/admin"],
    ),
    SearchDomain(
        name="intersectional_race_religion",
        queries=['"race discrimination" Muslim', '"ethnic origin" discrimination'],
        courts=["eat", "ewca/civ"],
    ),
    SearchDomain(
        name="echr_human_rights",
        queries=['"Article 9" religion', '"Article 14" discrimination'],
        courts=["uksc", "ewca/civ"],
    ),
]


class Settings(BaseSettings):
    # TNA
    tna_base_url: str = "https://caselaw.nationalarchives.gov.uk"
    tna_max_requests_per_minute: int = 150

    # Gemini
    gemini_api_key: str
    file_search_store_id: str

    # Database
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379"

    # Auth
    admin_api_key: str

    # Service
    port: int = 8002

    model_config = {"env_file": ".env", "extra": "ignore"}


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 2: Create app/database.py**

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:  # type: ignore[misc]
    async with async_session() as session:
        yield session
```

- [ ] **Step 3: Create alembic.ini**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 4: Create alembic/env.py**

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings
from app.models import Base  # noqa: F401 — import so Alembic sees metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()


def run_migrations_offline() -> None:
    context.configure(url=settings.database_url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = create_async_engine(settings.database_url)
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 5: Commit**

```bash
git add app/config.py app/database.py alembic.ini alembic/env.py
git commit -m "feat(document-uploader): config, database, and Alembic setup"
```

---

## Task 3: SQLAlchemy Model + Migration

**Files:**
- Create: `adil-document-uploader/app/models/__init__.py`
- Create: `adil-document-uploader/app/models/judgment.py`

- [ ] **Step 1: Create app/models/judgment.py**

```python
from __future__ import annotations

import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class JudgmentStatus(str, enum.Enum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    SKIPPED = "skipped"
    FAILED = "failed"


class Judgment(Base):
    __tablename__ = "judgments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    neutral_citation: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    tna_uri: Mapped[str] = mapped_column(String(200), nullable=False)
    tna_url: Mapped[str] = mapped_column(String(500), nullable=False)
    court: Mapped[str] = mapped_column(String(50), nullable=False)
    case_name: Mapped[str] = mapped_column(String(500), nullable=False)
    judgment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    search_domain: Mapped[str] = mapped_column(String(100), nullable=False)
    search_query: Mapped[str] = mapped_column(String(500), nullable=False)
    raw_xml: Mapped[str] = mapped_column(Text, nullable=False)
    clean_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[JudgmentStatus] = mapped_column(
        Enum(JudgmentStatus, native_enum=False), nullable=False, default=JudgmentStatus.PENDING
    )
    gemini_file_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    uploaded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_judgments_status", "status"),
        Index("ix_judgments_search_domain", "search_domain"),
        Index("ix_judgments_court", "court"),
    )
```

- [ ] **Step 2: Create app/models/__init__.py**

```python
from app.models.judgment import Base, Judgment, JudgmentStatus

__all__ = ["Base", "Judgment", "JudgmentStatus"]
```

- [ ] **Step 3: Generate Alembic migration**

```bash
cd adil-document-uploader
alembic revision --autogenerate -m "create judgments table"
```

Verify the generated migration creates the `judgments` table with all columns and indexes.

- [ ] **Step 4: Commit**

```bash
git add app/models/ alembic/
git commit -m "feat(document-uploader): Judgment model and initial migration"
```

---

## Task 4: Pydantic Schemas + Auth Dependency

**Files:**
- Create: `adil-document-uploader/app/schemas/__init__.py`
- Create: `adil-document-uploader/app/schemas/judgment.py`
- Create: `adil-document-uploader/app/auth/__init__.py`
- Create: `adil-document-uploader/app/auth/api_key.py`

- [ ] **Step 1: Create app/schemas/judgment.py**

```python
from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel

from app.models.judgment import JudgmentStatus


class JudgmentResponse(BaseModel):
    id: uuid.UUID
    neutral_citation: str
    tna_uri: str
    tna_url: str
    court: str
    case_name: str
    judgment_date: date | None
    search_domain: str
    status: JudgmentStatus
    gemini_file_id: str | None
    error_message: str | None
    fetched_at: datetime
    uploaded_at: datetime | None

    model_config = {"from_attributes": True}


class JudgmentDetail(JudgmentResponse):
    """Full detail including clean_text (excludes raw_xml for payload size)."""

    clean_text: str
    search_query: str
    created_at: datetime
    updated_at: datetime


class JudgmentListResponse(BaseModel):
    items: list[JudgmentResponse]
    total: int
    page: int
    page_size: int


class StatsResponse(BaseModel):
    total: int
    by_status: dict[str, int]
    by_domain: dict[str, int]
    by_court: dict[str, int]


class FetchResponse(BaseModel):
    message: str
    new_judgments: int
    skipped_duplicates: int


class UploadResponse(BaseModel):
    message: str
    uploaded: int
    failed: int
```

- [ ] **Step 2: Create app/schemas/__init__.py**

```python
from app.schemas.judgment import (
    FetchResponse,
    JudgmentDetail,
    JudgmentListResponse,
    JudgmentResponse,
    StatsResponse,
    UploadResponse,
)

__all__ = [
    "FetchResponse",
    "JudgmentDetail",
    "JudgmentListResponse",
    "JudgmentResponse",
    "StatsResponse",
    "UploadResponse",
]
```

- [ ] **Step 3: Create app/auth/api_key.py**

```python
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import get_settings

_api_key_header = APIKeyHeader(name="X-Admin-Key")


async def require_admin_key(key: str = Security(_api_key_header)) -> str:
    if key != get_settings().admin_api_key:
        raise HTTPException(status_code=403, detail="Invalid admin API key")
    return key
```

- [ ] **Step 4: Create app/auth/__init__.py**

Empty file.

- [ ] **Step 5: Commit**

```bash
git add app/schemas/ app/auth/
git commit -m "feat(document-uploader): Pydantic schemas and API key auth"
```

---

## Task 5: TNA Client Service (with tests)

**Files:**
- Create: `adil-document-uploader/app/services/__init__.py`
- Create: `adil-document-uploader/app/services/tna_client.py`
- Create: `adil-document-uploader/tests/__init__.py`
- Create: `adil-document-uploader/tests/conftest.py`
- Create: `adil-document-uploader/tests/test_tna_client.py`

This is the core TNA Atom API integration. Independent of Tasks 6 and 7 — can run in parallel with them.

- [ ] **Step 1: Write the failing test for Atom feed parsing**

Create `tests/test_tna_client.py`:

```python
import pytest
import httpx
import respx

from app.services.tna_client import TNAClient

SAMPLE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <title>Search results</title>
  <entry>
    <id>https://caselaw.nationalarchives.gov.uk/id/eat/2023/45</id>
    <title>Smith v Employer Ltd</title>
    <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/eat/2023/45"/>
    <updated>2023-06-15T00:00:00Z</updated>
    <summary>[2023] EAT 45</summary>
  </entry>
  <entry>
    <id>https://caselaw.nationalarchives.gov.uk/id/ewca/civ/2022/100</id>
    <title>Jones v Council</title>
    <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/ewca/civ/2022/100"/>
    <updated>2022-03-10T00:00:00Z</updated>
    <summary>[2022] EWCA Civ 100</summary>
  </entry>
</feed>"""


@pytest.fixture
def tna_client():
    return TNAClient(base_url="https://caselaw.nationalarchives.gov.uk", max_rpm=150)


@respx.mock
@pytest.mark.asyncio
async def test_search_returns_entries(tna_client):
    respx.get("https://caselaw.nationalarchives.gov.uk/atom.xml").mock(
        return_value=httpx.Response(200, text=SAMPLE_ATOM_FEED)
    )
    entries = await tna_client.search(query='"religious discrimination"', court="eat")
    assert len(entries) == 2
    assert entries[0].neutral_citation == "[2023] EAT 45"
    assert entries[0].case_name == "Smith v Employer Ltd"
    assert entries[0].tna_uri == "eat/2023/45"


@respx.mock
@pytest.mark.asyncio
async def test_search_follows_pagination(tna_client):
    page1 = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <link rel="next" href="https://caselaw.nationalarchives.gov.uk/atom.xml?query=test&amp;page=2"/>
      <entry>
        <id>https://caselaw.nationalarchives.gov.uk/id/eat/2023/1</id>
        <title>Case One</title>
        <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/eat/2023/1"/>
        <updated>2023-01-01T00:00:00Z</updated>
        <summary>[2023] EAT 1</summary>
      </entry>
    </feed>"""
    page2 = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom">
      <entry>
        <id>https://caselaw.nationalarchives.gov.uk/id/eat/2023/2</id>
        <title>Case Two</title>
        <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/eat/2023/2"/>
        <updated>2023-02-01T00:00:00Z</updated>
        <summary>[2023] EAT 2</summary>
      </entry>
    </feed>"""
    respx.get("https://caselaw.nationalarchives.gov.uk/atom.xml").mock(
        return_value=httpx.Response(200, text=page1)
    )
    respx.get("https://caselaw.nationalarchives.gov.uk/atom.xml", params={"query": "test", "page": "2"}).mock(
        return_value=httpx.Response(200, text=page2)
    )
    entries = await tna_client.search(query="test", court="eat")
    assert len(entries) == 2
    assert entries[1].neutral_citation == "[2023] EAT 2"


@respx.mock
@pytest.mark.asyncio
async def test_download_judgment_xml(tna_client):
    xml_body = "<akomaNtoso>test content</akomaNtoso>"
    respx.get("https://caselaw.nationalarchives.gov.uk/eat/2023/45/data.xml").mock(
        return_value=httpx.Response(200, text=xml_body)
    )
    raw = await tna_client.download_judgment("eat/2023/45")
    assert raw == xml_body
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd adil-document-uploader
pip install -e ".[dev]"
pytest tests/test_tna_client.py -v
```

Expected: ImportError — `app.services.tna_client` does not exist yet.

- [ ] **Step 3: Implement tna_client.py**

Create `app/services/tna_client.py`:

```python
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urljoin, urlparse, parse_qs

import httpx
from lxml import etree

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"


@dataclass
class AtomEntry:
    """A single case law entry from the TNA Atom feed."""

    neutral_citation: str
    case_name: str
    tna_uri: str
    tna_url: str
    updated: str


class TNAClient:
    """Client for The National Archives Case Law Atom API."""

    def __init__(self, base_url: str, max_rpm: int = 150):
        self.base_url = base_url.rstrip("/")
        self._semaphore = asyncio.Semaphore(max_rpm)
        self._client = httpx.AsyncClient(timeout=30.0)

    async def close(self):
        await self._client.aclose()

    async def _get(self, url: str, params: dict | None = None) -> httpx.Response:
        async with self._semaphore:
            resp = await self._client.get(url, params=params)
            resp.raise_for_status()
            return resp

    def _parse_feed(self, xml_text: str) -> tuple[list[AtomEntry], str | None]:
        """Parse an Atom feed, return entries and next page URL (if any)."""
        root = etree.fromstring(xml_text.encode())
        entries: list[AtomEntry] = []

        for entry_el in root.findall(f"{{{ATOM_NS}}}entry"):
            title = entry_el.findtext(f"{{{ATOM_NS}}}title", default="")
            summary = entry_el.findtext(f"{{{ATOM_NS}}}summary", default="")
            link_el = entry_el.find(f'{{{ATOM_NS}}}link[@rel="alternate"]')
            href = link_el.get("href", "") if link_el is not None else ""
            updated = entry_el.findtext(f"{{{ATOM_NS}}}updated", default="")

            # Extract tna_uri from href: https://caselaw.../eat/2023/45 -> eat/2023/45
            parsed = urlparse(href)
            tna_uri = parsed.path.strip("/")

            entries.append(
                AtomEntry(
                    neutral_citation=summary.strip(),
                    case_name=title.strip(),
                    tna_uri=tna_uri,
                    tna_url=href,
                    updated=updated,
                )
            )

        # Check for next page
        next_url = None
        for link_el in root.findall(f"{{{ATOM_NS}}}link"):
            if link_el.get("rel") == "next":
                next_url = link_el.get("href")
                break

        return entries, next_url

    async def search(self, query: str, court: str, max_pages: int = 50) -> list[AtomEntry]:
        """Search TNA for case law matching query and court, following pagination."""
        all_entries: list[AtomEntry] = []
        url = f"{self.base_url}/atom.xml"
        params: dict[str, str] = {"query": query, "court": court}

        for _ in range(max_pages):
            resp = await self._get(url, params=params)
            entries, next_url = self._parse_feed(resp.text)
            all_entries.extend(entries)

            if not next_url:
                break

            # Next page: use the full URL directly
            url = next_url
            params = {}  # params are embedded in next_url

        logger.info("TNA search query=%r court=%s found %d entries", query, court, len(all_entries))
        return all_entries

    async def download_judgment(self, tna_uri: str) -> str:
        """Download the full Akoma Ntoso XML for a judgment."""
        url = f"{self.base_url}/{tna_uri}/data.xml"
        resp = await self._get(url)
        return resp.text
```

Create `app/services/__init__.py` — empty file.

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_tna_client.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/ tests/
git commit -m "feat(document-uploader): TNA Atom API client with search, pagination, download"
```

---

## Task 6: XML Parser Service (with tests)

**Files:**
- Create: `adil-document-uploader/app/services/xml_parser.py`
- Create: `adil-document-uploader/tests/test_xml_parser.py`

Independent of Tasks 5 and 7 — can run in parallel.

- [ ] **Step 1: Write the failing test**

Create `tests/test_xml_parser.py`:

```python
import pytest

from app.services.xml_parser import parse_judgment_xml, JudgmentMetadata

SAMPLE_AKOMANTOSO = """<?xml version="1.0" encoding="UTF-8"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <judgment name="judgment">
    <meta>
      <identification source="#tna">
        <FRBRWork>
          <FRBRdate date="2023-06-15" name="judgment"/>
        </FRBRWork>
      </identification>
    </meta>
    <header>
      <p class="judgment-neutral-citation">[2023] EAT 45</p>
      <p class="case-name">Smith v Employer Ltd</p>
    </header>
    <judgmentBody>
      <section>
        <paragraph>
          <content><p>The appellant appeals against the decision of the Employment Tribunal.</p></content>
        </paragraph>
        <paragraph>
          <content><p>We find that the respondent engaged in direct religious discrimination.</p></content>
        </paragraph>
      </section>
    </judgmentBody>
  </judgment>
</akomaNtoso>"""


def test_parse_extracts_clean_text():
    result = parse_judgment_xml(SAMPLE_AKOMANTOSO)
    assert isinstance(result, JudgmentMetadata)
    assert "appellant appeals" in result.clean_text
    assert "direct religious discrimination" in result.clean_text
    # No XML tags in clean text
    assert "<" not in result.clean_text


def test_parse_extracts_date():
    result = parse_judgment_xml(SAMPLE_AKOMANTOSO)
    assert result.judgment_date == "2023-06-15"


def test_parse_preserves_paragraph_breaks():
    result = parse_judgment_xml(SAMPLE_AKOMANTOSO)
    assert "\n\n" in result.clean_text


def test_parse_handles_missing_date():
    xml_no_date = SAMPLE_AKOMANTOSO.replace(
        '<FRBRdate date="2023-06-15" name="judgment"/>', ""
    )
    result = parse_judgment_xml(xml_no_date)
    assert result.judgment_date is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_xml_parser.py -v
```

Expected: ImportError — `app.services.xml_parser` does not exist yet.

- [ ] **Step 3: Implement xml_parser.py**

Create `app/services/xml_parser.py`:

```python
from __future__ import annotations

from dataclasses import dataclass

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"


@dataclass
class JudgmentMetadata:
    """Extracted metadata and clean text from an Akoma Ntoso judgment."""

    clean_text: str
    judgment_date: str | None


def parse_judgment_xml(xml_text: str) -> JudgmentMetadata:
    """Parse Akoma Ntoso XML and extract clean text + metadata."""
    root = etree.fromstring(xml_text.encode())

    # Extract judgment date
    date_el = root.find(f".//{{{AKN_NS}}}FRBRdate[@name='judgment']")
    judgment_date = date_el.get("date") if date_el is not None else None

    # Extract all text from judgmentBody, preserving paragraph breaks
    body = root.find(f".//{{{AKN_NS}}}judgmentBody")
    if body is None:
        # Some documents use <mainBody> instead
        body = root.find(f".//{{{AKN_NS}}}mainBody")

    paragraphs: list[str] = []
    if body is not None:
        for p_el in body.iter(f"{{{AKN_NS}}}p"):
            text = "".join(p_el.itertext()).strip()
            if text:
                paragraphs.append(text)

    clean_text = "\n\n".join(paragraphs)

    return JudgmentMetadata(clean_text=clean_text, judgment_date=judgment_date)


def build_upload_text(
    neutral_citation: str,
    case_name: str,
    court: str,
    judgment_date: str | None,
    tna_url: str,
    clean_text: str,
) -> str:
    """Build the text document to upload to Gemini FST store with metadata header."""
    date_str = judgment_date or "unknown"
    return f"""CITATION: {neutral_citation}
CASE: {case_name}
COURT: {court}
DATE: {date_str}
SOURCE: {tna_url}
---
{clean_text}"""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_xml_parser.py -v
```

Expected: All 4 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/xml_parser.py tests/test_xml_parser.py
git commit -m "feat(document-uploader): Akoma Ntoso XML parser with metadata extraction"
```

---

## Task 7: Gemini Uploader Service (with tests)

**Files:**
- Create: `adil-document-uploader/app/services/gemini_uploader.py`
- Create: `adil-document-uploader/tests/test_gemini_uploader.py`

Independent of Tasks 5 and 6 — can run in parallel.

- [ ] **Step 1: Write the failing test**

Create `tests/test_gemini_uploader.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.gemini_uploader import GeminiUploader


@pytest.fixture
def mock_genai_client():
    client = MagicMock()
    # Mock the files.upload method
    mock_file = MagicMock()
    mock_file.name = "files/abc123"
    client.files.upload.return_value = mock_file
    return client


@pytest.fixture
def uploader(mock_genai_client):
    return GeminiUploader(
        client=mock_genai_client,
        store_id="fileSearchStores/test-store",
    )


def test_upload_document_returns_file_id(uploader, mock_genai_client):
    file_id = uploader.upload_document(
        text="CITATION: [2023] EAT 45\n---\nJudgment text here",
        display_name="[2023] EAT 45 - Smith v Employer Ltd",
    )
    assert file_id == "files/abc123"
    mock_genai_client.files.upload.assert_called_once()


def test_upload_document_sets_display_name(uploader, mock_genai_client):
    uploader.upload_document(
        text="test content",
        display_name="Test Case",
    )
    call_kwargs = mock_genai_client.files.upload.call_args
    # Verify display_name is passed through
    assert "display_name" in call_kwargs.kwargs or len(call_kwargs.args) > 0


def test_upload_failure_raises(mock_genai_client):
    mock_genai_client.files.upload.side_effect = Exception("API error")
    uploader = GeminiUploader(client=mock_genai_client, store_id="fileSearchStores/test-store")
    with pytest.raises(Exception, match="API error"):
        uploader.upload_document(text="test", display_name="test")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_gemini_uploader.py -v
```

Expected: ImportError — `app.services.gemini_uploader` does not exist yet.

- [ ] **Step 3: Implement gemini_uploader.py**

Create `app/services/gemini_uploader.py`:

```python
from __future__ import annotations

import io
import logging

from google import genai

logger = logging.getLogger(__name__)


class GeminiUploader:
    """Uploads documents to an existing Gemini File Search Tool store."""

    def __init__(self, client: genai.Client, store_id: str):
        self.client = client
        self.store_id = store_id

    def upload_document(self, text: str, display_name: str) -> str:
        """Upload text as a file to the Gemini FST store.

        Returns the Gemini file ID (e.g. 'files/abc123').
        """
        file_bytes = text.encode("utf-8")
        file_obj = io.BytesIO(file_bytes)

        uploaded = self.client.files.upload(
            file=file_obj,
            config=genai.types.UploadFileConfig(
                display_name=display_name,
                mime_type="text/plain",
            ),
        )

        logger.info("Uploaded %s -> %s", display_name, uploaded.name)
        return uploaded.name
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_gemini_uploader.py -v
```

Expected: All 3 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/gemini_uploader.py tests/test_gemini_uploader.py
git commit -m "feat(document-uploader): Gemini FST store uploader service"
```

---

## Task 8: API Endpoints (with tests)

**Files:**
- Create: `adil-document-uploader/app/api/__init__.py`
- Create: `adil-document-uploader/app/api/judgments.py`
- Create: `adil-document-uploader/app/api/admin.py`
- Create: `adil-document-uploader/tests/conftest.py`
- Create: `adil-document-uploader/tests/test_judgments_api.py`

Depends on Tasks 3 and 4 (model + schemas).

- [ ] **Step 1: Create tests/conftest.py with async DB + test client fixtures**

```python
import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.judgment import Base

# Use SQLite for tests
TEST_DB_URL = "sqlite+aiosqlite:///test.db"

engine = create_async_engine(TEST_DB_URL, echo=False)
test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with test_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def client(db):
    os.environ.setdefault("GEMINI_API_KEY", "test")
    os.environ.setdefault("FILE_SEARCH_STORE_ID", "fileSearchStores/test")
    os.environ.setdefault("DATABASE_URL", TEST_DB_URL)
    os.environ.setdefault("ADMIN_API_KEY", "test-key")

    from app.main import app
    from app.database import get_db

    async def override_get_db():
        async with test_session() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    app.dependency_overrides.clear()
```

- [ ] **Step 2: Write failing tests for judgment endpoints**

Create `tests/test_judgments_api.py`:

```python
import pytest
from app.models.judgment import Judgment, JudgmentStatus


@pytest.mark.asyncio
async def test_health(client):
    resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_list_judgments_empty(client):
    resp = await client.get("/api/v1/judgments", headers={"X-Admin-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"] == []
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_judgments_requires_auth(client):
    resp = await client.get("/api/v1/judgments")
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_stats_empty(client):
    resp = await client.get("/api/v1/stats", headers={"X-Admin-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 0


@pytest.mark.asyncio
async def test_list_judgments_with_data(client, db):
    j = Judgment(
        neutral_citation="[2023] EAT 45",
        tna_uri="eat/2023/45",
        tna_url="https://caselaw.nationalarchives.gov.uk/eat/2023/45",
        court="eat",
        case_name="Smith v Employer Ltd",
        search_domain="religious_discrimination_employment",
        search_query='"religious discrimination"',
        raw_xml="<test/>",
        clean_text="Test judgment text",
        status=JudgmentStatus.PENDING,
    )
    db.add(j)
    await db.commit()

    resp = await client.get("/api/v1/judgments", headers={"X-Admin-Key": "test-key"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] == 1
    assert data["items"][0]["neutral_citation"] == "[2023] EAT 45"
```

- [ ] **Step 3: Implement api/judgments.py**

```python
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_admin_key
from app.database import get_db
from app.models.judgment import Judgment, JudgmentStatus
from app.schemas.judgment import JudgmentDetail, JudgmentListResponse, JudgmentResponse

router = APIRouter(prefix="/api/v1/judgments", tags=["judgments"], dependencies=[Depends(require_admin_key)])


@router.get("", response_model=JudgmentListResponse)
async def list_judgments(
    status: JudgmentStatus | None = None,
    domain: str | None = None,
    court: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    query = select(Judgment)
    count_query = select(func.count(Judgment.id))

    if status:
        query = query.where(Judgment.status == status)
        count_query = count_query.where(Judgment.status == status)
    if domain:
        query = query.where(Judgment.search_domain == domain)
        count_query = count_query.where(Judgment.search_domain == domain)
    if court:
        query = query.where(Judgment.court == court)
        count_query = count_query.where(Judgment.court == court)

    total = (await db.execute(count_query)).scalar() or 0
    query = query.order_by(Judgment.fetched_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    items = [JudgmentResponse.model_validate(j) for j in result.scalars().all()]

    return JudgmentListResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{judgment_id}", response_model=JudgmentDetail)
async def get_judgment(judgment_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Judgment).where(Judgment.id == judgment_id))
    judgment = result.scalar_one_or_none()
    if not judgment:
        raise HTTPException(status_code=404, detail="Judgment not found")
    return JudgmentDetail.model_validate(judgment)
```

- [ ] **Step 4: Implement api/admin.py**

```python
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_admin_key
from app.database import get_db
from app.models.judgment import Judgment, JudgmentStatus
from app.schemas.judgment import StatsResponse

router = APIRouter(prefix="/api/v1", tags=["admin"], dependencies=[Depends(require_admin_key)])


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)):
    total = (await db.execute(select(func.count(Judgment.id)))).scalar() or 0

    # By status
    status_rows = await db.execute(
        select(Judgment.status, func.count(Judgment.id)).group_by(Judgment.status)
    )
    by_status = {row[0].value: row[1] for row in status_rows}

    # By domain
    domain_rows = await db.execute(
        select(Judgment.search_domain, func.count(Judgment.id)).group_by(Judgment.search_domain)
    )
    by_domain = {row[0]: row[1] for row in domain_rows}

    # By court
    court_rows = await db.execute(
        select(Judgment.court, func.count(Judgment.id)).group_by(Judgment.court)
    )
    by_court = {row[0]: row[1] for row in court_rows}

    return StatsResponse(total=total, by_status=by_status, by_domain=by_domain, by_court=by_court)
```

Create `app/api/__init__.py` — empty file.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_judgments_api.py -v
```

Expected: All 5 tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/api/ tests/
git commit -m "feat(document-uploader): judgment CRUD endpoints and stats"
```

---

## Task 9: FastAPI App + Health Endpoint

**Files:**
- Create: `adil-document-uploader/app/main.py`

Depends on Task 8 (routers).

- [ ] **Step 1: Create app/main.py**

```python
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin import router as admin_router
from app.api.judgments import router as judgments_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="AskAdil Document Uploader",
    description="Fetches UK case law from TNA and uploads to Gemini FST store",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "adil-document-uploader"}


app.include_router(judgments_router)
app.include_router(admin_router)
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add app/main.py
git commit -m "feat(document-uploader): FastAPI app with health, CORS, router wiring"
```

---

## Task 10: Worker Tasks (fetch + upload)

**Files:**
- Create: `adil-document-uploader/app/workers/__init__.py`
- Create: `adil-document-uploader/app/workers/tasks.py`
- Create: `adil-document-uploader/app/workers/settings.py`
- Create: `adil-document-uploader/tests/test_workers.py`

Depends on Tasks 5, 6, 7 (all three services).

- [ ] **Step 1: Write failing test for fetch task**

Create `tests/test_workers.py`:

```python
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.judgment import Base, Judgment, JudgmentStatus
from app.services.tna_client import AtomEntry

TEST_DB_URL = "sqlite+aiosqlite:///test_workers.db"
engine = create_async_engine(TEST_DB_URL, echo=False)
test_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest_asyncio.fixture
async def db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with test_session() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_fetch_stores_new_judgments(db):
    from app.workers.tasks import _fetch_for_domain
    from app.config import SearchDomain

    domain = SearchDomain(
        name="test_domain",
        queries=['"test query"'],
        courts=["eat"],
    )

    mock_tna = AsyncMock()
    mock_tna.search.return_value = [
        AtomEntry(
            neutral_citation="[2023] EAT 99",
            case_name="Test v Case",
            tna_uri="eat/2023/99",
            tna_url="https://caselaw.nationalarchives.gov.uk/eat/2023/99",
            updated="2023-06-15T00:00:00Z",
        )
    ]
    mock_tna.download_judgment.return_value = """<?xml version="1.0"?>
<akomaNtoso xmlns="http://docs.oasis-open.org/legaldocml/ns/akn/3.0">
  <judgment><meta><identification source="#tna">
    <FRBRWork><FRBRdate date="2023-06-15" name="judgment"/></FRBRWork>
  </identification></meta>
  <judgmentBody><section><paragraph><content><p>Test judgment body.</p></content></paragraph></section></judgmentBody>
  </judgment>
</akomaNtoso>"""

    new_count, skip_count = await _fetch_for_domain(
        tna_client=mock_tna, domain=domain, session_factory=test_session
    )

    assert new_count == 1
    assert skip_count == 0

    async with test_session() as session:
        result = await session.execute(select(Judgment))
        judgments = result.scalars().all()
        assert len(judgments) == 1
        assert judgments[0].neutral_citation == "[2023] EAT 99"
        assert judgments[0].status == JudgmentStatus.PENDING


@pytest.mark.asyncio
async def test_fetch_skips_duplicates(db):
    from app.workers.tasks import _fetch_for_domain
    from app.config import SearchDomain

    # Pre-insert a judgment
    async with test_session() as session:
        j = Judgment(
            neutral_citation="[2023] EAT 99",
            tna_uri="eat/2023/99",
            tna_url="https://caselaw.nationalarchives.gov.uk/eat/2023/99",
            court="eat",
            case_name="Test v Case",
            search_domain="test_domain",
            search_query='"test query"',
            raw_xml="<test/>",
            clean_text="Existing",
            status=JudgmentStatus.UPLOADED,
        )
        session.add(j)
        await session.commit()

    domain = SearchDomain(name="test_domain", queries=['"test query"'], courts=["eat"])

    mock_tna = AsyncMock()
    mock_tna.search.return_value = [
        AtomEntry(
            neutral_citation="[2023] EAT 99",
            case_name="Test v Case",
            tna_uri="eat/2023/99",
            tna_url="https://caselaw.nationalarchives.gov.uk/eat/2023/99",
            updated="2023-06-15T00:00:00Z",
        )
    ]

    new_count, skip_count = await _fetch_for_domain(
        tna_client=mock_tna, domain=domain, session_factory=test_session
    )

    assert new_count == 0
    assert skip_count == 1
    mock_tna.download_judgment.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_workers.py -v
```

Expected: ImportError — `app.workers.tasks` does not exist yet.

- [ ] **Step 3: Implement workers/tasks.py**

```python
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.config import SEARCH_DOMAINS, SearchDomain, get_settings
from app.models.judgment import Judgment, JudgmentStatus
from app.services.gemini_uploader import GeminiUploader
from app.services.tna_client import TNAClient
from app.services.xml_parser import build_upload_text, parse_judgment_xml

logger = logging.getLogger(__name__)


async def _fetch_for_domain(
    tna_client: TNAClient,
    domain: SearchDomain,
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[int, int]:
    """Fetch case law for a single search domain. Returns (new_count, skip_count)."""
    new_count = 0
    skip_count = 0

    for query in domain.queries:
        for court in domain.courts:
            entries = await tna_client.search(query=query, court=court)

            for entry in entries:
                async with session_factory() as session:
                    exists = await session.execute(
                        select(Judgment.id).where(Judgment.neutral_citation == entry.neutral_citation)
                    )
                    if exists.scalar_one_or_none() is not None:
                        skip_count += 1
                        continue

                try:
                    raw_xml = await tna_client.download_judgment(entry.tna_uri)
                    parsed = parse_judgment_xml(raw_xml)

                    judgment = Judgment(
                        neutral_citation=entry.neutral_citation,
                        tna_uri=entry.tna_uri,
                        tna_url=entry.tna_url,
                        court=court,
                        case_name=entry.case_name,
                        judgment_date=date.fromisoformat(parsed.judgment_date) if parsed.judgment_date else None,
                        search_domain=domain.name,
                        search_query=query,
                        raw_xml=raw_xml,
                        clean_text=parsed.clean_text,
                        status=JudgmentStatus.PENDING,
                    )

                    async with session_factory() as session:
                        session.add(judgment)
                        await session.commit()
                    new_count += 1

                except Exception:
                    logger.exception("Failed to fetch/parse %s", entry.neutral_citation)

    return new_count, skip_count


async def fetch_case_law(ctx: dict) -> dict:
    """arq task: fetch case law from TNA for all search domains."""
    settings = get_settings()
    tna_client = TNAClient(base_url=settings.tna_base_url, max_rpm=settings.tna_max_requests_per_minute)

    from app.database import async_session

    total_new = 0
    total_skip = 0

    try:
        for domain in SEARCH_DOMAINS:
            new, skip = await _fetch_for_domain(tna_client, domain, async_session)
            total_new += new
            total_skip += skip
            logger.info("Domain %s: %d new, %d skipped", domain.name, new, skip)
    finally:
        await tna_client.close()

    logger.info("Fetch complete: %d new judgments, %d duplicates skipped", total_new, total_skip)
    return {"new": total_new, "skipped": total_skip}


async def upload_pending(ctx: dict) -> dict:
    """arq task: upload pending judgments to Gemini FST store."""
    settings = get_settings()

    from google import genai
    from app.database import async_session

    client = genai.Client(api_key=settings.gemini_api_key)
    uploader = GeminiUploader(client=client, store_id=settings.file_search_store_id)

    uploaded = 0
    failed = 0

    async with async_session() as session:
        result = await session.execute(
            select(Judgment).where(Judgment.status == JudgmentStatus.PENDING)
        )
        judgments = result.scalars().all()

    for judgment in judgments:
        try:
            text = build_upload_text(
                neutral_citation=judgment.neutral_citation,
                case_name=judgment.case_name,
                court=judgment.court,
                judgment_date=str(judgment.judgment_date) if judgment.judgment_date else None,
                tna_url=judgment.tna_url,
                clean_text=judgment.clean_text,
            )
            display_name = f"{judgment.neutral_citation} - {judgment.case_name}"
            file_id = uploader.upload_document(text=text, display_name=display_name)

            async with async_session() as session:
                judgment.gemini_file_id = file_id
                judgment.status = JudgmentStatus.UPLOADED
                judgment.uploaded_at = datetime.now(timezone.utc)
                judgment.error_message = None
                session.add(judgment)
                await session.merge(judgment)
                await session.commit()
            uploaded += 1

        except Exception as exc:
            logger.exception("Failed to upload %s", judgment.neutral_citation)
            async with async_session() as session:
                judgment.status = JudgmentStatus.FAILED
                judgment.error_message = str(exc)
                await session.merge(judgment)
                await session.commit()
            failed += 1

    logger.info("Upload complete: %d uploaded, %d failed", uploaded, failed)
    return {"uploaded": uploaded, "failed": failed}
```

- [ ] **Step 4: Implement workers/settings.py**

```python
from arq.cron import cron

from app.workers.tasks import fetch_case_law, upload_pending
from app.config import get_settings


class WorkerSettings:
    functions = [fetch_case_law, upload_pending]

    cron_jobs = [
        cron(fetch_case_law, hour=3, minute=0),   # Daily at 03:00 UTC
        cron(upload_pending, hour=3, minute=30),   # Daily at 03:30 UTC
    ]

    @staticmethod
    def redis_settings():
        from arq.connections import RedisSettings
        settings = get_settings()
        return RedisSettings.from_dsn(settings.redis_url)
```

Create `app/workers/__init__.py` — empty file.

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_workers.py -v
```

Expected: Both tests PASS.

- [ ] **Step 6: Commit**

```bash
git add app/workers/ tests/test_workers.py
git commit -m "feat(document-uploader): arq worker tasks for fetch + upload cycles"
```

---

## Task 11: Admin Trigger Endpoints (POST /fetch, POST /upload)

**Files:**
- Modify: `adil-document-uploader/app/api/admin.py`

Depends on Task 10 (worker tasks).

- [ ] **Step 1: Add trigger endpoints to admin.py**

Append to `app/api/admin.py`:

```python
from app.workers.tasks import fetch_case_law, upload_pending
from app.schemas.judgment import FetchResponse, UploadResponse


@router.post("/fetch", response_model=FetchResponse)
async def trigger_fetch():
    """Manually trigger a fetch cycle (runs synchronously in request)."""
    result = await fetch_case_law(ctx={})
    return FetchResponse(
        message="Fetch cycle complete",
        new_judgments=result["new"],
        skipped_duplicates=result["skipped"],
    )


@router.post("/upload", response_model=UploadResponse)
async def trigger_upload():
    """Manually trigger upload of pending judgments."""
    result = await upload_pending(ctx={})
    return UploadResponse(
        message="Upload cycle complete",
        uploaded=result["uploaded"],
        failed=result["failed"],
    )
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add app/api/admin.py
git commit -m "feat(document-uploader): manual fetch/upload trigger endpoints"
```

---

## Task 12: README + Final Verification

**Files:**
- Create: `adil-document-uploader/README.md`

- [ ] **Step 1: Create README.md**

```markdown
# adil-document-uploader

Case law fetcher and Gemini File Search Tool store uploader for AskAdil.

Fetches UK discrimination/equality case law from The National Archives (TNA) Case Law API, deduplicates against Postgres, and uploads judgment text to the existing Gemini FST store — expanding AskAdil's legal knowledge base.

## Quick Start

```bash
# Copy env and fill in values
cp .env.example .env

# Start services
docker-compose up -d

# Run migrations
alembic upgrade head

# Manual fetch (downloads case law from TNA)
curl -X POST http://localhost:8002/api/v1/fetch -H "X-Admin-Key: $ADMIN_API_KEY"

# Manual upload (pushes pending judgments to Gemini store)
curl -X POST http://localhost:8002/api/v1/upload -H "X-Admin-Key: $ADMIN_API_KEY"

# Check stats
curl http://localhost:8002/api/v1/stats -H "X-Admin-Key: $ADMIN_API_KEY"
```

## Architecture

- **API** (FastAPI) — admin endpoints for manual triggers and judgment browsing
- **Worker** (arq) — scheduled daily fetch at 03:00 UTC + upload at 03:30 UTC
- **Postgres** — judgment storage, deduplication on neutral_citation
- **Redis** — arq job queue

## Railway Deployment

Two services from the same Dockerfile:
- API service: `SERVICE_ROLE=api` (default)
- Worker service: `SERVICE_ROLE=worker`

## Search Domains

Five predefined legal domains targeting AskAdil's core areas:
1. Religious discrimination (employment)
2. Hate crime / religious hatred
3. Goods & services discrimination
4. Intersectional (race + religion)
5. ECHR / human rights

## Environment Variables

See `.env.example` for all required variables.
```

- [ ] **Step 2: Run full test suite + lint**

```bash
cd adil-document-uploader
pytest tests/ -v
ruff check .
ruff format --check .
```

Expected: All tests PASS, no lint errors.

- [ ] **Step 3: Final commit**

```bash
git add README.md
git commit -m "docs(document-uploader): add README with quickstart and architecture"
```

---

## Parallel Execution Map

Tasks that can run in parallel (for subagent dispatch):

```
Task 1 (scaffold)
  └─> Task 2 (config + DB + alembic)
        └─> Task 3 (model + migration)
              └─> Task 4 (schemas + auth)
                    ├─> Task 5 (TNA client)      ← PARALLEL
                    ├─> Task 6 (XML parser)       ← PARALLEL
                    └─> Task 7 (Gemini uploader)  ← PARALLEL
                          └─> Task 8 (API endpoints)
                                └─> Task 9 (FastAPI app)
                                      └─> Task 10 (worker tasks)
                                            └─> Task 11 (admin triggers)
                                                  └─> Task 12 (README + verify)
```
