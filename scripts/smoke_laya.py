"""Opt-in smoke test: real Laya model load + predict (NOT part of pytest).

Usage:
    uv run python scripts/smoke_laya.py --mode router --device cuda
    uv run python scripts/smoke_laya.py --mode multilingual --device cpu

Verifies the M1 gate: torch cu126 + transformers 5.x + laya compatibility,
cache-hit loading (no download expected when the HF cache is prepared),
and noul answer shape for Chinese/English messages.
"""

from __future__ import annotations

import argparse
import sys
import time


def main() -> int:
    # Windows console may default to GBK; force UTF-8 for Chinese output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["router", "english", "multilingual"], default="router")
    parser.add_argument("--device", choices=["auto", "cuda", "cpu"], default="auto")
    args = parser.parse_args()

    import torch
    import transformers

    print(f"torch {torch.__version__} | cuda available: {torch.cuda.is_available()}")
    print(f"transformers {transformers.__version__}")
    if args.device == "cuda" and not torch.cuda.is_available():
        print("FAIL: CUDA requested but unavailable")
        return 1
    device = args.device
    if device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"

    import laya

    print(f"laya {getattr(laya, '__version__', '?')} | mode={args.mode} device={device}")

    # Cache availability check (informational; HF is reachable so a miss just downloads).
    try:
        from huggingface_hub import scan_cache_dir

        repos = {r.repo_id for r in scan_cache_dir().repos}
        for repo in ("convaiinnovations/laya", "convaiinnovations/laya-multilingual"):
            print(f"cache: {repo} -> {'HIT' if repo in repos else 'MISS (will download)'}")
    except Exception as exc:  # noqa: BLE001 - informational only
        print(f"cache scan skipped: {exc}")

    t0 = time.perf_counter()
    if args.mode == "router":
        engine = laya.Router(device=device, preload=True)
    elif args.mode == "english":
        engine = laya.load("en", device=device)
    else:
        engine = laya.load("ml", device=device)
    print(f"model loaded in {time.perf_counter() - t0:.1f}s")

    questions = {
        "monthly_meeting": {
            "type": "noul",
            "instructions": "这条消息是否与月例会有关？",
            "criteria": {
                "true": "消息讨论月例会的时间、议程、通知或总结",
                "false": "消息与月例会无关",
            },
        },
        "reimbursement": {
            "type": "noul",
            "instructions": "这条消息是否涉及报销政策？",
            "criteria": {
                "true": "消息询问或讨论报销政策、流程或标准，例如年会旅游报销",
                "false": "消息与报销政策无关",
            },
        },
    }
    messages = [
        "下周月例会改到周四下午三点，请提前准备议程。",
        "年会旅游报销政策什么时候发布？需要哪些单据？",
        "The monthly meeting has been moved to Thursday 3pm.",
        "What is the reimbursement policy for annual party travel?",
        "今天天气不错，适合出去散步。",
    ]
    for text in messages:
        t0 = time.perf_counter()
        result = engine.predict(text, questions)
        dt_ms = (time.perf_counter() - t0) * 1000
        answers = result["answers"]
        if set(answers) != set(questions):
            print(f"FAIL: answer keys {set(answers)} != question keys {set(questions)}")
            return 1
        parts = []
        for qid, ans in answers.items():
            if ans.get("type") != "noul" or not (0.0 <= ans["noul"] <= 1.0):
                print(f"FAIL: bad noul answer for {qid}: {ans}")
                return 1
            parts.append(f"{qid}={ans['noul']:.4f}")
        routing = result.get("routing")
        route_info = f" [routed: {routing.get('model')}]" if routing else ""
        print(f"[{dt_ms:6.0f}ms] {text[:32]} -> {', '.join(parts)}{route_info}")

    print("SMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
