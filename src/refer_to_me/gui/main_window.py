"""Fluent main window: navigation, global Save, tray integration, alert slots."""

from __future__ import annotations

from pydantic import ValidationError
from PySide6.QtCore import QUrl
from PySide6.QtMultimedia import QSoundEffect
from PySide6.QtWidgets import QApplication
from qfluentwidgets import (
    FluentIcon,
    FluentWindow,
    InfoBar,
    NavigationItemPosition,
    PrimaryPushButton,
)

from refer_to_me.alerts.qt_notify import show_tray_message
from refer_to_me.alerts.sound import resolve_sound_path
from refer_to_me.config import AppConfig
from refer_to_me.gui.monitor_tab import MonitorTab
from refer_to_me.gui.settings_tab import SettingsTab
from refer_to_me.gui.topics_tab import TopicsTab
from refer_to_me.gui.tray import create_tray


class MainWindow(FluentWindow):
    def __init__(self, cfg, store, runtime, signals, bridge):
        super().__init__()
        self.draft: AppConfig = cfg
        self.store = store
        self.runtime = runtime
        self.signals = signals
        self.bridge = bridge
        self._really_quit = False
        self._tray_hint_shown = False

        self.setWindowTitle("Refer to Me")
        self.resize(1080, 720)

        self.monitor_tab = MonitorTab(self)
        self.topics_tab = TopicsTab(self)
        self.settings_tab = SettingsTab(self)
        self.addSubInterface(self.monitor_tab, FluentIcon.HOME, self.tr("Monitor"))
        self.addSubInterface(self.topics_tab, FluentIcon.LABEL, self.tr("Topics"))
        self.addSubInterface(
            self.settings_tab,
            FluentIcon.SETTING,
            self.tr("Settings"),
            NavigationItemPosition.BOTTOM,
        )

        # Global Save button in the title bar (single save point).
        self.save_btn = PrimaryPushButton(self.tr("Save"), self)
        self.save_btn.clicked.connect(self.save_config)
        self.titleBar.hBoxLayout.insertWidget(
            self.titleBar.hBoxLayout.count() - 3, self.save_btn
        )

        self.tray = create_tray(self)
        self._sound = QSoundEffect(self)
        bridge.sound_requested.connect(self.play_sound)
        bridge.tray_requested.connect(self._tray_message)
        signals.llm_test_result.connect(self._llm_result)

        if store.load_warning:
            InfoBar.warning(
                self.tr("Configuration"), store.load_warning, parent=self, duration=8000
            )

    # ------------------------------------------------------------------ config
    def save_config(self) -> None:
        try:
            cfg = AppConfig.model_validate(self.draft.model_dump())
        except ValidationError as exc:
            InfoBar.error(
                self.tr("Invalid configuration"), str(exc), parent=self, duration=8000
            )
            return
        self.store.save(cfg)
        self.draft = cfg
        self.runtime.apply_config(cfg)
        InfoBar.success(
            self.tr("Saved"),
            self.tr("Configuration saved and applied."),
            parent=self,
            duration=3000,
        )

    def refresh_tabs(self) -> None:
        self.topics_tab.refresh()
        self.settings_tab.refresh()

    # ------------------------------------------------------------------ alerts
    def play_sound(self, sound_file: str) -> None:
        try:
            path = resolve_sound_path(sound_file)
            self._sound.setSource(QUrl.fromLocalFile(str(path)))
            self._sound.play()
        except Exception:  # noqa: BLE001 - fall back to system beep
            QApplication.beep()

    def _tray_message(self, title: str, body: str) -> None:
        show_tray_message(self.tray, title, body)

    def _llm_result(self, ok: bool, detail: str) -> None:
        if ok:
            InfoBar.success(self.tr("LLM connection"), detail, parent=self, duration=5000)
        else:
            InfoBar.error(self.tr("LLM connection"), detail, parent=self, duration=8000)

    # ------------------------------------------------------------------ close / tray
    def quit_from_tray(self) -> None:
        self._really_quit = True
        self.close()

    def closeEvent(self, event) -> None:
        if self._really_quit or self.tray is None or not self.tray.isVisible():
            self._really_quit = True
            event.accept()
            QApplication.quit()
            return
        event.ignore()
        self.hide()
        if not self._tray_hint_shown:
            self._tray_hint_shown = True
            self.tray.showMessage(
                self.tr("Refer to Me"),
                self.tr("Still running in the tray. Use the tray menu to quit."),
            )
