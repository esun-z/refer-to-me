"""ntfy publish channel: JSON variant POST to the server root URL.

The JSON body carries UTF-8 titles safely (HTTP headers are latin-1 and cannot
carry Chinese). No auth: local single-user deployment.
"""

from __future__ import annotations

import httpx

from refer_to_me.config import NtfyPublishConfig


def publish(cfg: NtfyPublishConfig, title: str, body: str) -> None:
    if not cfg.server.strip() or not cfg.topic.strip():
        raise RuntimeError("ntfy publish not configured (server/topic)")
    url = cfg.server.rstrip("/") + "/"
    payload = {
        "topic": cfg.topic,
        "title": title,
        "message": body,
        "priority": cfg.priority,
        "tags": ["bell"],
    }
    resp = httpx.post(url, json=payload, timeout=httpx.Timeout(10.0, connect=5.0))
    resp.raise_for_status()
