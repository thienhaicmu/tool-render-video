"""
test_deterministic_speech_density.py — guard for P1-1' (deterministic speech density).

Pins the pure ranking helper: chars/sec measured from the transcript and
min-max normalised across the job's clips (language-neutral relative density),
with safe no-op fallbacks that make the render-pipeline wiring behavior-neutral
when it can't differentiate.
"""
from __future__ import annotations

from app.features.render.engine.pipeline.pipeline_ranking import (
    _clip_chars_per_second,
    deterministic_speech_density_scores,
)


def _blocks():
    # 10s of dense text at [0,10], 10s of sparse text at [10,20].
    return [
        {"start": 0.0, "end": 10.0, "text": "x" * 100},   # 10 chars/sec
        {"start": 10.0, "end": 20.0, "text": "x" * 10},   # 1 char/sec
    ]


def test_chars_per_second_full_and_partial_overlap():
    b = _blocks()
    assert _clip_chars_per_second(0, 10, b) == 100 / 10       # dense block only
    assert _clip_chars_per_second(10, 20, b) == 10 / 10       # sparse block only
    # Half of the dense block: 50 chars over 5 s = 10 cps.
    assert abs(_clip_chars_per_second(0, 5, b) - (50 / 5)) < 1e-9


def test_relative_normalisation_maps_min0_max100():
    b = _blocks()
    windows = [(1, 0.0, 10.0), (2, 10.0, 20.0)]  # dense, sparse
    scores = deterministic_speech_density_scores(windows, b)
    assert scores[1] == 100.0   # densest → 100
    assert scores[2] == 0.0     # sparsest → 0


def test_three_clip_ordering():
    b = [
        {"start": 0.0, "end": 10.0, "text": "x" * 100},   # 10 cps
        {"start": 10.0, "end": 20.0, "text": "x" * 50},   # 5 cps
        {"start": 20.0, "end": 30.0, "text": "x" * 10},   # 1 cps
    ]
    windows = [(1, 0, 10), (2, 10, 20), (3, 20, 30)]
    s = deterministic_speech_density_scores(windows, b)
    assert s[1] == 100.0 and s[3] == 0.0
    assert 0.0 < s[2] < 100.0   # middle clip in between


def test_noop_fallbacks_return_empty():
    b = _blocks()
    # No blocks → {}
    assert deterministic_speech_density_scores([(1, 0, 10)], []) == {}
    # Single clip (can't normalise) → {}
    assert deterministic_speech_density_scores([(1, 0, 10)], b) == {}
    # All-equal density → {} (no differentiation)
    flat = [{"start": 0.0, "end": 30.0, "text": "x" * 300}]  # uniform 10 cps
    assert deterministic_speech_density_scores([(1, 0, 10), (2, 10, 20)], flat) == {}


def test_never_raises_on_junk():
    assert deterministic_speech_density_scores([(1, 0, 10)], [{"bad": "block"}]) == {}
    assert deterministic_speech_density_scores(None, None) == {}
