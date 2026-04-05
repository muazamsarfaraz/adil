from unittest.mock import AsyncMock

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

    new_count, skip_count = await _fetch_for_domain(tna_client=mock_tna, domain=domain, session_factory=test_session)

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

    new_count, skip_count = await _fetch_for_domain(tna_client=mock_tna, domain=domain, session_factory=test_session)

    assert new_count == 0
    assert skip_count == 1
    mock_tna.download_judgment.assert_not_called()
