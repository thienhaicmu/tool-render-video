"""test_content_narration_prepass.py — W5-6 one-shot narration transcription.

Covers the pure offset-split logic (the sync-critical part) and the best-effort
fallback, without needing Whisper/ffmpeg. The end-to-end word-by-word path keeps
its own fallback (per-scene transcribe) so a pre-pass failure is never fatal.
"""
from __future__ import annotations

from types import SimpleNamespace

import app.features.render.engine.stages.content.narration_stage as ns
from app.features.render.engine.stages.content.narration_stage import _split_srt_window

_GLOBAL = (
    "1\n00:00:00,000 --> 00:00:00,500\nHello\n\n"
    "2\n00:00:01,000 --> 00:00:01,400\nworld\n\n"
    "3\n00:00:03,200 --> 00:00:03,600\nnext\n\n"
    "4\n00:00:04,000 --> 00:00:04,300\nscene\n\n"
)


def test_split_window_first_scene_keeps_and_rebases():
    w = _split_srt_window(_GLOBAL, 0.0, 3.0)
    assert "Hello" in w and "world" in w
    assert "next" not in w and "scene" not in w
    assert "00:00:00,000 --> 00:00:00,500" in w  # start-of-video cue unchanged


def test_split_window_second_scene_rebases_to_zero():
    w = _split_srt_window(_GLOBAL, 3.0, 6.0)
    assert "next" in w and "scene" in w
    assert "Hello" not in w and "world" not in w
    # 3.2s in the concat → 0.2s within this scene.
    assert "00:00:00,200 --> 00:00:00,600" in w
    # cues are re-indexed from 1.
    assert w.strip().startswith("1")


def test_split_window_boundary_is_half_open():
    # a cue starting exactly at `end` belongs to the NEXT window, not this one.
    w = _split_srt_window(_GLOBAL, 0.0, 3.2)
    assert "next" not in w  # starts at 3.2 == end → excluded


def test_split_window_empty_srt():
    assert _split_srt_window("", 0.0, 5.0) == ""


def test_prepare_fallback_when_all_tts_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(ns, "synthesize_scene_narration", lambda **k: None)
    ctx = SimpleNamespace(
        scenes_dir=tmp_path, job_id="t", language="vi-VN", gender="female",
        voice_id=None, tts_engine="edge",
    )
    scenes = [SimpleNamespace(index=0, role="hook", narration="hi", pause_before=0.0)]
    audio_map, srt_map = ns.prepare_narration_word_timings(ctx, scenes)
    assert audio_map == {} and srt_map == {}  # nothing synth'd → clean empty maps
