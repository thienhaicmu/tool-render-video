"""test_content_emotion_tts.py — Phase D1 emotion-aware TTS.

- Edge/XTTS: emotion → a (rate delta %, pitch Hz) prosody, inert (0, 0) for
  ""/"normal"/unknown and when CONTENT_EMOTION_TTS is off.
- Gemini: emotion → a style directive appended to the content-type style, unless
  GEMINI_TTS_STYLE is explicitly set.
"""
from __future__ import annotations

import app.features.render.engine.audio.tts as tts
import app.features.render.engine.audio.tts_gemini as tg


def test_emotion_prosody_map():
    assert tts._emotion_prosody("excited") == (8, 15)
    assert tts._emotion_prosody("sad") == (-8, -18)
    assert tts._emotion_prosody("") == (0, 0)
    assert tts._emotion_prosody("normal") == (0, 0)       # inert
    assert tts._emotion_prosody("nonsense") == (0, 0)     # unknown → inert


def test_emotion_prosody_kill_switch(monkeypatch):
    monkeypatch.setattr(tts, "_CONTENT_EMOTION_TTS", False)
    assert tts._emotion_prosody("excited") == (0, 0)      # off → inert


def test_gemini_style_appends_emotion(monkeypatch):
    monkeypatch.delenv("GEMINI_TTS_STYLE", raising=False)
    monkeypatch.setenv("CONTENT_EMOTION_TTS", "1")
    plain = tg._resolve_style("vlog", language="en-US", rate="", emotion="")
    emo = tg._resolve_style("vlog", language="en-US", rate="", emotion="excited")
    assert emo != plain
    assert "excited" in emo.lower()


def test_gemini_style_emotion_off(monkeypatch):
    monkeypatch.delenv("GEMINI_TTS_STYLE", raising=False)
    monkeypatch.setenv("CONTENT_EMOTION_TTS", "0")
    plain = tg._resolve_style("vlog", language="en-US", rate="", emotion="")
    emo = tg._resolve_style("vlog", language="en-US", rate="", emotion="excited")
    assert emo == plain   # off → no directive appended


def test_gemini_env_style_overrides_emotion(monkeypatch):
    monkeypatch.setenv("GEMINI_TTS_STYLE", "MY FIXED STYLE")
    assert tg._resolve_style("vlog", emotion="excited") == "MY FIXED STYLE"
