from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from handler import (  # noqa: E402
    _classify_jurisdiction_reply,
    _is_consent,
    _is_delete,
    _is_help,
    _is_reset,
    parse_inbound,
)


def _wrap(messages: list[dict]) -> dict:
    return {
        "entry": [
            {
                "changes": [
                    {"value": {"messages": messages}},
                ]
            }
        ]
    }


def test_parse_text_message():
    payload = _wrap(
        [
            {
                "from": "447700900000",
                "id": "wamid.AAA",
                "type": "text",
                "text": {"body": "hello"},
            }
        ]
    )
    out = parse_inbound(payload)
    assert len(out) == 1
    assert out[0].phone == "447700900000"
    assert out[0].text == "hello"
    assert out[0].msg_type == "text"


def test_parse_image_message():
    payload = _wrap(
        [
            {
                "from": "447700900000",
                "id": "wamid.BBB",
                "type": "image",
                "image": {"id": "img-1", "caption": "look at this"},
            }
        ]
    )
    out = parse_inbound(payload)
    assert out[0].msg_type == "image"
    assert out[0].text == "look at this"
    assert out[0].image_id == "img-1"


def test_parse_ignores_statuses():
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "x"}]}}]}]}
    assert parse_inbound(payload) == []


def test_parse_handles_empty_payload():
    assert parse_inbound({}) == []


def test_jurisdiction_classifier():
    assert _classify_jurisdiction_reply("1") == "EW"
    assert _classify_jurisdiction_reply("England & Wales") == "EW"
    assert _classify_jurisdiction_reply("2") == "SCO"
    assert _classify_jurisdiction_reply("scotland") == "SCO"
    assert _classify_jurisdiction_reply("3") == "NI"
    assert _classify_jurisdiction_reply("Northern Ireland") == "NI"
    assert _classify_jurisdiction_reply("dunno") is None


def test_keyword_classifiers():
    assert _is_consent("YES")
    assert _is_consent("i agree")
    assert _is_delete("delete me")
    assert _is_delete("forget me")
    assert _is_reset("reset")
    assert _is_help("help")
    assert not _is_help("hello")
