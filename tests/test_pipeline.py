"""Pipeline short-circuit semantics and dataset record invariants."""

from refer_to_me.config import (
    AppConfig,
    KeywordRule,
    LayaConfig,
    LlmConfig,
    TopicConfig,
)
from refer_to_me.core.message import FinalStage
from refer_to_me.core.pipeline import Pipeline

from .conftest import FakeLayaEngine, FakeLlmEngine, MemoryRecorder


def cfg_with(topics, llm_enabled=False, threshold=0.5):
    return AppConfig(
        topics=tuple(topics),
        laya=LayaConfig(threshold=threshold),
        llm=LlmConfig(
            enabled=llm_enabled,
            base_url="http://localhost/v1" if llm_enabled else "",
            model="m" if llm_enabled else "",
        ),
    )


def topic(tid="t1", name="月例会", keywords=()):
    return TopicConfig(id=tid, name=name, keywords=tuple(keywords))


def run(msg, cfg, laya, llm):
    rec = MemoryRecorder()
    result = Pipeline(laya, llm).process(msg, cfg, rec)
    return result, rec


def test_keyword_short_circuit(make_message):
    t = topic(keywords=[KeywordRule(pattern="月例会")])
    laya, llm = FakeLayaEngine(), FakeLlmEngine()
    result, rec = run(make_message("下周月例会改到周四"), cfg_with([t]), laya, llm)
    assert result.stage == FinalStage.KEYWORD
    assert result.matched_topic_ids == ["t1"]
    assert result.alert_kind == "topics"
    assert laya.calls == [] and laya.ensure_loaded_calls == 0
    assert llm.calls == []
    assert rec.records == []  # keyword hits never produce dataset records


def test_laya_match(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.9})
    result, rec = run(make_message("语义消息"), cfg_with([topic()]), laya, FakeLlmEngine())
    assert result.stage == FinalStage.LAYA
    assert result.alert_kind == "topics"
    assert result.scores == {"t1": 0.9}
    assert len(rec.records) == 1
    assert rec.records[0]["final_stage"] == "laya"
    assert rec.records[0]["alerted_topics"] == ["t1"]
    assert rec.records[0]["human_label"] is None


def test_threshold_boundary_inclusive(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.5})
    result, _ = run(make_message("x"), cfg_with([topic()], threshold=0.5), laya, FakeLlmEngine())
    assert result.stage == FinalStage.LAYA


def test_multi_label_match(make_message):
    topics = [topic("t1", "月例会"), topic("t2", "报销")]
    laya = FakeLayaEngine(scores={"t1": 0.8, "t2": 0.7})
    result, rec = run(make_message("x"), cfg_with(topics), laya, FakeLlmEngine())
    assert result.stage == FinalStage.LAYA
    assert result.matched_topic_ids == ["t1", "t2"]
    assert rec.records[0]["laya_matched_topics"] == ["t1", "t2"]


def test_confident_no_is_laya_none(make_message):
    # p=0.2 -> confidence 0.8 >= 0.5: confidently unrelated, no alert, no LLM.
    laya = FakeLayaEngine(scores={"t1": 0.2})
    llm = FakeLlmEngine()
    result, rec = run(make_message("x"), cfg_with([topic()]), laya, llm)
    assert result.stage == FinalStage.LAYA_NONE
    assert result.alert_kind is None
    assert llm.calls == []
    assert len(rec.records) == 1
    assert rec.records[0]["final_stage"] == "laya_none"


def test_confident_no_even_with_llm_enabled(make_message):
    # threshold 0.8: p=0.1 -> conf 0.9 >= 0.8 -> confident no, LLM must NOT fire.
    laya = FakeLayaEngine(scores={"t1": 0.1})
    llm = FakeLlmEngine(matched=["t1"])
    result, _ = run(
        make_message("x"), cfg_with([topic()], llm_enabled=True, threshold=0.8), laya, llm
    )
    assert result.stage == FinalStage.LAYA_NONE
    assert llm.calls == []


def test_uncertain_no_llm_unclassified(make_message):
    # threshold 0.8: p=0.6 -> conf 0.6 < 0.8 -> uncertain, LLM not configured.
    laya = FakeLayaEngine(scores={"t1": 0.6})
    llm = FakeLlmEngine()
    result, rec = run(make_message("x"), cfg_with([topic()], threshold=0.8), laya, llm)
    assert result.stage == FinalStage.UNCLASSIFIED
    assert result.alert_kind == "unclassified"
    assert llm.calls == []
    assert rec.records[0]["laya_uncertain_topics"] == ["t1"]


def test_llm_fallback_match(make_message):
    # threshold 0.8: p=0.3 -> conf 0.7 < 0.8 -> uncertain -> LLM.
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(matched=["t1"])
    result, rec = run(
        make_message("x"), cfg_with([topic()], llm_enabled=True, threshold=0.8), laya, llm
    )
    assert result.stage == FinalStage.LLM
    assert result.alert_kind == "topics"
    assert len(llm.calls) == 1
    assert rec.records[0]["final_stage"] == "llm"
    assert rec.records[0]["llm"]["matched_topics"] == ["t1"]


def test_llm_none_is_normal_terminal(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(matched=[])
    result, rec = run(
        make_message("x"), cfg_with([topic()], llm_enabled=True, threshold=0.8), laya, llm
    )
    assert result.stage == FinalStage.LLM_NONE
    assert result.alert_kind is None  # no alert
    assert rec.records[0]["final_stage"] == "llm_none"


def test_llm_failure_unclassified(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(error=RuntimeError("boom"))
    result, rec = run(
        make_message("x"), cfg_with([topic()], llm_enabled=True, threshold=0.8), laya, llm
    )
    assert result.stage == FinalStage.UNCLASSIFIED
    assert result.alert_kind == "unclassified"
    assert "boom" in rec.records[0]["llm"]["error"]


def test_llm_unknown_ids_filtered(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(matched=["t1", "ghost"])
    result, _ = run(
        make_message("x"), cfg_with([topic()], llm_enabled=True, threshold=0.8), laya, llm
    )
    assert result.stage == FinalStage.LLM
    assert result.matched_topic_ids == ["t1"]


def test_mixed_confident_no_and_uncertain_routes_llm(make_message):
    topics = [topic("t1", "甲"), topic("t2", "乙")]
    laya = FakeLayaEngine(scores={"t1": 0.1, "t2": 0.6})  # conf 0.9 / 0.6
    llm = FakeLlmEngine(matched=["t2"])
    result, rec = run(
        make_message("x"), cfg_with(topics, llm_enabled=True, threshold=0.8), laya, llm
    )
    assert result.stage == FinalStage.LLM
    assert len(llm.calls) == 1
    assert rec.records[0]["laya_uncertain_topics"] == ["t2"]


def test_confident_yes_short_circuits_uncertain(make_message):
    topics = [topic("t1", "甲"), topic("t2", "乙")]
    laya = FakeLayaEngine(scores={"t1": 0.9, "t2": 0.6})
    llm = FakeLlmEngine(matched=["t2"])
    result, _ = run(
        make_message("x"), cfg_with(topics, llm_enabled=True, threshold=0.8), laya, llm
    )
    assert result.stage == FinalStage.LAYA
    assert result.matched_topic_ids == ["t1"]
    assert llm.calls == []


def test_laya_failure_unclassified_no_llm(make_message):
    laya = FakeLayaEngine(error=RuntimeError("model broken"))
    llm = FakeLlmEngine(matched=["t1"])
    result, rec = run(make_message("x"), cfg_with([topic()], llm_enabled=True), laya, llm)
    assert result.stage == FinalStage.UNCLASSIFIED
    assert result.alert_kind == "unclassified"
    assert llm.calls == []  # broken model must not silently burn LLM tokens
    assert len(rec.records) == 1
    assert "model broken" in rec.records[0]["error"]
    assert rec.records[0]["answers"] == {}


def test_no_topics(make_message):
    laya, llm = FakeLayaEngine(), FakeLlmEngine()
    result, rec = run(make_message("x"), cfg_with([]), laya, llm)
    assert result.stage == FinalStage.NO_TOPICS
    assert result.alert_kind is None
    assert laya.calls == []
    assert rec.records == []


def test_disabled_topic_skipped(make_message):
    t = TopicConfig(id="t1", name="x", enabled=False)
    laya = FakeLayaEngine(scores={"t1": 0.9})
    result, rec = run(make_message("x"), cfg_with([t]), laya, FakeLlmEngine())
    assert result.stage == FinalStage.NO_TOPICS
    assert rec.records == []


def test_long_message_truncated(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.9})
    result, rec = run(make_message("a" * 20000), cfg_with([topic()]), laya, FakeLlmEngine())
    assert len(laya.calls[0][0]) == 10000
    assert any(e.stage == "system" and "truncated" in e.text for e in result.events)
    assert rec.records[0]["message_text"] == "a" * 20000  # original preserved in dataset


def test_record_schema_complete(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.9})
    _, rec = run(make_message("下周月例会"), cfg_with([topic()]), laya, FakeLlmEngine())
    r = rec.records[0]
    expected_keys = {
        "schema_version", "record_id", "message_id", "ts", "source", "message_text",
        "sender", "channel", "model", "questions", "threshold", "answers", "usage",
        "duration_ms", "error", "laya_matched_topics", "laya_uncertain_topics",
        "final_stage", "llm", "alerted_topics", "human_label",
    }
    assert set(r) == expected_keys
    assert r["questions"]["t1"]["type"] == "noul"
    assert r["model"]["repo"] == "convaiinnovations/laya"
