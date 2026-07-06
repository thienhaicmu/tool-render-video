"""test_content_emphasis_subtitle.py — Phase D2 emphasis words in CapCut subs.

AI-chosen emphasis words get the keyword accent (colour + pop) in the word-by-word
CapCut ASS. emphasis=None is byte-identical to the pre-D2 output.
"""
from __future__ import annotations

from pathlib import Path

from app.features.render.engine.subtitle.generator.ass_capcut import (
    srt_to_ass_capcut, CAPCUT_PRESETS, _emphasis_set, _norm_emph,
)


def _make_word_srt(path: Path, words: list[str]) -> None:
    lines: list[str] = []
    t = 0.0
    for i, w in enumerate(words, 1):
        a, b = t, t + 0.4
        lines += [str(i), f"{_ts(a)} --> {_ts(b)}", w, ""]
        t = b
    path.write_text("\n".join(lines), encoding="utf-8")


def _ts(sec: float) -> str:
    h = int(sec // 3600); m = int((sec % 3600) // 60); s = int(sec % 60)
    ms = int(round((sec - int(sec)) * 1000))
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def test_emphasis_set_normalizes():
    assert _emphasis_set(["Amazing!", "big deal"]) == {"amazing", "big", "deal"}
    assert _emphasis_set(None) == set()
    assert _emphasis_set([]) == set()
    assert _norm_emph("  HELLO!! ") == "hello"


def test_emphasis_adds_keyword_accent(tmp_path):
    srt = tmp_path / "w.srt"
    _make_word_srt(srt, ["the", "amazing", "result", "is", "here"])
    base = tmp_path / "base.ass"
    emph = tmp_path / "emph.ass"
    srt_to_ass_capcut(str(srt), str(base), style="opus_pop")
    srt_to_ass_capcut(str(srt), str(emph), style="opus_pop", emphasis=["amazing"])

    b = base.read_text(encoding="utf-8")
    e = emph.read_text(encoding="utf-8")
    kw = CAPCUT_PRESETS["opus_pop"].keyword_color
    assert e != b                       # emphasis changed the output
    assert e.count(kw) > b.count(kw)    # "amazing" now carries the keyword colour


def test_emphasis_none_is_byte_identical(tmp_path):
    srt = tmp_path / "w.srt"
    _make_word_srt(srt, ["one", "two", "three", "four"])
    a = tmp_path / "a.ass"
    b = tmp_path / "b.ass"
    srt_to_ass_capcut(str(srt), str(a), style="opus_pop")
    srt_to_ass_capcut(str(srt), str(b), style="opus_pop", emphasis=None)
    assert a.read_text(encoding="utf-8") == b.read_text(encoding="utf-8")
