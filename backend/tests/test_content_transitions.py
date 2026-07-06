"""test_content_transitions.py — Phase A1 crossfade assembler (content only).

Verifies content_assembler.concat_with_transitions joins scene clips with an
xfade/acrossfade per the AI transition_hint, shortens the total by the overlaps
(so QA matches), and refuses < 2 clips (caller then uses the plain concat).
"""
from __future__ import annotations

import subprocess

import pytest

from app.features.render.engine.stages.content_assembler import (
    concat_with_transitions, _xtype, _probe_duration,
)


def _ffmpeg_ok() -> bool:
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        return subprocess.run([get_ffmpeg_bin(), "-version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


_NEEDS_FFMPEG = pytest.mark.skipif(not _ffmpeg_ok(), reason="FFmpeg not available")


def _make_av(path: str, dur: float, size: str = "320x568") -> None:
    from app.services.bin_paths import get_ffmpeg_bin
    subprocess.run(
        [get_ffmpeg_bin(), "-y", "-f", "lavfi", "-i", f"testsrc=size={size}:rate=30:duration={dur}",
         "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{dur}",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", path],
        capture_output=True, check=True, timeout=60,
    )


def _has(path: str, stream: str) -> bool:
    from app.services.bin_paths import get_ffprobe_bin
    r = subprocess.run(
        [get_ffprobe_bin(), "-v", "error", "-select_streams", stream,
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=15,
    )
    return bool((r.stdout or "").strip())


def test_xtype_mapping():
    assert _xtype("slide") == "slideleft"
    assert _xtype("flash") == "fadewhite"
    assert _xtype("zoom") == "zoomin"
    assert _xtype("fade") == "fade"
    assert _xtype("") == "fade"
    assert _xtype("weird-unknown") == "fade"   # unknown → safe default


@_NEEDS_FFMPEG
def test_transitions_join_with_overlap(tmp_path):
    clips = [str(tmp_path / f"c{i}.mp4") for i in range(3)]
    for p in clips:
        _make_av(p, 3.0)
    out = tmp_path / "joined.mp4"
    res = concat_with_transitions(clips, str(out), transitions=["fade", "slide"],
                                  width=320, height=568, fps=30)
    assert res["ok"] is True, res
    assert out.exists() and out.stat().st_size > 0
    assert _has(str(out), "v:0") and _has(str(out), "a:0")
    # 3×3s with two 0.4s crossfades → 9 − 0.8 = 8.2s.
    assert abs(res["expected_duration"] - 8.2) < 0.3, res
    assert abs(_probe_duration(str(out)) - res["expected_duration"]) < 0.6


@_NEEDS_FFMPEG
def test_transitions_refuse_single_clip(tmp_path):
    c = str(tmp_path / "only.mp4")
    _make_av(c, 3.0)
    res = concat_with_transitions([c], str(tmp_path / "o.mp4"), transitions=[],
                                  width=320, height=568, fps=30)
    assert res["ok"] is False   # < 2 clips → caller falls back to plain concat


@_NEEDS_FFMPEG
def test_transitions_missing_transitions_list_defaults_fade(tmp_path):
    clips = [str(tmp_path / f"c{i}.mp4") for i in range(2)]
    for p in clips:
        _make_av(p, 2.0)
    out = tmp_path / "j.mp4"
    res = concat_with_transitions(clips, str(out), transitions=[],  # padded → fade
                                  width=320, height=568, fps=30)
    assert res["ok"] is True and out.exists()
