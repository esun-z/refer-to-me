"""Thread bridge: alert thread -> GUI thread for Qt-bound channels (sound, tray)."""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal


class AlertBridge(QObject):
    sound_requested = Signal(str)  # sound file path ("" = built-in default)
    tray_requested = Signal(str, str)  # title, body

    def play_sound(self, sound_file: str) -> None:
        self.sound_requested.emit(sound_file)

    def show_tray_message(self, title: str, body: str) -> None:
        self.tray_requested.emit(title, body)
