"""noul question building from topic config."""

from refer_to_me.config import TopicConfig
from refer_to_me.core.questions import build_questions


def test_defaults_generated():
    t = TopicConfig(id="t1", name="月例会")
    q = build_questions([t])
    assert set(q) == {"t1"}
    assert q["t1"] == {
        "type": "noul",
        "instructions": "这条消息是否与「月例会」有关？",
        "criteria": {
            "true": "消息讨论月例会相关的内容、安排、通知或问题",
            "false": "消息与月例会无关",
        },
    }


def test_description_used_as_true_criterion():
    t = TopicConfig(id="t1", name="报销政策", description="讨论报销流程与标准")
    q = build_questions([t])
    assert q["t1"]["criteria"]["true"] == "讨论报销流程与标准"


def test_user_fields_override_defaults():
    t = TopicConfig(
        id="t1",
        name="月例会",
        laya_instructions="Is this about the monthly meeting?",
        laya_criteria_true="mentions agenda or schedule",
        laya_criteria_false="unrelated chatter",
    )
    q = build_questions([t])
    assert q["t1"]["instructions"] == "Is this about the monthly meeting?"
    assert q["t1"]["criteria"] == {
        "true": "mentions agenda or schedule",
        "false": "unrelated chatter",
    }


def test_only_three_keys():
    t = TopicConfig(id="t1", name="x", description="d")
    q = build_questions([t])
    assert set(q["t1"]) == {"type", "instructions", "criteria"}
    assert set(q["t1"]["criteria"]) == {"true", "false"}


def test_empty_topics():
    assert build_questions([]) == {}
