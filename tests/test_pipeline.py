"""Ordered per-topic cascade semantics and dataset record invariants."""

from refer_to_me.config import AppConfig, KeywordRule, LlmConfig, TopicConfig
from refer_to_me.core.message import FinalStage
from refer_to_me.core.pipeline import Pipeline

from .conftest import FakeLayaEngine, FakeLlmEngine, MemoryRecorder

LLM_CONFIGURED = LlmConfig(base_url="http://localhost/v1", model="m")


def cfg_with(topics, llm=None):
    return AppConfig(topics=tuple(topics), llm=llm or LlmConfig())


def topic(tid="t1", name="月例会", keywords=(), **kw):
    return TopicConfig(id=tid, name=name, keywords=tuple(keywords), **kw)


def run(msg, cfg, laya, llm):
    rec = MemoryRecorder()
    result = Pipeline(laya, llm).process(msg, cfg, rec)
    return result, rec


# ------------------------------------------------------------------ stage 1


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


def test_keyword_first_in_order_wins(make_message):
    topics = [
        topic("t1", "甲", keywords=[KeywordRule(pattern="报销")]),
        topic("t2", "乙", keywords=[KeywordRule(pattern="报销")]),
    ]
    laya, llm = FakeLayaEngine(), FakeLlmEngine()
    result, _ = run(make_message("报销政策"), cfg_with(topics), laya, llm)
    assert result.stage == FinalStage.KEYWORD
    assert result.matched_topic_ids == ["t1"]  # later topic never evaluated


def test_keyword_filter_short_circuits_before_laya(make_message):
    # A keyword-only front filter (no alert channels) must stop the pipeline
    # without ever running Laya on the remaining topics.
    topics = [
        topic("t1", "噪音过滤", keywords=[KeywordRule(pattern="广告")]),
        topic("t2", "月例会"),
    ]
    laya = FakeLayaEngine(scores={"t2": 0.99})
    result, rec = run(make_message("广告推送"), cfg_with(topics), laya, FakeLlmEngine())
    assert result.stage == FinalStage.KEYWORD
    assert result.matched_topic_ids == ["t1"]
    assert result.alert_kind == "topics"  # dispatcher decides it is silent
    assert laya.calls == [] and laya.ensure_loaded_calls == 0
    assert rec.records == []


def test_keyword_only_topics_never_record(make_message):
    topics = [topic("t1", "甲", laya_enabled=False), topic("t2", "乙", laya_enabled=False)]
    laya = FakeLayaEngine()
    result, rec = run(make_message("无关消息"), cfg_with(topics), laya, FakeLlmEngine())
    assert result.stage == FinalStage.NO_MATCH
    assert result.alert_kind is None
    assert laya.calls == []
    assert rec.records == []


# ------------------------------------------------------------------ stage 2


def test_laya_match(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.9})
    result, rec = run(make_message("语义消息"), cfg_with([topic()]), laya, FakeLlmEngine())
    assert result.stage == FinalStage.LAYA
    assert result.alert_kind == "topics"
    assert result.scores == {"t1": 0.9}
    assert len(rec.records) == 1
    assert rec.records[0]["schema_version"] == 2
    assert rec.records[0]["final_stage"] == "laya"
    assert rec.records[0]["alerted_topics"] == ["t1"]
    assert rec.records[0]["human_label"] is None


def test_threshold_boundary_inclusive(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.5})
    t = topic(match_threshold=0.5, llm_threshold=0.5)
    result, _ = run(make_message("x"), cfg_with([t]), laya, FakeLlmEngine())
    assert result.stage == FinalStage.LAYA


def test_ordered_laya_first_yes_wins(make_message):
    topics = [topic("t1", "甲"), topic("t2", "乙")]
    laya = FakeLayaEngine(scores={"t1": 0.9, "t2": 0.8})
    result, rec = run(make_message("x"), cfg_with(topics), laya, FakeLlmEngine())
    assert result.stage == FinalStage.LAYA
    assert result.matched_topic_ids == ["t1"]
    decisions = rec.records[0]["topic_decisions"]
    assert [d["topic_id"] for d in decisions] == ["t1"]  # t2 never evaluated


def test_laya_batch_is_single_pass(make_message):
    topics = [topic("t1", "甲"), topic("t2", "乙"), topic("t3", "丙")]
    laya = FakeLayaEngine(scores={"t1": 0.1, "t2": 0.1, "t3": 0.9})
    result, _ = run(make_message("x"), cfg_with(topics), laya, FakeLlmEngine())
    assert result.matched_topic_ids == ["t3"]
    assert len(laya.calls) == 1
    assert set(laya.calls[0][1]) == {"t1", "t2", "t3"}


def test_laya_disabled_excluded_from_questions(make_message):
    topics = [topic("t1", "甲", laya_enabled=False), topic("t2", "乙")]
    laya = FakeLayaEngine(scores={"t2": 0.9})
    result, rec = run(make_message("x"), cfg_with(topics), laya, FakeLlmEngine())
    assert result.matched_topic_ids == ["t2"]
    assert set(laya.calls[0][1]) == {"t2"}
    assert set(rec.records[0]["questions"]) == {"t2"}


def test_confident_no_skips_to_next_topic(make_message):
    # p=0.2 -> conf 0.8 >= 0.6: confidently unrelated, move on to t2.
    topics = [topic("t1", "甲"), topic("t2", "乙")]
    laya = FakeLayaEngine(scores={"t1": 0.2, "t2": 0.9})
    llm = FakeLlmEngine()
    result, rec = run(make_message("x"), cfg_with(topics), laya, llm)
    assert result.stage == FinalStage.LAYA
    assert result.matched_topic_ids == ["t2"]
    assert llm.calls == []
    decisions = rec.records[0]["topic_decisions"]
    assert (decisions[0]["outcome"], decisions[0]["detail"]) == ("skip", "confident no")


def test_all_confident_no_is_no_match(make_message):
    laya = FakeLayaEngine(scores={"t1": 0.2})
    llm = FakeLlmEngine()
    result, rec = run(make_message("x"), cfg_with([topic()]), laya, llm)
    assert result.stage == FinalStage.NO_MATCH
    assert result.alert_kind is None
    assert llm.calls == []
    assert rec.records[0]["final_stage"] == "no_match"


def test_confident_no_even_with_llm_enabled(make_message):
    # match 0.8: p=0.1 -> conf 0.9 >= 0.8 -> confident no, LLM must NOT fire.
    t = topic(match_threshold=0.8, llm_threshold=0.8, llm_enabled=True)
    laya = FakeLayaEngine(scores={"t1": 0.1})
    llm = FakeLlmEngine(matched=["t1"])
    result, _ = run(make_message("x"), cfg_with([t], llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.NO_MATCH
    assert llm.calls == []


def test_pass_through_band_skips_without_llm(make_message):
    # match 0.9, llm 0.6: conf 0.75 sits in [0.6, 0.9) -> not triggered, next topic.
    t = topic(match_threshold=0.9, llm_threshold=0.6, llm_enabled=True)
    laya = FakeLayaEngine(scores={"t1": 0.75})
    llm = FakeLlmEngine(matched=["t1"])
    result, rec = run(make_message("x"), cfg_with([t], llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.NO_MATCH
    assert result.alert_kind is None
    assert llm.calls == []
    assert rec.records[0]["topic_decisions"][0]["detail"] == "pass-through band"


def test_pass_through_then_next_topic_matches(make_message):
    topics = [
        topic("t1", "甲", match_threshold=0.9, llm_threshold=0.6, llm_enabled=True),
        topic("t2", "乙", keywords=[KeywordRule(pattern="例会")]),
    ]
    laya = FakeLayaEngine(scores={"t1": 0.75})
    llm = FakeLlmEngine(matched=["t1"])
    result, _ = run(make_message("月例会通知"), cfg_with(topics, llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.KEYWORD
    assert result.matched_topic_ids == ["t2"]
    assert llm.calls == []


def test_per_topic_thresholds_are_independent(make_message):
    topics = [
        topic("t1", "甲", match_threshold=0.9, llm_threshold=0.6),
        topic("t2", "乙", match_threshold=0.6, llm_threshold=0.6),
    ]
    laya = FakeLayaEngine(scores={"t1": 0.75, "t2": 0.75})
    result, _ = run(make_message("x"), cfg_with(topics), laya, FakeLlmEngine())
    assert result.matched_topic_ids == ["t2"]  # same score, different thresholds


# ------------------------------------------------------------------ stage 3


def test_low_confidence_llm_match(make_message):
    # equal thresholds 0.8: p=0.3 -> conf 0.7 < 0.8 -> LLM for this topic only.
    t = topic(match_threshold=0.8, llm_threshold=0.8, llm_enabled=True)
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(matched=["t1"])
    result, rec = run(make_message("x"), cfg_with([t], llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.LLM
    assert result.alert_kind == "topics"
    assert len(llm.calls) == 1
    assert llm.calls[0][1] == ["t1"]  # single-topic catalog
    assert rec.records[0]["final_stage"] == "llm"
    assert rec.records[0]["llm_calls"][0]["matched_topic_ids"] == ["t1"]


def test_llm_no_skips_to_next_topic(make_message):
    topics = [
        topic("t1", "甲", match_threshold=0.8, llm_threshold=0.8, llm_enabled=True),
        topic("t2", "乙"),
    ]
    laya = FakeLayaEngine(scores={"t1": 0.3, "t2": 0.9})
    llm = FakeLlmEngine(matched=[])
    result, rec = run(make_message("x"), cfg_with(topics, llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.LAYA
    assert result.matched_topic_ids == ["t2"]
    assert len(llm.calls) == 1 and llm.calls[0][1] == ["t1"]
    assert rec.records[0]["topic_decisions"][0]["detail"] == "LLM judged no"


def test_llm_no_at_end_is_no_match(make_message):
    t = topic(match_threshold=0.8, llm_threshold=0.8, llm_enabled=True)
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(matched=[])
    result, rec = run(make_message("x"), cfg_with([t], llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.NO_MATCH
    assert result.alert_kind is None
    assert rec.records[0]["final_stage"] == "no_match"


def test_uncertain_llm_disabled_is_unclassified(make_message):
    t = topic(match_threshold=0.8, llm_threshold=0.8)  # llm_enabled defaults False
    laya = FakeLayaEngine(scores={"t1": 0.6})
    llm = FakeLlmEngine()
    result, rec = run(make_message("x"), cfg_with([t], llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.UNCLASSIFIED
    assert result.alert_kind == "unclassified"
    assert llm.calls == []
    assert rec.records[0]["topic_decisions"][0]["outcome"] == "unresolved"


def test_uncertain_llm_not_configured_is_unclassified(make_message):
    t = topic(match_threshold=0.8, llm_threshold=0.8, llm_enabled=True)
    laya = FakeLayaEngine(scores={"t1": 0.6})
    result, _ = run(make_message("x"), cfg_with([t]), laya, FakeLlmEngine())
    assert result.stage == FinalStage.UNCLASSIFIED
    assert result.alert_kind == "unclassified"


def test_llm_failure_is_unclassified(make_message):
    t = topic(match_threshold=0.8, llm_threshold=0.8, llm_enabled=True)
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(error=RuntimeError("boom"))
    result, rec = run(make_message("x"), cfg_with([t], llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.UNCLASSIFIED
    assert result.alert_kind == "unclassified"
    assert "boom" in rec.records[0]["llm_calls"][0]["error"]


def test_llm_failure_continues_to_next_topic(make_message):
    topics = [
        topic("t1", "甲", match_threshold=0.8, llm_threshold=0.8, llm_enabled=True),
        topic("t2", "乙", keywords=[KeywordRule(pattern="例会")]),
    ]
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(error=RuntimeError("boom"))
    result, rec = run(
        make_message("月例会通知"), cfg_with(topics, llm=LLM_CONFIGURED), laya, llm
    )
    assert result.stage == FinalStage.KEYWORD
    assert result.matched_topic_ids == ["t2"]
    assert rec.records[0]["final_stage"] == "keyword"
    assert "boom" in rec.records[0]["llm_calls"][0]["error"]


def test_llm_unknown_ids_ignored(make_message):
    t = topic(match_threshold=0.8, llm_threshold=0.8, llm_enabled=True)
    laya = FakeLayaEngine(scores={"t1": 0.3})
    llm = FakeLlmEngine(matched=["ghost"])
    result, _ = run(make_message("x"), cfg_with([t], llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.NO_MATCH  # ghost id is not this topic


def test_mixed_confident_no_and_uncertain_routes_llm(make_message):
    topics = [
        topic("t1", "甲", match_threshold=0.8, llm_threshold=0.8, llm_enabled=True),
        topic("t2", "乙", match_threshold=0.8, llm_threshold=0.8, llm_enabled=True),
    ]
    laya = FakeLayaEngine(scores={"t1": 0.1, "t2": 0.6})  # conf 0.9 / 0.6
    llm = FakeLlmEngine(matched=["t2"])
    result, rec = run(make_message("x"), cfg_with(topics, llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.LLM
    assert len(llm.calls) == 1 and llm.calls[0][1] == ["t2"]
    assert rec.records[0]["topic_decisions"][0]["detail"] == "confident no"


def test_confident_yes_short_circuits_uncertain(make_message):
    topics = [
        topic("t1", "甲"),
        topic("t2", "乙", match_threshold=0.8, llm_threshold=0.8, llm_enabled=True),
    ]
    laya = FakeLayaEngine(scores={"t1": 0.9, "t2": 0.6})
    llm = FakeLlmEngine(matched=["t2"])
    result, _ = run(make_message("x"), cfg_with(topics, llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.LAYA
    assert result.matched_topic_ids == ["t1"]
    assert llm.calls == []  # t2 never evaluated


# ------------------------------------------------------------------ failures


def test_laya_failure_unclassified_no_llm(make_message):
    t = topic(llm_enabled=True)
    laya = FakeLayaEngine(error=RuntimeError("model broken"))
    llm = FakeLlmEngine(matched=["t1"])
    result, rec = run(make_message("x"), cfg_with([t], llm=LLM_CONFIGURED), laya, llm)
    assert result.stage == FinalStage.UNCLASSIFIED
    assert result.alert_kind == "unclassified"
    assert llm.calls == []  # broken model must not silently burn LLM tokens
    assert len(rec.records) == 1
    assert "model broken" in rec.records[0]["error"]
    assert rec.records[0]["answers"] == {}


def test_laya_failure_keyword_topic_still_matches(make_message):
    topics = [topic("t1", "甲"), topic("t2", "乙", keywords=[KeywordRule(pattern="例会")])]
    laya = FakeLayaEngine(error=RuntimeError("model broken"))
    result, rec = run(make_message("月例会通知"), cfg_with(topics), laya, FakeLlmEngine())
    assert result.stage == FinalStage.KEYWORD
    assert result.matched_topic_ids == ["t2"]
    assert "model broken" in rec.records[0]["error"]
    assert rec.records[0]["final_stage"] == "keyword"


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
        "sender", "channel", "model", "questions", "answers", "usage",
        "duration_ms", "error", "topic_decisions", "llm_calls",
        "final_stage", "alerted_topics", "human_label",
    }
    assert set(r) == expected_keys
    assert r["questions"]["t1"]["type"] == "noul"
    assert r["model"]["repo"] == "convaiinnovations/laya"
    decision = r["topic_decisions"][0]
    assert decision["topic_id"] == "t1"
    assert decision["match_threshold"] == 0.6 and decision["llm_threshold"] == 0.6
    assert decision["score"] == 0.9 and decision["confidence"] == 0.9
