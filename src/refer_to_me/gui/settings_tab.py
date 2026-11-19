"""Settings page: Laya / LLM / connectors / ntfy / unclassified / general / config file."""

from __future__ import annotations

from pathlib import Path

import yaml
from PySide6.QtCore import QCoreApplication, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CardWidget,
    ComboBox,
    InfoBar,
    LineEdit,
    PasswordLineEdit,
    PushButton,
    ScrollArea,
    SubtitleLabel,
    SwitchButton,
)

from refer_to_me.config import AlertChannel, AppConfig
from refer_to_me.gui.topics_tab import CHANNEL_LABELS
from refer_to_me.gui.widgets import DoubleSpinBox, SpinBox


class SettingsTab(QWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setObjectName("settingsTab")
        self._loading = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        container = QWidget()
        container.setObjectName("settingsContainer")
        self.cards = QVBoxLayout(container)
        self.cards.setContentsMargins(0, 0, 12, 0)
        self.cards.setSpacing(12)

        self._build_laya_card(container)
        self._build_llm_card(container)
        self._build_webhook_card(container)
        self._build_ntfy_input_card(container)
        self._build_ntfy_publish_card(container)
        self._build_unclassified_card(container)
        self._build_general_card(container)
        self._build_config_card(container)
        self.cards.addStretch(1)

        scroll.setWidget(container)
        root.addWidget(scroll)
        self.refresh()

    # ------------------------------------------------------------------ helpers
    def _card(self, parent, title: str) -> QFormLayout:
        card = CardWidget(parent)
        outer = QVBoxLayout(card)
        outer.addWidget(SubtitleLabel(title, card))
        form = QFormLayout()
        outer.addLayout(form)
        self.cards.addWidget(card)
        return form

    def _update(self, section: str | None, **kwargs) -> None:
        if self._loading:
            return
        draft = self.win.draft
        if section is None:
            self.win.draft = draft.model_copy(update=kwargs)
        else:
            self.win.draft = draft.model_copy(
                update={section: getattr(draft, section).model_copy(update=kwargs)}
            )

    # ------------------------------------------------------------------ cards
    def _build_laya_card(self, parent) -> None:
        form = self._card(parent, self.tr("Laya engine"))
        self.laya_mode = ComboBox(parent)
        self.laya_mode.addItems(["router", "english", "multilingual"])
        self.laya_mode.currentIndexChanged.connect(
            lambda i: self._update("laya", mode=self.laya_mode.itemText(i))
        )
        path_row = QHBoxLayout()
        self.laya_local_path = LineEdit(parent)
        self.laya_local_path.setPlaceholderText(self.tr("Optional local checkpoint directory"))
        browse = PushButton(self.tr("Browse…"), parent)
        browse.clicked.connect(self._browse_local_model)
        path_row.addWidget(self.laya_local_path, 1)
        path_row.addWidget(browse)
        self.laya_local_path.textChanged.connect(
            lambda t: self._update("laya", local_path=t)
        )
        self.laya_device = ComboBox(parent)
        self.laya_device.addItems(["auto", "cuda", "cpu"])
        self.laya_device.currentIndexChanged.connect(
            lambda i: self._update("laya", device=self.laya_device.itemText(i))
        )
        form.addRow(self.tr("Mode"), self.laya_mode)
        form.addRow(self.tr("Local model"), path_row)
        form.addRow(self.tr("Device"), self.laya_device)
        hint = BodyLabel(
            self.tr(
                "router: auto-routes per message language (recommended for mixed Chinese/English). "
                "english: English-only checkpoint. multilingual: 100+ languages. "
                "Local model applies to english/multilingual modes."
            ),
            parent,
        )
        hint.setWordWrap(True)
        form.addRow(hint)
        per_topic_hint = BodyLabel(
            self.tr(
                "Matching order, the Laya/LLM switches and the confidence thresholds are "
                "configured per topic on the Topics page."
            ),
            parent,
        )
        per_topic_hint.setWordWrap(True)
        form.addRow(per_topic_hint)

    def _build_llm_card(self, parent) -> None:
        form = self._card(parent, self.tr("LLM fallback (OpenAI-compatible)"))
        self.llm_base_url = LineEdit(parent)
        self.llm_base_url.setPlaceholderText("http://127.0.0.1:8080/v1")
        self.llm_base_url.textChanged.connect(lambda t: self._update("llm", base_url=t))
        self.llm_api_key = PasswordLineEdit(parent)
        self.llm_api_key.textChanged.connect(lambda t: self._update("llm", api_key=t))
        self.llm_model = LineEdit(parent)
        self.llm_model.textChanged.connect(lambda t: self._update("llm", model=t))
        self.llm_mode = ComboBox(parent)
        self.llm_mode.addItems(["JSON", "MD_JSON", "TOOLS"])
        self.llm_mode.currentIndexChanged.connect(
            lambda i: self._update("llm", mode=self.llm_mode.itemText(i))
        )
        self.llm_timeout = DoubleSpinBox(parent)
        self.llm_timeout.setRange(1.0, 300.0)
        self.llm_timeout.valueChanged.connect(lambda v: self._update("llm", timeout_s=v))
        self.llm_retries = SpinBox(parent)
        self.llm_retries.setRange(0, 5)
        self.llm_retries.valueChanged.connect(lambda v: self._update("llm", max_retries=v))
        self.llm_test_btn = PushButton(self.tr("Test connection"), parent)
        self.llm_test_btn.clicked.connect(self.win.runtime.test_llm)
        form.addRow(self.tr("Base URL"), self.llm_base_url)
        form.addRow(self.tr("API key"), self.llm_api_key)
        form.addRow(self.tr("Model"), self.llm_model)
        form.addRow(self.tr("Mode"), self.llm_mode)
        form.addRow(self.tr("Timeout (s)"), self.llm_timeout)
        form.addRow(self.tr("Max retries"), self.llm_retries)
        form.addRow("", self.llm_test_btn)
        llm_hint = BodyLabel(
            self.tr(
                "Connection settings are global. Whether the LLM is consulted for a topic "
                "is decided by that topic's 'Use LLM when uncertain' switch on the Topics "
                "page (requires Laya enabled for the topic)."
            ),
            parent,
        )
        llm_hint.setWordWrap(True)
        form.addRow(llm_hint)

    def _build_webhook_card(self, parent) -> None:
        form = self._card(parent, self.tr("Webhook input"))
        self.webhook_enabled = SwitchButton(parent)
        self.webhook_enabled.checkedChanged.connect(lambda v: self._update("webhook", enabled=v))
        self.webhook_host = LineEdit(parent)
        self.webhook_host.textChanged.connect(lambda t: self._update("webhook", host=t))
        self.webhook_port = SpinBox(parent)
        self.webhook_port.setRange(1, 65535)
        self.webhook_port.valueChanged.connect(lambda v: self._update("webhook", port=v))
        form.addRow(self.tr("Enabled"), self.webhook_enabled)
        form.addRow(self.tr("Host"), self.webhook_host)
        form.addRow(self.tr("Port"), self.webhook_port)
        hint = BodyLabel(self.tr("POST /webhook with JSON {text|message|content|body} or text/plain. GET /health."), parent)
        hint.setWordWrap(True)
        form.addRow(hint)

    def _build_ntfy_input_card(self, parent) -> None:
        form = self._card(parent, self.tr("ntfy subscribe (input)"))
        self.ntfy_in_enabled = SwitchButton(parent)
        self.ntfy_in_enabled.checkedChanged.connect(lambda v: self._update("ntfy_input", enabled=v))
        self.ntfy_in_server = LineEdit(parent)
        self.ntfy_in_server.setPlaceholderText("https://ntfy.example.com")
        self.ntfy_in_server.textChanged.connect(lambda t: self._update("ntfy_input", server=t))
        self.ntfy_in_topics = LineEdit(parent)
        self.ntfy_in_topics.setPlaceholderText(self.tr("comma-separated topics"))
        self.ntfy_in_topics.textChanged.connect(self._sync_ntfy_topics)
        form.addRow(self.tr("Enabled"), self.ntfy_in_enabled)
        form.addRow(self.tr("Server"), self.ntfy_in_server)
        form.addRow(self.tr("Topics"), self.ntfy_in_topics)

    def _build_ntfy_publish_card(self, parent) -> None:
        form = self._card(parent, self.tr("ntfy publish (alerts)"))
        self.ntfy_pub_server = LineEdit(parent)
        self.ntfy_pub_server.textChanged.connect(lambda t: self._update("ntfy_publish", server=t))
        self.ntfy_pub_topic = LineEdit(parent)
        self.ntfy_pub_topic.textChanged.connect(lambda t: self._update("ntfy_publish", topic=t))
        self.ntfy_pub_priority = SpinBox(parent)
        self.ntfy_pub_priority.setRange(1, 5)
        self.ntfy_pub_priority.valueChanged.connect(lambda v: self._update("ntfy_publish", priority=v))
        form.addRow(self.tr("Server"), self.ntfy_pub_server)
        form.addRow(self.tr("Topic"), self.ntfy_pub_topic)
        form.addRow(self.tr("Priority"), self.ntfy_pub_priority)

    def _build_unclassified_card(self, parent) -> None:
        form = self._card(parent, self.tr("Unclassified message alerts"))
        self.unclassified_boxes: dict[AlertChannel, object] = {}
        for channel, label in CHANNEL_LABELS.items():
            box = SwitchButton(parent)
            box.checkedChanged.connect(lambda *_: self._sync_unclassified())
            self.unclassified_boxes[channel] = box
            form.addRow(QCoreApplication.translate("TopicsTab", label), box)

    def _build_general_card(self, parent) -> None:
        form = self._card(parent, self.tr("General"))
        self.language = ComboBox(parent)
        self.language.addItems(["auto", "en", "zh_CN"])
        self.language.currentIndexChanged.connect(self._on_language)
        data_row = QHBoxLayout()
        self.data_dir = LineEdit(parent)
        self.data_dir.setPlaceholderText(self.tr("Default: user data directory"))
        self.data_dir.textChanged.connect(lambda t: self._update(None, data_dir=t or None))
        data_browse = PushButton(self.tr("Browse…"), parent)
        data_browse.clicked.connect(self._browse_data_dir)
        data_row.addWidget(self.data_dir, 1)
        data_row.addWidget(data_browse)
        sound_row = QHBoxLayout()
        self.sound_file = LineEdit(parent)
        self.sound_file.setPlaceholderText(self.tr("Default: built-in synthesized beep (.wav)"))
        self.sound_file.textChanged.connect(lambda t: self._update(None, sound_file=t))
        sound_browse = PushButton(self.tr("Browse…"), parent)
        sound_browse.clicked.connect(self._browse_sound)
        sound_preview = PushButton(self.tr("Preview"), parent)
        sound_preview.clicked.connect(lambda: self.win.play_sound(self.win.draft.sound_file))
        sound_row.addWidget(self.sound_file, 1)
        sound_row.addWidget(sound_browse)
        sound_row.addWidget(sound_preview)
        self.start_minimized = SwitchButton(parent)
        self.start_minimized.checkedChanged.connect(lambda v: self._update(None, start_minimized=v))
        form.addRow(self.tr("Language"), self.language)
        form.addRow(self.tr("Data directory"), data_row)
        form.addRow(self.tr("Alert sound"), sound_row)
        form.addRow(self.tr("Start minimized"), self.start_minimized)

    def _build_config_card(self, parent) -> None:
        form = self._card(parent, self.tr("Configuration file"))
        self.config_path = BodyLabel(str(self.win.store.path), parent)
        self.config_path.setWordWrap(True)
        row = QHBoxLayout()
        open_folder = PushButton(self.tr("Open folder"), parent)
        open_folder.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.win.store.path.parent)))
        )
        export_btn = PushButton(self.tr("Export…"), parent)
        export_btn.clicked.connect(self._export)
        import_btn = PushButton(self.tr("Import…"), parent)
        import_btn.clicked.connect(self._import)
        row.addWidget(open_folder)
        row.addWidget(export_btn)
        row.addWidget(import_btn)
        row.addStretch(1)
        form.addRow(self.config_path)
        form.addRow(row)
        hint = BodyLabel(
            self.tr(
                "The YAML config is a shareable document. When sharing, adjust absolute paths "
                "(local model, data dir, sound) and remove the LLM API key if present."
            ),
            parent,
        )
        hint.setWordWrap(True)
        form.addRow(hint)

    # ------------------------------------------------------------------ sync
    def refresh(self) -> None:
        self._loading = True
        cfg = self.win.draft
        self.laya_mode.setCurrentText(cfg.laya.mode)
        self.laya_local_path.setText(cfg.laya.local_path)
        self.laya_device.setCurrentText(cfg.laya.device)
        self.laya_local_path.setEnabled(cfg.laya.mode != "router")
        self.llm_base_url.setText(cfg.llm.base_url)
        self.llm_api_key.setText(cfg.llm.api_key)
        self.llm_model.setText(cfg.llm.model)
        self.llm_mode.setCurrentText(cfg.llm.mode)
        self.llm_timeout.setValue(cfg.llm.timeout_s)
        self.llm_retries.setValue(cfg.llm.max_retries)
        self.webhook_enabled.setChecked(cfg.webhook.enabled)
        self.webhook_host.setText(cfg.webhook.host)
        self.webhook_port.setValue(max(cfg.webhook.port, 1))
        self.ntfy_in_enabled.setChecked(cfg.ntfy_input.enabled)
        self.ntfy_in_server.setText(cfg.ntfy_input.server)
        self.ntfy_in_topics.setText(", ".join(cfg.ntfy_input.topics))
        self.ntfy_pub_server.setText(cfg.ntfy_publish.server)
        self.ntfy_pub_topic.setText(cfg.ntfy_publish.topic)
        self.ntfy_pub_priority.setValue(cfg.ntfy_publish.priority)
        for channel, box in self.unclassified_boxes.items():
            box.setChecked(channel in cfg.unclassified.channels)
        self.language.setCurrentText(cfg.language)
        self.data_dir.setText(cfg.data_dir or "")
        self.sound_file.setText(cfg.sound_file)
        self.start_minimized.setChecked(cfg.start_minimized)
        self._loading = False

    def _sync_ntfy_topics(self, text: str) -> None:
        topics = tuple(t.strip() for t in text.split(",") if t.strip())
        self._update("ntfy_input", topics=topics)

    def _sync_unclassified(self) -> None:
        channels = tuple(ch for ch, box in self.unclassified_boxes.items() if box.isChecked())
        self._update("unclassified", channels=channels)

    def _on_language(self, index: int) -> None:
        self._update(None, language=self.language.itemText(index))
        if not self._loading:
            InfoBar.info(
                self.tr("Language"),
                self.tr("Language changes take effect after restart."),
                parent=self,
                duration=4000,
            )

    def _browse_local_model(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr("Select Laya checkpoint directory"))
        if path:
            self.laya_local_path.setText(path)

    def _browse_data_dir(self) -> None:
        path = QFileDialog.getExistingDirectory(self, self.tr("Select data directory"))
        if path:
            self.data_dir.setText(path)

    def _browse_sound(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Select alert sound"), "", "WAV files (*.wav)"
        )
        if path:
            self.sound_file.setText(path)

    def _export(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, self.tr("Export configuration"), "refer-to-me-config.yaml", "YAML (*.yaml)"
        )
        if not path:
            return
        text = yaml.safe_dump(
            self.win.draft.model_dump(mode="json"), allow_unicode=True, sort_keys=False
        )
        Path(path).write_text(text, encoding="utf-8")
        InfoBar.success(self.tr("Exported"), path, parent=self, duration=4000)

    def _import(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, self.tr("Import configuration"), "", "YAML (*.yaml)"
        )
        if not path:
            return
        try:
            data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
            cfg = AppConfig.model_validate(data or {})
        except Exception as exc:  # noqa: BLE001 - report, never touch the source file
            InfoBar.error(self.tr("Import failed"), str(exc), parent=self, duration=8000)
            return
        self.win.draft = cfg
        self.win.refresh_tabs()
        InfoBar.success(
            self.tr("Imported"),
            self.tr("Press Save to apply the imported configuration."),
            parent=self,
            duration=5000,
        )
