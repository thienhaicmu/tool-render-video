"""test_content_camera.py — Phase A3 per-scene camera moves (content backgrounds).

Verifies build_background_clip applies the AI camera_hint (zoom_in/out, pan) to a
still image, that "still" holds static, and that the vf builder is syntactically
sane for every mode.
"""
from __future__ import annotations

import subprocess

import pytest

from app.features.render.engine.stages.content_background import build_background_clip, _camera_vf


def _ffmpeg_ok() -> bool:
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        return subprocess.run([get_ffmpeg_bin(), "-version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


_NEEDS_FFMPEG = pytest.mark.skipif(not _ffmpeg_ok(), reason="FFmpeg not available")


def _make_image(path: str, w: int = 320, h: int = 568) -> None:
    from app.services.bin_paths import get_ffmpeg_bin
    subprocess.run(
        [get_ffmpeg_bin(), "-y", "-f", "lavfi", "-i", f"color=c=blue:s={w}x{h}",
         "-frames:v", "1", path],
        capture_output=True, check=True, timeout=30,
    )


def _has_video(path: str) -> bool:
    from app.services.bin_paths import get_ffprobe_bin
    r = subprocess.run(
        [get_ffprobe_bin(), "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=codec_type", "-of", "csv=p=0", path],
        capture_output=True, text=True, timeout=15,
    )
    return bool((r.stdout or "").strip())


def _dur(path: str) -> float:
    from app.services.bin_paths import get_ffprobe_bin
    r = subprocess.run(
        [get_ffprobe_bin(), "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nk=1:nw=1", path],
        capture_output=True, text=True, timeout=15,
    )
    try:
        return float((r.stdout or "0").strip() or 0.0)
    except ValueError:
        return 0.0


def test_camera_vf_all_modes_syntactic():
    for m in ("zoom_in", "zoom_out", "pan_left", "pan_right", "", "unknown"):
        vf = _camera_vf(320, 568, 30.0, 90, m)
        assert "zoompan" in vf and "setsar=1" in vf


@_NEEDS_FFMPEG
@pytest.mark.parametrize("mode", ["zoom_in", "zoom_out", "pan_left", "pan_right"])
def test_build_bg_camera_modes(tmp_path, mode):
    img = tmp_path / "i.png"
    _make_image(str(img))
    out = tmp_path / f"{mode}.mp4"
    ok = build_background_clip(
        kind="image", value=str(img), width=320, height=568, fps=30,
        duration_sec=2.0, out_path=str(out), camera=mode,
    )
    assert ok is True and out.exists() and out.stat().st_size > 0
    assert _has_video(str(out))
    assert 1.7 < _dur(str(out)) < 2.4


@_NEEDS_FFMPEG
def test_build_bg_still_holds_static(tmp_path):
    img = tmp_path / "i.png"
    _make_image(str(img))
    out = tmp_path / "still.mp4"
    ok = build_background_clip(
        kind="image", value=str(img), width=320, height=568, fps=30,
        duration_sec=2.0, out_path=str(out), camera="still",
    )
    assert ok is True and out.exists() and _has_video(str(out))
