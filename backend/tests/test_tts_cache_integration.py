"""Architecture-review Batch D-1 (2026-06-30) — Edge-TTS cache wire-up.

Integration test: confirms the cache short-circuits the edge-tts SDK call
on the second invocation with identical inputs.

The edge-tts package is not installed in the test venv (it's an optional
runtime dep). We install a fake module into ``sys.modules`` so the lazy
``import edge_tts`` inside ``generate_narration_mp3`` resolves to our stub.
The stub writes a small MP3-shaped payload to the requested output path.

Contract pinned:
  1. First call → stub Communicate.save fires exactly once; file is written
     AND cached.
  2. Second call with identical inputs → cache hit; stub Communicate is
     NOT constructed at all (zero new save calls).
  3. Kill switch TTS_CACHE_ENABLED=0 → second call ALSO synthesises (cache
     bypassed); two save calls total.
  4. Different rate / voice_id / content_type → cache miss; new save call.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest


class _FakeCommunicate:
    """Stand-in for edge_tts.Communicate. Tracks construction count via a
    class-level counter and writes a fake MP3 to the target path."""

    instances: list["_FakeCommunicate"] = []
    payload: bytes = b"FAKE-EDGE-TTS-MP3-BYTES"

    def __init__(self, text, voice_id, rate=None):
        self.text = text
        self.voice_id = voice_id
        self.rate = rate
        type(self).instances.append(self)

    async def save(self, out_path: str) -> None:
        Path(out_path).parent.mkdir(parents=True, exist_ok=True)
        Path(out_path).write_bytes(self.payload)


@pytest.fixture(autouse=True)
def _inject_edge_tts_stub(monkeypatch, tmp_path):
    """Place a fake edge_tts module on sys.modules so the lazy import in
    generate_narration_mp3 picks it up. Also redirect APP_DATA_DIR + TEMP_DIR
    so disk writes are sandboxed and isolate the tts_cache module so
    tts_cache_clear() is local to this test."""
    _FakeCommunicate.instances = []
    stub = types.ModuleType("edge_tts")
    stub.Communicate = _FakeCommunicate  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "edge_tts", stub)

    # Redirect cache + temp roots into tmp_path so each test is isolated.
    from app.features.render.engine.audio import tts as tts_mod
    from app.features.render.engine.audio import tts_cache as tts_cache_mod
    monkeypatch.setattr(tts_mod, "TEMP_DIR", tmp_path, raising=False)
    monkeypatch.setattr(tts_cache_mod, "APP_DATA_DIR", tmp_path, raising=False)

    # Default ON; individual tests flip to "0" to test the kill switch.
    monkeypatch.setenv("TTS_CACHE_ENABLED", "1")

    # Make sure no stale cache leaks across tests.
    from app.features.render.engine.audio.tts_cache import tts_cache_clear
    tts_cache_clear()
    yield tmp_path
    tts_cache_clear()


def _gen(**overrides):
    """Invoke generate_narration_mp3 with sensible Vietnamese defaults; tests
    pass overrides to vary single inputs."""
    from app.features.render.engine.audio.tts import generate_narration_mp3
    base = dict(
        text="Lorem ipsum dolor sit amet.",
        language="vi-VN",
        gender="female",
        rate="+0%",
        job_id="job-test",
        content_type="vlog",
    )
    base.update(overrides)
    return generate_narration_mp3(**base)


# ---------------------------------------------------------------------------
# Happy path — second call short-circuits the synth
# ---------------------------------------------------------------------------


def test_first_call_synthesises_then_caches(_inject_edge_tts_stub):
    path1 = _gen(job_id="job-A")
    assert Path(path1).exists() and Path(path1).read_bytes() == _FakeCommunicate.payload
    assert len(_FakeCommunicate.instances) == 1


def test_second_call_with_identical_inputs_hits_cache(_inject_edge_tts_stub):
    _gen(job_id="job-1")
    assert len(_FakeCommunicate.instances) == 1
    # Second call — same content inputs (job_id is irrelevant to the cache
    # key but DOES change the default output_path, so this proves the cache
    # copies bytes to the new path).
    path2 = _gen(job_id="job-2")
    assert Path(path2).exists()
    assert Path(path2).read_bytes() == _FakeCommunicate.payload
    # Critical: no new Communicate was constructed.
    assert len(_FakeCommunicate.instances) == 1, (
        f"expected zero new edge-tts calls on cache hit, "
        f"got {len(_FakeCommunicate.instances)}"
    )


# ---------------------------------------------------------------------------
# Kill switch bypasses the cache
# ---------------------------------------------------------------------------


def test_kill_switch_disables_cache_layer(_inject_edge_tts_stub, monkeypatch):
    _gen(job_id="warm-1")
    assert len(_FakeCommunicate.instances) == 1
    # Flip the kill switch. The second call MUST synthesise again.
    monkeypatch.setenv("TTS_CACHE_ENABLED", "0")
    _gen(job_id="warm-2")
    assert len(_FakeCommunicate.instances) == 2, (
        "kill switch must force a fresh synth on every call"
    )


# ---------------------------------------------------------------------------
# Cache key sensitivity — varying inputs misses the cache
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("override,desc", [
    ({"text": "Different narration text entirely."}, "text changed"),
    ({"rate": "-5%"}, "rate changed"),
    ({"content_type": "tutorial"}, "content_type changed"),
    ({"gender": "male"}, "gender changed"),
])
def test_changing_a_cache_component_misses_cache(
    _inject_edge_tts_stub, override, desc,
):
    _gen(job_id="base")
    assert len(_FakeCommunicate.instances) == 1
    _gen(job_id="varied", **override)
    assert len(_FakeCommunicate.instances) == 2, (
        f"cache hit despite {desc} — key composition is broken"
    )


# ---------------------------------------------------------------------------
# Caller-supplied output_path still receives the cached bytes
# ---------------------------------------------------------------------------


def test_cache_hit_writes_to_caller_supplied_output_path(_inject_edge_tts_stub, tmp_path):
    # Warm the cache.
    _gen(job_id="warm")
    assert len(_FakeCommunicate.instances) == 1
    # Second call with an explicit output_path.
    custom = tmp_path / "custom" / "my-narration.mp3"
    result = _gen(job_id="warm-2", output_path=str(custom))
    assert Path(result) == custom
    assert custom.exists()
    assert custom.read_bytes() == _FakeCommunicate.payload
    # Still no new synth.
    assert len(_FakeCommunicate.instances) == 1
