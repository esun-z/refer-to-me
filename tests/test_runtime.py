"""Runtime integration with fake engines (no torch, no network)."""

from refer_to_me.config import (
    AlertChannel,
    AppConfig,
    KeywordRule,
    TopicConfig,
)
from refer_to_me.runtime import AppRuntime, RuntimeSignals

from .conftest import FakeLayaEngine, FakeLlmEngine, wait_until


class FakeDispatcher:
    def __init__(self, ok=None):
        self.requests = []
        self.ok = ["fake"] if ok is None else ok

    def dispatch(self, req):
        self.requests.append(req)
        return list(self.ok)


def build(tmp_path, topics, laya, llm=None, dispatcher=None):
    cfg = AppConfig(topics=tuple(topics), data_dir=str(tmp_path))
    signals = RuntimeSignals()
    logs, stats = [], []
    signals.log.connect(lambda s, t: logs.append((s, t)))
    signals.stats.connect(lambda s: stats.append(s))
    dispatcher = dispatcher if dispatcher is not None else FakeDispatcher()
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
    # thresholds 0.8: p=0.4 -> conf 0.6 < 0.8 -> uncertain, LLM disabled -> unclassified.
    t = TopicConfig(id="t1", name="x", match_threshold=0.8, llm_threshold=0.8)
    laya = FakeLayaEngine(scores={"t1": 0.4})
    runtime, _logs, stats, dispatcher = build(tmp_path, [t], laya)
    try:
        runtime.submit_message(make_message("无关消息"))
        wait_until(lambda: stats and stats[-1]["unclassified"] == 1, app=qapp)
        wait_until(lambda: dispatcher.requests, app=qapp)
        assert dispatcher.requests[0].kind == "unclassified"
    finally:
        runtime.shutdown()


def test_no_match_is_silent(qapp, tmp_path, make_message):
    # p=0.2 -> conf 0.8 >= 0.6: confident no -> no_match, no alert request.
    t = TopicConfig(id="t1", name="x")
    laya = FakeLayaEngine(scores={"t1": 0.2})
    runtime, _logs, stats, dispatcher = build(tmp_path, [t], laya)
    try:
        runtime.submit_message(make_message("无关消息"))
        wait_until(lambda: stats and stats[-1]["no_match"] == 1, app=qapp)
        assert dispatcher.requests == []
        assert stats[-1]["alerts"] == 0
    finally:
        runtime.shutdown()


def test_filter_match_without_channels_logs_silent(qapp, tmp_path, make_message):
    # Matched topic with no alert channels = filter: logged as silent, not failed.
    t = TopicConfig(id="t1", name="噪音过滤", keywords=(KeywordRule(pattern="广告"),))
    runtime, logs, stats, dispatcher = build(
        tmp_path, [t], FakeLayaEngine(), dispatcher=FakeDispatcher(ok=[])
    )
    try:
        runtime.submit_message(make_message("广告推送"))
        wait_until(lambda: dispatcher.requests, app=qapp)
        wait_until(lambda: any("silent:" in text for _s, text in logs), app=qapp)
        assert dispatcher.requests[0].kind == "topics"
        silent = [text for stage, text in logs if "silent:" in text]
        assert any("(filter)" in text and "噪音过滤" in text for text in silent)
        assert not any("alert failed" in text for _s, text in logs)
        assert stats[-1]["alerts"] == 0
    finally:
        runtime.shutdown()


def test_configured_channels_all_failed_logs_error(qapp, tmp_path, make_message):
    t = TopicConfig(
        id="t1",
        name="月例会",
        keywords=(KeywordRule(pattern="月例会"),),
        channels=(AlertChannel.SOUND,),
    )
    runtime, logs, _stats, dispatcher = build(
        tmp_path, [t], FakeLayaEngine(), dispatcher=FakeDispatcher(ok=[])
    )
    try:
        runtime.submit_message(make_message("下周月例会"))
        wait_until(lambda: dispatcher.requests, app=qapp)
        wait_until(lambda: any("alert failed" in text for _s, text in logs), app=qapp)
        failed = [(stage, text) for stage, text in logs if "alert failed" in text]
        assert failed[0][0] == "error"
        assert "月例会" in failed[0][1] and "sound" in failed[0][1]
        assert not any("silent:" in text for _s, text in logs)
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
    t = TopicConfig(id="t1", name="x", match_threshold=0.7, llm_threshold=0.7)
    laya = FakeLayaEngine(scores={"t1": 0.6})
    runtime, _logs, stats, _dispatcher = build(tmp_path, [t], laya)
    try:
        runtime.submit_message(make_message("第一条"))
        wait_until(lambda: stats and stats[-1]["unclassified"] == 1, app=qapp)
        # lower per-topic thresholds -> same score now matches
        relaxed = t.model_copy(update={"match_threshold": 0.5, "llm_threshold": 0.5})
        new_cfg = AppConfig(topics=(relaxed,), data_dir=str(tmp_path))
        runtime.apply_config(new_cfg)
        runtime.submit_message(make_message("第二条"))
        wait_until(lambda: stats and stats[-1]["laya"] == 1, app=qapp)
    finally:
        runtime.shutdown()


def test_topic_reorder_hot_update(qapp, tmp_path, make_message):
    # Both topics keyword-match; reordering changes which one wins.
    a = TopicConfig(id="a", name="甲", keywords=(KeywordRule(pattern="例会"),))
    b = TopicConfig(id="b", name="乙", keywords=(KeywordRule(pattern="例会"),))
    runtime, _logs, _stats, dispatcher = build(tmp_path, [a, b], FakeLayaEngine())
    try:
        runtime.submit_message(make_message("月例会通知"))
        wait_until(lambda: len(dispatcher.requests) == 1, app=qapp)
        assert dispatcher.requests[0].topics[0].id == "a"
        runtime.apply_config(AppConfig(topics=(b, a), data_dir=str(tmp_path)))
        runtime.submit_message(make_message("月例会通知"))
        wait_until(lambda: len(dispatcher.requests) == 2, app=qapp)
        assert dispatcher.requests[1].topics[0].id == "b"
    finally:
        runtime.shutdown()


def test_shutdown_joins_threads(qapp, tmp_path, make_message):
    runtime, *_ = build(tmp_path, [], FakeLayaEngine())
    worker = runtime._worker
    alert_worker = runtime._alert_worker
    runtime.shutdown()
    assert not worker.is_alive()
    assert not alert_worker.is_alive()
