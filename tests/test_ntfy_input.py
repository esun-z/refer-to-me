"""ntfy NDJSON parsing and backoff (pure functions, no network)."""

import json

from refer_to_me.connectors.ntfy_input import backoff_delay, parse_ntfy_line


def test_message_event():
    line = json.dumps(
        {"id": "x", "time": 1, "event": "message", "topic": "alerts", "message": "月例会改期"}
    )
    msg = parse_ntfy_line(line)
    assert msg is not None
    assert msg.text == "月例会改期"
    assert msg.source == "ntfy:alerts"
    assert msg.channel == "alerts"


def test_title_fallback():
    line = json.dumps({"event": "message", "topic": "t", "message": "", "title": "标题"})
    assert parse_ntfy_line(line).text == "标题"


def test_open_keepalive_ignored():
    assert parse_ntfy_line(json.dumps({"event": "open", "topic": "t"})) is None
    assert parse_ntfy_line(json.dumps({"event": "keepalive", "topic": "t"})) is None


def test_empty_message_ignored():
    assert parse_ntfy_line(json.dumps({"event": "message", "message": "  "})) is None


def test_bad_lines():
    assert parse_ntfy_line("not json") is None
    assert parse_ntfy_line("") is None
    assert parse_ntfy_line("[1,2,3]") is None


def test_backoff_sequence():
    assert [backoff_delay(i) for i in range(8)] == [1, 2, 4, 8, 16, 32, 60, 60]
