"""Stage 1 matcher semantics."""

from refer_to_me.config import KeywordRule, TopicConfig
from refer_to_me.core.matcher import match_keywords, topic_keyword_hit


def topic(name: str, rules: list[KeywordRule], enabled: bool = True) -> TopicConfig:
    return TopicConfig(name=name, keywords=tuple(rules), enabled=enabled)


def test_literal_substring_chinese():
    t = topic("月例会", [KeywordRule(pattern="月例会")])
    assert match_keywords("下周月例会改到周四", [t]) == [t]
    assert match_keywords("今天天气不错", [t]) == []


def test_literal_casefold_english():
    t = topic("OKR", [KeywordRule(pattern="OKR")])
    assert match_keywords("please review the okr draft", [t]) == [t]
    assert match_keywords("OKRs are due", [t]) == [t]


def test_regex_search():
    t = topic("报销", [KeywordRule(pattern=r"报销.{0,6}(政策|标准)", is_regex=True)])
    assert match_keywords("年会旅游报销政策什么时候发布", [t]) == [t]
    assert match_keywords("报销一下打车费", [t]) == []


def test_regex_case_insensitive():
    t = topic("meeting", [KeywordRule(pattern=r"monthly\s+meeting", is_regex=True)])
    assert match_keywords("Monthly  Meeting moved", [t]) == [t]


def test_multiple_topics_all_returned():
    a = topic("月例会", [KeywordRule(pattern="月例会")])
    b = topic("报销", [KeywordRule(pattern="报销")])
    assert match_keywords("月例会讨论报销政策", [a, b]) == [a, b]


def test_disabled_topic_skipped():
    t = topic("月例会", [KeywordRule(pattern="月例会")], enabled=False)
    assert match_keywords("下周月例会", [t]) == []


def test_no_keywords_no_match():
    t = topic("empty", [])
    assert match_keywords("anything", [t]) == []


def test_single_topic_hit():
    t = topic("月例会", [KeywordRule(pattern="月例会")])
    assert topic_keyword_hit("下周月例会改到周四", t) is True
    assert topic_keyword_hit("今天天气不错", t) is False
    assert topic_keyword_hit("anything", topic("empty", [])) is False


def test_single_topic_regex():
    t = topic("报销", [KeywordRule(pattern=r"报销.{0,6}(政策|标准)", is_regex=True)])
    assert topic_keyword_hit("年会旅游报销政策什么时候发布", t) is True
    assert topic_keyword_hit("报销一下打车费", t) is False
