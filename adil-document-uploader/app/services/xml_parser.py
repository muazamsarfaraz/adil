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

    date_el = root.find(f".//{{{AKN_NS}}}FRBRdate[@name='judgment']")
    judgment_date = date_el.get("date") if date_el is not None else None

    body = root.find(f".//{{{AKN_NS}}}judgmentBody")
    if body is None:
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
