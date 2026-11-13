"""Built-in HTTP webhook connector (stdlib ThreadingHTTPServer, no auth).

Contract:
- POST /webhook: JSON object with first non-empty string of text|message|content|body,
  optional sender/channel metadata; or text/plain body as the message text.
- GET /health: 200 {"status": "ok"}.
- 202 queued / 400 bad payload / 404 unknown path / 413 body > 1MB / 503 queue full.
"""

from __future__ import annotations

import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from refer_to_me.config import WebhookConfig
from refer_to_me.connectors.base import Connector, MessageSink, StatusCallback
from refer_to_me.core.message import IncomingMessage

logger = logging.getLogger(__name__)

MAX_BODY = 1024 * 1024
TEXT_FIELDS = ("text", "message", "content", "body")


class _Handler(BaseHTTPRequestHandler):
    server_version = "ReferToMe/0.1"

    def log_message(self, fmt, *args):
        logger.debug("webhook: " + fmt, *args)

    def _respond(self, code: int, payload: dict) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {"status": "ok"})
        else:
            self._respond(404, {"error": "not found"})

    def do_POST(self):
        if self.path != "/webhook":
            self._respond(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        if length > MAX_BODY:
            # Drain a bounded amount so the client can read the 413 response
            # instead of hitting a connection abort mid-upload.
            remaining = min(length, 2 * MAX_BODY)
            while remaining > 0:
                chunk = self.rfile.read(min(remaining, 65536))
                if not chunk:
                    break
                remaining -= len(chunk)
            self._respond(413, {"error": "body too large"})
            return
        body = self.rfile.read(length) if length else b""
        ctype = (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        text: str | None = None
        sender: str | None = None
        channel: str | None = None
        raw: dict | None = None
        if ctype == "text/plain":
            text = body.decode("utf-8", errors="replace")
        else:
            try:
                raw = json.loads(body.decode("utf-8"))
            except (ValueError, UnicodeDecodeError):
                self._respond(400, {"error": "invalid JSON"})
                return
            if not isinstance(raw, dict):
                self._respond(400, {"error": "JSON body must be an object"})
                return
            for field in TEXT_FIELDS:
                value = raw.get(field)
                if isinstance(value, str) and value.strip():
                    text = value
                    break
            if isinstance(raw.get("sender"), str):
                sender = raw["sender"]
            if isinstance(raw.get("channel"), str):
                channel = raw["channel"]
        if not text or not text.strip():
            self._respond(400, {"error": "no text field (text|message|content|body)"})
            return
        msg = IncomingMessage.create(
            source="webhook", text=text, sender=sender, channel=channel, raw=raw
        )
        if not self.server.connector._sink(msg):
            self._respond(503, {"error": "queue full"})
            return
        self._respond(202, {"status": "queued", "id": msg.id})


class WebhookConnector(Connector):
    name = "webhook"

    def __init__(
        self,
        cfg: WebhookConfig,
        sink: MessageSink,
        on_status: StatusCallback | None = None,
    ):
        super().__init__(sink, on_status)
        self._cfg = cfg
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

    @property
    def port(self) -> int:
        """Actual bound port (useful when configured with port=0)."""
        return self._server.server_address[1] if self._server else self._cfg.port

    def start(self) -> None:
        with self._lock:
            if self._server is not None:
                return
            server = ThreadingHTTPServer((self._cfg.host, self._cfg.port), _Handler)
            server.connector = self
            server.daemon_threads = True
            self._server = server
            self._thread = threading.Thread(
                target=server.serve_forever, name="webhook", daemon=True
            )
            self._thread.start()
            self._status("running", f"{self._cfg.host}:{self.port}")

    def stop(self) -> None:
        with self._lock:
            server, self._server = self._server, None
            thread, self._thread = self._thread, None
        if server is not None:
            server.shutdown()
            server.server_close()
        if thread is not None:
            thread.join(timeout=5)
        self._status("stopped", "")
