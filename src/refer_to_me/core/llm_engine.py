"""Pipeline stage 3: OpenAI-compatible LLM fallback via instructor."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from pydantic import BaseModel, Field

from refer_to_me.config import LlmConfig, TopicConfig

logger = logging.getLogger(__name__)


class LlmError(RuntimeError):
    """LLM call failed after retries; pipeline routes to unclassified."""


class TopicDecision(BaseModel):
    matched_topic_ids: list[str] = Field(default_factory=list)
    reason: str = ""


class _Ping(BaseModel):
    ok: bool


_SYSTEM_PROMPT = (
    "You are a message topic classifier. Given a catalog of topics and one message, "
    "select zero or more topic ids the message relates to. Only use ids from the "
    "catalog; select none if the message is unrelated to every topic."
)


class LlmEngine:
    def __init__(self, cfg: LlmConfig):
        self._cfg = cfg
        self._client = None

    def _ensure_client(self):
        if self._client is None:
            import instructor

            self._client = instructor.from_provider(
                f"openai/{self._cfg.model}",
                api_key=self._cfg.api_key or "EMPTY",
                base_url=self._cfg.base_url,
                mode=instructor.Mode[self._cfg.mode],
            )
        return self._client

    def classify(
        self,
        text: str,
        topics: Sequence[TopicConfig],
        scores: dict[str, float],
    ) -> TopicDecision:
        client = self._ensure_client()
        catalog = "\n".join(
            f"- id={t.id} name={t.name} description={t.description}" for t in topics
        )
        score_lines = "\n".join(f"- {tid}: {score:.4f}" for tid, score in scores.items())
        user = (
            f"Topics:\n{catalog}\n\n"
            f"Laya model scores (auxiliary, below threshold):\n{score_lines}\n\n"
            f"Message:\n{text}"
        )
        try:
            decision = client.create(
                response_model=TopicDecision,
                messages=[
                    {"role": "system", "content": _SYSTEM_PROMPT},
                    {"role": "user", "content": user},
                ],
                max_retries=self._cfg.max_retries,
                timeout=self._cfg.timeout_s,
            )
        except Exception as exc:
            raise LlmError(f"{type(exc).__name__}: {exc}") from exc
        valid = {t.id for t in topics}
        filtered = [tid for tid in decision.matched_topic_ids if tid in valid]
        if len(filtered) != len(decision.matched_topic_ids):
            logger.warning("LLM returned unknown topic ids; dropped")
        return TopicDecision(matched_topic_ids=filtered, reason=decision.reason)

    def test_connection(self) -> tuple[bool, str]:
        try:
            client = self._ensure_client()
            ping = client.create(
                response_model=_Ping,
                messages=[{"role": "user", "content": "Reply with ok=true."}],
                max_retries=0,
                timeout=self._cfg.timeout_s,
            )
            return True, "Connection OK" if ping.ok else "Endpoint responded (ok=false)"
        except Exception as exc:  # noqa: BLE001 - report, never raise
            return False, f"{type(exc).__name__}: {exc}"
