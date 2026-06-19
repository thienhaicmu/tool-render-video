"""Dispatch + fallback behaviour for the Piper offline-TTS integration.

These tests mock the actual synthesis calls so they run without the
~63 MB voice model or any network. They pin the routing contract:

  - tts_engine="piper" → Piper, with Edge fallback on failure.
  - tts_engine="edge" (default) → Edge, with automatic offline-Piper
    fallback when Edge fails AND a Piper model exists for the language.
  - Edge fails AND no Piper model → the original error re-raises (no
    silent loss of narration; the caller still emits voice_failed).
"""
import app.features.render.engine.audio.tts as tts
import app.features.render.engine.audio.tts_piper as tts_piper
import app.features.render.engine.audio.tts_xtts as tts_xtts
import app.features.render.ai.dependencies as deps

import pytest


@pytest.fixture
def edge_ok(monkeypatch):
    calls = {"edge": 0}

    def _edge(**kw):
        calls["edge"] += 1
        return "EDGE.mp3"

    monkeypatch.setattr(tts, "generate_narration_mp3", _edge)
    return calls


@pytest.fixture
def edge_fail(monkeypatch):
    def _edge(**kw):
        raise RuntimeError("simulated edge offline/403")

    monkeypatch.setattr(tts, "generate_narration_mp3", _edge)


@pytest.fixture
def piper_ok(monkeypatch):
    calls = {"piper": 0}

    def _synth(**kw):
        calls["piper"] += 1
        return "PIPER.mp3"

    monkeypatch.setattr(deps, "has_piper", lambda: True)
    monkeypatch.setattr(tts_piper, "synthesize_piper", _synth)
    monkeypatch.setattr(tts_piper, "piper_model_available", lambda lang, gender="": True)
    return calls


def _call(engine="edge", language="vi-VN"):
    return tts.generate_narration_audio(
        text="xin chao", language=language, gender="female", rate="+0%",
        job_id="t", content_type="vlog", tts_engine=engine,
    )


def test_piper_engine_uses_piper(edge_ok, piper_ok):
    assert _call(engine="piper") == "PIPER.mp3"
    assert piper_ok["piper"] == 1
    assert edge_ok["edge"] == 0


def test_piper_engine_falls_back_to_edge_on_failure(edge_ok, monkeypatch):
    monkeypatch.setattr(deps, "has_piper", lambda: True)

    def _boom(**kw):
        raise RuntimeError("piper model missing")

    monkeypatch.setattr(tts_piper, "synthesize_piper", _boom)
    assert _call(engine="piper") == "EDGE.mp3"
    assert edge_ok["edge"] == 1


def test_piper_engine_falls_back_when_package_absent(edge_ok, monkeypatch):
    monkeypatch.setattr(deps, "has_piper", lambda: False)
    assert _call(engine="piper") == "EDGE.mp3"
    assert edge_ok["edge"] == 1


def test_default_edge_succeeds_without_touching_piper(edge_ok, monkeypatch):
    # Piper must not be invoked when Edge works — zero behaviour change.
    called = {"piper": 0}
    monkeypatch.setattr(deps, "has_piper", lambda: True)
    monkeypatch.setattr(
        tts_piper, "synthesize_piper",
        lambda **kw: called.__setitem__("piper", called["piper"] + 1) or "PIPER.mp3",
    )
    assert _call(engine="edge") == "EDGE.mp3"
    assert called["piper"] == 0


def test_edge_failure_falls_back_to_offline_piper(edge_fail, piper_ok):
    # The bug fix: existing edge config auto-recovers offline via Piper.
    assert _call(engine="edge", language="vi-VN") == "PIPER.mp3"
    assert piper_ok["piper"] == 1


def test_edge_failure_falls_back_to_xtts_when_no_piper_model(edge_fail, monkeypatch):
    # ja/ko have no Piper voice — offline path is XTTS (GPU).
    monkeypatch.setattr(deps, "has_piper", lambda: True)
    monkeypatch.setattr(tts_piper, "piper_model_available", lambda lang, gender="": False)
    monkeypatch.setattr(deps, "has_xtts", lambda: True)
    monkeypatch.setattr(tts_xtts, "synthesize_xtts", lambda **kw: "XTTS.mp3")
    assert _call(engine="edge", language="ja-JP") == "XTTS.mp3"


def test_edge_failure_reraises_when_no_offline_engine(edge_fail, monkeypatch):
    monkeypatch.setattr(deps, "has_piper", lambda: True)
    monkeypatch.setattr(tts_piper, "piper_model_available", lambda lang, gender="": False)
    monkeypatch.setattr(deps, "has_xtts", lambda: False)
    with pytest.raises(RuntimeError, match="simulated edge"):
        _call(engine="edge", language="ko-KR")
