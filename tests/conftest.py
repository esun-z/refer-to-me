"""Shared fakes: pipeline tests run without GPU, model downloads, or network."""

from __future__ import annotations

import os
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from refer_to_me.core.laya_engine import LayaRawResult
from refer_to_me.core.llm_engine import TopicDecision
from refer_to_me.core.message import IncomingMessage


class FakeLayaEngine:
    def __init__(self, scores: dict | None = None, error: Exception | None = None):
        self.scores = scores or {}
        self.error = error
        self.calls: list[tuple[str, dict]] = []
        self.ensure_loaded_calls = 0

    def ensure_loaded(self) -> None:
        self.ensure_loaded_calls += 1
        if self.error:
            raise self.error

    def classify(self, text: str, questions: dict) -> LayaRawResult:
        self.calls.append((text, questions))
        if self.error:
            raise self.error
        answers = {}
        for tid in questions:
            p = self.scores.get(tid, 0.0)
            answers[tid] = {"type": "noul", "noul": p, "confidence": max(p, 1 - p)}
        return LayaRawResult(
            answers=answers,
            usage={"input_tokens": 1},
            duration_ms=1.0,
            mode="multilingual",
            repo="convaiinnovations/laya",
            subfolder="multilingual",
            revision=None,
            device="cpu",
        )

    def reload_if_needed(self, cfg) -> None:
        pass

    def force_reload(self) -> None:
        pass

    def unload(self) -> None:
        pass


class FakeLlmEngine:
    def __init__(self, matched: list[str] | None = None, error: Exception | None = None):
        self.matched = matched or []
        self.error = error
        self.calls: list[tuple] = []

    def classify(self, text, topics, scores) -> TopicDecision:
        self.calls.append((text, [t.id for t in topics], scores))
        if self.error:
            raise self.error
        return TopicDecision(matched_topic_ids=list(self.matched), reason="fake")


class MemoryRecorder:
    def __init__(self):
        self.records: list[dict] = []

    def append(self, record: dict) -> bool:
        self.records.append(record)
        return True


@pytest.fixture
def make_message():
    def _make(text: str = "hello", source: str = "simulator") -> IncomingMessage:
        return IncomingMessage.create(source=source, text=text)

    return _make


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def wait_until(predicate, timeout: float = 5.0, app=None) -> None:
    """Spin the Qt event loop until predicate() is truthy (queued signals)."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        if app is not None:
            app.processEvents()
        time.sleep(0.01)
    raise AssertionError("wait_until timed out")
