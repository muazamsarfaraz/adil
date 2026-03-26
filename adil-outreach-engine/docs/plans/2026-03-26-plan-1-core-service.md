# Plan 1: Core Service & Campaign CRUD

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Scaffold the adil-outreach-engine FastAPI service with database models, campaign/contact CRUD endpoints, API key auth, and health check.

**Architecture:** Independent FastAPI microservice with SQLAlchemy async ORM on PostgreSQL. Pydantic v2 schemas for request/response validation. Alembic for migrations. API key auth for internal endpoints.

**Tech Stack:** FastAPI, SQLAlchemy (async), asyncpg, Pydantic v2, Alembic, PostgreSQL

---

## Task 1: Project Scaffold

**Create:**
- `pyproject.toml`
- `app/__init__.py`
- `app/main.py`
- `app/config.py`
- `Dockerfile`
- `docker-compose.yml`
- `.env.example`
- `.gitignore`

### Steps

- [ ] **1.1** Create `pyproject.toml`

```toml
[project]
name = "adil-outreach-engine"
version = "0.1.0"
description = "AI-powered outreach and conversion platform"
requires-python = ">=3.12"
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
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.0",
    "pytest-asyncio>=0.25.0",
    "httpx>=0.28.0",
    "aiosqlite>=0.20.0",
    "ruff>=0.8.0",
]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
target-version = "py312"
line-length = 120
```

- [ ] **1.2** Create `app/__init__.py`

```python
```

- [ ] **1.3** Create `app/config.py`

```python
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    app_name: str = "adil-outreach-engine"
    app_version: str = "0.1.0"
    debug: bool = False

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/outreach"

    # Auth
    api_key: str = "change-me-in-production"

    # Server
    host: str = "0.0.0.0"
    port: int = 8000

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
```

- [ ] **1.4** Create `app/main.py`

```python
from fastapi import FastAPI

from app.config import settings

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": settings.app_version}
```

- [ ] **1.5** Create `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
RUN pip install --no-cache-dir .

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **1.6** Create `docker-compose.yml`

```yaml
services:
  db:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: outreach
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    ports:
      - "5433:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  api:
    build: .
    ports:
      - "8001:8000"
    environment:
      DATABASE_URL: postgresql+asyncpg://postgres:postgres@db:5432/outreach
      API_KEY: dev-api-key-change-me
    depends_on:
      db:
        condition: service_healthy
    volumes:
      - .:/app

volumes:
  pgdata:
```

- [ ] **1.7** Create `.env.example`

```env
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5433/outreach
API_KEY=dev-api-key-change-me
DEBUG=true
```

- [ ] **1.8** Create `.gitignore`

```gitignore
__pycache__/
*.py[cod]
*$py.class
.env
.venv/
venv/
*.egg-info/
dist/
build/
.pytest_cache/
.ruff_cache/
```

- [ ] **1.9** Verify scaffold

```bash
cd adil-outreach-engine
pip install -e ".[dev]"
uvicorn app.main:app --host 0.0.0.0 --port 8001 &
sleep 2
curl http://localhost:8001/
# Expected: {"service":"adil-outreach-engine","version":"0.1.0"}
kill %1
```

- [ ] **1.10** Commit

```bash
git init
git add -A
git commit -m "feat: project scaffold with FastAPI, config, Docker setup"
```

---

## Task 2: Database Setup

**Create:**
- `app/database.py`
- `app/models/__init__.py`
- `alembic.ini`
- `alembic/env.py`
- `alembic/script.py.mako`
- `alembic/versions/` (directory)

### Steps

- [ ] **2.1** Create `app/database.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

engine = create_async_engine(settings.database_url, echo=settings.debug)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()
```

- [ ] **2.2** Create `app/models/__init__.py`

```python
from app.models.campaign import Campaign
from app.models.contact import Contact
from app.models.outreach_event import OutreachEvent
from app.models.conversion import Conversion
from app.models.agent_checkpoint import AgentCheckpoint

__all__ = ["Campaign", "Contact", "OutreachEvent", "Conversion", "AgentCheckpoint"]
```

> Note: This file will cause import errors until all model files exist. Create it now but verify after Task 7.

- [ ] **2.3** Initialise Alembic

```bash
cd adil-outreach-engine
alembic init alembic
```

- [ ] **2.4** Update `alembic.ini` — set `sqlalchemy.url` to empty (we override in env.py)

Replace the `sqlalchemy.url` line:

```ini
sqlalchemy.url =
```

- [ ] **2.5** Update `alembic/env.py`

```python
import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import settings
from app.database import Base

# Import all models so they register with Base.metadata
from app.models import *  # noqa: F401, F403

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    connectable = create_async_engine(settings.database_url)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **2.6** Verify Alembic can see config (will fail on model imports until Task 3-7, that is expected)

```bash
alembic --help
# Expected: Alembic help output without import errors
```

- [ ] **2.7** Commit

```bash
git add -A
git commit -m "feat: async database setup with SQLAlchemy and Alembic"
```

---

## Task 3: Campaign Model + Migration

**Create:**
- `app/models/campaign.py`

### Steps

- [ ] **3.1** Create `app/models/campaign.py`

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CampaignGoal(str, enum.Enum):
    signup = "signup"
    booking = "booking"
    payment = "payment"
    custom = "custom"


class CampaignStatus(str, enum.Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    completed = "completed"


class Campaign(Base):
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    slug: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    goal: Mapped[CampaignGoal] = mapped_column(Enum(CampaignGoal, name="campaign_goal"), nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        Enum(CampaignStatus, name="campaign_status"), nullable=False, default=CampaignStatus.draft
    )
    templates: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    cadence: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    llm_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    research_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    compose_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    classify_instructions: Mapped[str | None] = mapped_column(Text, nullable=True)
    conversion_config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    auto_send: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sender_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    sender_email: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_to: Mapped[str | None] = mapped_column(Text, nullable=True)
    success_criteria: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=datetime.utcnow
    )

    # Relationships
    contacts = relationship("Contact", back_populates="campaign", cascade="all, delete-orphan")
```

- [ ] **3.2** Generate migration

```bash
alembic revision --autogenerate -m "create campaigns table"
```

- [ ] **3.3** Run migration

```bash
alembic upgrade head
```

- [ ] **3.4** Verify table exists

```bash
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d outreach -c "\d campaigns"
# Expected: Table with all columns listed
```

- [ ] **3.5** Commit

```bash
git add -A
git commit -m "feat: campaign model with migration"
```

---

## Task 4: Contact Model + Migration

**Create:**
- `app/models/contact.py`

### Steps

- [ ] **4.1** Create `app/models/contact.py`

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Index, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ContactStatus(str, enum.Enum):
    pending = "pending"
    researching = "researching"
    ready = "ready"
    draft_pending = "draft_pending"
    emailed = "emailed"
    replied = "replied"
    converted = "converted"
    declined = "declined"
    unresponsive = "unresponsive"
    bounced = "bounced"


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("campaigns.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    email: Mapped[str] = mapped_column(Text, nullable=False)
    phone: Mapped[str | None] = mapped_column(Text, nullable=True)
    firm_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    research_data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[ContactStatus] = mapped_column(
        Enum(ContactStatus, name="contact_status"), nullable=False, default=ContactStatus.pending
    )
    current_cadence_step: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consent: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=datetime.utcnow
    )

    # Relationships
    campaign = relationship("Campaign", back_populates="contacts")
    events = relationship("OutreachEvent", back_populates="contact", cascade="all, delete-orphan")
    conversion = relationship("Conversion", back_populates="contact", uselist=False, cascade="all, delete-orphan")
    checkpoints = relationship("AgentCheckpoint", back_populates="contact", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_contacts_campaign_status", "campaign_id", "status"),
    )
```

- [ ] **4.2** Generate migration

```bash
alembic revision --autogenerate -m "create contacts table"
```

- [ ] **4.3** Run migration

```bash
alembic upgrade head
```

- [ ] **4.4** Verify table and index

```bash
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d outreach -c "\d contacts"
PGPASSWORD=postgres psql -h localhost -p 5433 -U postgres -d outreach -c "\di ix_contacts_campaign_status"
```

- [ ] **4.5** Commit

```bash
git add -A
git commit -m "feat: contact model with campaign FK and composite index"
```

---

## Task 5: OutreachEvent Model + Migration

**Create:**
- `app/models/outreach_event.py`

### Steps

- [ ] **5.1** Create `app/models/outreach_event.py`

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class EventType(str, enum.Enum):
    email_sent = "email_sent"
    email_opened = "email_opened"
    email_clicked = "email_clicked"
    reply_received = "reply_received"
    reply_classified = "reply_classified"
    follow_up_sent = "follow_up_sent"
    draft_created = "draft_created"
    draft_approved = "draft_approved"
    signup_completed = "signup_completed"
    booking_made = "booking_made"
    payment_received = "payment_received"
    manually_updated = "manually_updated"


class EventChannel(str, enum.Enum):
    email = "email"
    webhook = "webhook"
    manual = "manual"
    system = "system"


class OutreachEvent(Base):
    __tablename__ = "outreach_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[EventType] = mapped_column(Enum(EventType, name="event_type"), nullable=False)
    channel: Mapped[EventChannel] = mapped_column(Enum(EventChannel, name="event_channel"), nullable=False)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    contact = relationship("Contact", back_populates="events")

    __table_args__ = (
        Index("ix_outreach_events_contact_created", "contact_id", "created_at"),
    )
```

- [ ] **5.2** Generate migration

```bash
alembic revision --autogenerate -m "create outreach_events table"
```

- [ ] **5.3** Run migration

```bash
alembic upgrade head
```

- [ ] **5.4** Commit

```bash
git add -A
git commit -m "feat: outreach event model with timeline index"
```

---

## Task 6: Conversion Model + Migration

**Create:**
- `app/models/conversion.py`

### Steps

- [ ] **6.1** Create `app/models/conversion.py`

```python
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ConversionType(str, enum.Enum):
    signup = "signup"
    booking = "booking"
    payment = "payment"


class Conversion(Base):
    __tablename__ = "conversions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    type: Mapped[ConversionType] = mapped_column(Enum(ConversionType, name="conversion_type"), nullable=False)
    data: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )

    # Relationships
    contact = relationship("Contact", back_populates="conversion")
```

- [ ] **6.2** Generate migration

```bash
alembic revision --autogenerate -m "create conversions table"
```

- [ ] **6.3** Run migration

```bash
alembic upgrade head
```

- [ ] **6.4** Commit

```bash
git add -A
git commit -m "feat: conversion model with unique contact constraint"
```

---

## Task 7: AgentCheckpoint Model + Migration

**Create:**
- `app/models/agent_checkpoint.py`

### Steps

- [ ] **7.1** Create `app/models/agent_checkpoint.py`

```python
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class AgentCheckpoint(Base):
    __tablename__ = "agent_checkpoints"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    contact_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("contacts.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    graph_name: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    current_node: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()"), onupdate=datetime.utcnow
    )

    # Relationships
    contact = relationship("Contact", back_populates="checkpoints")

    __table_args__ = (
        Index(
            "ix_agent_checkpoints_contact_active",
            "contact_id",
            "is_active",
            unique=True,
            postgresql_where=text("is_active = true"),
        ),
    )
```

- [ ] **7.2** Generate migration

```bash
alembic revision --autogenerate -m "create agent_checkpoints table"
```

- [ ] **7.3** Run migration

```bash
alembic upgrade head
```

- [ ] **7.4** Verify all models import cleanly

```bash
python -c "from app.models import Campaign, Contact, OutreachEvent, Conversion, AgentCheckpoint; print('All models imported OK')"
# Expected: All models imported OK
```

- [ ] **7.5** Commit

```bash
git add -A
git commit -m "feat: agent checkpoint model with partial unique index"
```

---

## Task 8: Pydantic Schemas

**Create:**
- `app/schemas/__init__.py`
- `app/schemas/campaign.py`
- `app/schemas/contact.py`
- `app/schemas/event.py`
- `app/schemas/conversion.py`
- `app/schemas/stats.py`

### Steps

- [ ] **8.1** Create `app/schemas/__init__.py`

```python
```

- [ ] **8.2** Create `app/schemas/campaign.py`

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.campaign import CampaignGoal, CampaignStatus


class CampaignCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    slug: str = Field(..., min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    goal: CampaignGoal
    templates: dict | None = None
    cadence: list | None = None
    llm_config: dict | None = None
    research_instructions: str | None = None
    compose_instructions: str | None = None
    classify_instructions: str | None = None
    conversion_config: dict | None = None
    auto_send: bool = False
    sender_name: str | None = None
    sender_email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    reply_to: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    success_criteria: dict | None = None


class CampaignUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    slug: str | None = Field(None, min_length=1, max_length=200, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    goal: CampaignGoal | None = None
    templates: dict | None = None
    cadence: list | None = None
    llm_config: dict | None = None
    research_instructions: str | None = None
    compose_instructions: str | None = None
    classify_instructions: str | None = None
    conversion_config: dict | None = None
    auto_send: bool | None = None
    sender_name: str | None = None
    sender_email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    reply_to: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    success_criteria: dict | None = None


class CampaignResponse(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    goal: CampaignGoal
    status: CampaignStatus
    templates: dict | None
    cadence: list | None
    llm_config: dict | None
    research_instructions: str | None
    compose_instructions: str | None
    classify_instructions: str | None
    conversion_config: dict | None
    auto_send: bool
    sender_name: str | None
    sender_email: str | None
    reply_to: str | None
    success_criteria: dict | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CampaignWithStats(CampaignResponse):
    stats: "CampaignStats"


# Import here to avoid circular imports
from app.schemas.stats import CampaignStats  # noqa: E402

CampaignWithStats.model_rebuild()


class CampaignListResponse(BaseModel):
    items: list[CampaignResponse]
    total: int
    limit: int
    offset: int
```

- [ ] **8.3** Create `app/schemas/contact.py`

```python
import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.models.contact import ContactStatus


class ContactCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: str | None = None
    firm_name: str | None = None
    website: str | None = None
    metadata: dict | None = None


class ContactBulkCreate(BaseModel):
    contacts: list[ContactCreate] = Field(..., min_length=1, max_length=1000)


class ContactUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=500)
    email: str | None = Field(None, pattern=r"^[^@]+@[^@]+\.[^@]+$")
    phone: str | None = None
    firm_name: str | None = None
    website: str | None = None
    metadata: dict | None = None
    status: ContactStatus | None = None
    consent: bool | None = None


class ContactResponse(BaseModel):
    id: uuid.UUID
    campaign_id: uuid.UUID
    name: str
    email: str
    phone: str | None
    firm_name: str | None
    website: str | None
    metadata: dict | None
    research_data: dict | None
    status: ContactStatus
    current_cadence_step: int
    consent: bool | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactDetailResponse(ContactResponse):
    events: list["EventResponse"] = []

    model_config = {"from_attributes": True}


# Import here to avoid circular imports
from app.schemas.event import EventResponse  # noqa: E402

ContactDetailResponse.model_rebuild()


class ContactListResponse(BaseModel):
    items: list[ContactResponse]
    total: int
    limit: int
    offset: int


class BulkCreateResponse(BaseModel):
    created: int
    errors: list[dict] = []
```

- [ ] **8.4** Create `app/schemas/event.py`

```python
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.outreach_event import EventChannel, EventType


class EventResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    event_type: EventType
    channel: EventChannel
    subject: str | None
    content: str | None
    metadata: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **8.5** Create `app/schemas/conversion.py`

```python
import uuid
from datetime import datetime

from pydantic import BaseModel

from app.models.conversion import ConversionType


class ConversionResponse(BaseModel):
    id: uuid.UUID
    contact_id: uuid.UUID
    type: ConversionType
    data: dict | None
    created_at: datetime

    model_config = {"from_attributes": True}
```

- [ ] **8.6** Create `app/schemas/stats.py`

```python
from pydantic import BaseModel


class CampaignStats(BaseModel):
    total_contacts: int = 0
    pending: int = 0
    researching: int = 0
    ready: int = 0
    draft_pending: int = 0
    emailed: int = 0
    replied: int = 0
    converted: int = 0
    declined: int = 0
    unresponsive: int = 0
    bounced: int = 0
    open_rate: float = 0.0
    reply_rate: float = 0.0
    conversion_rate: float = 0.0
```

- [ ] **8.7** Verify schemas import cleanly

```bash
python -c "from app.schemas.campaign import CampaignCreate, CampaignResponse, CampaignWithStats; from app.schemas.contact import ContactCreate, ContactResponse; from app.schemas.stats import CampaignStats; print('All schemas OK')"
# Expected: All schemas OK
```

- [ ] **8.8** Commit

```bash
git add -A
git commit -m "feat: Pydantic v2 schemas for campaign, contact, event, conversion, stats"
```

---

## Task 9: API Key Auth Middleware

**Create:**
- `app/auth/__init__.py`
- `app/auth/api_key.py`
- `tests/test_auth.py`

### Steps

- [ ] **9.1** Write test first: Create `tests/__init__.py` and `tests/conftest.py`

```python
# tests/__init__.py
```

```python
# tests/conftest.py
import asyncio
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.database import Base, get_db
from app.main import app

# Use SQLite for tests
TEST_DATABASE_URL = "sqlite+aiosqlite:///./test.db"

engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestingSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_database():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestingSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db


@pytest.fixture
async def client() -> AsyncGenerator[AsyncClient, None]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
def auth_headers() -> dict:
    return {"X-API-Key": settings.api_key}
```

- [ ] **9.2** Write test: Create `tests/test_auth.py`

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_missing_api_key_returns_401(client: AsyncClient):
    response = await client.get("/api/v1/outreach/campaigns")
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing X-API-Key header"


@pytest.mark.asyncio
async def test_invalid_api_key_returns_403(client: AsyncClient):
    response = await client.get(
        "/api/v1/outreach/campaigns",
        headers={"X-API-Key": "wrong-key"},
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid API key"


@pytest.mark.asyncio
async def test_valid_api_key_passes(client: AsyncClient, auth_headers: dict):
    response = await client.get("/api/v1/outreach/campaigns", headers=auth_headers)
    assert response.status_code == 200
```

- [ ] **9.3** Run test (should fail — endpoint and auth not yet created)

```bash
pytest tests/test_auth.py -v
# Expected: FAILED (no route, no auth)
```

- [ ] **9.4** Create `app/auth/__init__.py`

```python
```

- [ ] **9.5** Create `app/auth/api_key.py`

```python
from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.config import settings

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def require_api_key(api_key: str | None = Security(api_key_header)) -> str:
    if api_key is None:
        raise HTTPException(status_code=401, detail="Missing X-API-Key header")
    if api_key != settings.api_key:
        raise HTTPException(status_code=403, detail="Invalid API key")
    return api_key
```

- [ ] **9.6** Run auth tests again (will pass once campaign endpoints exist in Task 10; skip for now, revisit after Task 10)

- [ ] **9.7** Commit

```bash
git add -A
git commit -m "feat: API key auth dependency with tests"
```

---

## Task 10: Campaign CRUD Endpoints

**Create:**
- `app/api/__init__.py`
- `app/api/campaigns.py`
- `tests/test_campaigns.py`

**Modify:**
- `app/main.py` (register router)

### Steps

- [ ] **10.1** Write test first: Create `tests/test_campaigns.py`

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_create_campaign(client: AsyncClient, auth_headers: dict):
    payload = {
        "name": "Test Campaign",
        "slug": "test-campaign",
        "goal": "signup",
        "auto_send": False,
        "sender_name": "Test Sender",
        "sender_email": "test@example.com",
        "reply_to": "reply@example.com",
    }
    response = await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Campaign"
    assert data["slug"] == "test-campaign"
    assert data["goal"] == "signup"
    assert data["status"] == "draft"
    assert "id" in data


@pytest.mark.asyncio
async def test_create_campaign_duplicate_slug(client: AsyncClient, auth_headers: dict):
    payload = {
        "name": "Campaign A",
        "slug": "duplicate-slug",
        "goal": "signup",
    }
    await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    response = await client.post("/api/v1/outreach/campaigns", json=payload, headers=auth_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_list_campaigns(client: AsyncClient, auth_headers: dict):
    # Create two campaigns
    for i in range(2):
        await client.post(
            "/api/v1/outreach/campaigns",
            json={"name": f"List Campaign {i}", "slug": f"list-camp-{i}", "goal": "signup"},
            headers=auth_headers,
        )
    response = await client.get("/api/v1/outreach/campaigns", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data
    assert data["total"] >= 2


@pytest.mark.asyncio
async def test_list_campaigns_filter_status(client: AsyncClient, auth_headers: dict):
    await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Filter Campaign", "slug": "filter-camp", "goal": "signup"},
        headers=auth_headers,
    )
    response = await client.get("/api/v1/outreach/campaigns?status=draft", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert all(item["status"] == "draft" for item in data["items"])


@pytest.mark.asyncio
async def test_get_campaign_detail(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Detail Campaign", "slug": "detail-camp", "goal": "booking"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == campaign_id
    assert "stats" in data


@pytest.mark.asyncio
async def test_get_campaign_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/outreach/campaigns/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Update Campaign", "slug": "update-camp", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.patch(
        f"/api/v1/outreach/campaigns/{campaign_id}",
        json={"name": "Updated Name", "auto_send": True},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    assert response.json()["auto_send"] is True


@pytest.mark.asyncio
async def test_delete_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Delete Campaign", "slug": "delete-camp", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.delete(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert response.status_code == 204

    # Verify it's gone (soft delete — should return 404 or status=deleted)
    get_resp = await client.get(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_launch_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Launch Campaign", "slug": "launch-camp", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/launch", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "active"


@pytest.mark.asyncio
async def test_launch_already_active_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Already Active", "slug": "already-active", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/launch", headers=auth_headers)
    response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/launch", headers=auth_headers)
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_pause_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Pause Campaign", "slug": "pause-camp", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    # Launch first
    await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/launch", headers=auth_headers)
    # Then pause
    response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/pause", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "paused"


@pytest.mark.asyncio
async def test_pause_non_active_campaign(client: AsyncClient, auth_headers: dict):
    create_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Pause Draft", "slug": "pause-draft", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = create_resp.json()["id"]
    response = await client.post(f"/api/v1/outreach/campaigns/{campaign_id}/pause", headers=auth_headers)
    assert response.status_code == 409
```

- [ ] **10.2** Run tests (should fail)

```bash
pytest tests/test_campaigns.py -v
# Expected: FAILED (no routes)
```

- [ ] **10.3** Create `app/api/__init__.py`

```python
```

- [ ] **10.4** Create `app/api/campaigns.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.api_key import require_api_key
from app.database import get_db
from app.models.campaign import Campaign, CampaignStatus
from app.models.contact import Contact, ContactStatus
from app.models.outreach_event import EventType, OutreachEvent
from app.schemas.campaign import (
    CampaignCreate,
    CampaignListResponse,
    CampaignResponse,
    CampaignUpdate,
    CampaignWithStats,
)
from app.schemas.stats import CampaignStats

router = APIRouter(prefix="/api/v1/outreach/campaigns", tags=["campaigns"], dependencies=[Depends(require_api_key)])


@router.post("", response_model=CampaignResponse, status_code=201)
async def create_campaign(payload: CampaignCreate, db: AsyncSession = Depends(get_db)):
    campaign = Campaign(**payload.model_dump())
    db.add(campaign)
    try:
        await db.commit()
        await db.refresh(campaign)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Campaign with slug '{payload.slug}' already exists")
    return campaign


@router.get("", response_model=CampaignListResponse)
async def list_campaigns(
    status: CampaignStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Campaign)
    count_query = select(func.count(Campaign.id))

    if status:
        query = query.where(Campaign.status == status)
        count_query = count_query.where(Campaign.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.order_by(Campaign.created_at.desc()).limit(limit).offset(offset))
    campaigns = result.scalars().all()

    return CampaignListResponse(items=campaigns, total=total, limit=limit, offset=offset)


@router.get("/{campaign_id}", response_model=CampaignWithStats)
async def get_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    stats = await _compute_campaign_stats(campaign_id, db)

    response = CampaignWithStats.model_validate(campaign)
    response.stats = stats
    return response


@router.patch("/{campaign_id}", response_model=CampaignResponse)
async def update_campaign(
    campaign_id: uuid.UUID, payload: CampaignUpdate, db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(campaign, field, value)

    try:
        await db.commit()
        await db.refresh(campaign)
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail=f"Campaign with slug '{payload.slug}' already exists")

    return campaign


@router.delete("/{campaign_id}", status_code=204)
async def delete_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    await db.execute(delete(Campaign).where(Campaign.id == campaign_id))
    await db.commit()


@router.post("/{campaign_id}/launch", response_model=CampaignResponse)
async def launch_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status == CampaignStatus.active:
        raise HTTPException(status_code=409, detail="Campaign is already active")
    if campaign.status not in (CampaignStatus.draft, CampaignStatus.paused):
        raise HTTPException(status_code=409, detail=f"Cannot launch campaign with status '{campaign.status.value}'")

    campaign.status = CampaignStatus.active
    await db.commit()
    await db.refresh(campaign)
    return campaign


@router.post("/{campaign_id}/pause", response_model=CampaignResponse)
async def pause_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    if campaign.status != CampaignStatus.active:
        raise HTTPException(status_code=409, detail="Can only pause an active campaign")

    campaign.status = CampaignStatus.paused
    await db.commit()
    await db.refresh(campaign)
    return campaign


async def _compute_campaign_stats(campaign_id: uuid.UUID, db: AsyncSession) -> CampaignStats:
    """Compute aggregate stats for a campaign by counting contact statuses."""
    result = await db.execute(
        select(Contact.status, func.count(Contact.id))
        .where(Contact.campaign_id == campaign_id)
        .group_by(Contact.status)
    )
    status_counts = dict(result.all())

    total = sum(status_counts.values()) if status_counts else 0

    # Count opens from outreach_events
    open_count_result = await db.execute(
        select(func.count(func.distinct(OutreachEvent.contact_id)))
        .join(Contact, OutreachEvent.contact_id == Contact.id)
        .where(Contact.campaign_id == campaign_id)
        .where(OutreachEvent.event_type == EventType.email_opened)
    )
    open_count = open_count_result.scalar() or 0

    emailed = status_counts.get(ContactStatus.emailed, 0)
    replied = status_counts.get(ContactStatus.replied, 0)
    converted = status_counts.get(ContactStatus.converted, 0)

    # Denominator for rates: contacts that have been emailed or beyond
    sent_total = emailed + replied + converted + status_counts.get(ContactStatus.declined, 0) + status_counts.get(
        ContactStatus.unresponsive, 0
    )

    return CampaignStats(
        total_contacts=total,
        pending=status_counts.get(ContactStatus.pending, 0),
        researching=status_counts.get(ContactStatus.researching, 0),
        ready=status_counts.get(ContactStatus.ready, 0),
        draft_pending=status_counts.get(ContactStatus.draft_pending, 0),
        emailed=emailed,
        replied=replied,
        converted=converted,
        declined=status_counts.get(ContactStatus.declined, 0),
        unresponsive=status_counts.get(ContactStatus.unresponsive, 0),
        bounced=status_counts.get(ContactStatus.bounced, 0),
        open_rate=round(open_count / sent_total, 2) if sent_total > 0 else 0.0,
        reply_rate=round(replied / sent_total, 2) if sent_total > 0 else 0.0,
        conversion_rate=round(converted / sent_total, 2) if sent_total > 0 else 0.0,
    )
```

- [ ] **10.5** Update `app/main.py` to register the campaigns router

```python
from fastapi import FastAPI

from app.config import settings
from app.api.campaigns import router as campaigns_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(campaigns_router)


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": settings.app_version}
```

- [ ] **10.6** Run tests

```bash
pytest tests/test_campaigns.py -v
# Expected: All tests PASSED
```

- [ ] **10.7** Run auth tests

```bash
pytest tests/test_auth.py -v
# Expected: All tests PASSED
```

- [ ] **10.8** Commit

```bash
git add -A
git commit -m "feat: campaign CRUD endpoints with list, detail, launch, pause, delete"
```

---

## Task 11: Contact CRUD Endpoints

**Create:**
- `app/api/contacts.py`
- `tests/test_contacts.py`

**Modify:**
- `app/main.py` (register router)

### Steps

- [ ] **11.1** Write test first: Create `tests/test_contacts.py`

```python
import pytest
from httpx import AsyncClient


@pytest.fixture
async def campaign_id(client: AsyncClient, auth_headers: dict) -> str:
    response = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Contact Test Campaign", "slug": "contact-test", "goal": "signup"},
        headers=auth_headers,
    )
    return response.json()["id"]


@pytest.mark.asyncio
async def test_create_contact(client: AsyncClient, auth_headers: dict, campaign_id: str):
    payload = {
        "name": "Samara Iqbal",
        "email": "info@aramaslaw.com",
        "firm_name": "Aramas Family Law",
        "website": "https://www.aramaslaw.com",
        "metadata": {"specialisms": ["islamic_family_law"], "location": "Manchester"},
    }
    response = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Samara Iqbal"
    assert data["email"] == "info@aramaslaw.com"
    assert data["status"] == "pending"
    assert data["campaign_id"] == campaign_id


@pytest.mark.asyncio
async def test_create_contact_invalid_campaign(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    payload = {"name": "Test", "email": "test@example.com"}
    response = await client.post(
        f"/api/v1/outreach/campaigns/{fake_id}/contacts",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_bulk_create_contacts(client: AsyncClient, auth_headers: dict, campaign_id: str):
    payload = {
        "contacts": [
            {"name": "Contact A", "email": "a@example.com", "firm_name": "Firm A"},
            {"name": "Contact B", "email": "b@example.com", "firm_name": "Firm B"},
            {"name": "Contact C", "email": "c@example.com"},
        ]
    }
    response = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk",
        json=payload,
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["created"] == 3
    assert data["errors"] == []


@pytest.mark.asyncio
async def test_list_contacts(client: AsyncClient, auth_headers: dict, campaign_id: str):
    # Create contacts
    for i in range(3):
        await client.post(
            f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
            json={"name": f"List Contact {i}", "email": f"list{i}@example.com"},
            headers=auth_headers,
        )
    response = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["total"] >= 3
    assert len(data["items"]) >= 3


@pytest.mark.asyncio
async def test_list_contacts_filter_status(client: AsyncClient, auth_headers: dict, campaign_id: str):
    await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Pending Contact", "email": "pending@example.com"},
        headers=auth_headers,
    )
    response = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts?status=pending",
        headers=auth_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert all(item["status"] == "pending" for item in data["items"])


@pytest.mark.asyncio
async def test_get_contact_detail(client: AsyncClient, auth_headers: dict, campaign_id: str):
    create_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Detail Contact", "email": "detail@example.com"},
        headers=auth_headers,
    )
    contact_id = create_resp.json()["id"]
    response = await client.get(f"/api/v1/outreach/contacts/{contact_id}", headers=auth_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == contact_id
    assert "events" in data


@pytest.mark.asyncio
async def test_get_contact_not_found(client: AsyncClient, auth_headers: dict):
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = await client.get(f"/api/v1/outreach/contacts/{fake_id}", headers=auth_headers)
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_contact(client: AsyncClient, auth_headers: dict, campaign_id: str):
    create_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Update Contact", "email": "update@example.com"},
        headers=auth_headers,
    )
    contact_id = create_resp.json()["id"]
    response = await client.patch(
        f"/api/v1/outreach/contacts/{contact_id}",
        json={"name": "Updated Name", "firm_name": "New Firm"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["name"] == "Updated Name"
    assert response.json()["firm_name"] == "New Firm"


@pytest.mark.asyncio
async def test_delete_contact(client: AsyncClient, auth_headers: dict, campaign_id: str):
    create_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Delete Contact", "email": "delete@example.com"},
        headers=auth_headers,
    )
    contact_id = create_resp.json()["id"]
    response = await client.delete(f"/api/v1/outreach/contacts/{contact_id}", headers=auth_headers)
    assert response.status_code == 204

    get_resp = await client.get(f"/api/v1/outreach/contacts/{contact_id}", headers=auth_headers)
    assert get_resp.status_code == 404


@pytest.mark.asyncio
async def test_retry_contact(client: AsyncClient, auth_headers: dict, campaign_id: str):
    create_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Retry Contact", "email": "retry@example.com"},
        headers=auth_headers,
    )
    contact_id = create_resp.json()["id"]

    # Update status to unresponsive so retry is valid
    await client.patch(
        f"/api/v1/outreach/contacts/{contact_id}",
        json={"status": "unresponsive"},
        headers=auth_headers,
    )

    response = await client.post(f"/api/v1/outreach/contacts/{contact_id}/retry", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["status"] == "pending"
    assert response.json()["current_cadence_step"] == 0
```

- [ ] **11.2** Run tests (should fail)

```bash
pytest tests/test_contacts.py -v
# Expected: FAILED (no routes)
```

- [ ] **11.3** Create `app/api/contacts.py`

```python
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth.api_key import require_api_key
from app.database import get_db
from app.models.campaign import Campaign
from app.models.contact import Contact, ContactStatus
from app.schemas.contact import (
    BulkCreateResponse,
    ContactBulkCreate,
    ContactCreate,
    ContactDetailResponse,
    ContactListResponse,
    ContactResponse,
    ContactUpdate,
)

router = APIRouter(prefix="/api/v1/outreach", tags=["contacts"], dependencies=[Depends(require_api_key)])

# Statuses that allow retry
RETRYABLE_STATUSES = {ContactStatus.unresponsive, ContactStatus.bounced, ContactStatus.declined}


@router.post("/campaigns/{campaign_id}/contacts", response_model=ContactResponse, status_code=201)
async def create_contact(
    campaign_id: uuid.UUID, payload: ContactCreate, db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    contact = Contact(
        campaign_id=campaign_id,
        name=payload.name,
        email=payload.email,
        phone=payload.phone,
        firm_name=payload.firm_name,
        website=payload.website,
        metadata_=payload.metadata,
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return contact


@router.post("/campaigns/{campaign_id}/contacts/bulk", response_model=BulkCreateResponse, status_code=201)
async def bulk_create_contacts(
    campaign_id: uuid.UUID, payload: ContactBulkCreate, db: AsyncSession = Depends(get_db)
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    created = 0
    errors = []

    for i, contact_data in enumerate(payload.contacts):
        try:
            contact = Contact(
                campaign_id=campaign_id,
                name=contact_data.name,
                email=contact_data.email,
                phone=contact_data.phone,
                firm_name=contact_data.firm_name,
                website=contact_data.website,
                metadata_=contact_data.metadata,
            )
            db.add(contact)
            await db.flush()
            created += 1
        except Exception as e:
            errors.append({"index": i, "email": contact_data.email, "error": str(e)})

    await db.commit()
    return BulkCreateResponse(created=created, errors=errors)


@router.get("/campaigns/{campaign_id}/contacts", response_model=ContactListResponse)
async def list_contacts(
    campaign_id: uuid.UUID,
    status: ContactStatus | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(Contact).where(Contact.campaign_id == campaign_id)
    count_query = select(func.count(Contact.id)).where(Contact.campaign_id == campaign_id)

    if status:
        query = query.where(Contact.status == status)
        count_query = count_query.where(Contact.status == status)

    total = (await db.execute(count_query)).scalar() or 0
    result = await db.execute(query.order_by(Contact.created_at.desc()).limit(limit).offset(offset))
    contacts = result.scalars().all()

    return ContactListResponse(items=contacts, total=total, limit=limit, offset=offset)


@router.get("/contacts/{contact_id}", response_model=ContactDetailResponse)
async def get_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Contact).options(selectinload(Contact.events)).where(Contact.id == contact_id)
    )
    contact = result.scalar_one_or_none()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    return contact


@router.patch("/contacts/{contact_id}", response_model=ContactResponse)
async def update_contact(
    contact_id: uuid.UUID, payload: ContactUpdate, db: AsyncSession = Depends(get_db)
):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    update_data = payload.model_dump(exclude_unset=True)

    # Map 'metadata' field to 'metadata_' attribute
    if "metadata" in update_data:
        update_data["metadata_"] = update_data.pop("metadata")

    for field, value in update_data.items():
        setattr(contact, field, value)

    await db.commit()
    await db.refresh(contact)
    return contact


@router.delete("/contacts/{contact_id}", status_code=204)
async def delete_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    await db.execute(delete(Contact).where(Contact.id == contact_id))
    await db.commit()


@router.post("/contacts/{contact_id}/retry", response_model=ContactResponse)
async def retry_contact(contact_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    contact = await db.get(Contact, contact_id)
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if contact.status not in RETRYABLE_STATUSES:
        raise HTTPException(
            status_code=409,
            detail=f"Cannot retry contact with status '{contact.status.value}'. "
            f"Retryable statuses: {', '.join(s.value for s in RETRYABLE_STATUSES)}",
        )

    contact.status = ContactStatus.pending
    contact.current_cadence_step = 0
    await db.commit()
    await db.refresh(contact)
    return contact
```

- [ ] **11.4** Update `app/main.py` to register the contacts router

```python
from fastapi import FastAPI

from app.config import settings
from app.api.campaigns import router as campaigns_router
from app.api.contacts import router as contacts_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(campaigns_router)
app.include_router(contacts_router)


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": settings.app_version}
```

- [ ] **11.5** Run tests

```bash
pytest tests/test_contacts.py -v
# Expected: All tests PASSED
```

- [ ] **11.6** Commit

```bash
git add -A
git commit -m "feat: contact CRUD endpoints with bulk create, retry, list filtering"
```

---

## Task 12: Health Endpoint

**Create:**
- `app/api/dashboard.py`
- `tests/test_health.py`

**Modify:**
- `app/main.py` (register router)

### Steps

- [ ] **12.1** Write test first: Create `tests/test_health.py`

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_endpoint(client: AsyncClient):
    response = await client.get("/api/v1/outreach/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "postgres" in data["checks"]
    assert "version" in data


@pytest.mark.asyncio
async def test_health_no_auth_required(client: AsyncClient):
    """Health endpoint should not require API key auth."""
    response = await client.get("/api/v1/outreach/health")
    assert response.status_code == 200
```

- [ ] **12.2** Run tests (should fail)

```bash
pytest tests/test_health.py -v
# Expected: FAILED (no route)
```

- [ ] **12.3** Create `app/api/dashboard.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db

router = APIRouter(prefix="/api/v1/outreach", tags=["dashboard"])


@router.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    checks = {}

    # Check PostgreSQL
    try:
        result = await db.execute(text("SELECT 1"))
        result.scalar()
        checks["postgres"] = "ok"
    except Exception as e:
        checks["postgres"] = f"error: {str(e)}"

    overall_status = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"

    return {
        "status": overall_status,
        "version": settings.app_version,
        "service": settings.app_name,
        "checks": checks,
    }
```

- [ ] **12.4** Update `app/main.py` to register the dashboard router

```python
from fastapi import FastAPI

from app.config import settings
from app.api.campaigns import router as campaigns_router
from app.api.contacts import router as contacts_router
from app.api.dashboard import router as dashboard_router

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    docs_url="/docs",
    redoc_url="/redoc",
)

app.include_router(campaigns_router)
app.include_router(contacts_router)
app.include_router(dashboard_router)


@app.get("/")
async def root():
    return {"service": settings.app_name, "version": settings.app_version}
```

- [ ] **12.5** Run tests

```bash
pytest tests/test_health.py -v
# Expected: All tests PASSED
```

- [ ] **12.6** Commit

```bash
git add -A
git commit -m "feat: health check endpoint with Postgres connectivity check"
```

---

## Task 13: Integration Tests

**Create:**
- `tests/test_integration.py`

### Steps

- [ ] **13.1** Create `tests/test_integration.py`

```python
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_full_campaign_lifecycle(client: AsyncClient, auth_headers: dict):
    """End-to-end test: create campaign -> add contacts -> launch -> pause."""

    # 1. Create campaign
    campaign_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={
            "name": "Integration Test Campaign",
            "slug": "integration-test",
            "goal": "signup",
            "auto_send": False,
            "sender_name": "Test",
            "sender_email": "test@example.com",
            "reply_to": "reply@example.com",
            "templates": {
                "initial": {"subject": "Hello {{contact_name}}", "body": "Test body"},
            },
            "cadence": [
                {"day": 0, "action": "send_initial"},
                {"day": 3, "action": "follow_up", "template": "follow_up_1"},
            ],
        },
        headers=auth_headers,
    )
    assert campaign_resp.status_code == 201
    campaign_id = campaign_resp.json()["id"]

    # 2. Add single contact
    contact_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={
            "name": "Samara Iqbal",
            "email": "samara@example.com",
            "firm_name": "Aramas Family Law",
            "website": "https://aramaslaw.com",
            "metadata": {"specialisms": ["islamic_family_law"], "location": "Manchester"},
        },
        headers=auth_headers,
    )
    assert contact_resp.status_code == 201
    contact_id = contact_resp.json()["id"]

    # 3. Bulk add contacts
    bulk_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts/bulk",
        json={
            "contacts": [
                {"name": "Contact A", "email": "a@example.com"},
                {"name": "Contact B", "email": "b@example.com"},
            ]
        },
        headers=auth_headers,
    )
    assert bulk_resp.status_code == 201
    assert bulk_resp.json()["created"] == 2

    # 4. List contacts
    list_resp = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 3

    # 5. Get contact detail
    detail_resp = await client.get(
        f"/api/v1/outreach/contacts/{contact_id}",
        headers=auth_headers,
    )
    assert detail_resp.status_code == 200
    assert detail_resp.json()["events"] == []

    # 6. Get campaign with stats
    stats_resp = await client.get(
        f"/api/v1/outreach/campaigns/{campaign_id}",
        headers=auth_headers,
    )
    assert stats_resp.status_code == 200
    stats = stats_resp.json()["stats"]
    assert stats["total_contacts"] == 3
    assert stats["pending"] == 3

    # 7. Launch campaign
    launch_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/launch",
        headers=auth_headers,
    )
    assert launch_resp.status_code == 200
    assert launch_resp.json()["status"] == "active"

    # 8. Pause campaign
    pause_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/pause",
        headers=auth_headers,
    )
    assert pause_resp.status_code == 200
    assert pause_resp.json()["status"] == "paused"

    # 9. Update contact
    update_resp = await client.patch(
        f"/api/v1/outreach/contacts/{contact_id}",
        json={"consent": True},
        headers=auth_headers,
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["consent"] is True

    # 10. Health check still works
    health_resp = await client.get("/api/v1/outreach/health")
    assert health_resp.status_code == 200
    assert health_resp.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_campaign_contact_cascade_delete(client: AsyncClient, auth_headers: dict):
    """Deleting a campaign should cascade-delete its contacts."""
    campaign_resp = await client.post(
        "/api/v1/outreach/campaigns",
        json={"name": "Cascade Test", "slug": "cascade-test", "goal": "signup"},
        headers=auth_headers,
    )
    campaign_id = campaign_resp.json()["id"]

    contact_resp = await client.post(
        f"/api/v1/outreach/campaigns/{campaign_id}/contacts",
        json={"name": "Cascade Contact", "email": "cascade@example.com"},
        headers=auth_headers,
    )
    contact_id = contact_resp.json()["id"]

    # Delete campaign
    del_resp = await client.delete(f"/api/v1/outreach/campaigns/{campaign_id}", headers=auth_headers)
    assert del_resp.status_code == 204

    # Contact should be gone too
    get_resp = await client.get(f"/api/v1/outreach/contacts/{contact_id}", headers=auth_headers)
    assert get_resp.status_code == 404
```

- [ ] **13.2** Run all tests

```bash
pytest tests/ -v
# Expected: All tests PASSED
```

- [ ] **13.3** Run with coverage (optional)

```bash
pip install pytest-cov
pytest tests/ -v --cov=app --cov-report=term-missing
# Expected: Coverage report showing all endpoints tested
```

- [ ] **13.4** Commit

```bash
git add -A
git commit -m "feat: integration tests for full campaign lifecycle and cascade delete"
```

---

## Final Verification

- [ ] **Run the full test suite**

```bash
pytest tests/ -v
```

- [ ] **Start the server and test manually**

```bash
docker-compose up -d
alembic upgrade head
curl http://localhost:8001/api/v1/outreach/health
# Expected: {"status":"healthy","version":"0.1.0","service":"adil-outreach-engine","checks":{"postgres":"ok"}}
```

- [ ] **Verify OpenAPI docs are generated**

Open `http://localhost:8001/docs` in browser. All campaign and contact endpoints should be documented with request/response schemas.

---

## File Tree (Final State)

```
adil-outreach-engine/
├── pyproject.toml
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── alembic.ini
├── alembic/
│   ├── env.py
│   ├── script.py.mako
│   └── versions/
│       ├── xxxx_create_campaigns_table.py
│       ├── xxxx_create_contacts_table.py
│       ├── xxxx_create_outreach_events_table.py
│       ├── xxxx_create_conversions_table.py
│       └── xxxx_create_agent_checkpoints_table.py
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── config.py
│   ├── database.py
│   ├── auth/
│   │   ├── __init__.py
│   │   └── api_key.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── campaign.py
│   │   ├── contact.py
│   │   ├── outreach_event.py
│   │   ├── conversion.py
│   │   └── agent_checkpoint.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── campaign.py
│   │   ├── contact.py
│   │   ├── event.py
│   │   ├── conversion.py
│   │   └── stats.py
│   └── api/
│       ├── __init__.py
│       ├── campaigns.py
│       ├── contacts.py
│       └── dashboard.py
└── tests/
    ├── __init__.py
    ├── conftest.py
    ├── test_auth.py
    ├── test_campaigns.py
    ├── test_contacts.py
    ├── test_health.py
    └── test_integration.py
```
