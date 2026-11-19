"""Regression: the topic list must keep a usable width next to the editor form."""

import tempfile
from pathlib import Path

from refer_to_me.alerts.bridge import AlertBridge
from refer_to_me.config import AppConfig, ConfigStore, TopicConfig
from refer_to_me.gui.main_window import MainWindow
from refer_to_me.runtime import RuntimeSignals


class StubRuntime:
    def reload_model(self):
        pass

    def test_llm(self):
        pass

    def submit_message(self, msg):
        return True

    def apply_config(self, cfg):
        pass


def make_window(topics):
    store = ConfigStore(Path(tempfile.mkdtemp()) / "c.yaml")
    cfg = AppConfig(topics=tuple(topics))
    win = MainWindow(cfg, store, StubRuntime(), RuntimeSignals(), AlertBridge())
    win.resize(1080, 720)
    win.show()
    win.switchTo(win.topics_tab)
    return win


def test_topic_list_width(qapp):
    win = make_window([TopicConfig(name="月例会"), TopicConfig(name="年会旅游报销政策")])
    qapp.processEvents()
    assert win.topics_tab.list.width() >= 200
    assert win.topics_tab.list.count() == 2
    win.close()


def test_move_topic_up_and_down(qapp):
    a, b, c = (TopicConfig(id=i, name=n) for i, n in [("a", "甲"), ("b", "乙"), ("c", "丙")])
    win = make_window([a, b, c])
    tab = win.topics_tab
    qapp.processEvents()
    tab.list.setCurrentRow(2)  # select 丙
    qapp.processEvents()
    tab.up_btn.click()
    qapp.processEvents()
    assert [t.id for t in win.draft.topics] == ["a", "c", "b"]
    assert tab.list.currentRow() == 1  # selection follows the topic
    assert tab.list.item(1).text().startswith("2.")
    tab.down_btn.click()
    qapp.processEvents()
    assert [t.id for t in win.draft.topics] == ["a", "b", "c"]
    # boundaries are no-ops
    tab.list.setCurrentRow(0)
    qapp.processEvents()
    tab.up_btn.click()
    assert [t.id for t in win.draft.topics] == ["a", "b", "c"]
    win.close()


def test_laya_switch_off_disables_and_clears_llm(qapp):
    t = TopicConfig(id="t1", name="x", laya_enabled=True, llm_enabled=True)
    win = make_window([t])
    tab = win.topics_tab
    qapp.processEvents()
    tab.list.setCurrentRow(0)
    qapp.processEvents()
    assert tab.llm_switch.isEnabled()
    tab.laya_switch.setChecked(False)
    qapp.processEvents()
    topic = win.draft.topics[0]
    assert topic.laya_enabled is False
    assert topic.llm_enabled is False  # LLM requires Laya
    assert not tab.llm_switch.isChecked()
    assert not tab.llm_switch.isEnabled()
    assert not tab.instructions_edit.isEnabled()
    assert not tab.match_threshold_spin.isEnabled()
    # keywords stay editable for a filter topic
    assert tab.kw_table.isEnabled()
    win.close()


def test_threshold_spboxes_clamp_to_valid_order(qapp):
    t = TopicConfig(id="t1", name="x", match_threshold=0.9, llm_threshold=0.8)
    win = make_window([t])
    tab = win.topics_tab
    qapp.processEvents()
    tab.list.setCurrentRow(0)
    qapp.processEvents()
    tab.match_threshold_spin.setValue(0.7)  # below llm 0.8 -> llm clamps down
    qapp.processEvents()
    topic = win.draft.topics[0]
    assert topic.match_threshold == 0.7
    assert topic.llm_threshold == 0.7
    assert tab.llm_threshold_spin.value() == 0.7
    tab.llm_threshold_spin.setValue(0.95)  # above match 0.7 -> clamps to match
    qapp.processEvents()
    topic = win.draft.topics[0]
    assert topic.llm_threshold == 0.7
    assert tab.llm_threshold_spin.value() == 0.7
    win.close()
