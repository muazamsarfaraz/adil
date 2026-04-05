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
    assert resp.status_code in (401, 403)


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
