"""Pin parse_segment_response overshoot-clamp behaviour (Batch 10T).

Live bug (2026-06-07): a render against a 65 s video failed at
``JobStage.SEGMENT_BUILDING`` because Gemini ``2.5-flash`` returned a
single segment ``{"start": 4.2, "end": 70.0, ...}``. The parser's
strict-bounds path correctly rejected it (``end > video_duration + 1.0``)
and the relaxed-retry path ALSO kept the bounds check, so the segment
was lost and the pipeline hard-failed with zero usable segments.

Fix: in the relaxed-retry path, call ``_clamp_overshoot_end`` first.
Small overshoots (≤ max(10 s, 10 % of the video)) are clamped to
``video_duration``; larger overshoots are left alone so a wildly-off
hallucination still fails clearly.

These tests pin:
  1. The helper itself (small overshoot clamps, large overshoot no-op,
     edge inputs return original).
  2. The integration into ``parse_segment_response`` — the exact live
     case (start=4.2, end=70.0 on a 65 s video) now produces a usable
     segment with end=65.0.
"""
from __future__ import annotations

import json

import pytest

from app.features.render.ai.llm.parser import (
    _clamp_overshoot_end,
    parse_segment_response,
)


# ---------------------------------------------------------------------------
# 1. Unit: _clamp_overshoot_end
# ---------------------------------------------------------------------------


def test_clamp_small_overshoot_clamps_end_to_video_duration():
    """5 s overshoot on a 65 s video is small (tolerance = max(10, 6.5) = 10)
    → clamp end to 65.0."""
    item = {"start": 4.2, "end": 70.0, "score": 0.8}
    result = _clamp_overshoot_end(item, video_duration=65.0)
    assert isinstance(result, dict)
    assert result["end"] == 65.0
    assert result["start"] == 4.2  # untouched
    assert result["score"] == 0.8  # untouched


def test_clamp_does_not_mutate_caller_dict():
    """Helper must return a NEW dict on clamp, not mutate the caller's."""
    item = {"start": 4.2, "end": 70.0, "score": 0.8}
    _clamp_overshoot_end(item, video_duration=65.0)
    assert item["end"] == 70.0  # original untouched


def test_clamp_large_overshoot_leaves_item_alone():
    """50 s overshoot on a 65 s video is huge — leave it for the bounds
    check to reject."""
    item = {"start": 4.2, "end": 120.0, "score": 0.8}
    result = _clamp_overshoot_end(item, video_duration=65.0)
    assert result is item  # original returned untouched
    assert result["end"] == 120.0


def test_clamp_at_10_percent_tolerance_boundary():
    """1000 s video → tolerance = max(10, 100) = 100. Overshoot of exactly
    100 should clamp; overshoot of 101 should not."""
    just_in = {"start": 0, "end": 1100.0}
    out = _clamp_overshoot_end(just_in, video_duration=1000.0)
    assert out["end"] == 1000.0

    just_out = {"start": 0, "end": 1101.0}
    out = _clamp_overshoot_end(just_out, video_duration=1000.0)
    assert out is just_out
    assert out["end"] == 1101.0


def test_clamp_no_overshoot_returns_original():
    """end ≤ video_duration → no-op, return original object."""
    item = {"start": 0, "end": 60.0}
    result = _clamp_overshoot_end(item, video_duration=65.0)
    assert result is item


def test_clamp_handles_missing_end():
    """Missing 'end' key → no clamp, return original."""
    item = {"start": 0}
    result = _clamp_overshoot_end(item, video_duration=65.0)
    assert result is item


def test_clamp_handles_garbage_end_value():
    """end='abc' → no crash, return original."""
    item = {"start": 0, "end": "abc"}
    result = _clamp_overshoot_end(item, video_duration=65.0)
    assert result is item


def test_clamp_handles_non_dict_input():
    """Non-dict input (e.g. list, str) returns unchanged — defensive."""
    assert _clamp_overshoot_end("not a dict", video_duration=65.0) == "not a dict"
    assert _clamp_overshoot_end([1, 2, 3], video_duration=65.0) == [1, 2, 3]
    assert _clamp_overshoot_end(None, video_duration=65.0) is None


def test_clamp_handles_invalid_video_duration():
    """video_duration ≤ 0 or non-numeric → no-op."""
    item = {"start": 0, "end": 70.0}
    assert _clamp_overshoot_end(item, video_duration=0) is item
    assert _clamp_overshoot_end(item, video_duration=-5) is item
    assert _clamp_overshoot_end(item, video_duration="oops") is item  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 2. Integration: parse_segment_response with the live failure case
# ---------------------------------------------------------------------------


def test_parse_segment_response_live_bug_2026_06_07_recovers_segment():
    """The exact wire shape Gemini returned on 2026-06-07: one segment
    starting at 4.2, ending at 70.0 on a 65 s video, with min_part_sec=65
    so the strict bounds reject it AND the duration filter is impossible.

    The relaxed-retry path must clamp end → 65.0 and produce a valid
    segment so the pipeline doesn't hard-fail.
    """
    raw = json.dumps([
        {
            "start": 4.2,
            "end": 70.0,
            "score": 0.9,
            "clip_name": "Marriage proposal",
            "title": "Fastest marriage proposal",
            "reason": "Strong viral hook",
        }
    ])
    result = parse_segment_response(
        raw=raw,
        output_count=1,
        min_sec=65.0,
        max_sec=120.0,
        video_duration=65.0,
    )
    assert result is not None
    assert len(result) == 1
    assert result[0].end == 65.0
    assert result[0].start == 4.2


def test_parse_segment_response_large_overshoot_still_rejected():
    """Overshoot beyond tolerance keeps the strict-rejection behaviour —
    no silent acceptance of wildly-off LLM hallucinations."""
    raw = json.dumps([
        {
            "start": 0.0,
            "end": 1000.0,  # 935 s overshoot on a 65 s video — huge
            "score": 0.9,
            "clip_name": "bogus",
        }
    ])
    result = parse_segment_response(
        raw=raw,
        output_count=1,
        min_sec=1.0,
        max_sec=120.0,
        video_duration=65.0,
    )
    assert result is None  # hard-fail signal


def test_parse_segment_response_in_bounds_path_unchanged():
    """Happy-path: an in-bounds segment is parsed without invoking the
    relaxed-retry / clamp logic at all."""
    raw = json.dumps([
        {
            "start": 5.0,
            "end": 35.0,
            "score": 0.85,
            "clip_name": "happy clip",
        }
    ])
    result = parse_segment_response(
        raw=raw,
        output_count=1,
        min_sec=10.0,
        max_sec=60.0,
        video_duration=120.0,
    )
    assert result is not None
    assert len(result) == 1
    assert result[0].start == 5.0
    assert result[0].end == 35.0
