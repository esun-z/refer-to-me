"""Pipeline stage 2: Laya engine wrapper.

Mode mapping (verified against laya 0.4.31):
- router       -> laya.Router(device=..., preload=True)  (auto language routing)
- english      -> laya.load(local_path or "en", device=...)
- multilingual -> laya.load(local_path or "ml", device=...)

``import laya`` / ``import torch`` happen lazily inside load so that importing
this module (e.g. in unit tests) never pulls heavy dependencies.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from refer_to_me.config import LayaConfig

logger = logging.getLogger(__name__)

HUB_REPO = "convaiinnovations/laya"


class EngineState(str, Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    READY = "ready"
    ERROR = "error"


class LayaEngineError(RuntimeError):
    """Model unavailable or inference failed."""


@dataclass
class LayaRawResult:
    answers: dict
    usage: dict | None
    duration_ms: float
    mode: str
    repo: str | None
    subfolder: str | None
    revision: str | None
    device: str
    routing: dict | None = None


class LayaEngine:
    def __init__(
        self,
        cfg: LayaConfig,
        on_status: Callable[[EngineState, str], None] | None = None,
    ):
        self._cfg = cfg
        self._on_status = on_status or (lambda state, detail: None)
        self._agent = None
        self._state = EngineState.UNLOADED
        self._detail = ""
        self._device = "cpu"
        self._revision: str | None = None

    @property
    def state(self) -> EngineState:
        return self._state

    @property
    def detail(self) -> str:
        return self._detail

    def _set_status(self, state: EngineState, detail: str = "") -> None:
        self._state = state
        self._detail = detail
        self._on_status(state, detail)

    def _resolve_device(self) -> str:
        import torch

        requested = self._cfg.device
        if requested == "auto":
            return "cuda" if torch.cuda.is_available() else "cpu"
        if requested == "cuda" and not torch.cuda.is_available():
            logger.warning("CUDA requested but unavailable; falling back to CPU")
            return "cpu"
        return requested

    def _availability_detail(self) -> str:
        """Lightweight pre-load check: local dir validity or HF cache presence."""
        cfg = self._cfg
        if cfg.mode != "router" and cfg.local_path:
            path = Path(cfg.local_path)
            if not (path / "rl_agent_config.json").exists():
                raise FileNotFoundError(
                    f"local checkpoint invalid (no rl_agent_config.json): {path}"
                )
            return f"local checkpoint: {path}"
        try:
            from huggingface_hub import scan_cache_dir

            repos = {r.repo_id for r in scan_cache_dir().repos}
            if HUB_REPO in repos:
                return f"cache hit: {HUB_REPO}"
            return f"not cached; will download {HUB_REPO} from Hugging Face"
        except Exception as exc:  # noqa: BLE001 - informational only
            return f"cache scan skipped: {exc}"

    def ensure_loaded(self) -> None:
        """Load the model. ERROR state does NOT auto-retry (manual reload only)."""
        if self._state == EngineState.READY:
            return
        if self._state == EngineState.ERROR:
            raise LayaEngineError(self._detail)
        self._set_status(EngineState.LOADING, "checking model availability")
        try:
            detail = self._availability_detail()
            self._set_status(EngineState.LOADING, detail)
            import laya

            self._device = self._resolve_device()
            cfg = self._cfg
            if cfg.mode == "router":
                self._agent = laya.Router(device=self._device, preload=True)
            else:
                source = cfg.local_path or ("en" if cfg.mode == "english" else "ml")
                self._agent = laya.load(source, device=self._device)
            self._revision = self._try_revision()
            self._set_status(EngineState.READY, f"{cfg.mode} on {self._device}")
        except Exception as exc:
            self._agent = None
            self._set_status(EngineState.ERROR, f"{type(exc).__name__}: {exc}")
            raise LayaEngineError(self._detail) from exc

    def _try_revision(self) -> str | None:
        if self._cfg.mode == "router" or self._cfg.local_path:
            return None
        try:
            from huggingface_hub import model_info

            return model_info(HUB_REPO).sha
        except Exception:  # noqa: BLE001 - best effort, never blocks loading
            return None

    def reload_if_needed(self, cfg: LayaConfig) -> None:
        old = (self._cfg.mode, self._cfg.local_path, self._cfg.device)
        new = (cfg.mode, cfg.local_path, cfg.device)
        self._cfg = cfg
        if old != new:
            self.force_reload()

    def force_reload(self) -> None:
        self.unload()
        self.ensure_loaded()

    def classify(self, text: str, questions: dict) -> LayaRawResult:
        self.ensure_loaded()
        t0 = time.perf_counter()
        result = self._agent.predict(text, questions)
        duration_ms = (time.perf_counter() - t0) * 1000
        routing = result.get("routing")
        repo, subfolder = self._model_identity(routing)
        return LayaRawResult(
            answers=result.get("answers", {}),
            usage=result.get("usage"),
            duration_ms=duration_ms,
            mode=self._cfg.mode,
            repo=repo,
            subfolder=subfolder,
            revision=self._revision,
            device=self._device,
            routing=routing,
        )

    def _model_identity(self, routing: dict | None) -> tuple[str | None, str | None]:
        if self._cfg.mode == "router":
            if routing:
                return routing.get("repo"), None
            return None, None
        if self._cfg.local_path:
            return self._cfg.local_path, None
        return HUB_REPO, "multilingual" if self._cfg.mode == "multilingual" else None

    def unload(self) -> None:
        self._agent = None
        self._revision = None
        self._set_status(EngineState.UNLOADED, "")
        try:
            import torch

            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception as exc:  # noqa: BLE001 - best effort cleanup
            logger.debug("torch cleanup skipped: %s", exc)
