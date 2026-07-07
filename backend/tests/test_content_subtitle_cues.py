"""test_content_subtitle_cues.py — W5-5 readable sentence-level caption splitting.

When word-by-word is OFF, captions are timed at sentence granularity. W5-5
sub-splits an over-long single sentence at clause boundaries (commas etc.) so it
doesn't sit on screen as one wall of text. Pure text logic — no ffmpeg/Whisper.
"""
from __future__ import annotations

from app.features.render.engine.stages.content_scene_render import _split_cues


def _norm(s: str) -> str:
    return " ".join(s.split())


def test_long_sentence_with_commas_splits_and_preserves_order():
    s = ("Napoleon lost the battle, the heavy rain turned the field to mud, "
         "the Prussians arrived on the flank, and his old guard finally broke.")
    cues = _split_cues(s, 6)
    assert len(cues) > 1, cues                       # split at clause boundaries
    assert all(len(c) < len(s) for c in cues)        # each shorter than the whole
    assert _norm(" ".join(cues)) == _norm(s)         # word order preserved, nothing lost


def test_long_sentence_without_clause_boundary_stays_one():
    s = "Napoleon finally lost the great and famous decisive battle at Waterloo that year"
    cues = _split_cues(s, 6)
    assert cues == [s]                               # no comma → can't split cleanly


def test_short_sentence_unchanged():
    assert _split_cues("Hello world.", 6) == ["Hello world."]


def test_many_sentences_stay_capped():
    s = ". ".join(f"This is sentence number {i}" for i in range(10)) + "."
    cues = _split_cues(s, 6)
    assert len(cues) <= 6


def test_empty_narration_no_cues():
    assert _split_cues("   ", 6) == []
