"""Architecture-review Batch D-2-thin (2026-06-30) — SceneMap domain contract.

Pins the SceneMap dataclass behaviour:

  1. Schema additivity — defaults safe, legacy/partial blobs load.
  2. Defensive coercion — malformed shots dropped, no raise.
  3. Helpers — find_shot_containing, nearest_boundary, shot_count.
  4. JSON round-trip — deterministic, sorted-key serialisation.
  5. scene_map_from_detector_result — convenience builder for the stage runner.
"""
from __future__ import annotations

import json

import pytest

from app.domain.scene_map import (
    SCENE_MAP_SCHEMA_VERSION,
    SceneMap,
    Shot,
    scene_map_from_detector_result,
)


# ---------------------------------------------------------------------------
# Schema + defaults
# ---------------------------------------------------------------------------


def test_schema_version_pinned():
    assert SCENE_MAP_SCHEMA_VERSION == 1


def test_empty_map_defaults():
    sm = SceneMap()
    assert sm.schema_version == 1
    assert sm.shots == []
    assert sm.source_fps == 0.0
    assert sm.total_duration_sec == 0.0
    assert sm.is_empty() is True
    assert sm.shot_count() == 0


def test_shot_default_zero_duration():
    s = Shot()
    assert s.duration == 0.0


def test_shot_duration_clamps_to_zero_when_inverted():
    s = Shot(start=10.0, end=5.0)
    assert s.duration == 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _three_shot_map() -> SceneMap:
    return SceneMap(
        shots=[
            Shot(start=0.0, end=10.0, transition_score=0.0),
            Shot(start=10.0, end=25.5, transition_score=0.8),
            Shot(start=25.5, end=60.0, transition_score=0.9),
        ],
        source_fps=30.0,
        total_duration_sec=60.0,
    )


def test_shot_count():
    assert _three_shot_map().shot_count() == 3


def test_find_shot_containing_inside():
    sm = _three_shot_map()
    shot = sm.find_shot_containing(15.0)
    assert shot is not None
    assert shot.start == 10.0 and shot.end == 25.5


def test_find_shot_containing_on_boundary():
    """Boundary times count as inside (inclusive)."""
    sm = _three_shot_map()
    assert sm.find_shot_containing(10.0) is not None
    assert sm.find_shot_containing(60.0) is not None


def test_find_shot_containing_out_of_range():
    sm = _three_shot_map()
    assert sm.find_shot_containing(999.0) is None
    assert sm.find_shot_containing(-1.0) is None


def test_find_shot_containing_handles_garbage_input():
    """Sacred Contract #3 spirit — never raise on bad input."""
    sm = _three_shot_map()
    assert sm.find_shot_containing("garbage") is None  # type: ignore[arg-type]
    assert sm.find_shot_containing(None) is None  # type: ignore[arg-type]


def test_nearest_boundary_empty_map_returns_input():
    sm = SceneMap()
    assert sm.nearest_boundary(42.0) == 42.0


def test_nearest_boundary_picks_closest():
    sm = _three_shot_map()
    # 11.0 is closest to the shot[1].start = 10.0 boundary.
    assert sm.nearest_boundary(11.0) == 10.0
    # 24.0 is closer to shot[2].start = 25.5.
    assert sm.nearest_boundary(24.0) == 25.5
    # 26.0 is also closer to 25.5.
    assert sm.nearest_boundary(26.0) == 25.5


def test_nearest_boundary_handles_garbage_input():
    sm = _three_shot_map()
    assert sm.nearest_boundary("bad") == 0.0  # type: ignore[arg-type]
    assert sm.nearest_boundary(None) == 0.0  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_round_trip_preserves_shots():
    sm = _three_shot_map()
    raw = sm.to_json()
    sm2 = SceneMap.from_json(raw)
    assert sm2 is not None
    assert sm2.shot_count() == 3
    assert sm2.shots[1].start == 10.0 and sm2.shots[1].end == 25.5
    assert sm2.source_fps == 30.0
    assert sm2.total_duration_sec == 60.0
    assert sm2.schema_version == SCENE_MAP_SCHEMA_VERSION


def test_to_json_is_deterministic():
    sm = _three_shot_map()
    a = sm.to_json()
    b = sm.to_json()
    assert a == b


def test_from_json_returns_none_on_none_input():
    assert SceneMap.from_json(None) is None


def test_from_json_returns_none_on_unparseable():
    assert SceneMap.from_json("not-json") is None
    assert SceneMap.from_json("") is None
    assert SceneMap.from_json("[]") is None  # list, not dict


def test_from_json_drops_unknown_keys():
    raw = json.dumps({
        "schema_version": 1,
        "shots": [],
        "source_fps": 24.0,
        "unknown_future_field": "ignored",
    })
    sm = SceneMap.from_json(raw)
    assert sm is not None
    assert sm.source_fps == 24.0


def test_from_json_defaults_missing_keys():
    """Sacred Contract #3 spirit — partial blob loads without error."""
    raw = json.dumps({"shots": [{"start": 0.0, "end": 5.0}]})
    sm = SceneMap.from_json(raw)
    assert sm is not None
    assert sm.shot_count() == 1
    assert sm.source_fps == 0.0
    assert sm.total_duration_sec == 0.0


def test_from_json_drops_malformed_shots():
    raw = json.dumps({
        "shots": [
            {"start": 0.0, "end": 5.0},        # valid
            {"start": 10.0, "end": 5.0},       # inverted → dropped
            {"start": "garbage", "end": "x"},  # malformed → dropped
            {"start": 10.0, "end": 10.0},      # zero duration → dropped
            "string-shot",                     # not a dict → dropped
            {"start": 15.0, "end": 20.0, "transition_score": 0.5},  # valid
        ],
    })
    sm = SceneMap.from_json(raw)
    assert sm is not None
    assert sm.shot_count() == 2
    assert sm.shots[0].end == 5.0
    assert sm.shots[1].transition_score == 0.5


# ---------------------------------------------------------------------------
# scene_map_from_detector_result
# ---------------------------------------------------------------------------


def test_builder_from_detector_result_happy_path():
    raw = [
        {"start": 0.0, "end": 5.0, "transition_score": 0.0},
        {"start": 5.0, "end": 12.0, "transition_score": 0.7},
    ]
    sm = scene_map_from_detector_result(raw, source_fps=24.0, total_duration_sec=12.0)
    assert sm.shot_count() == 2
    assert sm.source_fps == 24.0
    assert sm.total_duration_sec == 12.0


def test_builder_drops_malformed_entries():
    raw = [
        {"start": 0.0, "end": 5.0},
        {"junk": True},
        None,
    ]
    sm = scene_map_from_detector_result(raw)  # type: ignore[arg-type]
    assert sm.shot_count() == 1


def test_builder_handles_empty_list():
    sm = scene_map_from_detector_result([])
    assert sm.is_empty()


def test_builder_handles_non_list_input():
    """Defensive — never raise on garbage."""
    sm = scene_map_from_detector_result("not a list")  # type: ignore[arg-type]
    assert sm.is_empty()


def test_to_public_dict_is_json_safe():
    sm = _three_shot_map()
    d = sm.to_public_dict()
    # Should round-trip through json.dumps without TypeError.
    json.dumps(d)


# ---------------------------------------------------------------------------
# SceneMap.slice — D-2-motion Phase 1 D1.2
# ---------------------------------------------------------------------------


def test_slice_empty_map_returns_empty():
    """The motion/crop.py caller treats `[]` as "no SceneMap available" and
    falls back to the legacy pixel-diff detector."""
    sm = SceneMap()
    assert sm.slice(0.0, 30.0) == []


def test_slice_full_overlap_returns_all_shots_clipped():
    sm = _three_shot_map()  # shots 0-10, 10-25, 25-60
    result = sm.slice(0.0, 60.0)
    assert result == [(0.0, 10.0), (10.0, 25.5), (25.5, 60.0)]


def test_slice_window_drops_out_of_range_shots():
    sm = _three_shot_map()
    # Window covers only the middle shot.
    result = sm.slice(11.0, 24.0)
    assert result == [(11.0, 24.0)]  # clipped to window edges


def test_slice_partial_overlap_clips_to_window_edges():
    sm = _three_shot_map()
    # Window straddles shot 0 (0-10) and shot 1 (10-25.5) partially.
    result = sm.slice(5.0, 15.0)
    assert result == [(5.0, 10.0), (10.0, 15.0)]


def test_slice_window_before_all_shots_returns_empty():
    sm = SceneMap(shots=[Shot(start=10.0, end=20.0)])
    assert sm.slice(0.0, 5.0) == []


def test_slice_window_after_all_shots_returns_empty():
    sm = SceneMap(shots=[Shot(start=10.0, end=20.0)])
    assert sm.slice(30.0, 40.0) == []


def test_slice_window_inside_single_shot():
    sm = SceneMap(shots=[Shot(start=0.0, end=100.0)])
    result = sm.slice(20.0, 80.0)
    assert result == [(20.0, 80.0)]


def test_slice_window_touches_boundary_excludes_zero_width():
    """If the window's start exactly equals a shot's end, no overlap → no entry.
    Prevents zero-duration ranges in the output."""
    sm = SceneMap(shots=[Shot(start=0.0, end=10.0), Shot(start=10.0, end=20.0)])
    # Window starts exactly at the first shot's end → only shot[1] qualifies.
    result = sm.slice(10.0, 20.0)
    assert result == [(10.0, 20.0)]


def test_slice_invalid_window_returns_empty():
    sm = _three_shot_map()
    # end <= start.
    assert sm.slice(20.0, 10.0) == []
    assert sm.slice(10.0, 10.0) == []


def test_slice_garbage_window_does_not_raise():
    sm = _three_shot_map()
    # Defensive — never raise on bad input.
    assert sm.slice("garbage", 10.0) == []  # type: ignore[arg-type]
    assert sm.slice(None, None) == []       # type: ignore[arg-type]
    assert sm.slice(0.0, "x") == []         # type: ignore[arg-type]


def test_slice_output_is_chronological_and_non_overlapping():
    sm = SceneMap(shots=[
        Shot(start=0.0, end=10.0),
        Shot(start=10.0, end=25.5),
        Shot(start=25.5, end=60.0),
    ])
    result = sm.slice(5.0, 30.0)
    # Verify ordering.
    for i in range(len(result) - 1):
        assert result[i][0] < result[i][1], f"non-monotonic range at index {i}"
        assert result[i][1] <= result[i + 1][0], f"overlap between {i} and {i+1}"


def test_slice_matches_pixel_diff_contract_shape():
    """Slice output must be drop-in compatible with
    ``_detect_scene_ranges_in_clip`` shape: list of (start, end) float tuples,
    chronological, non-overlapping, in source-global seconds."""
    sm = _three_shot_map()
    result = sm.slice(0.0, 60.0)
    assert isinstance(result, list)
    for entry in result:
        assert isinstance(entry, tuple) and len(entry) == 2
        assert isinstance(entry[0], float) and isinstance(entry[1], float)
        assert entry[1] > entry[0]


def test_slice_single_shot_window_returns_one_range():
    """A window that touches only one shot returns exactly one range."""
    sm = _three_shot_map()
    result = sm.slice(12.0, 20.0)
    assert len(result) == 1
    assert result[0] == (12.0, 20.0)


def test_slice_window_clip_preserves_shot_inside_when_short():
    """A short window contained entirely inside a long shot returns just
    that window (the whole window IS the scene from motion/crop.py's POV)."""
    sm = SceneMap(shots=[Shot(start=0.0, end=100.0)])
    result = sm.slice(40.0, 41.0)
    assert result == [(40.0, 41.0)]


def test_slice_negative_window_start_clamps_to_shot_start():
    """A negative window start is clamped against each shot's actual start —
    no shot starts before 0.0, so the leftmost shot's start wins."""
    sm = _three_shot_map()
    result = sm.slice(-10.0, 5.0)
    # Window [-10, 5] overlaps shot 0 (0, 10) → clipped to (0, 5).
    assert result == [(0.0, 5.0)]


def test_slice_zero_duration_inputs_handled_gracefully():
    sm = SceneMap(shots=[Shot(start=0.0, end=5.0)])
    # Equal-bound window → empty (invalid window).
    assert sm.slice(2.0, 2.0) == []


# ---------------------------------------------------------------------------
# Slice + nearest_boundary cross-check — invariant
# ---------------------------------------------------------------------------


def test_slice_results_align_with_nearest_boundary():
    """For each range in the slice output, the start/end should be either:
      - The window edge, OR
      - A shot boundary in the original map.
    This is the invariant motion/crop.py relies on for EMA state carry."""
    sm = _three_shot_map()
    start_sec, end_sec = 5.0, 30.0
    result = sm.slice(start_sec, end_sec)
    all_boundaries = {start_sec, end_sec}
    for shot in sm.shots:
        all_boundaries.add(shot.start)
        all_boundaries.add(shot.end)
    for r_start, r_end in result:
        assert r_start in all_boundaries, f"unexpected start {r_start}"
        assert r_end in all_boundaries, f"unexpected end {r_end}"
