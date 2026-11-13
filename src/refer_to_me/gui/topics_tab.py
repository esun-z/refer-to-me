"""Topics page: topic list + editor (keywords, Laya question/criteria, alert channels)."""

from __future__ import annotations

from pydantic import ValidationError
from PySide6.QtCore import QT_TRANSLATE_NOOP, Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from qfluentwidgets import (
    BodyLabel,
    CaptionLabel,
    CardWidget,
    CheckBox,
    LineEdit,
    ListWidget,
    MessageBox,
    PushButton,
    ScrollArea,
    SubtitleLabel,
    SwitchButton,
    TableWidget,
    TextEdit,
)

from refer_to_me.config import AlertChannel, KeywordRule, TopicConfig
from refer_to_me.core.questions import (
    default_criteria_false,
    default_criteria_true,
    default_instructions,
)

CHANNEL_LABELS = {
    AlertChannel.SOUND: QT_TRANSLATE_NOOP("TopicsTab", "Play sound"),
    AlertChannel.TOAST: QT_TRANSLATE_NOOP("TopicsTab", "Windows Toast"),
    AlertChannel.QT: QT_TRANSLATE_NOOP("TopicsTab", "Tray notification"),
    AlertChannel.NTFY: QT_TRANSLATE_NOOP("TopicsTab", "ntfy publish"),
}


class TopicsTab(QWidget):
    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setObjectName("topicsTab")
        self._loading = False
        self._current_id: str | None = None

        root = QHBoxLayout(self)
        root.setContentsMargins(24, 24, 24, 24)
        root.setSpacing(16)

        # Left: topic list (fixed width so names are never squeezed by the form)
        left_panel = QWidget(self)
        left_panel.setFixedWidth(240)
        left = QVBoxLayout(left_panel)
        left.setContentsMargins(0, 0, 0, 0)
        left.addWidget(SubtitleLabel(self.tr("Topics"), left_panel))
        self.list = ListWidget(left_panel)
        left.addWidget(self.list, 1)
        buttons = QHBoxLayout()
        self.add_btn = PushButton(self.tr("Add"), left_panel)
        self.del_btn = PushButton(self.tr("Delete"), left_panel)
        buttons.addWidget(self.add_btn)
        buttons.addWidget(self.del_btn)
        left.addLayout(buttons)
        root.addWidget(left_panel)

        # Right: editor form in a scroll area
        scroll = ScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.enableTransparentBackground()
        container = QWidget()
        container.setObjectName("topicForm")
        self.form_layout = QVBoxLayout(container)
        self.form_layout.setContentsMargins(0, 0, 12, 0)
        self.form_layout.setSpacing(12)

        base_card = CardWidget(container)
        base_form = QFormLayout(base_card)
        self.name_edit = LineEdit(base_card)
        self.enabled_switch = SwitchButton(base_card)
        self.desc_edit = TextEdit(base_card)
        self.desc_edit.setFixedHeight(72)
        base_form.addRow(self.tr("Name"), self.name_edit)
        base_form.addRow(self.tr("Enabled"), self.enabled_switch)
        base_form.addRow(self.tr("Description"), self.desc_edit)
        self.form_layout.addWidget(base_card)

        guidance = CaptionLabel(
            self.tr(
                "Keywords short-circuit the pipeline (literal substring or regex). "
                "The Laya question must be answerable yes/no; criteria should describe "
                "concrete positive/negative features (schedule, agenda, notices, receipts…), "
                "not vague words like 'related'. Example — 月例会: question "
                "「这条消息是否与月例会有关？」, true criterion 「讨论月例会的时间、议程、通知或总结」."
            ),
            container,
        )
        guidance.setWordWrap(True)
        self.form_layout.addWidget(guidance)

        kw_card = CardWidget(container)
        kw_layout = QVBoxLayout(kw_card)
        kw_layout.addWidget(BodyLabel(self.tr("Keywords (stage 1)"), kw_card))
        self.kw_table = TableWidget(kw_card)
        self.kw_table.setColumnCount(2)
        self.kw_table.setRowCount(0)
        self.kw_table.setHorizontalHeaderLabels([self.tr("Pattern"), self.tr("Regex")])
        self.kw_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.kw_table.setColumnWidth(1, 64)
        self.kw_table.verticalHeader().hide()
        self.kw_table.setFixedHeight(160)
        kw_layout.addWidget(self.kw_table)
        kw_buttons = QHBoxLayout()
        self.kw_add = PushButton(self.tr("Add row"), kw_card)
        self.kw_del = PushButton(self.tr("Remove row"), kw_card)
        kw_buttons.addWidget(self.kw_add)
        kw_buttons.addWidget(self.kw_del)
        kw_buttons.addStretch(1)
        kw_layout.addLayout(kw_buttons)
        self.form_layout.addWidget(kw_card)

        laya_card = CardWidget(container)
        laya_form = QFormLayout(laya_card)
        self.instructions_edit = LineEdit(laya_card)
        self.criteria_true_edit = LineEdit(laya_card)
        self.criteria_false_edit = LineEdit(laya_card)
        self.gen_defaults_btn = PushButton(self.tr("Generate defaults"), laya_card)
        laya_form.addRow(self.tr("Laya question"), self.instructions_edit)
        laya_form.addRow(self.tr("True criterion"), self.criteria_true_edit)
        laya_form.addRow(self.tr("False criterion"), self.criteria_false_edit)
        laya_form.addRow("", self.gen_defaults_btn)
        self.form_layout.addWidget(laya_card)

        channel_card = CardWidget(container)
        channel_layout = QVBoxLayout(channel_card)
        channel_layout.addWidget(BodyLabel(self.tr("Alert channels (none checked = silent)"), channel_card))
        self.channel_boxes: dict[AlertChannel, CheckBox] = {}
        for channel, label in CHANNEL_LABELS.items():
            box = CheckBox(self.tr(label), channel_card)
            self.channel_boxes[channel] = box
            channel_layout.addWidget(box)
        hint = CaptionLabel(
            self.tr("Note: Windows Toast plays its own sound; combining it with 'Play sound' rings twice."),
            channel_card,
        )
        hint.setWordWrap(True)
        channel_layout.addWidget(hint)
        self.form_layout.addWidget(channel_card)
        self.form_layout.addStretch(1)

        scroll.setWidget(container)
        root.addWidget(scroll, 2)
        self.form_container = container
        container.setEnabled(False)

        # Wiring
        self.add_btn.clicked.connect(self._add_topic)
        self.del_btn.clicked.connect(self._delete_topic)
        self.list.currentItemChanged.connect(self._on_select)
        self.name_edit.textChanged.connect(lambda t: self._update_topic(name=t))
        self.enabled_switch.checkedChanged.connect(lambda v: self._update_topic(enabled=v))
        self.desc_edit.textChanged.connect(lambda: self._update_topic(description=self.desc_edit.toPlainText()))
        self.instructions_edit.textChanged.connect(lambda t: self._update_topic(laya_instructions=t))
        self.criteria_true_edit.textChanged.connect(lambda t: self._update_topic(laya_criteria_true=t))
        self.criteria_false_edit.textChanged.connect(lambda t: self._update_topic(laya_criteria_false=t))
        self.gen_defaults_btn.clicked.connect(self._generate_defaults)
        self.kw_add.clicked.connect(self._add_kw_row)
        self.kw_del.clicked.connect(self._remove_kw_row)
        self.kw_table.cellChanged.connect(lambda *_: self._sync_keywords())
        for box in self.channel_boxes.values():
            box.toggled.connect(lambda *_: self._sync_channels())

        self.refresh()

    # ------------------------------------------------------------------ list
    def refresh(self, select_id: str | None = None) -> None:
        self._loading = True
        self.list.clear()
        for topic in self.win.draft.topics:
            from PySide6.QtWidgets import QListWidgetItem

            item = QListWidgetItem(self._item_text(topic))
            item.setData(Qt.ItemDataRole.UserRole, topic.id)
            self.list.addItem(item)
            if select_id == topic.id or (select_id is None and topic.id == self._current_id):
                self.list.setCurrentItem(item)
        self._loading = False
        current = self.list.currentItem()
        if current is not None:
            self._load_topic(current.data(Qt.ItemDataRole.UserRole))
        else:
            self._current_id = None
            self.form_container.setEnabled(False)

    def _item_text(self, topic: TopicConfig) -> str:
        return topic.name + ("" if topic.enabled else "  " + self.tr("(disabled)"))

    def _on_select(self, current, previous) -> None:
        if self._loading or current is None:
            return
        self._load_topic(current.data(Qt.ItemDataRole.UserRole))

    def _load_topic(self, topic_id: str) -> None:
        topic = next((t for t in self.win.draft.topics if t.id == topic_id), None)
        if topic is None:
            return
        self._loading = True
        self._current_id = topic_id
        self.form_container.setEnabled(True)
        self.name_edit.setText(topic.name)
        self.enabled_switch.setChecked(topic.enabled)
        self.desc_edit.setPlainText(topic.description)
        self.instructions_edit.setText(topic.laya_instructions)
        self.criteria_true_edit.setText(topic.laya_criteria_true)
        self.criteria_false_edit.setText(topic.laya_criteria_false)
        self.kw_table.setRowCount(0)
        for rule in topic.keywords:
            self._add_kw_row(rule.pattern, rule.is_regex)
        for channel, box in self.channel_boxes.items():
            box.setChecked(channel in topic.channels)
        self._loading = False

    # ------------------------------------------------------------------ edits
    def _update_topic(self, **kwargs) -> None:
        if self._loading or self._current_id is None:
            return
        topics = list(self.win.draft.topics)
        for i, topic in enumerate(topics):
            if topic.id == self._current_id:
                topics[i] = topic.model_copy(update=kwargs)
                item = self.list.currentItem()
                if item is not None:
                    item.setText(self._item_text(topics[i]))
                break
        self.win.draft = self.win.draft.model_copy(update={"topics": tuple(topics)})

    def _add_topic(self) -> None:
        topic = TopicConfig(name=self.tr("New topic"))
        self.win.draft = self.win.draft.model_copy(
            update={"topics": self.win.draft.topics + (topic,)}
        )
        self.refresh(select_id=topic.id)

    def _delete_topic(self) -> None:
        if self._current_id is None:
            return
        box = MessageBox(
            self.tr("Delete topic"), self.tr("Delete the selected topic?"), self
        )
        if box.exec():
            topics = tuple(t for t in self.win.draft.topics if t.id != self._current_id)
            self.win.draft = self.win.draft.model_copy(update={"topics": topics})
            self._current_id = None
            self.refresh()

    def _generate_defaults(self) -> None:
        topic = next((t for t in self.win.draft.topics if t.id == self._current_id), None)
        if topic is None:
            return
        self.instructions_edit.setText(default_instructions(topic.name))
        self.criteria_true_edit.setText(default_criteria_true(topic.name, topic.description))
        self.criteria_false_edit.setText(default_criteria_false(topic.name))

    # ------------------------------------------------------------------ keywords
    def _add_kw_row(self, pattern: str = "", is_regex: bool = False) -> None:
        row = self.kw_table.rowCount()
        self.kw_table.insertRow(row)
        self.kw_table.setItem(row, 0, QTableWidgetItem(pattern))
        box = CheckBox(self.kw_table)
        box.setChecked(is_regex)
        box.stateChanged.connect(lambda *_: self._sync_keywords())
        self.kw_table.setCellWidget(row, 1, box)

    def _remove_kw_row(self) -> None:
        row = self.kw_table.currentRow()
        if row >= 0:
            self.kw_table.removeRow(row)
            self._sync_keywords()

    def _sync_keywords(self) -> None:
        if self._loading:
            return
        rules = []
        invalid = False
        for row in range(self.kw_table.rowCount()):
            item = self.kw_table.item(row, 0)
            pattern = item.text().strip() if item else ""
            box = self.kw_table.cellWidget(row, 1)
            is_regex = box.isChecked() if box else False
            if not pattern:
                continue
            try:
                rules.append(KeywordRule(pattern=pattern, is_regex=is_regex))
                if item:
                    item.setData(Qt.ItemDataRole.ForegroundRole, None)
            except ValidationError:
                invalid = True
                if item:
                    item.setForeground(QBrush(QColor("#c62828")))
        if not invalid:
            self._update_topic(keywords=tuple(rules))

    def _sync_channels(self) -> None:
        if self._loading:
            return
        channels = tuple(ch for ch, box in self.channel_boxes.items() if box.isChecked())
        self._update_topic(channels=channels)
