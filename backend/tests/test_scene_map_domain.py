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
