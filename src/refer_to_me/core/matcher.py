"""Pipeline stage 1: literal (casefold) substring and regex keyword matching."""

from __future__ import annotations

import re
from collections.abc import Sequence

from refer_to_me.config import TopicConfig


def topic_keyword_hit(text: str, topic: TopicConfig) -> bool:
    """Whether any keyword rule of one topic matches the text.

    Literal rules compare casefolded substrings (Chinese unaffected, English
    case-insensitive). Regex rules use ``re.search`` with ``re.IGNORECASE``.
    Patterns are validated at config-save time, so no compile errors here.
    """
    folded = text.casefold()
    for rule in topic.keywords:
        hit = (
            re.search(rule.pattern, text, re.IGNORECASE) is not None
            if rule.is_regex
            else rule.pattern.casefold() in folded
        )
        if hit:
            return True
    return False


def match_keywords(text: str, topics: Sequence[TopicConfig]) -> list[TopicConfig]:
    """Return every enabled topic with at least one matching keyword rule.

    The ordered pipeline uses ``topic_keyword_hit`` per topic instead; this
    bulk helper remains for callers that want all hits at once.
    """
    return [t for t in topics if t.enabled and topic_keyword_hit(text, t)]
