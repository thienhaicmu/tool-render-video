"""test_content_tempo_fit.py — W5-1 engine-aware duration enforcement.

The plan's duration fit scales each scene's reading_speed, but only Edge TTS
applies `rate`; xtts/piper ignore it and gemini only soft-hints it, so the fitted
duration wouldn't actually hold. W5-1 enforces reading_speed with a post-TTS
atempo for non-edge engines (edge stays untouched). Here generate_narration_audio
is mocked to always emit a 4s clip REGARDLESS of rate (simulating a rate-ignoring
engine), so the observable effect is purely the atempo pass.
"""
from __future__ import annotations

import shutil
import subprocess
from types import SimpleNamespace

import pytest

from app.features.render.engine.stages.content_scene_render import synthesize_scene_narration


def _ffmpeg_ok() -> bool:
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        return bool(shutil.which(get_ffmpeg_bin()) or get_ffmpeg_bin())
    except Exception:
        return False


_NEEDS_FFMPEG = pytest.mark.skipif(not _ffmpeg_ok(), reason="ffmpeg required")


def _fake_tts_4s(*, text, language, gender, rate, job_id, output_path, **kwargs):
    """A TTS stub that emits a 4.0s silent mp3 and IGNORES `rate` — i.e. behaves
    like xtts/piper. Lets the test isolate the W5-1 atempo effect."""
    from app.services.bin_paths import get_ffmpeg_bin
    subprocess.run(
        [get_ffmpeg_bin(), "-y", "-f", "lavfi",
         "-i", "anullsrc=r=48000:cl=stereo", "-t", "4", "-c:a", "libmp3lame", output_path],
        capture_output=True, check=True, timeout=60,
    )
    return output_path


def _scene(reading_speed):
    return SimpleNamespace(narration="xin chao cac ban", reading_speed=reading_speed, emotion="", index=0)


@_NEEDS_FFMPEG
def test_non_edge_atempo_shortens_to_reading_speed(monkeypatch, tmp_path):
    monkeypatch.setattr("app.features.render.engine.audio.tts.generate_narration_audio", _fake_tts_4s)
    r = synthesize_scene_narration(
        scene=_scene(1.5), job_id="t", tts_engine="xtts", out_path=str(tmp_path / "n.mp3"),
    )
    assert r is not None
    _, dur = r
    # 4.0s at 1.5x → ~2.67s. atempo enforced the fitted reading_speed.
    assert 2.3 < dur < 3.05, dur


@_NEEDS_FFMPEG
def test_edge_is_untouched(monkeypatch, tmp_path):
    monkeypatch.setattr("app.features.render.engine.audio.tts.generate_narration_audio", _fake_tts_4s)
    r = synthesize_scene_narration(
        scene=_scene(1.5), job_id="t", tts_engine="edge", out_path=str(tmp_path / "n.mp3"),
    )
    assert r is not None
    _, dur = r
    # Edge path skips atempo (edge applies rate natively); the rate-ignoring mock
    # therefore leaves the clip at ~4.0s → proves no double-application on edge.
    assert 3.7 < dur < 4.3, dur


@_NEEDS_FFMPEG
def test_speed_one_no_atempo(monkeypatch, tmp_path):
    monkeypatch.setattr("app.features.render.engine.audio.tts.generate_narration_audio", _fake_tts_4s)
    r = synthesize_scene_narration(
        scene=_scene(1.0), job_id="t", tts_engine="xtts", out_path=str(tmp_path / "n.mp3"),
    )
    assert r is not None
    _, dur = r
    assert 3.7 < dur < 4.3, dur  # reading_speed 1.0 → no tempo change
