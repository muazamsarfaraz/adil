import os

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.judgment import Base

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
