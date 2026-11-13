"""Alert dispatch: per-topic channel union with per-channel dedup.

Runs on the alert thread. sound/qt are marshaled to the GUI thread via
AlertBridge signals; toast/ntfy execute locally. Each channel is isolated:
one failure never blocks the others.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Literal

from PySide6.QtCore import QCoreApplication

from refer_to_me.alerts.bridge import AlertBridge
from refer_to_me.alerts.windows_toast import WindowsToastChannel
from refer_to_me.config import AlertChannel, AppConfig, TopicConfig
from refer_to_me.core.message import IncomingMessage

logger = logging.getLogger(__name__)


def tr(text: str, n: int = -1) -> str:
    return QCoreApplication.translate("Alerts", text, n=n)


@dataclass(frozen=True)
class AlertRequest:
    message: IncomingMessage
    kind: Literal["topics", "unclassified"]
    topics: tuple[TopicConfig, ...]  # empty for unclassified
    cfg: AppConfig


class AlertDispatcher:
    def __init__(
        self,
        bridge: AlertBridge | None = None,
        toaster_factory=None,
        publisher=None,
    ):
        self._bridge = bridge
        self._toaster_factory = toaster_factory
        self._publisher = publisher
        self._toast_channel: WindowsToastChannel | None = None

    def dispatch(self, req: AlertRequest) -> list[str]:
        """Fire the union of channels once per message; return successful channel names."""
        if req.kind == "topics":
            channels = {ch for t in req.topics for ch in t.channels}
            names = " ".join(f"「{t.name}」" for t in req.topics)
            title = tr("Refer to Me · %n topic(s) matched", n=len(req.topics))
            body = names + "\n" + req.message.text[:200]
        else:
            channels = set(req.cfg.unclassified.channels)
            title = tr("Unclassified message")
            body = req.message.text[:200]
        ok: list[str] = []
        for ch in sorted(channels, key=lambda c: c.value):
            try:
                self._fire(ch, title, body, req)
                ok.append(ch.value)
            except Exception as exc:  # noqa: BLE001 - channel isolation
                logger.error("alert channel %s failed: %s", ch.value, exc)
        return ok

    def _fire(self, ch: AlertChannel, title: str, body: str, req: AlertRequest) -> None:
        if ch == AlertChannel.SOUND:
            if self._bridge is None:
                raise RuntimeError("no alert bridge (headless?)")
            self._bridge.play_sound(req.cfg.sound_file)
        elif ch == AlertChannel.QT:
            if self._bridge is None:
                raise RuntimeError("no alert bridge (headless?)")
            self._bridge.show_tray_message(title, body)
        elif ch == AlertChannel.TOAST:
            if self._toast_channel is None:
                self._toast_channel = WindowsToastChannel(
                    toaster_factory=self._toaster_factory
                )
            self._toast_channel.show(title, body)
        elif ch == AlertChannel.NTFY:
            if self._publisher is not None:
                self._publisher(req.cfg.ntfy_publish, title, body)
            else:
                from refer_to_me.alerts.ntfy_publish import publish

                publish(req.cfg.ntfy_publish, title, body)
