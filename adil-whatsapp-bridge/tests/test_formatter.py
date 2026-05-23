from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from formatter import (  # noqa: E402
    SAFE_SPLIT,
    format_sources,
    format_viability,
    split_for_whatsapp,
    to_whatsapp,
)


def test_headers_become_bold():
    md = "# Direct discrimination\n\nUnder the Equality Act..."
    assert to_whatsapp(md).startswith("*Direct discrimination")


def test_double_star_becomes_single_star():
    assert to_whatsapp("This is **bold** text") == "This is *bold* text"


def test_links_become_label_with_url_in_parens():
    out = to_whatsapp("See [the Act](https://example.com/act)")
    assert out == "See the Act (https://example.com/act)"


def test_bullets_normalised_to_dot():
    out = to_whatsapp("- one\n- two")
    assert "• one" in out and "• two" in out


def test_split_below_limit_is_single_chunk():
    assert split_for_whatsapp("hello world") == ["hello world"]


def test_split_above_limit_numbers_chunks():
    body = ("para. " * (SAFE_SPLIT // 6 + 200)).strip()
    parts = split_for_whatsapp(body)
    assert len(parts) >= 2
    assert parts[0].startswith("(1/")
    assert parts[-1].startswith(f"({len(parts)}/{len(parts)})")
    assert all(len(p) <= SAFE_SPLIT + 20 for p in parts)


def test_format_sources_handles_empty():
    assert format_sources([]) == ""


def test_format_sources_includes_section_and_url():
    out = format_sources(
        [
            {
                "title": "Equality Act 2010",
                "section": "s.13",
                "url": "https://legislation.gov.uk/ukpga/2010/15",
            }
        ]
    )
    assert "Equality Act 2010 s.13" in out
    assert "legislation.gov.uk" in out


def test_format_viability_renders_score_and_band():
    out = format_viability({"score": 75, "band": "Middle"})
    assert "75/100" in out
    assert "Middle" in out


def test_format_viability_handles_missing():
    assert format_viability(None) == ""
    assert format_viability({}) == ""
