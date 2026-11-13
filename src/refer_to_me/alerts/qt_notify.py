"""Qt tray notification helper (GUI thread only).

QSystemTrayIcon.showMessage silently does nothing when the tray icon is not
visible; Windows truncates title to 64 and body to 256 chars.
"""

from __future__ import annotations

import logging

from PySide6.QtWidgets import QSystemTrayIcon

logger = logging.getLogger(__name__)


def show_tray_message(tray: QSystemTrayIcon | None, title: str, body: str) -> bool:
    if tray is None or not tray.isVisible():
        logger.warning("tray notification skipped: tray icon not visible")
        return False
    if not QSystemTrayIcon.isSystemTrayAvailable() or not QSystemTrayIcon.supportsMessages():
        logger.warning("tray notification skipped: not supported on this platform")
        return False
    tray.showMessage(
        title[:64], body[:256], QSystemTrayIcon.MessageIcon.Information, 10000
    )
    return True
