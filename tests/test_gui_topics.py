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


def test_topic_list_width(qapp):
    store = ConfigStore(Path(tempfile.mkdtemp()) / "c.yaml")
    cfg = AppConfig(
        topics=(
            TopicConfig(name="月例会"),
            TopicConfig(name="年会旅游报销政策"),
        )
    )
    win = MainWindow(cfg, store, StubRuntime(), RuntimeSignals(), AlertBridge())
    win.resize(1080, 720)
    win.show()
    win.switchTo(win.topics_tab)
    qapp.processEvents()
    assert win.topics_tab.list.width() >= 200
    assert win.topics_tab.list.count() == 2
    win.close()
