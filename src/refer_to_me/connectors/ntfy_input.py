"""Built-in ntfy subscription connector: NDJSON stream with reconnect backoff.

Single connection for all topics (ntfy native comma-joined subscription).
``since=latest`` avoids replaying history; messages arriving during a reconnect
window are lost (v1 trade-off, logged on reconnect).
"""

from __future__ import annotations

import json
import logging
import threading

import httpx

from refer_to_me.config import NtfyInputConfig
from refer_to_me.connectors.base import Connector, MessageSink, StatusCallback
from refer_to_me.core.message import IncomingMessage

logger = logging.getLogger(__name__)


def parse_ntfy_line(line: str) -> IncomingMessage | None:
    """Pure parser: message events -> IncomingMessage; anything else -> None."""
    try:
        ev = json.loads(line)
    except ValueError:
        return None
    if not isinstance(ev, dict) or ev.get("event") != "message":
        return None
    text = ev.get("message") or ev.get("title") or ""
    if not isinstance(text, str) or not text.strip():
        return None
    topic = ev.get("topic") or ""
    return IncomingMessage.create(
        source=f"ntfy:{topic}", text=text, channel=topic or None, raw=ev
    )


def backoff_delay(attempt: int) -> float:
    return float(min(2**attempt, 60))


class NtfyInputConnector(Connector):
    name = "ntfy"

    def __init__(
        self,
        cfg: NtfyInputConfig,
        sink: MessageSink,
        on_status: StatusCallback | None = None,
    ):
        super().__init__(sink, on_status)
        self._cfg = cfg
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._response: httpx.Response | None = None
        self._lock = threading.Lock()

    def _url(self) -> str:
        server = self._cfg.server.rstrip("/")
        topics = ",".join(self._cfg.topics)
        return f"{server}/{topics}/json?since=latest"

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, name="ntfy-input", daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        with self._lock:
            resp = self._response
        if resp is not None:
            try:
                resp.close()
            except Exception as exc:  # noqa: BLE001 - unblock iter_lines at any cost
                logger.debug("ntfy response close failed: %s", exc)
        thread = self._thread
        if thread is not None:
            thread.join(timeout=5)
        with self._lock:
            self._thread = None
        self._status("stopped", "")

    def _run(self) -> None:
        attempt = 0
        while not self._stop.is_set():
            try:
                self._status("connecting", self._url())
                timeout = httpx.Timeout(10.0, connect=10.0, read=90.0)
                with (
                    httpx.Client(timeout=timeout) as client,
                    client.stream("GET", self._url()) as resp,
                ):
                    with self._lock:
                        self._response = resp
                    if resp.status_code != 200:
                        raise httpx.HTTPError(f"HTTP {resp.status_code}")
                    self._status("running", ", ".join(self._cfg.topics))
                    attempt = 0
                    for line in resp.iter_lines():
                        if self._stop.is_set():
                            break
                        if not line:
                            continue
                        msg = parse_ntfy_line(line)
                        if msg is None:
                            continue
                        if not self._sink(msg):
                            logger.warning("ntfy message dropped: queue full")
                    with self._lock:
                        self._response = None
            except Exception as exc:  # noqa: BLE001 - reconnect on any stream error
                if self._stop.is_set():
                    break
                self._status("error", f"{type(exc).__name__}: {exc}")
            if self._stop.is_set():
                break
            delay = backoff_delay(attempt)
            attempt += 1
            logger.info(
                "ntfy stream ended; reconnecting in %.0fs (messages in the gap may be lost)",
                delay,
            )
            self._stop.wait(delay)
