"""test_content_overlay.py — Phase E1 animated text overlay (title / lower-third).

build_overlay_ass emits a valid, burnable ASS for the supported animation_hints,
escapes the title (no override injection), and refuses empty/unsupported input.
"""
from __future__ import annotations

import subprocess

import pytest

from app.features.render.engine.stages.content_overlay import build_overlay_ass


def _ffmpeg_ok() -> bool:
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        return subprocess.run([get_ffmpeg_bin(), "-version"], capture_output=True, timeout=5).returncode == 0
    except Exception:
        return False


_NEEDS_FFMPEG = pytest.mark.skipif(not _ffmpeg_ok(), reason="FFmpeg not available")


def test_title_ass_has_events_and_title(tmp_path):
    ov = tmp_path / "t.ass"
    assert build_overlay_ass("Hello World", "title", 1080, 1920, 3.0, str(ov)) is True
    txt = ov.read_text(encoding="utf-8")
    assert "[Events]" in txt and "Dialogue:" in txt and "Hello World" in txt
    assert "\\fad" in txt


def test_lower_third_ass(tmp_path):
    ov = tmp_path / "l.ass"
    assert build_overlay_ass("Breaking News", "lower_third", 1080, 1920, 3.0, str(ov)) is True
    assert "Breaking News" in ov.read_text(encoding="utf-8")


def test_empty_title_returns_false(tmp_path):
    assert build_overlay_ass("   ", "title", 1080, 1920, 3.0, str(tmp_path / "x.ass")) is False


def test_unsupported_hint_returns_false(tmp_path):
    assert build_overlay_ass("T", "progress_bar", 1080, 1920, 3.0, str(tmp_path / "x.ass")) is False
    assert build_overlay_ass("T", "", 1080, 1920, 3.0, str(tmp_path / "y.ass")) is False


def test_title_is_escaped(tmp_path):
    ov = tmp_path / "e.ass"
    assert build_overlay_ass("a{b}c\\d", "title", 1080, 1920, 3.0, str(ov)) is True
    txt = ov.read_text(encoding="utf-8")
    assert "a(b)c" in txt          # braces neutralised (no override injection)


@_NEEDS_FFMPEG
def test_overlay_ass_burns_without_error(tmp_path):
    ov = tmp_path / "ov.ass"
    assert build_overlay_ass("My Epic Title", "title", 320, 568, 2.0, str(ov)) is True
    from app.services.bin_paths import get_ffmpeg_bin
    from app.features.render.engine.encoder.encoder_helpers import safe_filter_path
    out = tmp_path / "frame.jpg"
    r = subprocess.run(
        [get_ffmpeg_bin(), "-y", "-f", "lavfi", "-i", "color=c=navy:s=320x568:d=2:r=30",
         "-vf", f"ass='{safe_filter_path(str(ov))}'", "-frames:v", "1", str(out)],
        capture_output=True, timeout=60,
    )
    assert r.returncode == 0, r.stderr.decode(errors="ignore")[:400]
    assert out.exists() and out.stat().st_size > 0
