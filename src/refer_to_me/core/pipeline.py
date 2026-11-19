"""Ordered per-topic classification pipeline (pure logic, engines injected).

Topics are evaluated front-to-back; the first successful match short-circuits
all subsequent work. Per topic the cascade is: keyword/regex -> Laya (if the
topic enables it) -> LLM (if the topic enables it and Laya confidence is below
the topic's ``llm_threshold``).

Laya still runs as ONE batched forward pass over all Laya-enabled topics, but
lazily: it is triggered by the first topic that actually needs a Laya answer.
An early keyword-only filter topic can therefore match without the model ever
running. LLM calls are per topic (single-topic catalog) so a match stops the
cascade before later topics burn tokens.

Every Laya invocation produces exactly one JSONL dataset record (schema v2),
written in ``finally`` so the final stage and LLM outcomes are included even
on failure.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Protocol

from refer_to_me.config import AppConfig, TopicConfig
from refer_to_me.core.laya_engine import LayaRawResult
from refer_to_me.core.llm_engine import TopicDecision
from refer_to_me.core.matcher import topic_keyword_hit
from refer_to_me.core.message import FinalStage, IncomingMessage, LogEvent, PipelineResult
from refer_to_me.core.questions import build_questions
from refer_to_me.core.recorder import Recorder

logger = logging.getLogger(__name__)

MAX_TEXT_LEN = 10000


class LayaEngineProtocol(Protocol):
    def ensure_loaded(self) -> None: ...

    def classify(self, text: str, questions: dict) -> LayaRawResult: ...


class LlmEngineProtocol(Protocol):
    def classify(
        self, text: str, topics: Sequence[TopicConfig], scores: dict[str, float]
    ) -> TopicDecision: ...


class Pipeline:
    def __init__(self, laya: LayaEngineProtocol, llm: LlmEngineProtocol):
        self._laya = laya
        self._llm = llm

    def process(
        self, msg: IncomingMessage, cfg: AppConfig, recorder: Recorder
    ) -> PipelineResult:
        events: list[LogEvent] = []
        text = msg.text.strip()
        if len(text) > MAX_TEXT_LEN:
            text = text[:MAX_TEXT_LEN]
            events.append(LogEvent("system", f"message truncated to {MAX_TEXT_LEN} chars"))
        events.append(LogEvent("input", f"[{msg.source}] {text[:200]}"))
        topics = cfg.enabled_topics()  # configuration order = matching priority
        if not topics:
            events.append(LogEvent("system", "no enabled topics; skipping classification"))
            return PipelineResult(stage=FinalStage.NO_TOPICS, events=events)

        questions = build_questions(topics)
        record: dict | None = None  # created only when a Laya inference is attempted
        scores: dict[str, float] = {}
        laya_error: str | None = None
        decisions: list[dict] = []
        llm_calls: list[dict] = []
        unresolved: list[TopicConfig] = []
        result = PipelineResult(stage=FinalStage.NO_MATCH, events=events)

        try:
            for topic in topics:
                # Stage 1 (per topic): keyword / regex short-circuit.
                if topic_keyword_hit(text, topic):
                    decisions.append(self._decision(topic, "match", "keyword"))
                    events.append(
                        LogEvent("keyword", f"matched 「{topic.name}」 by keyword")
                    )
                    return self._matched(result, FinalStage.KEYWORD, topic)
                if not topic.laya_enabled:
                    decisions.append(
                        self._decision(topic, "skip", None, detail="keyword-only; no hit")
                    )
                    events.append(
                        LogEvent(
                            "keyword",
                            f"「{topic.name}」 skipped: no keyword hit (Laya disabled)",
                        )
                    )
                    continue

                # Stage 2: Laya — one batched forward pass, lazily on first need.
                if record is None:
                    record = self._new_record(msg, cfg, questions)
                    try:
                        self._laya.ensure_loaded()
                        raw = self._laya.classify(text, questions)
                    except Exception as exc:  # noqa: BLE001 - engine failure
                        laya_error = f"{type(exc).__name__}: {exc}"
                        record["error"] = laya_error
                        events.append(LogEvent("error", f"Laya failed: {exc}"))
                    else:
                        record["answers"] = raw.answers
                        record["usage"] = raw.usage
                        record["duration_ms"] = raw.duration_ms
                        record["model"] = {
                            "mode": raw.mode,
                            "repo": raw.repo,
                            "subfolder": raw.subfolder,
                            "revision": raw.revision,
                            "device": raw.device,
                        }
                        for tid in questions:
                            ans = raw.answers.get(tid)
                            if ans is None or "noul" not in ans:
                                logger.warning(
                                    "Laya answer missing for topic %s; treated as 0.0", tid
                                )
                                scores[tid] = 0.0
                            else:
                                scores[tid] = float(ans["noul"])
                        result.scores = scores
                        events.append(
                            LogEvent(
                                "laya",
                                "scores: "
                                + ", ".join(
                                    f"{t.name}={scores[t.id]:.3f} "
                                    f"(conf {max(scores[t.id], 1 - scores[t.id]):.3f})"
                                    for t in topics
                                    if t.laya_enabled
                                ),
                            )
                        )
                if laya_error is not None:
                    decisions.append(
                        self._decision(topic, "unresolved", None, detail="Laya failed")
                    )
                    unresolved.append(topic)
                    continue

                # Score = P(true); confidence = max(p, 1-p) in [0.5, 1].
                # conf >= match_threshold: Laya's yes/no is final.
                # llm_threshold <= conf < match_threshold: pass-through band,
                #   the topic is not triggered; move on to the next topic.
                # conf < llm_threshold: consult the LLM if the topic allows it.
                p = scores[topic.id]
                conf = max(p, 1.0 - p)
                if conf >= topic.match_threshold:
                    if p >= topic.match_threshold:
                        decisions.append(
                            self._decision(topic, "match", "laya", p, conf, "confident yes")
                        )
                        events.append(
                            LogEvent(
                                "laya",
                                f"matched 「{topic.name}」 "
                                f"(p={p:.3f} ≥ {topic.match_threshold:.2f})",
                            )
                        )
                        return self._matched(result, FinalStage.LAYA, topic)
                    decisions.append(
                        self._decision(topic, "skip", "laya", p, conf, "confident no")
                    )
                    events.append(
                        LogEvent(
                            "laya",
                            f"「{topic.name}」 skipped: confident no "
                            f"(conf {conf:.3f} ≥ {topic.match_threshold:.2f})",
                        )
                    )
                    continue
                if conf >= topic.llm_threshold:
                    decisions.append(
                        self._decision(topic, "skip", "laya", p, conf, "pass-through band")
                    )
                    events.append(
                        LogEvent(
                            "laya",
                            f"「{topic.name}」 skipped: conf {conf:.3f} in pass-through "
                            f"band [{topic.llm_threshold:.2f}, {topic.match_threshold:.2f})",
                        )
                    )
                    continue

                # Stage 3 (per topic): low confidence -> optional LLM.
                if not topic.llm_enabled or not cfg.llm.is_configured():
                    reason = (
                        "LLM disabled for topic"
                        if not topic.llm_enabled
                        else "LLM not configured"
                    )
                    decisions.append(
                        self._decision(topic, "unresolved", None, p, conf, reason)
                    )
                    events.append(
                        LogEvent(
                            "laya",
                            f"「{topic.name}」 unresolved: "
                            f"conf {conf:.3f} < {topic.llm_threshold:.2f}; {reason}",
                        )
                    )
                    unresolved.append(topic)
                    continue
                try:
                    decision = self._llm.classify(text, [topic], {topic.id: p})
                except Exception as exc:  # noqa: BLE001 - LLM failure
                    llm_calls.append(
                        {"topic_id": topic.id, "error": f"{type(exc).__name__}: {exc}"}
                    )
                    decisions.append(
                        self._decision(topic, "unresolved", "llm", p, conf, "LLM failed")
                    )
                    events.append(LogEvent("error", f"LLM failed for 「{topic.name}」: {exc}"))
                    unresolved.append(topic)
                    continue
                llm_calls.append(
                    {
                        "topic_id": topic.id,
                        "matched_topic_ids": decision.matched_topic_ids,
                        "reason": decision.reason,
                    }
                )
                if topic.id in decision.matched_topic_ids:
                    decisions.append(
                        self._decision(topic, "match", "llm", p, conf, "LLM matched")
                    )
                    events.append(LogEvent("llm", f"matched 「{topic.name}」 via LLM"))
                    return self._matched(result, FinalStage.LLM, topic)
                decisions.append(
                    self._decision(topic, "skip", "llm", p, conf, "LLM judged no")
                )
                events.append(LogEvent("llm", f"「{topic.name}」 skipped: LLM judged no"))

            # No topic matched: unresolved topics route to the unclassified
            # alert; otherwise the message is silently archived.
            if unresolved:
                events.append(
                    LogEvent(
                        "system",
                        "unresolved topics: " + ", ".join(t.name for t in unresolved),
                    )
                )
                result.stage = FinalStage.UNCLASSIFIED
                result.alert_kind = "unclassified"
            else:
                events.append(LogEvent("system", "no topic matched"))
            return result
        finally:
            if record is not None:
                record["topic_decisions"] = decisions
                record["llm_calls"] = llm_calls
                record["final_stage"] = result.stage.value
                record["alerted_topics"] = (
                    result.matched_topic_ids if result.alert_kind == "topics" else []
                )
                result.dataset_written = recorder.append(record)
                if not result.dataset_written:
                    events.append(LogEvent("error", "dataset write failed"))

    @staticmethod
    def _matched(result: PipelineResult, stage: FinalStage, topic: TopicConfig) -> PipelineResult:
        result.stage = stage
        result.matched_topic_ids = [topic.id]
        result.alert_kind = "topics"
        return result

    @staticmethod
    def _decision(
        topic: TopicConfig,
        outcome: str,
        via: str | None,
        score: float | None = None,
        confidence: float | None = None,
        detail: str = "",
    ) -> dict:
        return {
            "topic_id": topic.id,
            "outcome": outcome,  # match | skip | unresolved
            "via": via,  # keyword | laya | llm | None
            "score": score,
            "confidence": confidence,
            "match_threshold": topic.match_threshold,
            "llm_threshold": topic.llm_threshold,
            "detail": detail,
        }

    @staticmethod
    def _new_record(msg: IncomingMessage, cfg: AppConfig, questions: dict) -> dict:
        return {
            "schema_version": 2,
            "record_id": uuid.uuid4().hex,
            "message_id": msg.id,
            "ts": datetime.now(UTC).isoformat(),
            "source": msg.source,
            "message_text": msg.text,
            "sender": msg.sender,
            "channel": msg.channel,
            "model": {
                "mode": cfg.laya.mode,
                "repo": None,
                "subfolder": None,
                "revision": None,
                "device": None,
            },
            "questions": questions,
            "answers": {},
            "usage": None,
            "duration_ms": None,
            "error": None,
            "topic_decisions": [],
            "llm_calls": [],
            "final_stage": None,
            "alerted_topics": [],
            "human_label": None,
        }
