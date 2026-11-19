"""Config models + YAML store."""

import pytest
import yaml
from pydantic import ValidationError

from refer_to_me.config import (
    AlertChannel,
    AppConfig,
    ConfigStore,
    KeywordRule,
    LlmConfig,
    NtfyInputConfig,
    TopicConfig,
)


def test_defaults():
    cfg = AppConfig()
    assert cfg.laya.mode == "router"
    assert cfg.laya.device == "auto"
    assert cfg.language == "auto"
    assert cfg.webhook.enabled is False
    assert cfg.llm.is_configured() is False
    t = TopicConfig(name="x")
    assert t.laya_enabled is True
    assert t.llm_enabled is False
    assert t.match_threshold == 0.6
    assert t.llm_threshold == 0.6


def test_frozen():
    cfg = AppConfig()
    with pytest.raises(ValidationError):
        cfg.language = "en"


def test_bad_regex_rejected():
    with pytest.raises(ValidationError):
        KeywordRule(pattern="[unclosed", is_regex=True)


def test_empty_pattern_rejected():
    with pytest.raises(ValidationError):
        KeywordRule(pattern="   ")


def test_duplicate_topic_ids_rejected():
    with pytest.raises(ValidationError):
        AppConfig(topics=(TopicConfig(id="a", name="x"), TopicConfig(id="a", name="y")))


def test_llm_is_configured():
    assert LlmConfig().is_configured() is False
    assert LlmConfig(base_url="http://x/v1").is_configured() is False
    assert LlmConfig(base_url="http://x/v1", model="m").is_configured() is True


def test_topic_llm_requires_laya():
    with pytest.raises(ValidationError):
        TopicConfig(name="x", laya_enabled=False, llm_enabled=True)
    TopicConfig(name="x", laya_enabled=True, llm_enabled=True)
    TopicConfig(name="x", laya_enabled=False, llm_enabled=False)


def test_topic_threshold_order_and_range():
    with pytest.raises(ValidationError):
        TopicConfig(name="x", match_threshold=0.6, llm_threshold=0.9)
    with pytest.raises(ValidationError):
        TopicConfig(name="x", match_threshold=0.4)
    with pytest.raises(ValidationError):
        TopicConfig(name="x", llm_threshold=1.1)
    TopicConfig(name="x", match_threshold=0.9, llm_threshold=0.6)
    TopicConfig(name="x", match_threshold=0.6, llm_threshold=0.6)  # equal = no band


def test_legacy_global_threshold_migrated():
    cfg = AppConfig.model_validate(
        {
            "version": 1,
            "laya": {"threshold": 0.8},
            "topics": [{"name": "a"}, {"name": "b", "match_threshold": 0.95}],
        }
    )
    assert (cfg.topics[0].match_threshold, cfg.topics[0].llm_threshold) == (0.8, 0.8)
    # explicit per-topic values win over the legacy global one
    assert (cfg.topics[1].match_threshold, cfg.topics[1].llm_threshold) == (0.95, 0.8)


def test_legacy_threshold_clamped_into_range():
    cfg = AppConfig.model_validate(
        {"laya": {"threshold": 0.3}, "topics": [{"name": "a"}]}
    )
    assert cfg.topics[0].match_threshold == 0.5
    assert cfg.topics[0].llm_threshold == 0.5


def test_topic_order_preserved():
    cfg = AppConfig(
        topics=(TopicConfig(id="b", name="second"), TopicConfig(id="a", name="first"))
    )
    assert [t.id for t in cfg.enabled_topics()] == ["b", "a"]


def test_ntfy_topic_charset():
    with pytest.raises(ValidationError):
        NtfyInputConfig(topics=("bad,topic",))
    NtfyInputConfig(topics=("good-topic_1",))


def test_enabled_topics_filters():
    cfg = AppConfig(
        topics=(TopicConfig(name="on"), TopicConfig(name="off", enabled=False))
    )
    assert [t.name for t in cfg.enabled_topics()] == ["on"]


def test_yaml_roundtrip_chinese(tmp_path):
    cfg = AppConfig(
        topics=(
            TopicConfig(
                name="月例会",
                description="每月例行会议",
                keywords=(KeywordRule(pattern="月例会"),),
                laya_enabled=True,
                llm_enabled=True,
                match_threshold=0.9,
                llm_threshold=0.6,
                channels=(AlertChannel.TOAST, AlertChannel.SOUND),
            ),
        )
    )
    store = ConfigStore(tmp_path / "config.yaml")
    store.save(cfg)
    text = store.path.read_text(encoding="utf-8")
    assert "月例会" in text  # not escaped
    loaded = store.load()
    assert loaded == cfg
    assert store.load_warning is None


def test_missing_file_returns_defaults(tmp_path):
    store = ConfigStore(tmp_path / "nope.yaml")
    assert store.load() == AppConfig()
    assert store.load_warning is None


def test_corrupt_file_backed_up(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("topics: [this is not valid: yaml: {{{", encoding="utf-8")
    store = ConfigStore(path)
    cfg = store.load()
    assert cfg == AppConfig()
    assert store.load_warning is not None
    assert path.with_suffix(".yaml.bak").exists()


def test_invalid_schema_backed_up(tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump({"laya": {"device": "tpu"}}), encoding="utf-8")
    store = ConfigStore(path)
    assert store.load() == AppConfig()
    assert store.load_warning is not None


def test_save_atomic_no_tmp_left(tmp_path):
    store = ConfigStore(tmp_path / "config.yaml")
    store.save(AppConfig())
    assert list(tmp_path.iterdir()) == [store.path]
