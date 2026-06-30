"""Architecture-review Batch D-2-snap (2026-06-30) — RecapPlan.snap_scenes_to_shots.

Pins the deterministic snap-to-shot reconciler that consumes the SceneMap
produced by the D-2-thin scene_map_stage.

Contract:
  1. ``scene_map`` None / empty → returns 0, no mutation.
  2. In-tolerance start and/or end → snapped to the nearest shot boundary.
  3. Out-of-tolerance boundaries → preserved.
  4. Asymmetric: one boundary in-tolerance, the other not → only the
     in-tolerance one snaps.
  5. Post-snap inversion (end <= start) → REJECTED, scene preserved.
  6. Idempotent: second call returns 0 (already at boundary).
  7. JSON round-trip preserves snapped values.
  8. Defensive: garbage tolerance falls back to default 0.5.
"""
from __future__ import annotations

import json

import pytest

from app.domain.recap_plan import (
    Act,
    Episode,
    RecapPlan,
    RecapScene,
)
from app.domain.scene_map import SceneMap, Shot


def _plan_with_scenes(scenes: list[RecapScene]) -> RecapPlan:
    return RecapPlan(
        episodes=[Episode(title="", acts=[Act(title="", scenes=list(scenes))])],
    )


def _three_shot_map() -> SceneMap:
    return SceneMap(
        shots=[
            Shot(start=0.0, end=10.0),
            Shot(start=10.0, end=25.0),
            Shot(start=25.0, end=60.0),
        ],
        source_fps=30.0,
        total_duration_sec=60.0,
    )


# ---------------------------------------------------------------------------
# Empty / None inputs
# ---------------------------------------------------------------------------


def test_none_scene_map_is_noop():
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])
    assert plan.snap_scenes_to_shots(None) == 0
    assert plan.scenes()[0].start == 0.3
    assert plan.scenes()[0].end == 9.7


def test_empty_scene_map_is_noop():
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])
    assert plan.snap_scenes_to_shots(SceneMap()) == 0
    assert plan.scenes()[0].start == 0.3


def test_empty_plan_is_noop():
    plan = RecapPlan()
    assert plan.snap_scenes_to_shots(_three_shot_map()) == 0


# ---------------------------------------------------------------------------
# In-tolerance snaps
# ---------------------------------------------------------------------------


def test_both_boundaries_in_tolerance_snap():
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=0.5)
    assert snaps == 2  # start + end
    assert plan.scenes()[0].start == 0.0
    assert plan.scenes()[0].end == 10.0


def test_multiple_scenes_each_snap_independently():
    plan = _plan_with_scenes([
        RecapScene(start=0.3, end=9.8),    # both in tolerance
        RecapScene(start=10.4, end=24.7),  # both in tolerance
    ])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=0.5)
    assert snaps == 4
    assert plan.scenes()[0].start == 0.0 and plan.scenes()[0].end == 10.0
    assert plan.scenes()[1].start == 10.0 and plan.scenes()[1].end == 25.0


# ---------------------------------------------------------------------------
# Out-of-tolerance preservation
# ---------------------------------------------------------------------------


def test_out_of_tolerance_boundaries_preserved():
    """Scene at (30.0, 50.0) — nearest shot boundary is 25.0 (5s away) or
    60.0 (10s away). Both out of 0.5s tolerance → no snap."""
    plan = _plan_with_scenes([RecapScene(start=30.0, end=50.0)])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=0.5)
    assert snaps == 0
    assert plan.scenes()[0].start == 30.0 and plan.scenes()[0].end == 50.0


def test_asymmetric_one_boundary_snaps_other_preserved():
    """start in tolerance, end out of tolerance."""
    plan = _plan_with_scenes([RecapScene(start=0.3, end=50.0)])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=0.5)
    assert snaps == 1
    assert plan.scenes()[0].start == 0.0
    assert plan.scenes()[0].end == 50.0  # unchanged


def test_tolerance_zero_means_only_exact_boundaries_snap():
    """Zero tolerance: only scenes already AT shot boundaries 'snap' (no-op);
    everything else is preserved."""
    plan = _plan_with_scenes([
        RecapScene(start=0.0, end=10.0),   # already at boundaries — no change
        RecapScene(start=0.3, end=9.7),    # off by 0.3 — exceeds 0
    ])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=0.0)
    assert snaps == 0
    assert plan.scenes()[0].start == 0.0  # already aligned
    assert plan.scenes()[1].start == 0.3  # preserved


def test_custom_larger_tolerance_snaps_further_boundaries():
    """With tolerance=5.0, a scene 4s off a boundary should snap."""
    plan = _plan_with_scenes([RecapScene(start=4.0, end=14.0)])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=5.0)
    # start=4.0 → nearest is 0.0 OR 10.0 (both 4s away). Implementation picks
    # the first found in iteration order → 0.0. end=14.0 → nearest is 10.0
    # (4s) vs 25.0 (11s) → 10.0. But then 0.0..10.0 is valid → snap applies.
    assert snaps >= 1
    assert plan.scenes()[0].start in (0.0, 10.0)
    assert plan.scenes()[0].end in (10.0, 25.0)


# ---------------------------------------------------------------------------
# Post-snap inversion guard
# ---------------------------------------------------------------------------


def test_post_snap_inversion_rejects_snap_and_preserves_scene():
    """A scene at (9.8, 10.2) — both in 0.5 tolerance of 10.0. Naive snap
    would collapse both to 10.0 → end <= start → MUST be rejected.
    The scene reverts to its original timestamps."""
    plan = _plan_with_scenes([RecapScene(start=9.8, end=10.2)])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=0.5)
    assert snaps == 0
    assert plan.scenes()[0].start == 9.8
    assert plan.scenes()[0].end == 10.2


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_second_call_is_noop_after_alignment():
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])
    sm = _three_shot_map()
    first = plan.snap_scenes_to_shots(sm, tolerance_sec=0.5)
    assert first == 2
    second = plan.snap_scenes_to_shots(sm, tolerance_sec=0.5)
    assert second == 0
    # Values unchanged.
    assert plan.scenes()[0].start == 0.0 and plan.scenes()[0].end == 10.0


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_round_trip_preserves_snapped_values():
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])
    plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=0.5)
    raw = plan.to_json()
    restored = RecapPlan.from_json(raw)
    assert restored is not None
    assert restored.scenes()[0].start == 0.0
    assert restored.scenes()[0].end == 10.0


# ---------------------------------------------------------------------------
# Defensive — never raises
# ---------------------------------------------------------------------------


def test_garbage_tolerance_falls_back_to_default():
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])
    # str / None / NaN tolerance → should be treated as default 0.5
    assert plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec="garbage") == 2  # type: ignore[arg-type]


def test_negative_tolerance_clamps_to_zero():
    """A negative tolerance is meaningless — treated as 0.0 (no snap unless
    already at boundary)."""
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=-1.0)
    assert snaps == 0


def test_scene_map_without_nearest_boundary_does_not_raise():
    """Defensive — if a future caller passes a non-SceneMap duck type with
    no ``is_empty`` AND a broken ``nearest_boundary``, the method must
    not propagate the exception."""
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])

    class _BrokenMap:
        def nearest_boundary(self, t):
            raise RuntimeError("broken")

    snaps = plan.snap_scenes_to_shots(_BrokenMap())
    # No mutation, no raise.
    assert snaps == 0
    assert plan.scenes()[0].start == 0.3


def test_scene_map_none_returns_zero_not_raise():
    plan = _plan_with_scenes([RecapScene(start=0.3, end=9.7)])
    assert plan.snap_scenes_to_shots(None) == 0


# ---------------------------------------------------------------------------
# Real-world shape: snap preserves the other scenes when only one matches
# ---------------------------------------------------------------------------


def test_partial_snap_preserves_other_scenes():
    """One scene snaps, the others outside tolerance → only one mutates."""
    plan = _plan_with_scenes([
        RecapScene(start=0.3, end=9.8),    # snaps
        RecapScene(start=40.0, end=55.0),  # out of tolerance
    ])
    snaps = plan.snap_scenes_to_shots(_three_shot_map(), tolerance_sec=0.5)
    assert snaps == 2  # the first scene's start + end
    assert plan.scenes()[0].start == 0.0 and plan.scenes()[0].end == 10.0
    assert plan.scenes()[1].start == 40.0 and plan.scenes()[1].end == 55.0
