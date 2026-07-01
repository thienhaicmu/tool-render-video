"""
test_clip_parser_dedup.py — guard for P1-3 (near-duplicate clip removal).

The clip prompt asks the model to drop near-duplicate clips; the parser now
enforces it deterministically via an IoU filter. These tests pin the intended
behaviour: heavy-overlap clips collapse to the higher-scored one, while
partial-overlap (different-hook) and disjoint clips are preserved.
"""
from __future__ import annotations

import json

from app.features.render.ai.llm.parser import (
    _dedup_overlapping_clips,
    _interval_iou,
    parse_render_plan_response,
)


# ── helper units ─────────────────────────────────────────────────────────────

def test_interval_iou_math():
    assert _interval_iou(0, 10, 0, 10) == 1.0            # identical
    assert _interval_iou(0, 10, 20, 30) == 0.0           # disjoint
    assert _interval_iou(0, 10, 10, 20) == 0.0           # touching, no overlap
    # [0,10] vs [5,15]: inter=5, union=15 → 1/3
    assert abs(_interval_iou(0, 10, 5, 15) - (5 / 15)) < 1e-9


def test_dedup_keeps_higher_scored_of_heavy_overlap():
    clips = [  # already sorted best-first
        {"start": 10.0, "end": 40.0, "score": 0.9, "clip_name": "A"},
        {"start": 11.0, "end": 41.0, "score": 0.5, "clip_name": "B"},  # ~0.94 IoU → dup
    ]
    out = _dedup_overlapping_clips(clips, 0.7)
    assert [c["clip_name"] for c in out] == ["A"]


def test_dedup_keeps_partial_overlap_different_hooks():
    clips = [
        {"start": 0.0, "end": 30.0, "score": 0.9, "clip_name": "A"},
        {"start": 20.0, "end": 50.0, "score": 0.8, "clip_name": "B"},  # IoU=10/50=0.2
    ]
    out = _dedup_overlapping_clips(clips, 0.7)
    assert [c["clip_name"] for c in out] == ["A", "B"]


def test_dedup_keeps_disjoint():
    clips = [
        {"start": 0.0, "end": 30.0, "score": 0.9, "clip_name": "A"},
        {"start": 100.0, "end": 140.0, "score": 0.8, "clip_name": "B"},
    ]
    assert len(_dedup_overlapping_clips(clips, 0.7)) == 2


def test_dedup_disabled_when_threshold_zero():
    clips = [
        {"start": 0.0, "end": 30.0, "score": 0.9},
        {"start": 0.0, "end": 30.0, "score": 0.8},
    ]
    assert len(_dedup_overlapping_clips(clips, 0.0)) == 2


# ── end-to-end through the parser ────────────────────────────────────────────

def test_parse_render_plan_dedups_duplicate_clips():
    # Two near-identical clips + one distinct → parser should return 2.
    raw = json.dumps({
        "clips": [
            {"start": 10.0, "end": 45.0, "score": 0.95, "clip_name": "hook1"},
            {"start": 11.0, "end": 46.0, "score": 0.80, "clip_name": "hook1_dup"},
            {"start": 120.0, "end": 160.0, "score": 0.85, "clip_name": "hook2"},
        ],
        "subtitle_policy": {}, "camera_strategy": {}, "audio_plan": {}, "overlays": [],
    })
    plan = parse_render_plan_response(raw, output_count=5, min_sec=20, max_sec=60,
                                      video_duration=600)
    assert plan is not None
    spans = sorted((c.start, c.end) for c in plan.clips)
    assert spans == [(10.0, 45.0), (120.0, 160.0)], "near-duplicate should be dropped"
    assert len(plan.clips) == 2
