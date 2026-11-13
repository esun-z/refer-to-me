"""Runtime integration with fake engines (no torch, no network)."""

from refer_to_me.config import (
    AlertChannel,
    AppConfig,
    KeywordRule,
    LayaConfig,
    TopicConfig,
)
from refer_to_me.runtime import AppRuntime, RuntimeSignals

from .conftest import FakeLayaEngine, FakeLlmEngine, wait_until


class FakeDispatcher:
    def __init__(self):
        self.requests = []

    def dispatch(self, req):
        self.requests.append(req)
        return ["fake"]


def build(tmp_path, topics, laya, llm=None, threshold=0.5):
    cfg = AppConfig(
        topics=tuple(topics),
        laya=LayaConfig(threshold=threshold),
        data_dir=str(tmp_path),
    )
    signals = RuntimeSignals()
    logs, stats = [], []
    signals.log.connect(lambda s, t: logs.append((s, t)))
    signals.stats.connect(lambda s: stats.append(s))
    dispatcher = FakeDispatcher()
    runtime = AppRuntime(
        cfg,
        signals,
        alert_dispatcher=dispatcher,
        laya_engine=laya,
        llm_engine=llm or FakeLlmEngine(),
    )
    runtime.start()
    return runtime, logs, stats, dispatcher


def test_keyword_flow(qapp, tmp_path, make_message):
    t = TopicConfig(
        id="t1",
        name="月例会",
        keywords=(KeywordRule(pattern="月例会"),),
        channels=(AlertChannel.TOAST,),
    )
    laya = FakeLayaEngine()
    runtime, _logs, stats, dispatcher = build(tmp_path, [t], laya)
    try:
        assert runtime.submit_message(make_message("下周月例会改到周四"))
        wait_until(lambda: stats and stats[-1]["keyword"] == 1, app=qapp)
        wait_until(lambda: dispatcher.requests, app=qapp)
        assert dispatcher.requests[0].kind == "topics"
        assert dispatcher.requests[0].topics[0].id == "t1"
        assert laya.calls == []
    finally:
        runtime.shutdown()


def test_unclassified_alert(qapp, tmp_path, make_message):
    # threshold 0.8: p=0.4 -> conf 0.6 < 0.8 -> uncertain, LLM disabled -> unclassified.
    t = TopicConfig(id="t1", name="x")
    laya = FakeLayaEngine(scores={"t1": 0.4})
    runtime, _logs, stats, dispatcher = build(tmp_path, [t], laya, threshold=0.8)
    try:
        runtime.submit_message(make_message("无关消息"))
        wait_until(lambda: stats and stats[-1]["unclassified"] == 1, app=qapp)
        wait_until(lambda: dispatcher.requests, app=qapp)
        assert dispatcher.requests[0].kind == "unclassified"
    finally:
        runtime.shutdown()


def test_empty_message_ignored(qapp, tmp_path, make_message):
    runtime, _logs, stats, dispatcher = build(tmp_path, [], FakeLayaEngine())
    try:
        runtime.submit_message(make_message("   "))
        wait_until(lambda: stats and stats[-1]["ignored"] == 1, app=qapp)
        assert stats[-1]["received"] == 0
        assert dispatcher.requests == []
    finally:
        runtime.shutdown()


def test_config_hot_update(qapp, tmp_path, make_message):
    t = TopicConfig(id="t1", name="x")
    laya = FakeLayaEngine(scores={"t1": 0.6})
    runtime, _logs, stats, _dispatcher = build(tmp_path, [t], laya, threshold=0.7)
    try:
        runtime.submit_message(make_message("第一条"))
        wait_until(lambda: stats and stats[-1]["unclassified"] == 1, app=qapp)
        # lower threshold -> same score now matches
        new_cfg = AppConfig(
            topics=(t,), laya=LayaConfig(threshold=0.5), data_dir=str(tmp_path)
        )
        runtime.apply_config(new_cfg)
        runtime.submit_message(make_message("第二条"))
        wait_until(lambda: stats and stats[-1]["laya"] == 1, app=qapp)
    finally:
        runtime.shutdown()


def test_shutdown_joins_threads(qapp, tmp_path, make_message):
    runtime, *_ = build(tmp_path, [], FakeLayaEngine())
    worker = runtime._worker
    alert_worker = runtime._alert_worker
    runtime.shutdown()
    assert not worker.is_alive()
    assert not alert_worker.is_alive()
