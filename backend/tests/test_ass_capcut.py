"""Unit tests for the CapCut-style subtitle generator (ass_capcut).

Pure text-generation tests — no FFmpeg, no fonts, no network. They assert
the ASS body carries the per-word highlight contract that makes the new
look CapCut/Opus-grade (active accent, box mode, dim/reveal, keyword).
"""
from pathlib import Path

import pytest

from app.features.render.engine.subtitle.generator.ass_capcut import (
    CAPCUT_PRESETS,
    resolve_capcut_style,
    srt_to_ass_capcut,
)


def _write_word_srt(tmp_path: Path) -> str:
    # Word-level SRT: a number + an ALL-CAPS token to exercise keyword logic.
    words = [
        ("This", 0.0, 0.4), ("made", 0.4, 0.8), ("me", 0.8, 1.1),
        ("10000", 1.1, 1.7), ("FAST", 1.7, 2.2),
    ]

    def ts(s):
        h, m, sec = int(s // 3600), int(s % 3600 // 60), s % 60
        return f"{h:02d}:{m:02d}:{sec:06.3f}".replace(".", ",")

    p = tmp_path / "w.srt"
    p.write_text(
        "".join(f"{i}\n{ts(a)} --> {ts(b)}\n{w}\n\n" for i, (w, a, b) in enumerate(words, 1)),
        encoding="utf-8",
    )
    return str(p)


@pytest.fixture
def word_srt(tmp_path):
    return _write_word_srt(tmp_path)


def _gen(word_srt, tmp_path, style):
    out = tmp_path / f"{style}.ass"
    srt_to_ass_capcut(word_srt, str(out), style=style, play_res_x=540, play_res_y=960)
    return out.read_text(encoding="utf-8")


@pytest.mark.parametrize("style", list(CAPCUT_PRESETS.keys()))
def test_every_preset_generates_valid_ass(word_srt, tmp_path, style):
    body = _gen(word_srt, tmp_path, style)
    assert "[Script Info]" in body
    assert "[V4+ Styles]" in body
    assert "[Events]" in body
    assert "Dialogue:" in body
    # Active-word colour override is the core of the look.
    assert r"\c&H" in body


def test_box_preset_uses_borderstyle_3(word_srt, tmp_path):
    body = _gen(word_srt, tmp_path, "capcut_box")
    # BorderStyle is the 16th field; BorderStyle=3 = opaque box.
    style_line = next(l for l in body.splitlines() if l.startswith("Style: Default"))
    assert style_line.split(",")[15] == "3"


def test_pop_preset_has_scale_transform(word_srt, tmp_path):
    body = _gen(word_srt, tmp_path, "opus_pop")
    assert r"\fscx118" in body and r"\t(" in body  # overshoot pop on active word


def test_smooth_preset_has_fade_reveal(word_srt, tmp_path):
    body = _gen(word_srt, tmp_path, "smooth_premiere")
    assert r"\alpha&HFF&" in body            # future words hidden / fade-in
    assert r"\fscx94" in body                # gentle grow (no overshoot)


def test_keyword_colour_applied_to_number(word_srt, tmp_path):
    # opus_pop has a keyword colour; the number 10000 should carry it even
    # while it is not the active word.
    body = _gen(word_srt, tmp_path, "opus_pop")
    kw = CAPCUT_PRESETS["opus_pop"].keyword_color
    assert kw and kw in body


def test_word_level_produces_one_dialogue_per_active_word(word_srt, tmp_path):
    # 5 words → 5 active windows → 5 Dialogue events (groups don't reduce count).
    body = _gen(word_srt, tmp_path, "opus_pop")
    assert sum(1 for l in body.splitlines() if l.startswith("Dialogue:")) == 5


def test_resolve_legacy_and_unknown_styles():
    assert resolve_capcut_style("tiktok_bounce_v1") == "opus_pop"
    assert resolve_capcut_style("gaming") == "punch_green"
    assert resolve_capcut_style("clean") == "smooth_premiere"
    assert resolve_capcut_style("pro_karaoke") == "karaoke_clean"
    assert resolve_capcut_style("opus_pop") == "opus_pop"      # already new
    assert resolve_capcut_style("nonsense_xyz") == "opus_pop"  # unknown → default
    assert resolve_capcut_style("") == "opus_pop"
