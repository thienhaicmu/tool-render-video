"""Audit FINDING-BR15 closure (Batch 10E 2026-06-06).

Whisper models are heavy (tiny ~75 MB, base ~150 MB, small ~500 MB,
medium ~1.5 GB, large-v3 ~3 GB). Holding more than a couple resident
exhausts RAM on a desktop machine. The previous cache (a plain dict
with no eviction) grew unbounded when callers mixed sizes — e.g.,
prepare.py uses `tiny` for preview, the render pipeline uses
`large-v3` for the main pass.

Two production caches are guarded:

- ``whisper._MODEL_CACHE`` (OpenAI whisper)        — keyed by model_name
- ``adapters._FW_MODEL_CACHE`` (faster-whisper)    — keyed by (name, device, compute)

Both are now OrderedDicts with LRU eviction and an explicit
``unload_all_*`` helper for shutdown / maintenance use.

Tests pin: insertion order, MRU move on access, eviction at the cap,
and the explicit unload path.
"""
from __future__ import annotations

from collections import OrderedDict

import pytest


# ---------------------------------------------------------------------------
# whisper.py — OpenAI whisper cache
# ---------------------------------------------------------------------------


@pytest.fixture
def _whisper_isolated(monkeypatch):
    """Reset the cache + cap so each test gets a clean view, and replace
    ``whisper.load_model`` with a marker-returning stub so we don't try to
    actually load a 1+ GB model."""
    from app.features.render.engine.subtitle.transcription import whisper as wmod
    monkeypatch.setattr(wmod, "_MODEL_CACHE", OrderedDict())
    monkeypatch.setattr(wmod, "_MODEL_CACHE_MAX", 2)
    monkeypatch.setattr(wmod, "_MODEL_TRANSCRIBE_LOCKS", {})

    def _stub_load(model_name, download_root):
        return f"<model:{model_name}>"

    monkeypatch.setattr(wmod.whisper, "load_model", _stub_load)
    return wmod


def test_whisper_cache_evicts_oldest_when_third_loaded(_whisper_isolated):
    wmod = _whisper_isolated

    a = wmod.get_whisper_model("tiny")
    b = wmod.get_whisper_model("base")
    # Cache should hold both; insertion order is tiny → base.
    assert list(wmod._MODEL_CACHE.keys()) == ["tiny", "base"]

    # Third distinct load evicts the LRU entry (tiny) — base remains.
    c = wmod.get_whisper_model("large-v3")

    assert "tiny" not in wmod._MODEL_CACHE
    assert list(wmod._MODEL_CACHE.keys()) == ["base", "large-v3"]
    assert a == "<model:tiny>"  # caller's handle still valid
    assert b == "<model:base>"
    assert c == "<model:large-v3>"


def test_whisper_cache_touch_moves_entry_to_mru(_whisper_isolated):
    """Access ordering: a touched entry must NOT be evicted when a new
    entry pushes the cache over the cap."""
    wmod = _whisper_isolated

    wmod.get_whisper_model("tiny")    # LRU
    wmod.get_whisper_model("base")    # MRU
    wmod.get_whisper_model("tiny")    # touch — tiny now MRU, base now LRU

    wmod.get_whisper_model("large-v3")  # eviction trigger

    # "base" was LRU at eviction time → evicted; "tiny" survives.
    assert "base" not in wmod._MODEL_CACHE
    assert list(wmod._MODEL_CACHE.keys()) == ["tiny", "large-v3"]


def test_whisper_cache_returns_cached_instance_on_repeat(_whisper_isolated):
    wmod = _whisper_isolated

    first = wmod.get_whisper_model("tiny")
    second = wmod.get_whisper_model("tiny")

    assert first is second
    assert list(wmod._MODEL_CACHE.keys()) == ["tiny"]


def test_unload_all_whisper_models_clears_cache(_whisper_isolated):
    wmod = _whisper_isolated

    wmod.get_whisper_model("tiny")
    wmod.get_whisper_model("base")

    n = wmod.unload_all_whisper_models()

    assert n == 2
    assert len(wmod._MODEL_CACHE) == 0
    # Subsequent loads start clean.
    wmod.get_whisper_model("tiny")
    assert list(wmod._MODEL_CACHE.keys()) == ["tiny"]


def test_whisper_cache_evicts_to_cap_one_when_lowered(monkeypatch):
    """The while-loop eviction handles a cap that is lower than the current
    cache size — e.g., an operator reduces WHISPER_MODEL_CACHE_MAX at
    runtime and the next load shrinks the cache appropriately."""
    from app.features.render.engine.subtitle.transcription import whisper as wmod
    monkeypatch.setattr(wmod, "_MODEL_CACHE", OrderedDict())
    monkeypatch.setattr(wmod, "_MODEL_CACHE_MAX", 3)
    monkeypatch.setattr(wmod, "_MODEL_TRANSCRIBE_LOCKS", {})
    monkeypatch.setattr(wmod.whisper, "load_model",
                        lambda name, download_root: f"<model:{name}>")

    wmod.get_whisper_model("tiny")
    wmod.get_whisper_model("base")
    wmod.get_whisper_model("small")
    assert len(wmod._MODEL_CACHE) == 3

    # Operator drops the cap; next insert must evict TWO entries to hit it.
    monkeypatch.setattr(wmod, "_MODEL_CACHE_MAX", 1)
    wmod.get_whisper_model("medium")

    assert list(wmod._MODEL_CACHE.keys()) == ["medium"]


# ---------------------------------------------------------------------------
# adapters.py — faster-whisper cache
# ---------------------------------------------------------------------------


@pytest.fixture
def _fw_isolated(monkeypatch):
    """Reset the faster-whisper cache + stub the WhisperModel constructor."""
    from app.features.render.engine.subtitle.transcription import adapters as amod
    monkeypatch.setattr(amod, "_FW_MODEL_CACHE", OrderedDict())
    monkeypatch.setattr(amod, "_FW_MODEL_CACHE_MAX", 2)

    class _StubModel:
        def __init__(self, name, device, compute_type):
            self.name = name
            self.device = device
            self.compute_type = compute_type

        def __repr__(self):
            return f"<fw:{self.name}/{self.device}/{self.compute_type}>"

    # Insert a stub `faster_whisper` module so the lazy import inside
    # _get_fw_model resolves without needing the real package.
    import sys
    fake_fw = type(sys)("faster_whisper")
    fake_fw.WhisperModel = _StubModel  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)
    return amod


def test_fw_cache_evicts_oldest_when_third_distinct_key(_fw_isolated):
    amod = _fw_isolated

    amod._get_fw_model("tiny", "cpu", "int8")
    amod._get_fw_model("base", "cpu", "int8")
    assert len(amod._FW_MODEL_CACHE) == 2

    amod._get_fw_model("large-v3", "cpu", "int8")

    assert ("tiny", "cpu", "int8") not in amod._FW_MODEL_CACHE
    keys = list(amod._FW_MODEL_CACHE.keys())
    assert keys[-1] == ("large-v3", "cpu", "int8")


def test_fw_cache_touch_keeps_entry_alive(_fw_isolated):
    amod = _fw_isolated

    amod._get_fw_model("tiny", "cpu", "int8")
    amod._get_fw_model("base", "cpu", "int8")
    amod._get_fw_model("tiny", "cpu", "int8")  # touch → tiny MRU
    amod._get_fw_model("large-v3", "cpu", "int8")  # base LRU → evicted

    assert ("base", "cpu", "int8") not in amod._FW_MODEL_CACHE
    assert ("tiny", "cpu", "int8") in amod._FW_MODEL_CACHE


def test_fw_cache_returns_same_instance_on_repeat(_fw_isolated):
    amod = _fw_isolated

    a = amod._get_fw_model("tiny", "cpu", "int8")
    b = amod._get_fw_model("tiny", "cpu", "int8")
    assert a is b


def test_unload_all_fw_models_clears_cache(_fw_isolated):
    amod = _fw_isolated

    amod._get_fw_model("tiny", "cpu", "int8")
    amod._get_fw_model("base", "cpu", "int8")

    n = amod.unload_all_fw_models()

    assert n == 2
    assert len(amod._FW_MODEL_CACHE) == 0


def test_fw_cache_cuda_to_cpu_fallback_inserts_alias(_fw_isolated, monkeypatch):
    """If the CUDA init raises, the helper retries with CPU int8 AND
    inserts a cache entry under the CPU key so future CPU queries hit
    the cache. Both entries count toward the LRU cap."""
    amod = _fw_isolated

    import sys
    cuda_attempts = {"n": 0}

    class _CudaFails:
        def __init__(self, name, device, compute_type):
            cuda_attempts["n"] += 1
            if device == "cuda":
                raise RuntimeError("simulated CUDA OOM")
            self.name = name
            self.device = device
            self.compute_type = compute_type

    fake_fw = type(sys)("faster_whisper")
    fake_fw.WhisperModel = _CudaFails  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_fw)

    amod._get_fw_model("large-v3", "cuda", "float16")

    # Both the requested CUDA key AND the CPU fallback key are cached so
    # a subsequent CPU-keyed lookup hits the cache rather than re-loading.
    assert ("large-v3", "cuda", "float16") in amod._FW_MODEL_CACHE
    assert ("large-v3", "cpu", "int8") in amod._FW_MODEL_CACHE
