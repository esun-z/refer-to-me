"""Application configuration: frozen pydantic models + YAML document store.

The config file is managed like a shareable document (default:
``<Documents>/ReferToMe/config.yaml``), not machine-private state.
"""

from __future__ import annotations

import os
import re
import tempfile
import uuid
from enum import Enum
from pathlib import Path
from typing import Literal

import yaml
from platformdirs import user_data_dir, user_documents_dir
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

APP_DIR_NAME = "ReferToMe"


class AlertChannel(str, Enum):
    SOUND = "sound"
    TOAST = "toast"
    QT = "qt"
    NTFY = "ntfy"


class KeywordRule(BaseModel):
    model_config = ConfigDict(frozen=True)

    pattern: str
    is_regex: bool = False

    @field_validator("pattern")
    @classmethod
    def _nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("keyword pattern must not be empty")
        return v

    @model_validator(mode="after")
    def _regex_compiles(self) -> KeywordRule:
        if self.is_regex:
            try:
                re.compile(self.pattern)
            except re.error as exc:
                raise ValueError(f"invalid regex {self.pattern!r}: {exc}") from exc
        return self


class TopicConfig(BaseModel):
    """One ordered entry in the matching cascade.

    Topics are evaluated front-to-back; the first match short-circuits the
    rest. Per topic: keywords always apply; ``laya_enabled`` adds the Laya
    question; ``llm_enabled`` (requires Laya) adds the LLM fallback for
    low-confidence results.

    Two confidence thresholds on max(p, 1-p), both in [0.5, 1]:
    - ``match_threshold``: confidence >= it -> Laya's yes/no is final
      (yes -> match, no -> skip to the next topic).
    - ``llm_threshold``: confidence < it -> consult the LLM (if enabled).
    The band [llm_threshold, match_threshold) is a pass-through: the topic
    is neither matched nor sent to the LLM; evaluation moves on. Equal
    thresholds (the 0.6 default) reproduce the single-threshold behavior.
    """

    model_config = ConfigDict(frozen=True)

    id: str = Field(default_factory=lambda: uuid.uuid4().hex)
    name: str
    description: str = ""
    enabled: bool = True
    keywords: tuple[KeywordRule, ...] = ()
    laya_enabled: bool = True
    llm_enabled: bool = False
    match_threshold: float = Field(0.6, ge=0.5, le=1.0)
    llm_threshold: float = Field(0.6, ge=0.5, le=1.0)
    laya_instructions: str = ""
    laya_criteria_true: str = ""
    laya_criteria_false: str = ""
    channels: tuple[AlertChannel, ...] = ()

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("topic name must not be empty")
        return v

    @model_validator(mode="after")
    def _switch_and_threshold_consistency(self) -> TopicConfig:
        if self.llm_enabled and not self.laya_enabled:
            raise ValueError("topic llm_enabled requires laya_enabled")
        if self.llm_threshold > self.match_threshold:
            raise ValueError("topic llm_threshold must not exceed match_threshold")
        return self


class LayaConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    mode: Literal["router", "english", "multilingual"] = "router"
    local_path: str = ""  # local checkpoint dir; only used in english/multilingual modes
    device: Literal["auto", "cuda", "cpu"] = "auto"


class LlmConfig(BaseModel):
    """Global LLM connection settings; per-topic ``llm_enabled`` decides usage."""

    model_config = ConfigDict(frozen=True)

    base_url: str = ""
    api_key: str = ""
    model: str = ""
    mode: Literal["JSON", "MD_JSON", "TOOLS"] = "JSON"
    timeout_s: float = Field(30.0, gt=0)
    max_retries: int = Field(2, ge=0, le=5)

    def is_configured(self) -> bool:
        return bool(self.base_url.strip() and self.model.strip())


class WebhookConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    host: str = "127.0.0.1"
    port: int = Field(8765, ge=0, le=65535)  # 0 = ephemeral (tests)


class NtfyInputConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    server: str = ""
    topics: tuple[str, ...] = ()

    @field_validator("topics")
    @classmethod
    def _topic_charset(cls, v: tuple[str, ...]) -> tuple[str, ...]:
        for topic in v:
            if not re.fullmatch(r"[A-Za-z0-9_-]+", topic):
                raise ValueError(f"invalid ntfy topic name: {topic!r}")
        return v

    @model_validator(mode="after")
    def _enabled_requires_fields(self) -> NtfyInputConfig:
        if self.enabled and (not self.server.strip() or not self.topics):
            raise ValueError("ntfy subscribe enabled requires server and topics")
        return self


class NtfyPublishConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    server: str = ""
    topic: str = ""
    priority: int = Field(4, ge=1, le=5)


class UnclassifiedConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    channels: tuple[AlertChannel, ...] = ()


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    version: int = 2
    language: Literal["auto", "en", "zh_CN"] = "auto"
    topics: tuple[TopicConfig, ...] = ()
    laya: LayaConfig = LayaConfig()
    llm: LlmConfig = LlmConfig()
    webhook: WebhookConfig = WebhookConfig()
    ntfy_input: NtfyInputConfig = NtfyInputConfig()
    ntfy_publish: NtfyPublishConfig = NtfyPublishConfig()
    unclassified: UnclassifiedConfig = UnclassifiedConfig()
    data_dir: str | None = None
    sound_file: str = ""
    start_minimized: bool = False

    @model_validator(mode="before")
    @classmethod
    def _migrate_v1_global_threshold(cls, data):
        """v1 kept one global ``laya.threshold``; v2 thresholds are per topic.

        Carry the legacy value onto topics that do not specify their own, so
        tuned configurations survive the upgrade. Values below 0.5 (allowed
        by v1) are clamped into the v2 range.
        """
        if not isinstance(data, dict):
            return data
        laya = data.get("laya")
        legacy = laya.get("threshold") if isinstance(laya, dict) else None
        if legacy is None:
            return data
        try:
            legacy = min(max(float(legacy), 0.5), 1.0)
        except (TypeError, ValueError):
            return data
        topics = data.get("topics")
        if not isinstance(topics, list):
            return data
        migrated = [
            {
                **t,
                "match_threshold": t.get("match_threshold", legacy),
                "llm_threshold": t.get("llm_threshold", legacy),
            }
            if isinstance(t, dict)
            else t
            for t in topics
        ]
        return {**data, "topics": migrated}

    @model_validator(mode="after")
    def _unique_topic_ids(self) -> AppConfig:
        ids = [t.id for t in self.topics]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate topic ids")
        return self

    def enabled_topics(self) -> tuple[TopicConfig, ...]:
        return tuple(t for t in self.topics if t.enabled)

    def dataset_path(self) -> Path:
        base = (
            Path(self.data_dir)
            if self.data_dir
            else Path(user_data_dir(APP_DIR_NAME, appauthor=False))
        )
        return base / "laya_dataset.jsonl"


def default_config_path() -> Path:
    return Path(user_documents_dir()) / APP_DIR_NAME / "config.yaml"


class ConfigStore:
    """Atomic YAML load/save. Corrupt files are backed up to ``.yaml.bak``."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path) if path is not None else default_config_path()
        self.load_warning: str | None = None

    def load(self) -> AppConfig:
        self.load_warning = None
        if not self.path.exists():
            return AppConfig()
        try:
            data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
            if data is None:
                return AppConfig()
            if not isinstance(data, dict):
                raise TypeError("config root must be a mapping")
            return AppConfig.model_validate(data)
        except Exception as exc:  # noqa: BLE001 - any corrupt file -> backup + defaults
            try:
                self.path.replace(self.path.with_suffix(".yaml.bak"))
            except OSError:
                pass
            self.load_warning = f"Config file was invalid ({exc}); backed up and reset to defaults."
            return AppConfig()

    def save(self, cfg: AppConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        text = yaml.safe_dump(cfg.model_dump(mode="json"), allow_unicode=True, sort_keys=False)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".config-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(text)
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
