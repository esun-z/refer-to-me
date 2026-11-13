"""Pipeline stage 1: literal (casefold) substring and regex keyword matching."""

from __future__ import annotations

import re
from collections.abc import Sequence

from refer_to_me.config import TopicConfig


def match_keywords(text: str, topics: Sequence[TopicConfig]) -> list[TopicConfig]:
    """Return every enabled topic with at least one matching keyword rule.

    Literal rules compare casefolded substrings (Chinese unaffected, English
    case-insensitive). Regex rules use ``re.search`` with ``re.IGNORECASE``.
    Patterns are validated at config-save time, so no compile errors here.
    """
    folded = text.casefold()
    matched: list[TopicConfig] = []
    for topic in topics:
        if not topic.enabled:
            continue
        for rule in topic.keywords:
            hit = (
                re.search(rule.pattern, text, re.IGNORECASE) is not None
                if rule.is_regex
                else rule.pattern.casefold() in folded
            )
            if hit:
                matched.append(topic)
                break
    return matched
