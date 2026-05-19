"""Integration tests for the ``fetch_acts`` arq worker task."""

from __future__ import annotations

import os
from unittest.mock import patch

# Settings load eagerly on import — set fakes before app.* imports.
os.environ.setdefault("GEMINI_API_KEY", "test")
os.environ.setdefault("FILE_SEARCH_STORE_ID", "fileSearchStores/test")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///test.db")
os.environ.setdefault("ADMIN_API_KEY", "test-key")

import pytest
import respx
from httpx import Response
from sqlalchemy import select

from app.models.act import Act, ActSection, ActSubsection
from app.services.acts_seed import ActSeed
from app.workers import tasks as worker_tasks

MINIMAL_CLML = """<?xml version="1.0" encoding="UTF-8"?>
<Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
  <Primary><Body>
    <P1 id="section-1">
      <Pnumber>1</Pnumber>
      <Title>Short title</Title>
      <P1para><Text>This Act may be cited as the Sample Act.</Text></P1para>
    </P1>
    <P1 id="section-2">
      <Pnumber>2</Pnumber>
      <Title>Definitions</Title>
      <P1para>
        <Text>In this Act—</Text>
        <P2 id="section-2-1">
          <Pnumber>1</Pnumber>
          <P2para><Text>"thing" means anything.</Text></P2para>
        </P2>
      </P1para>
    </P1>
  </Body></Primary>
</Legislation>
"""


@pytest.fixture
def seed_two_acts():
    """Replace UK_ACTS_SEED for the duration of the test."""
    fake = [
        ActSeed("Sample Act 2024", "https://www.legislation.gov.uk/ukpga/2024/1"),
        ActSeed("Other Sample Act 2024", "https://www.legislation.gov.uk/ukpga/2024/2"),
    ]
    with patch.object(worker_tasks, "UK_ACTS_SEED", fake):
        yield fake


@pytest.fixture
def patch_async_session(db):
    """Make fetch_acts use the in-memory test session factory."""
    from tests.conftest import test_session

    # `fetch_acts` does `from app.database import async_session` lazily;
    # patch the module-level binding so the import inside picks up our fixture.
    import app.database as database_module

    original = database_module.async_session
    database_module.async_session = test_session
    yield
    database_module.async_session = original


@pytest.mark.asyncio
@respx.mock
async def test_fetch_acts_persists_act_with_sections_and_subsections(seed_two_acts, patch_async_session, db):
    respx.get("https://www.legislation.gov.uk/ukpga/2024/1/data.xml").mock(
        return_value=Response(200, text=MINIMAL_CLML)
    )
    respx.get("https://www.legislation.gov.uk/ukpga/2024/2/data.xml").mock(
        return_value=Response(200, text=MINIMAL_CLML)
    )

    result = await worker_tasks.fetch_acts({})

    assert result["fetched"] == 2
    assert result["failed"] == []
    # No ontology DB configured — write_act_to_ontology returns 0.
    assert result["ontology_nodes_written"] == 0

    acts = (await db.execute(select(Act))).scalars().all()
    assert len(acts) == 2
    assert {a.name for a in acts} == {"Sample Act 2024", "Other Sample Act 2024"}

    sections = (await db.execute(select(ActSection))).scalars().all()
    assert len(sections) == 4  # 2 per Act
    subsections = (await db.execute(select(ActSubsection))).scalars().all()
    assert len(subsections) == 2  # 1 per Act


@pytest.mark.asyncio
@respx.mock
async def test_fetch_acts_records_failures_without_aborting(seed_two_acts, patch_async_session, db):
    respx.get("https://www.legislation.gov.uk/ukpga/2024/1/data.xml").mock(
        return_value=Response(200, text=MINIMAL_CLML)
    )
    respx.get("https://www.legislation.gov.uk/ukpga/2024/2/data.xml").mock(return_value=Response(503))

    result = await worker_tasks.fetch_acts({})

    assert result["fetched"] == 1
    assert result["failed"] == ["Other Sample Act 2024"]
    acts = (await db.execute(select(Act))).scalars().all()
    assert [a.name for a in acts] == ["Sample Act 2024"]


@pytest.mark.asyncio
@respx.mock
async def test_fetch_acts_is_idempotent(seed_two_acts, patch_async_session, db):
    respx.get("https://www.legislation.gov.uk/ukpga/2024/1/data.xml").mock(
        return_value=Response(200, text=MINIMAL_CLML)
    )
    respx.get("https://www.legislation.gov.uk/ukpga/2024/2/data.xml").mock(
        return_value=Response(200, text=MINIMAL_CLML)
    )

    await worker_tasks.fetch_acts({})
    await worker_tasks.fetch_acts({})

    acts = (await db.execute(select(Act))).scalars().all()
    sections = (await db.execute(select(ActSection))).scalars().all()
    assert len(acts) == 2
    assert len(sections) == 4
