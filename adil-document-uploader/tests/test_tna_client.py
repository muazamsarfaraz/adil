import pytest
import httpx
import respx

from app.services.tna_client import TNAClient

SAMPLE_ATOM_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:tna="https://caselaw.nationalarchives.gov.uk">
  <title>Search results</title>
  <entry>
    <id>https://caselaw.nationalarchives.gov.uk/id/eat/2023/45</id>
    <title>Smith v Employer Ltd</title>
    <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/eat/2023/45"/>
    <updated>2023-06-15T00:00:00Z</updated>
    <summary type="html"/>
    <tna:identifier type="ukncn">[2023] EAT 45</tna:identifier>
  </entry>
  <entry>
    <id>https://caselaw.nationalarchives.gov.uk/id/ewca/civ/2022/100</id>
    <title>Jones v Council</title>
    <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/ewca/civ/2022/100"/>
    <updated>2022-03-10T00:00:00Z</updated>
    <summary type="html"/>
    <tna:identifier type="ukncn">[2022] EWCA Civ 100</tna:identifier>
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
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:tna="https://caselaw.nationalarchives.gov.uk">
      <link rel="next" href="https://caselaw.nationalarchives.gov.uk/atom.xml?query=test&amp;page=2"/>
      <entry>
        <id>https://caselaw.nationalarchives.gov.uk/id/eat/2023/1</id>
        <title>Case One</title>
        <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/eat/2023/1"/>
        <updated>2023-01-01T00:00:00Z</updated>
        <summary type="html"/>
        <tna:identifier type="ukncn">[2023] EAT 1</tna:identifier>
      </entry>
    </feed>"""
    page2 = """<?xml version="1.0" encoding="UTF-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom" xmlns:tna="https://caselaw.nationalarchives.gov.uk">
      <entry>
        <id>https://caselaw.nationalarchives.gov.uk/id/eat/2023/2</id>
        <title>Case Two</title>
        <link rel="alternate" href="https://caselaw.nationalarchives.gov.uk/eat/2023/2"/>
        <updated>2023-02-01T00:00:00Z</updated>
        <summary type="html"/>
        <tna:identifier type="ukncn">[2023] EAT 2</tna:identifier>
      </entry>
    </feed>"""
    respx.get("https://caselaw.nationalarchives.gov.uk/atom.xml?query=test&page=2").mock(
        return_value=httpx.Response(200, text=page2)
    )
    respx.get("https://caselaw.nationalarchives.gov.uk/atom.xml").mock(return_value=httpx.Response(200, text=page1))
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
