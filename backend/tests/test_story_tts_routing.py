"""Story-to-Video P4 — TTS engine routing + ElevenLabs branch + provider tests."""
from __future__ import annotations

import pytest

from app.features.render.engine.audio import tts, tts_elevenlabs


# ── resolve_story_tts_engine ──────────────────────────────────────────────────

def test_routing_by_language(monkeypatch):
    monkeypatch.delenv("STORY_TTS_ENGINE_OVERRIDE", raising=False)
    assert tts.resolve_story_tts_engine("vi") == "gemini"
    assert tts.resolve_story_tts_engine("vi-VN") == "gemini"
    assert tts.resolve_story_tts_engine("en") == "elevenlabs"
    assert tts.resolve_story_tts_engine("en-US") == "elevenlabs"
    assert tts.resolve_story_tts_engine("ja") == "elevenlabs"
    assert tts.resolve_story_tts_engine("ko") == "gemini"  # other → gemini


def test_routing_override(monkeypatch):
    monkeypatch.setenv("STORY_TTS_ENGINE_OVERRIDE", "edge")
    assert tts.resolve_story_tts_engine("en") == "edge"
    assert tts.resolve_story_tts_engine("vi") == "edge"


# ── ElevenLabs branch inside generate_narration_audio ─────────────────────────

def test_elevenlabs_branch_success(monkeypatch):
    monkeypatch.setattr(tts_elevenlabs, "elevenlabs_available", lambda: True)
    monkeypatch.setattr(tts_elevenlabs, "synthesize_elevenlabs", lambda **kw: "ELEVEN_OK.mp3")
    out = tts.generate_narration_audio(
        text="Hello world", language="en", gender="female", rate="+0%",
        job_id="t", tts_engine="elevenlabs",
    )
    assert out == "ELEVEN_OK.mp3"


# ── P4: Gemini failure → ElevenLabs (user directive) ─────────────────────────

def test_gemini_failure_falls_back_to_elevenlabs(monkeypatch):
    from app.features.render.engine.audio import tts_gemini
    monkeypatch.setenv("TTS_GEMINI_ELEVEN_FALLBACK", "1")
    monkeypatch.setattr(tts_gemini, "gemini_tts_available", lambda: True)
    monkeypatch.setattr(tts_gemini, "synthesize_gemini",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("gemini down")))
    monkeypatch.setattr(tts_elevenlabs, "elevenlabs_available", lambda: True)
    monkeypatch.setattr(tts_elevenlabs, "synthesize_elevenlabs", lambda **kw: "ELEVEN_FALLBACK.mp3")
    out = tts.generate_narration_audio(text="Xin chào", language="vi", gender="male",
                                       rate="+0%", job_id="t", tts_engine="gemini")
    assert out == "ELEVEN_FALLBACK.mp3"


def test_gemini_eleven_fallback_kill_switch(monkeypatch):
    from app.features.render.engine.audio import tts_gemini
    monkeypatch.setenv("TTS_GEMINI_ELEVEN_FALLBACK", "0")   # off → skip ElevenLabs
    monkeypatch.setattr(tts_gemini, "gemini_tts_available", lambda: True)
    monkeypatch.setattr(tts_gemini, "synthesize_gemini",
                        lambda **kw: (_ for _ in ()).throw(RuntimeError("gemini down")))
    seen = {"eleven": False}
    monkeypatch.setattr(tts_elevenlabs, "elevenlabs_available",
                        lambda: (seen.__setitem__("eleven", True) or True))
    monkeypatch.setattr(tts, "generate_narration_mp3", lambda **kw: "EDGE.mp3")   # edge sentinel
    out = tts.generate_narration_audio(text="Xin chào", language="vi", gender="male",
                                       rate="+0%", job_id="t", tts_engine="gemini")
    assert out == "EDGE.mp3" and seen["eleven"] is False    # went straight to edge


# ── provider guards ───────────────────────────────────────────────────────────

def test_available_false_without_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    assert tts_elevenlabs.elevenlabs_available() is False


def test_synthesize_raises_on_empty_text():
    with pytest.raises(RuntimeError):
        tts_elevenlabs.synthesize_elevenlabs(text="  ", language="en")


def test_synthesize_raises_without_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        tts_elevenlabs.synthesize_elevenlabs(text="hi", language="en")
