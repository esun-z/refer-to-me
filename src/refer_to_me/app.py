"""Application assembly: config -> i18n -> Qt app -> Fluent window -> runtime."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from platformdirs import user_data_dir


def _setup_logging() -> None:
    log_dir = Path(user_data_dir("ReferToMe", appauthor=False))
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        handlers=[
            logging.FileHandler(log_dir / "app.log", encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def run() -> None:
    from PySide6.QtCore import QLocale, QTranslator
    from PySide6.QtWidgets import QApplication
    from qfluentwidgets import Theme, setTheme

    from refer_to_me.alerts.bridge import AlertBridge
    from refer_to_me.alerts.dispatcher import AlertDispatcher
    from refer_to_me.config import ConfigStore
    from refer_to_me.gui.main_window import MainWindow
    from refer_to_me.runtime import AppRuntime, RuntimeSignals

    _setup_logging()
    store = ConfigStore()
    cfg = store.load()

    app = QApplication(sys.argv)
    app.setApplicationName("Refer to Me")
    app.setQuitOnLastWindowClosed(False)  # tray keeps the app alive

    language = cfg.language
    if language == "auto":
        language = QLocale.system().name()
    if language.startswith("zh"):
        translator = QTranslator()
        qm_path = Path(__file__).parent / "i18n" / "zh_CN.qm"
        if translator.load(str(qm_path)):
            app.installTranslator(translator)
            # Plural-form selection follows the locale; match it to the translation.
            QLocale.setDefault(QLocale("zh_CN"))

    setTheme(Theme.AUTO)

    signals = RuntimeSignals()
    bridge = AlertBridge()
    runtime = AppRuntime(cfg, signals, alert_dispatcher=AlertDispatcher(bridge=bridge))
    win = MainWindow(cfg, store, runtime, signals, bridge)
    runtime.start()
    app.aboutToQuit.connect(lambda: runtime.shutdown())

    if not cfg.start_minimized:
        win.show()
    sys.exit(app.exec())
