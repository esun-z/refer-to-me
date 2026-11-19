"""Opt-in smoke test: real LLM fallback via an OpenAI-compatible endpoint.

Usage (e.g. local llama.cpp server):
    uv run python scripts/smoke_llm.py --base-url http://127.0.0.1:8080/v1 --model local

Gate: test_connection succeeds and every classify call returns a valid
structured TopicDecision with known topic ids. Match quality is printed for
human review (a 4B local model may over/under-match; that is not the gate).
"""

from __future__ import annotations

import argparse
import sys

from refer_to_me.config import LlmConfig, TopicConfig
from refer_to_me.core.llm_engine import LlmEngine


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model", default="local-model")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--mode", choices=["JSON", "MD_JSON", "TOOLS"], default="JSON")
    args = parser.parse_args()

    cfg = LlmConfig(
        base_url=args.base_url,
        api_key=args.api_key,
        model=args.model,
        mode=args.mode,
        timeout_s=120,
        max_retries=2,
    )
    engine = LlmEngine(cfg)

    ok, detail = engine.test_connection()
    print(f"test_connection: {ok} | {detail}")
    if not ok:
        return 1

    topics = [
        TopicConfig(id="monthly_meeting", name="月例会", description="每月例行工作会议"),
        TopicConfig(id="reimbursement", name="报销政策", description="报销流程与标准"),
    ]
    cases = [
        ("年会旅游报销政策什么时候发布？需要哪些单据？", {"reimbursement"}),
        ("The monthly meeting moved to Thursday 3pm.", {"monthly_meeting"}),
        ("今天天气不错，适合出去散步。", set()),
    ]
    valid = {t.id for t in topics}
    for text, expected in cases:
        decision = engine.classify(text, topics, scores={})
        got = set(decision.matched_topic_ids)
        if not got <= valid:
            print(f"FAIL: unknown ids {got - valid}")
            return 1
        mark = "OK " if got == expected else "DIFF"
        print(f"[{mark}] {text[:40]} -> {sorted(got)} (expected {sorted(expected)})")
        print(f"       reason: {decision.reason[:120]}")
    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
