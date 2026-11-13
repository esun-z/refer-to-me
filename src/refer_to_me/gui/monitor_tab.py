"""Monitor page: engine/connector status, stats, live log, simulated message input."""

from __future__ import annotations

import html
import time

from PySide6.QtCore import QT_TRANSLATE_NOOP
from PySide6.QtWidgets import QHBoxLayout, QVBoxLayout, QWidget
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    InfoBar,
    LineEdit,
    PlainTextEdit,
    PrimaryPushButton,
    PushButton,
    StrongBodyLabel,
)

from refer_to_me.core.message import IncomingMessage
from refer_to_me.runtime import STAT_KEYS

STAT_LABELS = {
    "received": QT_TRANSLATE_NOOP("MonitorTab", "Received"),
    "keyword": QT_TRANSLATE_NOOP("MonitorTab", "Keyword"),
    "laya": QT_TRANSLATE_NOOP("MonitorTab", "Laya"),
    "laya_none": QT_TRANSLATE_NOOP("MonitorTab", "Laya none"),
    "llm": QT_TRANSLATE_NOOP("MonitorTab", "LLM"),
    "llm_none": QT_TRANSLATE_NOOP("MonitorTab", "LLM none"),
    "unclassified": QT_TRANSLATE_NOOP("MonitorTab", "Unclassified"),
    "no_topics": QT_TRANSLATE_NOOP("MonitorTab", "No topics"),
    "alerts": QT_TRANSLATE_NOOP("MonitorTab", "Alerts"),
    "ignored": QT_TRANSLATE_NOOP("MonitorTab", "Ignored"),
}

STAGE_TAGS = {
    "input": QT_TRANSLATE_NOOP("MonitorTab", "Input"),
    "keyword": QT_TRANSLATE_NOOP("MonitorTab", "Keyword"),
    "laya": QT_TRANSLATE_NOOP("MonitorTab", "Laya"),
    "llm": QT_TRANSLATE_NOOP("MonitorTab", "LLM"),
    "alert": QT_TRANSLATE_NOOP("MonitorTab", "Alert"),
    "error": QT_TRANSLATE_NOOP("MonitorTab", "Error"),
    "system": QT_TRANSLATE_NOOP("MonitorTab", "System"),
}

ENGINE_STATES = {
    "unloaded": QT_TRANSLATE_NOOP("MonitorTab", "Unloaded"),
    "loading": QT_TRANSLATE_NOOP("MonitorTab", "Loading"),
    "ready": QT_TRANSLATE_NOOP("MonitorTab", "Ready"),
    "error": QT_TRANSLATE_NOOP("MonitorTab", "Error"),
}

CONNECTOR_STATES = {
    "off": QT_TRANSLATE_NOOP("MonitorTab", "Off"),
    "running": QT_TRANSLATE_NOOP("MonitorTab", "Running"),
    "stopped": QT_TRANSLATE_NOOP("MonitorTab", "Stopped"),
    "connecting": QT_TRANSLATE_NOOP("MonitorTab", "Connecting"),
    "error": QT_TRANSLATE_NOOP("MonitorTab", "Error"),
}

STAGE_COLORS = {
    "input": "#8a8a8a",
    "keyword": "#2e7d32",
    "laya": "#1565c0",
    "llm": "#6a1b9a",
    "alert": "#ef6c00",
    "error": "#c62828",
    "system": "#8a8a8a",
}


class MonitorTab(QWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setObjectName("monitorTab")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # Status card
        status_card = CardWidget(self)
        status_row = QHBoxLayout(status_card)
        self.engine_label = BodyLabel(f"{self.tr('Engine')}: {self.tr('Unloaded')}", status_card)
        self.webhook_label = BodyLabel(f"{self.tr('Webhook')}: {self.tr('Off')}", status_card)
        self.ntfy_label = BodyLabel(f"{self.tr('ntfy')}: {self.tr('Off')}", status_card)
        self.reload_btn = PushButton(self.tr("Reload model"), status_card)
        self.reload_btn.clicked.connect(win.runtime.reload_model)
        status_row.addWidget(self.engine_label)
        status_row.addWidget(self.webhook_label)
        status_row.addWidget(self.ntfy_label)
        status_row.addStretch(1)
        status_row.addWidget(self.reload_btn)
        layout.addWidget(status_card)

        # Stats card
        stats_card = CardWidget(self)
        stats_row = QHBoxLayout(stats_card)
        self.stat_labels: dict[str, StrongBodyLabel] = {}
        for key in STAT_KEYS:
            box = QVBoxLayout()
            box.addWidget(CaptionLabel(self.tr(STAT_LABELS[key]), stats_card))
            value = StrongBodyLabel("0", stats_card)
            box.addWidget(value)
            stats_row.addLayout(box)
            self.stat_labels[key] = value
        layout.addWidget(stats_card)

        # Log
        self.log = PlainTextEdit(self)
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        layout.addWidget(self.log, 1)

        # Bottom row: auto-scroll + simulator
        bottom = QHBoxLayout()
        self.autoscroll = CheckBox(self.tr("Auto-scroll"), self)
        self.autoscroll.setChecked(True)
        self.sim_input = LineEdit(self)
        self.sim_input.setPlaceholderText(self.tr("Type a simulated message to test the pipeline…"))
        self.sim_send = PrimaryPushButton(self.tr("Send test message"), self)
        bottom.addWidget(self.autoscroll)
        bottom.addWidget(self.sim_input, 1)
        bottom.addWidget(self.sim_send)
        layout.addLayout(bottom)
        self.sim_send.clicked.connect(self._send_sim)
        self.sim_input.returnPressed.connect(self._send_sim)

        win.signals.log.connect(self.append_log)
        win.signals.stats.connect(self.update_stats)
        win.signals.engine_status.connect(self.update_engine)
        win.signals.connector_status.connect(self.update_connector)

    def _send_sim(self) -> None:
        text = self.sim_input.text().strip()
        if not text:
            return
        msg = IncomingMessage.create(source="simulator", text=text)
        if self.win.runtime.submit_message(msg):
            self.sim_input.clear()
        else:
            InfoBar.warning(
                self.tr("Queue full"),
                self.tr("The pipeline queue is full; try again shortly."),
                parent=self,
                duration=4000,
            )

    def append_log(self, stage: str, text: str) -> None:
        color = STAGE_COLORS.get(stage, "#8a8a8a")
        tag = self.tr(STAGE_TAGS.get(stage, stage))
        stamp = time.strftime("%H:%M:%S")
        self.log.appendHtml(
            f'<span style="color:{color};font-weight:bold">[{html.escape(tag)}]</span> '
            f'<span style="color:#8a8a8a">{stamp}</span> {html.escape(text)}'
        )
        if self.autoscroll.isChecked():
            scrollbar = self.log.verticalScrollBar()
            scrollbar.setValue(scrollbar.maximum())

    def update_stats(self, stats: dict) -> None:
        for key, label in self.stat_labels.items():
            label.setText(str(stats.get(key, 0)))

    def update_engine(self, state: str, detail: str) -> None:
        state_text = self.tr(ENGINE_STATES.get(state, state))
        self.engine_label.setText(f"{self.tr('Engine')}: {state_text}")
        self.engine_label.setToolTip(detail)

    def update_connector(self, name: str, state: str, detail: str) -> None:
        label = self.webhook_label if name == "webhook" else self.ntfy_label
        prefix = "Webhook" if name == "webhook" else "ntfy"
        state_text = self.tr(CONNECTOR_STATES.get(state, state))
        label.setText(f"{self.tr(prefix)}: {state_text}")
        label.setToolTip(detail)
