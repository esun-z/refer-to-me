"""Laya engine mode mapping / state machine with fake laya+torch modules."""

import sys
import types

import pytest

from refer_to_me.config import LayaConfig
from refer_to_me.core.laya_engine import EngineState, LayaEngine, LayaEngineError


class FakeAgent:
    def __init__(self):
        self.predict_calls = []

    def predict(self, text, questions):
        self.predict_calls.append((text, questions))
        return {
            "answers": {
                qid: {"type": "noul", "noul": 0.9, "confidence": 0.9} for qid in questions
            },
            "usage": {"input_tokens": 5},
        }


class FakeRouter(FakeAgent):
    def __init__(self, device=None, preload=False):
        super().__init__()
        self.init_kwargs = {"device": device, "preload": preload}

    def predict(self, text, questions):
        result = super().predict(text, questions)
        result["routing"] = {
            "model": "multilingual",
            "repo": "convaiinnovations/laya-multilingual",
        }
        return result


@pytest.fixture
def fake_laya(monkeypatch):
    mod = types.ModuleType("laya")
    calls = {"load": [], "router": []}

    def load(source, device=None, **kw):
        calls["load"].append((source, device))
        return FakeAgent()

    def router(device=None, preload=False, **kw):
        calls["router"].append((device, preload))
        return FakeRouter(device=device, preload=preload)

    mod.load = load
    mod.Router = router
    monkeypatch.setitem(sys.modules, "laya", mod)

    torch_mod = types.ModuleType("torch")
    torch_mod.cuda = types.SimpleNamespace(
        is_available=lambda: True, empty_cache=lambda: None
    )
    monkeypatch.setitem(sys.modules, "torch", torch_mod)

    hub = types.ModuleType("huggingface_hub")
    hub.scan_cache_dir = lambda: types.SimpleNamespace(repos=[])
    hub.model_info = lambda repo: types.SimpleNamespace(sha="deadbeef")
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    return calls


def test_router_mode(fake_laya):
    engine = LayaEngine(LayaConfig(mode="router"))
    engine.ensure_loaded()
    assert fake_laya["router"] == [("cuda", True)]
    assert fake_laya["load"] == []
    assert engine.state == EngineState.READY


def test_english_mode(fake_laya):
    engine = LayaEngine(LayaConfig(mode="english"))
    engine.ensure_loaded()
    assert fake_laya["load"] == [("en", "cuda")]


def test_multilingual_mode(fake_laya):
    engine = LayaEngine(LayaConfig(mode="multilingual"))
    engine.ensure_loaded()
    assert fake_laya["load"] == [("ml", "cuda")]


def test_local_path(fake_laya, tmp_path):
    (tmp_path / "rl_agent_config.json").write_text("{}", encoding="utf-8")
    engine = LayaEngine(LayaConfig(mode="multilingual", local_path=str(tmp_path)))
    engine.ensure_loaded()
    assert fake_laya["load"] == [(str(tmp_path), "cuda")]


def test_invalid_local_path_error(fake_laya, tmp_path):
    engine = LayaEngine(LayaConfig(mode="english", local_path=str(tmp_path)))
    with pytest.raises(LayaEngineError):
        engine.ensure_loaded()
    assert engine.state == EngineState.ERROR
    assert fake_laya["load"] == []


def test_error_no_auto_retry(fake_laya, tmp_path):
    engine = LayaEngine(LayaConfig(mode="english", local_path=str(tmp_path)))
    with pytest.raises(LayaEngineError):
        engine.ensure_loaded()
    with pytest.raises(LayaEngineError):
        engine.ensure_loaded()  # must not attempt loading again
    assert fake_laya["load"] == []


def test_force_reload_recovers(fake_laya, tmp_path):
    engine = LayaEngine(LayaConfig(mode="english", local_path=str(tmp_path)))
    with pytest.raises(LayaEngineError):
        engine.ensure_loaded()
    (tmp_path / "rl_agent_config.json").write_text("{}", encoding="utf-8")
    engine.force_reload()
    assert engine.state == EngineState.READY
    assert len(fake_laya["load"]) == 1


def test_reload_if_needed(fake_laya):
    engine = LayaEngine(LayaConfig(mode="multilingual"))
    engine.ensure_loaded()
    engine.reload_if_needed(LayaConfig(mode="multilingual", threshold=0.9))
    assert len(fake_laya["load"]) == 1  # threshold change: no reload
    engine.reload_if_needed(LayaConfig(mode="multilingual", device="cpu"))
    assert len(fake_laya["load"]) == 2  # device change: reload
    assert fake_laya["load"][-1] == ("ml", "cpu")


def test_auto_device_cpu_fallback(fake_laya, monkeypatch):
    sys.modules["torch"].cuda.is_available = lambda: False
    engine = LayaEngine(LayaConfig(mode="english", device="auto"))
    engine.ensure_loaded()
    assert fake_laya["load"] == [("en", "cpu")]


def test_requested_cuda_unavailable_falls_back(fake_laya):
    sys.modules["torch"].cuda.is_available = lambda: False
    engine = LayaEngine(LayaConfig(mode="english", device="cuda"))
    engine.ensure_loaded()
    assert fake_laya["load"] == [("en", "cpu")]


def test_classify_router_routing(fake_laya):
    engine = LayaEngine(LayaConfig(mode="router"))
    raw = engine.classify("消息", {"t1": {"type": "noul", "instructions": "q"}})
    assert raw.answers["t1"]["noul"] == 0.9
    assert raw.routing["repo"] == "convaiinnovations/laya-multilingual"
    assert raw.repo == "convaiinnovations/laya-multilingual"
    assert raw.device == "cuda"


def test_classify_single_identity(fake_laya):
    engine = LayaEngine(LayaConfig(mode="multilingual"))
    raw = engine.classify("消息", {"t1": {"type": "noul", "instructions": "q"}})
    assert raw.repo == "convaiinnovations/laya"
    assert raw.subfolder == "multilingual"
    assert raw.revision == "deadbeef"


def test_unload(fake_laya):
    engine = LayaEngine(LayaConfig(mode="english"))
    engine.ensure_loaded()
    engine.unload()
    assert engine.state == EngineState.UNLOADED


def test_status_callbacks(fake_laya):
    seen = []
    engine = LayaEngine(
        LayaConfig(mode="english"), on_status=lambda s, d: seen.append((s, d))
    )
    engine.ensure_loaded()
    assert seen[0][0] == EngineState.LOADING
    assert seen[-1][0] == EngineState.READY
