"""
formatter.py — Markdown → WhatsApp-flavoured formatting + length splitter.

WhatsApp uses a non-CommonMark subset:
  *bold*      — single asterisks (not double)
  _italic_    — single underscores
  ~strike~    — single tildes
  ```mono```  — triple-backtick monospace block
WhatsApp does NOT render headers (`#`, `##`), tables, or link previews unless
the first URL in the body is allowed. Link previews are suppressed by setting
`preview_url=false` on the Graph API send (see meta_client.send_text).
"""

from __future__ import annotations

import re

WA_MAX = 4096  # Meta hard cap per text message body
SAFE_SPLIT = 3900  # leave room for prefix/numbering


_HEADER_RE = re.compile(r"^\s{0,3}#{1,6}\s+", re.MULTILINE)
_BOLD_RE = re.compile(r"\*\*(.+?)\*\*", re.DOTALL)
_ITAL_RE = re.compile(r"(?<!\w)_([^_]+)_(?!\w)")
_LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
_HRULE_RE = re.compile(r"^\s*[-*_]{3,}\s*$", re.MULTILINE)
_LIST_RE = re.compile(r"^(\s*)[-*]\s+", re.MULTILINE)


def to_whatsapp(md: str) -> str:
    """Convert a Markdown answer to WhatsApp-flavoured text."""
    if not md:
        return ""
    text = md
    text = _HEADER_RE.sub("*", text)
    text = _HRULE_RE.sub("", text)
    text = _BOLD_RE.sub(r"*\1*", text)
    text = _ITAL_RE.sub(r"_\1_", text)
    text = _LINK_RE.sub(lambda m: f"{m.group(1)} ({m.group(2)})", text)
    text = _LIST_RE.sub(lambda m: f"{m.group(1)}• ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_for_whatsapp(body: str, limit: int = SAFE_SPLIT) -> list[str]:
    """Split into ≤limit-char chunks at paragraph/sentence/space boundaries.

    Adds ``(1/n) … (n/n)`` prefixes only when n > 1.
    """
    if len(body) <= limit:
        return [body]

    chunks: list[str] = []
    remaining = body
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break
        cut = remaining.rfind("\n\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(". ", 0, limit)
            if cut < limit // 2:
                cut = remaining.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip()

    total = len(chunks)
    return [f"({i + 1}/{total}) {c}" for i, c in enumerate(chunks)]


def format_sources(sources: list[dict]) -> str:
    """Render the sources list in a WhatsApp-friendly tail."""
    if not sources:
        return ""
    lines = ["_Sources:_"]
    for s in sources[:5]:
        title = s.get("title") or s.get("act_name") or "Source"
        section = s.get("section")
        cite = s.get("neutral_citation")
        url = s.get("url")
        label = title
        if section:
            label += f" {section}"
        if cite:
            label += f" {cite}"
        if url:
            label += f" — {url}"
        lines.append(f"• {label}")
    return "\n".join(lines)


def format_viability(viability: dict | None) -> str:
    """Render the viability assessment in a single line."""
    if not viability:
        return ""
    score = viability.get("score")
    band = viability.get("vento_band") or viability.get("band")
    if score is None:
        return ""
    line = f"_Viability:_ {score}/100"
    if band:
        line += f" ({band})"
    return line
