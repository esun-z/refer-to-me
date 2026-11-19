"""AppRuntime: pipeline worker thread + alert thread + connectors + Qt signal bridge.

The only shared mutable state is the queues. Configuration is an immutable
snapshot; the worker swaps its reference between messages (ConfigUpdate control
item). Stats counters have a single writer per key (worker, except ``alerts``
which only the alert thread writes).
"""

from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal

from refer_to_me.config import AppConfig
from refer_to_me.connectors.base import Connector
from refer_to_me.connectors.ntfy_input import NtfyInputConnector
from refer_to_me.connectors.webhook import WebhookConnector
from refer_to_me.core.laya_engine import LayaEngine
from refer_to_me.core.llm_engine import LlmEngine
from refer_to_me.core.message import IncomingMessage
from refer_to_me.core.pipeline import Pipeline
from refer_to_me.core.recorder import Recorder

logger = logging.getLogger(__name__)

QUEUE_MAX = 1000

STAT_KEYS = (
    "received",
    "keyword",
    "laya",
    "llm",
    "no_match",
    "unclassified",
    "no_topics",
    "alerts",
    "ignored",
)


class RuntimeSignals(QObject):
    log = Signal(str, str)  # stage, text
    stats = Signal(dict)
    engine_status = Signal(str, str)  # state, detail
    connector_status = Signal(str, str, str)  # name, state, detail
    llm_test_result = Signal(bool, str)


@dataclass(frozen=True)
class ConfigUpdate:
    cfg: AppConfig


@dataclass(frozen=True)
class ReloadModel:
    pass


@dataclass(frozen=True)
class TestLlm:
    pass


@dataclass(frozen=True)
class Shutdown:
    pass


class AppRuntime:
    def __init__(
        self,
        cfg: AppConfig,
        signals: RuntimeSignals,
        alert_dispatcher=None,
        laya_engine=None,
        llm_engine=None,
    ):
        self._cfg = cfg  # GUI-side view (connector lifecycle)
        self._worker_cfg = cfg  # worker-owned snapshot
        self._signals = signals
        self._queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAX)
        self._alert_queue: queue.Queue = queue.Queue()
        self._dispatcher = alert_dispatcher
        self._engine = laya_engine or LayaEngine(
            cfg.laya,
            on_status=lambda s, d: signals.engine_status.emit(s.value, d),
        )
        self._llm = llm_engine or LlmEngine(cfg.llm)
        self._pipeline = Pipeline(self._engine, self._llm)
        self._recorder = Recorder(cfg.dataset_path())
        self._stats = dict.fromkeys(STAT_KEYS, 0)
        self._worker: threading.Thread | None = None
        self._alert_worker: threading.Thread | None = None
        self._connectors: list[Connector] = []
        self._stopping = False

    # ------------------------------------------------------------------ lifecycle
    def start(self) -> None:
        self._start_connectors()
        self._worker = threading.Thread(target=self._run_worker, name="pipeline", daemon=True)
        self._worker.start()
        self._alert_worker = threading.Thread(target=self._run_alerts, name="alerts", daemon=True)
        self._alert_worker.start()

    def shutdown(self, timeout: float = 5.0) -> None:
        if self._stopping:
            return
        self._stopping = True
        self._stop_connectors()
        try:
            self._queue.put_nowait(Shutdown())
        except queue.Full:
            pass  # daemon worker dies with the process
        if self._worker is not None:
            self._worker.join(timeout=timeout)
        self._alert_queue.put(None)
        if self._alert_worker is not None:
            self._alert_worker.join(timeout=timeout)

    # ------------------------------------------------------------------ public API
    def submit_message(self, msg: IncomingMessage) -> bool:
        try:
            self._queue.put_nowait(msg)
            return True
        except queue.Full:
            return False

    def apply_config(self, cfg: AppConfig) -> None:
        """GUI thread: restart connectors if needed, then hand the snapshot to the worker."""
        old = self._cfg
        self._cfg = cfg
        if old.webhook != cfg.webhook or old.ntfy_input != cfg.ntfy_input:
            self._stop_connectors()
            self._start_connectors()
        self._queue.put(ConfigUpdate(cfg))

    def reload_model(self) -> None:
        self._queue.put(ReloadModel())

    def test_llm(self) -> None:
        self._queue.put(TestLlm())

    # ------------------------------------------------------------------ worker
    def _run_worker(self) -> None:
        # Eager load at startup so the first message is not delayed — but only
        # when some enabled topic actually uses Laya (keyword-only setups never
        # need the model).
        if any(t.laya_enabled for t in self._worker_cfg.enabled_topics()):
            try:
                self._engine.ensure_loaded()
            except Exception as exc:  # noqa: BLE001 - ERROR state; manual reload only
                self._signals.log.emit("error", f"Model load failed: {exc}")
        while True:
            item = self._queue.get()
            match item:
                case Shutdown():
                    break
                case ConfigUpdate(cfg):
                    self._apply_cfg(cfg)
                case ReloadModel():
                    try:
                        self._engine.force_reload()
                    except Exception as exc:  # noqa: BLE001
                        self._signals.log.emit("error", f"Model reload failed: {exc}")
                case TestLlm():
                    ok, detail = self._llm.test_connection()
                    self._signals.llm_test_result.emit(ok, detail)
                case IncomingMessage() as msg:
                    self._process(msg)
        self._engine.unload()

    def _apply_cfg(self, cfg: AppConfig) -> None:
        old = self._worker_cfg
        self._worker_cfg = cfg
        try:
            self._engine.reload_if_needed(cfg.laya)
        except Exception as exc:  # noqa: BLE001
            self._signals.log.emit("error", f"Model reload failed: {exc}")
        if cfg.llm != old.llm:
            self._llm = LlmEngine(cfg.llm)
            self._pipeline = Pipeline(self._engine, self._llm)
        if cfg.dataset_path() != old.dataset_path():
            self._recorder = Recorder(cfg.dataset_path())

    def _process(self, msg: IncomingMessage) -> None:
        if not msg.text.strip():
            self._stats["ignored"] += 1
            self._signals.log.emit("system", "Empty message ignored")
            self._signals.stats.emit(dict(self._stats))
            return
        self._stats["received"] += 1
        result = self._pipeline.process(msg, self._worker_cfg, self._recorder)
        for ev in result.events:
            self._signals.log.emit(ev.stage, ev.text)
        self._stats[result.stage.value] += 1
        if result.alert_kind is not None:
            self._enqueue_alert(msg, result)
        self._signals.stats.emit(dict(self._stats))

    def _enqueue_alert(self, msg: IncomingMessage, result) -> None:
        from refer_to_me.alerts.dispatcher import AlertRequest

        if result.alert_kind == "topics":
            by_id = {t.id: t for t in self._worker_cfg.topics}
            topics = tuple(by_id[i] for i in result.matched_topic_ids if i in by_id)
        else:
            topics = ()
        self._alert_queue.put(
            AlertRequest(
                message=msg, kind=result.alert_kind, topics=topics, cfg=self._worker_cfg
            )
        )

    # ------------------------------------------------------------------ alert thread
    def _run_alerts(self) -> None:
        while True:
            req = self._alert_queue.get()
            if req is None:
                break
            if self._dispatcher is None:
                self._signals.log.emit("alert", f"(no dispatcher) {req.kind}")
                continue
            try:
                ok_channels = self._dispatcher.dispatch(req)
            except Exception as exc:  # noqa: BLE001 - never kill the alert thread
                self._signals.log.emit("error", f"Alert dispatch failed: {exc}")
                continue
            if ok_channels:
                self._stats["alerts"] += 1
                self._signals.log.emit("alert", "sent via: " + ", ".join(ok_channels))
                self._signals.stats.emit(dict(self._stats))
            else:
                self._log_silent_or_failed(req)

    def _log_silent_or_failed(self, req) -> None:
        """Distinguish a filter entry (no channels by design) from a failure."""
        if req.kind == "topics":
            configured = {ch for t in req.topics for ch in t.channels}
            subject = " ".join(f"「{t.name}」" for t in req.topics)
            silent_text = f"silent: {subject} matched but no alert channels configured (filter)"
        else:
            configured = set(req.cfg.unclassified.channels)
            subject = "unclassified message"
            silent_text = "silent: unclassified message; no alert channels configured"
        if not configured:
            self._signals.log.emit("alert", silent_text)
        else:
            tried = ", ".join(sorted(ch.value for ch in configured))
            self._signals.log.emit(
                "error", f"alert failed for {subject}: no channel succeeded (tried: {tried})"
            )

    # ------------------------------------------------------------------ connectors
    def _start_connectors(self) -> None:
        cfg = self._cfg

        def sink(msg: IncomingMessage) -> bool:
            try:
                self._queue.put_nowait(msg)
                return True
            except queue.Full:
                return False

        def status(name: str):
            return lambda state, detail: self._signals.connector_status.emit(name, state, detail)

        if cfg.webhook.enabled:
            connector = WebhookConnector(cfg.webhook, sink, status("webhook"))
            try:
                connector.start()
                self._connectors.append(connector)
            except OSError as exc:
                self._signals.log.emit("error", f"Webhook start failed: {exc}")
        if cfg.ntfy_input.enabled:
            connector = NtfyInputConnector(cfg.ntfy_input, sink, status("ntfy"))
            connector.start()
            self._connectors.append(connector)

    def _stop_connectors(self) -> None:
        for connector in self._connectors:
            try:
                connector.stop()
            except Exception as exc:  # noqa: BLE001
                logger.error("connector %s stop failed: %s", connector.name, exc)
        self._connectors.clear()
