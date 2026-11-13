"""Build Laya noul questions from topic configuration.

One yes/no question per topic; all questions are answered in a single forward
pass. Only ``type`` / ``instructions`` / ``criteria`` keys are read by Laya.
"""

from __future__ import annotations

from collections.abc import Sequence

from refer_to_me.config import TopicConfig


def default_instructions(name: str) -> str:
    return f"这条消息是否与「{name}」有关？"


def default_criteria_true(name: str, description: str) -> str:
    return description.strip() or f"消息讨论{name}相关的内容、安排、通知或问题"


def default_criteria_false(name: str) -> str:
    return f"消息与{name}无关"


def build_questions(topics: Sequence[TopicConfig]) -> dict:
    questions: dict = {}
    for topic in topics:
        questions[topic.id] = {
            "type": "noul",
            "instructions": topic.laya_instructions.strip()
            or default_instructions(topic.name),
            "criteria": {
                "true": topic.laya_criteria_true.strip()
                or default_criteria_true(topic.name, topic.description),
                "false": topic.laya_criteria_false.strip()
                or default_criteria_false(topic.name),
            },
        }
    return questions
