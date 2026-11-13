"""Webhook connector against a real ephemeral-port server (no auth)."""

import http.client
import json

import pytest

from refer_to_me.config import WebhookConfig
from refer_to_me.connectors.webhook import WebhookConnector


def make_connector(sink):
    conn = WebhookConnector(WebhookConfig(enabled=True, host="127.0.0.1", port=0), sink)
    conn.start()
    return conn


def request(conn, method, path, body=None, ctype="application/json"):
    c = http.client.HTTPConnection("127.0.0.1", conn.port, timeout=5)
    headers = {"Content-Type": ctype} if body is not None else {}
    c.request(method, path, body=body, headers=headers)
    resp = c.getresponse()
    data = resp.read()
    c.close()
    return resp.status, json.loads(data) if data else None


@pytest.fixture
def server():
    received = []

    def sink(msg):
        received.append(msg)
        return True

    conn = make_connector(sink)
    yield conn, received
    conn.stop()


def test_json_text_field(server):
    conn, received = server
    status, payload = request(conn, "POST", "/webhook", json.dumps({"text": "下周月例会"}))
    assert status == 202
    assert payload["status"] == "queued"
    assert len(received) == 1
    assert received[0].text == "下周月例会"
    assert received[0].source == "webhook"
    assert received[0].id == payload["id"]


def test_field_fallback_order(server):
    conn, received = server
    for field in ("message", "content", "body"):
        status, _ = request(conn, "POST", "/webhook", json.dumps({field: f"via {field}"}))
        assert status == 202
    assert [m.text for m in received] == ["via message", "via content", "via body"]


def test_metadata(server):
    conn, received = server
    body = {"text": "hi", "sender": "alice", "channel": "general"}
    status, _ = request(conn, "POST", "/webhook", json.dumps(body))
    assert status == 202
    assert received[0].sender == "alice"
    assert received[0].channel == "general"


def test_text_plain(server):
    conn, received = server
    status, _ = request(
        conn, "POST", "/webhook", "纯文本消息".encode(), ctype="text/plain"
    )
    assert status == 202
    assert received[0].text == "纯文本消息"


def test_missing_text_400(server):
    conn, received = server
    status, _payload = request(conn, "POST", "/webhook", json.dumps({"other": 1}))
    assert status == 400
    assert received == []


def test_invalid_json_400(server):
    conn, _ = server
    status, _ = request(conn, "POST", "/webhook", "{not json")
    assert status == 400


def test_unknown_path_404(server):
    conn, _ = server
    assert request(conn, "GET", "/nope")[0] == 404
    assert request(conn, "POST", "/nope", "{}")[0] == 404


def test_health(server):
    conn, _ = server
    status, payload = request(conn, "GET", "/health")
    assert status == 200
    assert payload == {"status": "ok"}


def test_body_too_large_413(server):
    conn, received = server
    status, _ = request(conn, "POST", "/webhook", "x" * (1024 * 1024 + 1), ctype="text/plain")
    assert status == 413
    assert received == []


def test_queue_full_503():
    conn = make_connector(lambda msg: False)
    try:
        status, payload = request(conn, "POST", "/webhook", json.dumps({"text": "hi"}))
        assert status == 503
        assert payload["error"] == "queue full"
    finally:
        conn.stop()


def test_stop_releases_port(server):
    conn, _ = server
    port = conn.port
    conn.stop()
    # port can be rebound after stop
    conn2 = WebhookConnector(
        WebhookConfig(enabled=True, host="127.0.0.1", port=port), lambda m: True
    )
    conn2.start()
    conn2.stop()
