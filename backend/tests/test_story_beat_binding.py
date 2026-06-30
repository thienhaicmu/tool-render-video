"""Architecture-review Batch B (2026-06-30) — StoryBeat ↔ RecapScene binding.

Pins the v3 ``StoryBeat.bound_scene_index`` contract and the deterministic
post-Pass-3 reconciler ``RecapPlan.bind_story_beats_to_scenes()``.

Contract:
  1. ``StoryBeat.bound_scene_index`` is additive — defaults to ``-1`` (unbound).
  2. ``STORY_SCHEMA_VERSION`` bumps to 3 but v2 blobs (no field) load fine.
  3. Reconciler binds a beat to scene ``i`` iff ``scene.start <= beat.t <= scene.end``.
  4. Anchored-but-out-of-range beats stay at ``-1`` — pass-3 omitted that region.
  5. Unanchored beats (``t < 0``) stay at ``-1``.
  6. Reconciler is idempotent: a second call on an already-bound plan returns 0.
  7. Reconciler is defensive: any internal failure returns 0 (Sacred Contract #3 spirit).
  8. Helpers: ``is_bound``, ``bound_count``, ``unbound_count``, ``coverage_pct``.
  9. JSON round-trip preserves ``bound_scene_index`` and ``schema_version=3``.
"""
from __future__ import annotations

import json

import pytest

from app.domain.recap_plan import (
    STORY_SCHEMA_VERSION,
    Act,
    Episode,
    RecapPlan,
    RecapScene,
    StoryBeat,
    StoryModel,
)


# ---------------------------------------------------------------------------
# Schema additivity
# ---------------------------------------------------------------------------


def test_story_schema_version_bumped_to_3():
    assert STORY_SCHEMA_VERSION == 3


def test_storybeat_default_unbound():
    b = StoryBeat(text="setup")
    assert b.bound_scene_index == -1
    assert b.is_bound is False


def test_storybeat_constructed_bound():
    b = StoryBeat(text="climax", t=120.0, bound_scene_index=2)
    assert b.is_bound is True
    assert b.bound_scene_index == 2


# ---------------------------------------------------------------------------
# Back-compat — v2 (no bound_scene_index) blobs load fine
# ---------------------------------------------------------------------------


def test_v2_blob_loads_with_default_unbound():
    """A v2 persisted blob (pre-Batch-B) carries no bound_scene_index. The
    parser must default it to -1 without raising."""
    v2_payload = json.dumps({
        "schema_version": 4,
        "story": {
            "schema_version": 2,
            "summary": "a film about coffee",
            "beats": [
                {"text": "inciting", "t": 15.0, "kind": "setup"},
                {"text": "climax", "t": 120.0, "kind": "climax"},
            ],
        },
        "episodes": [],
    })
    plan = RecapPlan.from_json(v2_payload)
    assert plan is not None
    assert len(plan.story.beats) == 2
    for b in plan.story.beats:
        assert b.bound_scene_index == -1
        assert b.is_bound is False


def test_v3_blob_loads_with_explicit_index():
    v3_payload = json.dumps({
        "schema_version": 4,
        "story": {
            "schema_version": 3,
            "beats": [
                {"text": "setup", "t": 10.0, "bound_scene_index": 0},
                {"text": "climax", "t": 120.0, "bound_scene_index": 2},
            ],
        },
        "episodes": [],
    })
    plan = RecapPlan.from_json(v3_payload)
    assert plan is not None
    assert plan.story.beats[0].bound_scene_index == 0
    assert plan.story.beats[1].bound_scene_index == 2


def test_malformed_index_falls_back_to_unbound():
    """A garbage bound_scene_index value must NOT raise (parser is defensive)."""
    payload = json.dumps({
        "story": {
            "beats": [{"text": "x", "t": 10.0, "bound_scene_index": "garbage"}],
        },
    })
    plan = RecapPlan.from_json(payload)
    assert plan is not None
    assert plan.story.beats[0].bound_scene_index == -1


# ---------------------------------------------------------------------------
# Reconciler — bind_story_beats_to_scenes
# ---------------------------------------------------------------------------


def _three_scene_plan(beats: list[StoryBeat]) -> RecapPlan:
    return RecapPlan(
        story=StoryModel(beats=list(beats)),
        episodes=[Episode(title="ep", acts=[Act(title="a", scenes=[
            RecapScene(start=0.0, end=30.0),
            RecapScene(start=60.0, end=90.0),
            RecapScene(start=120.0, end=150.0),
        ])])],
    )


def test_reconciler_binds_in_range_beats():
    plan = _three_scene_plan([
        StoryBeat(text="opening", t=15.0),
        StoryBeat(text="midpoint", t=75.0),
        StoryBeat(text="finale", t=135.0),
    ])
    plan.bind_story_beats_to_scenes()
    assert [b.bound_scene_index for b in plan.story.beats] == [0, 1, 2]


def test_reconciler_leaves_unanchored_beats_unbound():
    plan = _three_scene_plan([
        StoryBeat(text="anchored", t=15.0),
        StoryBeat(text="unanchored", t=-1.0),
    ])
    plan.bind_story_beats_to_scenes()
    assert plan.story.beats[0].bound_scene_index == 0
    assert plan.story.beats[1].bound_scene_index == -1


def test_reconciler_leaves_out_of_range_beats_unbound():
    """Anchor at t=45 falls in the GAP between scenes 0 (0-30) and 1 (60-90)."""
    plan = _three_scene_plan([StoryBeat(text="in-gap", t=45.0)])
    plan.bind_story_beats_to_scenes()
    assert plan.story.beats[0].bound_scene_index == -1


def test_reconciler_handles_anchor_past_last_scene():
    plan = _three_scene_plan([StoryBeat(text="overflow", t=999.0)])
    plan.bind_story_beats_to_scenes()
    assert plan.story.beats[0].bound_scene_index == -1


def test_reconciler_returns_count_of_changes():
    """First call binds all in-range beats. Second call should be a no-op."""
    plan = _three_scene_plan([
        StoryBeat(text="a", t=15.0),
        StoryBeat(text="b", t=75.0),
    ])
    changes_first = plan.bind_story_beats_to_scenes()
    assert changes_first == 2
    changes_second = plan.bind_story_beats_to_scenes()
    assert changes_second == 0


def test_reconciler_resets_stale_binding_when_anchor_drifts_out():
    """If a previously-bound beat's anchor no longer falls in any scene, it
    must be unbound — stale persisted indices must not survive."""
    plan = _three_scene_plan([StoryBeat(text="stale", t=200.0, bound_scene_index=1)])
    plan.bind_story_beats_to_scenes()
    assert plan.story.beats[0].bound_scene_index == -1


def test_reconciler_handles_empty_beats():
    plan = _three_scene_plan([])
    assert plan.bind_story_beats_to_scenes() == 0


def test_reconciler_handles_empty_scenes():
    """A model with beats but no selected scenes must reset every binding and
    return 0 freshly-bound."""
    plan = RecapPlan(
        story=StoryModel(beats=[StoryBeat(text="x", t=10.0, bound_scene_index=5)]),
        episodes=[],
    )
    plan.bind_story_beats_to_scenes()
    assert plan.story.beats[0].bound_scene_index == -1


# ---------------------------------------------------------------------------
# Coverage helpers
# ---------------------------------------------------------------------------


def test_bound_count_and_unbound_count_after_reconcile():
    plan = _three_scene_plan([
        StoryBeat(text="in", t=15.0),
        StoryBeat(text="in", t=75.0),
        StoryBeat(text="unanchored", t=-1.0),
        StoryBeat(text="gap", t=45.0),
    ])
    plan.bind_story_beats_to_scenes()
    assert plan.story.bound_count() == 2
    assert plan.story.unbound_count() == 2


def test_coverage_pct_on_empty_model_is_zero():
    sm = StoryModel()
    assert sm.coverage_pct() == 0.0


def test_coverage_pct_after_reconcile():
    plan = _three_scene_plan([
        StoryBeat(text="hit", t=15.0),
        StoryBeat(text="miss", t=45.0),
    ])
    plan.bind_story_beats_to_scenes()
    assert plan.story.coverage_pct() == 0.5


def test_coverage_pct_unbound_when_never_reconciled():
    """A v2-loaded story (no reconciler run yet) reports 0.0 — the diagnostic
    surface honestly says 'nothing has been bound yet'."""
    sm = StoryModel(beats=[StoryBeat(text="x", t=10.0)])
    assert sm.coverage_pct() == 0.0


# ---------------------------------------------------------------------------
# JSON round-trip
# ---------------------------------------------------------------------------


def test_round_trip_preserves_bound_scene_index():
    plan = _three_scene_plan([StoryBeat(text="x", t=15.0)])
    plan.bind_story_beats_to_scenes()
    raw = plan.to_json()
    plan2 = RecapPlan.from_json(raw)
    assert plan2 is not None
    assert plan2.story.beats[0].bound_scene_index == 0
    assert plan2.story.schema_version == STORY_SCHEMA_VERSION
