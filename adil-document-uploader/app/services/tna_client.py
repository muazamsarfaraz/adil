from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from lxml import etree

logger = logging.getLogger(__name__)

ATOM_NS = "http://www.w3.org/2005/Atom"
TNA_NS = "https://caselaw.nationalarchives.gov.uk"


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
            link_el = entry_el.find(f'{{{ATOM_NS}}}link[@rel="alternate"]')
            href = link_el.get("href", "") if link_el is not None else ""
            updated = entry_el.findtext(f"{{{ATOM_NS}}}updated", default="")

            # Neutral citation is in <tna:identifier type="ukncn">
            citation_el = entry_el.find(f'{{{TNA_NS}}}identifier[@type="ukncn"]')
            neutral_citation = citation_el.text.strip() if citation_el is not None and citation_el.text else ""

            parsed = urlparse(href)
            tna_uri = parsed.path.strip("/")

            entries.append(
                AtomEntry(
                    neutral_citation=neutral_citation,
                    case_name=title.strip(),
                    tna_uri=tna_uri,
                    tna_url=href,
                    updated=updated,
                )
            )

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

            url = next_url
            params = None

        logger.info("TNA search query=%r court=%s found %d entries", query, court, len(all_entries))
        return all_entries

    async def download_judgment(self, tna_uri: str) -> str:
        """Download the full Akoma Ntoso XML for a judgment."""
        url = f"{self.base_url}/{tna_uri}/data.xml"
        resp = await self._get(url)
        return resp.text
