"""Three-stage short-circuit classification pipeline (pure logic, engines injected).

Stage 1 keyword/regex -> Stage 2 Laya (per-topic noul) -> Stage 3 optional LLM.
Every Laya invocation produces exactly one JSONL dataset record, written in
``finally`` so the final stage and LLM outcome are included even on failure.
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
from refer_to_me.core.matcher import match_keywords
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
        topics = cfg.enabled_topics()

        # Stage 1: keyword / regex short-circuit (no model, no dataset record).
        hits = match_keywords(text, topics)
        if hits:
            events.append(LogEvent("keyword", "matched: " + ", ".join(t.name for t in hits)))
            return PipelineResult(
                stage=FinalStage.KEYWORD,
                matched_topic_ids=[t.id for t in hits],
                alert_kind="topics",
                events=events,
            )

        if not topics:
            events.append(LogEvent("system", "no enabled topics; skipping classification"))
            return PipelineResult(stage=FinalStage.NO_TOPICS, events=events)

        # Stage 2 (+3): Laya, then optional LLM. One dataset record per path.
        questions = build_questions(topics)
        record = self._new_record(msg, cfg, questions)
        result = PipelineResult(stage=FinalStage.UNCLASSIFIED, events=events)
        try:
            try:
                self._laya.ensure_loaded()
                raw = self._laya.classify(text, questions)
            except Exception as exc:  # noqa: BLE001 - engine failure -> unclassified
                record["error"] = f"{type(exc).__name__}: {exc}"
                events.append(LogEvent("error", f"Laya failed: {exc}"))
                result.alert_kind = "unclassified"
                return result

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
            scores: dict[str, float] = {}
            for tid in questions:
                ans = raw.answers.get(tid)
                if ans is None or "noul" not in ans:
                    logger.warning("Laya answer missing for topic %s; treated as 0.0", tid)
                    scores[tid] = 0.0
                else:
                    scores[tid] = float(ans["noul"])
            result.scores = scores
            # Score = P(true); confidence = max(p, 1-p) in [0.5, 1].
            # The threshold applies to CONFIDENCE: a topic matches when the
            # model is confidently "yes" (p >= threshold >= 0.5); it is
            # uncertain when confidence < threshold; otherwise it is a
            # confident "no". Only uncertainty routes to the LLM.
            threshold = cfg.laya.threshold
            confidences = {tid: max(p, 1.0 - p) for tid, p in scores.items()}
            matched = [t for t in topics if scores[t.id] >= threshold]
            uncertain = [t for t in topics if confidences[t.id] < threshold]
            record["laya_matched_topics"] = [t.id for t in matched]
            record["laya_uncertain_topics"] = [t.id for t in uncertain]
            events.append(
                LogEvent(
                    "laya",
                    "scores: "
                    + ", ".join(
                        f"{t.name}={scores[t.id]:.3f} (conf {confidences[t.id]:.3f})"
                        for t in topics
                    ),
                )
            )
            if matched:
                result.stage = FinalStage.LAYA
                result.matched_topic_ids = [t.id for t in matched]
                result.alert_kind = "topics"
                return result

            if not uncertain:
                # Confidently unrelated to every topic: no alert, no LLM.
                events.append(LogEvent("laya", "confident: no topic matches"))
                result.stage = FinalStage.LAYA_NONE
                return result

            # Stage 3: at least one topic is uncertain (low confidence).
            if not cfg.llm.enabled:
                events.append(LogEvent("llm", "low confidence; LLM not configured"))
                result.alert_kind = "unclassified"
                return result
            try:
                decision = self._llm.classify(text, topics, scores)
            except Exception as exc:  # noqa: BLE001 - LLM failure -> unclassified
                record["llm"] = {"error": f"{type(exc).__name__}: {exc}"}
                events.append(LogEvent("error", f"LLM failed: {exc}"))
                result.alert_kind = "unclassified"
                return result
            record["llm"] = {
                "matched_topics": decision.matched_topic_ids,
                "reason": decision.reason,
            }
            by_id = {t.id: t for t in topics}
            llm_matched = [by_id[tid] for tid in decision.matched_topic_ids if tid in by_id]
            if llm_matched:
                events.append(
                    LogEvent("llm", "matched: " + ", ".join(t.name for t in llm_matched))
                )
                result.stage = FinalStage.LLM
                result.matched_topic_ids = [t.id for t in llm_matched]
                result.alert_kind = "topics"
            else:
                events.append(LogEvent("llm", "decided: no topic matches"))
                result.stage = FinalStage.LLM_NONE
            return result
        finally:
            record["final_stage"] = result.stage.value
            record["alerted_topics"] = (
                result.matched_topic_ids if result.alert_kind == "topics" else []
            )
            result.dataset_written = recorder.append(record)
            if not result.dataset_written:
                events.append(LogEvent("error", "dataset write failed"))

    @staticmethod
    def _new_record(msg: IncomingMessage, cfg: AppConfig, questions: dict) -> dict:
        return {
            "schema_version": 1,
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
            "threshold": cfg.laya.threshold,
            "answers": {},
            "usage": None,
            "duration_ms": None,
            "error": None,
            "laya_matched_topics": [],
            "laya_uncertain_topics": [],
            "final_stage": None,
            "llm": None,
            "alerted_topics": [],
            "human_label": None,
        }
