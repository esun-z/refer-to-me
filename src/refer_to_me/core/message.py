"""Message and pipeline result value objects."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Literal


class FinalStage(str, Enum):
    """Terminal stage of the classification pipeline for one message."""

    KEYWORD = "keyword"  # matched by keyword/regex
    LAYA = "laya"  # matched by a confident Laya "yes"
    LLM = "llm"  # matched by the LLM fallback
    NO_MATCH = "no_match"  # every topic decisively skipped; no alert
    UNCLASSIFIED = "unclassified"  # some topic unresolved (uncertain/engine failure)
    NO_TOPICS = "no_topics"


@dataclass(frozen=True)
class IncomingMessage:
    id: str
    source: str  # "webhook" | "ntfy:<topic>" | "simulator"
    text: str
    received_at: float
    sender: str | None = None
    channel: str | None = None
    raw: dict | None = None

    @staticmethod
    def create(
        source: str,
        text: str,
        sender: str | None = None,
        channel: str | None = None,
        raw: dict | None = None,
    ) -> IncomingMessage:
        return IncomingMessage(
            id=uuid.uuid4().hex,
            source=source,
            text=text,
            received_at=time.time(),
            sender=sender,
            channel=channel,
            raw=raw,
        )


@dataclass(frozen=True)
class LogEvent:
    stage: str  # input | keyword | laya | llm | alert | error | system
    text: str


@dataclass
class PipelineResult:
    stage: FinalStage
    matched_topic_ids: list[str] = field(default_factory=list)
    scores: dict[str, float] = field(default_factory=dict)
    alert_kind: Literal["topics", "unclassified"] | None = None
    events: list[LogEvent] = field(default_factory=list)
    dataset_written: bool = False
