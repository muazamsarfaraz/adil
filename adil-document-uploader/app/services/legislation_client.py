"""Client for legislation.gov.uk — fetches UK Acts as CLML XML and parses
them into Sections + Subsections.

CLML (Crown Legislation Markup Language) reference:
    https://www.legislation.gov.uk/developer/formats/xml

The full text of any Act is available at
``https://www.legislation.gov.uk/<type>/<year>/<number>/data.xml``. We use
the *current* version only (v1 — time-bounded versioning deferred).

Structure (simplified):

    <Legislation xmlns="http://www.legislation.gov.uk/namespaces/legislation">
      <Primary><Body>
        <P1 id="section-13">                 ← Section
          <Pnumber>13</Pnumber>
          <Title>Direct discrimination</Title>
          <P1para>
            <Text>...intro text...</Text>
            <P2>                              ← Subsection (1)
              <Pnumber>1</Pnumber>
              <P2para><Text>...</Text></P2para>
            </P2>
            ...
          </P1para>
        </P1>
      </Body></Primary>
    </Legislation>

Note: ``P1`` elements can be nested inside ``Part`` / ``Group`` / ``Chapter``
wrappers — we pick them up regardless of depth.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass, field
from urllib.parse import urlparse

import httpx
from lxml import etree

logger = logging.getLogger(__name__)

LEG_NS = "http://www.legislation.gov.uk/namespaces/legislation"
NSMAP = {"leg": LEG_NS}


@dataclass
class ParsedSubsection:
    number: str
    text: str
    ordering: int


@dataclass
class ParsedSection:
    number: str
    title: str | None
    text: str
    ordering: int
    subsections: list[ParsedSubsection] = field(default_factory=list)


@dataclass
class ParsedAct:
    name: str
    year: int
    leg_type: str
    leg_number: int
    url: str
    raw_xml: str
    sections: list[ParsedSection]


_URL_RE = re.compile(r"^https?://(?:www\.)?legislation\.gov\.uk/(?P<type>[a-z]+)/(?P<year>\d{4})/(?P<num>\d+)")


def parse_legislation_ref(url: str) -> tuple[str, int, int]:
    """Return (leg_type, year, leg_number) from a legislation.gov.uk URL."""
    m = _URL_RE.match(url.strip())
    if not m:
        raise ValueError(f"Not a legislation.gov.uk URL: {url}")
    return m["type"], int(m["year"]), int(m["num"])


def data_xml_url(base_url: str) -> str:
    """Return the canonical ``.../data.xml`` URL for an Act base URL."""
    parsed = urlparse(base_url)
    path = parsed.path.rstrip("/")
    # Strip trailing /contents if present — we want the Act itself.
    if path.endswith("/contents"):
        path = path[: -len("/contents")]
    return f"{parsed.scheme}://{parsed.netloc}{path}/data.xml"


def _elem_text(elem: etree._Element) -> str:
    """Return concatenated visible text from an element, stripped & normalised."""
    if elem is None:
        return ""
    raw = "".join(elem.itertext())
    # Collapse runs of whitespace; CLML pretty-prints heavily.
    return re.sub(r"\s+", " ", raw).strip()


def _section_number(p1: etree._Element) -> str:
    """Extract section number from a P1 element."""
    pnum = p1.find(f"{{{LEG_NS}}}Pnumber")
    if pnum is not None and pnum.text:
        return pnum.text.strip()
    # Fall back to the trailing digits in the id attribute (e.g. id="section-13")
    sec_id = p1.get("id", "")
    m = re.search(r"section-(\w+)", sec_id)
    return m.group(1) if m else ""


def _subsection_number(p2: etree._Element) -> str:
    pnum = p2.find(f"{{{LEG_NS}}}Pnumber")
    if pnum is not None and pnum.text:
        return pnum.text.strip()
    sec_id = p2.get("id", "")
    m = re.search(r"-(\d+\w*)$", sec_id)
    return m.group(1) if m else ""


def parse_act_xml(raw_xml: str, *, name: str, url: str) -> ParsedAct:
    """Parse a CLML XML document into a ParsedAct tree."""
    # ``recover=True`` lets us tolerate the occasional malformed Act dump
    # rather than failing the entire fetch run.
    parser = etree.XMLParser(recover=True, huge_tree=True)
    root = etree.fromstring(raw_xml.encode("utf-8"), parser=parser)

    leg_type, year, leg_number = parse_legislation_ref(url)

    sections: list[ParsedSection] = []
    # Find every P1 (Section) anywhere under the legislation root.
    for ordering, p1 in enumerate(root.iterfind(f".//{{{LEG_NS}}}P1")):
        number = _section_number(p1)
        if not number:
            continue
        title_el = p1.find(f"{{{LEG_NS}}}Title")
        title = _elem_text(title_el) or None

        subsections: list[ParsedSubsection] = []
        for sub_ordering, p2 in enumerate(p1.iterfind(f".//{{{LEG_NS}}}P2")):
            sub_num = _subsection_number(p2)
            if not sub_num:
                continue
            subsections.append(
                ParsedSubsection(
                    number=sub_num,
                    text=_elem_text(p2),
                    ordering=sub_ordering,
                )
            )

        sections.append(
            ParsedSection(
                number=number,
                title=title,
                text=_elem_text(p1),
                ordering=ordering,
                subsections=subsections,
            )
        )

    return ParsedAct(
        name=name,
        year=year,
        leg_type=leg_type,
        leg_number=leg_number,
        url=url,
        raw_xml=raw_xml,
        sections=sections,
    )


class LegislationClient:
    """Async HTTP client for legislation.gov.uk CLML downloads."""

    def __init__(
        self,
        *,
        base_url: str = "https://www.legislation.gov.uk",
        max_rpm: int = 30,
        timeout: float = 60.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        # Be polite — legislation.gov.uk is a public-good site. Hold a
        # small concurrency cap rather than blasting it.
        self._semaphore = asyncio.Semaphore(max_rpm)
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={
                "User-Agent": "adil-document-uploader/1.0 (askadil.org)",
                "Accept": "application/xml",
            },
        )

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> LegislationClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    async def fetch_xml(self, act_url: str) -> str:
        """Fetch the CLML XML for a single Act and return it as text."""
        url = data_xml_url(act_url)
        async with self._semaphore:
            resp = await self._client.get(url)
            resp.raise_for_status()
            return resp.text

    async def fetch_act(self, *, name: str, act_url: str) -> ParsedAct:
        """Fetch and parse an Act in one call."""
        raw = await self.fetch_xml(act_url)
        return parse_act_xml(raw, name=name, url=act_url)
