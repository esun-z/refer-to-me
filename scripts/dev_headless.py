"""Headless development harness: QCoreApplication + runtime + console logs.

Usage:
    uv run python scripts/dev_headless.py [--config path.yaml] [--duration 30]

Runs the full pipeline (connectors + classification + alerts) without the GUI.
Qt-bound alert channels (sound/tray) need the GUI; toast/ntfy work headless.
"""

from __future__ import annotations

import argparse
import logging
import signal
import sys

from PySide6.QtCore import QCoreApplication, QTimer

from refer_to_me.alerts.dispatcher import AlertDispatcher
from refer_to_me.config import ConfigStore
from refer_to_me.runtime import AppRuntime, RuntimeSignals


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", help="config YAML path (default: Documents/ReferToMe)")
    parser.add_argument("--duration", type=float, default=0, help="auto-exit after N seconds")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s"
    )
    app = QCoreApplication(sys.argv)
    store = ConfigStore(args.config)
    cfg = store.load()
    if store.load_warning:
        print(f"[config] {store.load_warning}")
    print(f"[config] {store.path}")

    signals = RuntimeSignals()
    signals.log.connect(lambda stage, text: print(f"[{stage}] {text}"))
    signals.engine_status.connect(lambda s, d: print(f"[engine] {s} | {d}"))
    signals.connector_status.connect(lambda n, s, d: print(f"[connector:{n}] {s} | {d}"))
    signals.stats.connect(lambda s: print(f"[stats] {s}"))
    signals.llm_test_result.connect(lambda ok, d: print(f"[llm-test] {ok} | {d}"))

    runtime = AppRuntime(cfg, signals, alert_dispatcher=AlertDispatcher())
    runtime.start()

    if args.duration > 0:
        QTimer.singleShot(int(args.duration * 1000), app.quit)
    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer()  # let Python process SIGINT periodically
    heartbeat.timeout.connect(lambda: None)
    heartbeat.start(200)
    app.aboutToQuit.connect(lambda: runtime.shutdown())
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
