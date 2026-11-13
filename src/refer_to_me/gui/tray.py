"""System tray icon (runtime-painted, zero binary assets)."""

from __future__ import annotations

from PySide6.QtCore import QCoreApplication, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import QMenu, QSystemTrayIcon


def tr(text: str) -> str:
    return QCoreApplication.translate("MainWindow", text)


def make_icon() -> QIcon:
    pix = QPixmap(64, 64)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QColor("#0078D4"))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawEllipse(2, 2, 60, 60)
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Segoe UI", 30, QFont.Weight.Bold))
    painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "R")
    painter.end()
    return QIcon(pix)


def create_tray(win) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(make_icon(), win)
    menu = QMenu(win)
    show_action = menu.addAction(tr("Show main window"))
    quit_action = menu.addAction(tr("Quit"))
    show_action.triggered.connect(win.showNormal)
    quit_action.triggered.connect(win.quit_from_tray)
    tray.setContextMenu(menu)
    tray.activated.connect(
        lambda reason: (
            win.showNormal()
            if reason == QSystemTrayIcon.ActivationReason.DoubleClick
            else None
        )
    )
    tray.setToolTip("Refer to Me")
    tray.show()
    return tray
