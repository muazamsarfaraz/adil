import asyncio
from collections.abc import AsyncGenerator

import pytest
import sqlalchemy as sa
from httpx import ASGITransport, AsyncClient
from sqlalchemy import event, text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.config import settings
from app.database import Base, get_db
from app.main import app

# ---------------------------------------------------------------------------
# SQLite compatibility: compile PostgreSQL types for SQLite dialect
# ---------------------------------------------------------------------------


@compiles(JSONB, "sqlite")
def compile_jsonb_sqlite(type_, compiler, **kw):
    return "JSON"


@compiles(PG_UUID, "sqlite")
def compile_uuid_sqlite(type_, compiler, **kw):
    return "VARCHAR(36)"


# ---------------------------------------------------------------------------
# Patch server_defaults that use PostgreSQL functions so SQLite can handle them.
# gen_random_uuid() -> stripped (Python-side uuid4 default handles it)
# now()            -> CURRENT_TIMESTAMP (SQLite-compatible)
# ---------------------------------------------------------------------------
_pg_defaults_patched = False


@event.listens_for(Base.metadata, "before_create")
def _patch_pg_server_defaults(target, connection, **kw):
    """Replace PostgreSQL-specific server_defaults with SQLite-compatible ones."""
    global _pg_defaults_patched
    if connection.dialect.name != "sqlite" or _pg_defaults_patched:
        return
    _pg_defaults_patched = True
    for table in target.tables.values():
        for column in table.columns:
            if column.server_default is not None:
                sd_text = str(column.server_default.arg) if hasattr(column.server_default, "arg") else ""
                if "gen_random_uuid" in sd_text:
                    column.server_default = None
                elif "now()" in sd_text:
                    column.server_default = sa.schema.DefaultClause(text("CURRENT_TIMESTAMP"))


# ---------------------------------------------------------------------------
# Test infrastructure
# ---------------------------------------------------------------------------
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

engine_test = create_async_engine(TEST_DATABASE_URL, echo=True)
async_session_test = async_sessionmaker(engine_test, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
async def setup_db():
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine_test.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
async def db_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_test() as session:
        yield session


@pytest.fixture
async def client(db_session: AsyncSession) -> AsyncGenerator[AsyncClient, None]:
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict:
    return {"X-API-Key": settings.api_key}
