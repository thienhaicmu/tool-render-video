"""Strategic-1b closure regression guard — Audit 2026-06-08 (Batch A V8-A12 follow-up).

Strategic-1 wired clip_lock / clip_exclude into the LLM prompt
(commit eecc95f). Strategic-1b adds the LOCAL-SIDE DEFENCE-IN-DEPTH:
after the LLM-derived scored list is built by
``_scored_from_render_plan``, the orchestrator runs the operator's
clip_lock / clip_exclude ranges through
``_apply_clip_lock_exclude_filter`` to:

  1. DROP any clip whose [start, end) overlaps any operator-supplied
     exclude range. Each drop emits a structured render event so
     operators can see why a clip disappeared.

  2. VERIFY each operator-supplied lock range is covered by at least
     one surviving clip. Uncovered locks emit a warning event so the
     FE can render a 'lock uncovered' badge.

The filter complements Strategic-1's prompt wiring — even if the LLM
ignores the HARD EXCLUDED RANGES instruction, the BE filter enforces
it locally. Trust but verify.

Helper behaviour (this file):
  - _ranges_overlap uses strict (half-open) endpoints so adjoining
    ranges don't count as overlap.
  - _coerce_range silently coerces or skips arbitrary dict entries.
  - _apply_clip_lock_exclude_filter is defensive — None / empty
    inputs collapse to no-op, malformed entries skip silently, any
    unexpected error returns the input list unchanged (Sacred
    Contract #3 spirit).
"""
from __future__ import annotations

from unittest.mock import patch

import pytest


# ---------------------------------------------------------------------------
# 1. _ranges_overlap — half-open interval semantics.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "a_start, a_end, b_start, b_end, expected",
    [
        # Clear overlap (left edge inside).
        (10.0, 30.0, 20.0, 40.0, True),
        # Clear overlap (B fully inside A).
        (10.0, 50.0, 20.0, 30.0, True),
        # Clear overlap (A fully inside B).
        (20.0, 30.0, 10.0, 50.0, True),
        # Touching at right edge (a_end == b_start) — NO overlap.
        (10.0, 20.0, 20.0, 30.0, False),
        # Touching at left edge (b_end == a_start) — NO overlap.
        (20.0, 30.0, 10.0, 20.0, False),
        # Disjoint with gap.
        (10.0, 20.0, 30.0, 40.0, False),
        # Equal ranges — overlap.
        (10.0, 20.0, 10.0, 20.0, True),
    ],
)
def test_ranges_overlap_half_open_semantics(a_start, a_end, b_start, b_end, expected):
    """The half-open semantic (touching edges DON'T overlap) matches
    the operator's intent: 'exclude [20s, 30s]' should NOT reject a
    clip [10s, 20s] that ends right at the exclude start."""
    from app.features.render.engine.pipeline.render_pipeline import _ranges_overlap
    assert _ranges_overlap(a_start, a_end, b_start, b_end) == expected


# ---------------------------------------------------------------------------
# 2. _coerce_range — defensive dict to tuple coercion.
# ---------------------------------------------------------------------------


def test_coerce_range_accepts_valid_dict():
    from app.features.render.engine.pipeline.render_pipeline import _coerce_range
    assert _coerce_range({"start_sec": 10.0, "end_sec": 20.0}) == (10.0, 20.0)


def test_coerce_range_accepts_numeric_strings():
    """Pydantic may pass floats from JSON as plain numbers; some
    stored payload blobs may carry strings. ``float()`` handles both."""
    from app.features.render.engine.pipeline.render_pipeline import _coerce_range
    assert _coerce_range({"start_sec": "10", "end_sec": "20"}) == (10.0, 20.0)


@pytest.mark.parametrize(
    "entry",
    [
        None,                                          # not a dict
        "garbage",                                     # string
        {"start_sec": "x", "end_sec": 5},              # non-numeric start
        {"start_sec": 10},                             # missing end
        {"end_sec": 20},                               # missing start
        {"start_sec": -5, "end_sec": 10},              # negative start
        {"start_sec": 10, "end_sec": 10},              # zero length
        {"start_sec": 20, "end_sec": 15},              # end < start
    ],
)
def test_coerce_range_skips_malformed(entry):
    """Each malformed entry returns None instead of raising. Sacred
    Contract #3 spirit applies."""
    from app.features.render.engine.pipeline.render_pipeline import _coerce_range
    assert _coerce_range(entry) is None


# ---------------------------------------------------------------------------
# 3. Exclude filter behaviour.
# ---------------------------------------------------------------------------


def _make_clip(start, end):
    """Minimal seg shape — only the fields the filter reads."""
    return {"start": float(start), "end": float(end), "duration": float(end - start)}


def test_filter_no_op_when_no_ranges():
    """The filter must be a no-op when neither lock nor exclude is
    supplied — the most common path (operator doesn't use UP26)."""
    from app.features.render.engine.pipeline.render_pipeline import _apply_clip_lock_exclude_filter
    scored = [_make_clip(0, 30), _make_clip(60, 90)]
    result = _apply_clip_lock_exclude_filter(scored, None, None)
    assert result is scored
    # The identity check above is the strongest guarantee — same
    # list object, not a copy.


def test_filter_no_op_when_scored_empty():
    """Empty scored list short-circuits — no filter work to do."""
    from app.features.render.engine.pipeline.render_pipeline import _apply_clip_lock_exclude_filter
    assert _apply_clip_lock_exclude_filter([], None, None) == []
    assert _apply_clip_lock_exclude_filter(
        [],
        clip_exclude=[{"start_sec": 0, "end_sec": 10}],
        clip_lock=[{"start_sec": 30, "end_sec": 40}],
    ) == []


def test_filter_drops_clips_overlapping_exclude_range():
    """Any clip whose [start, end) overlaps an exclude range MUST be
    dropped. Other clips are preserved."""
    from app.features.render.engine.pipeline.render_pipeline import _apply_clip_lock_exclude_filter
    scored = [
        _make_clip(0, 30),    # before exclude — kept
        _make_clip(40, 70),   # overlaps [50, 60] — DROPPED
        _make_clip(80, 110),  # after exclude — kept
    ]
    result = _apply_clip_lock_exclude_filter(
        scored,
        clip_lock=None,
        clip_exclude=[{"start_sec": 50, "end_sec": 60}],
    )
    assert [c["start"] for c in result] == [0.0, 80.0]


def test_filter_preserves_adjoining_clips():
    """A clip ending exactly where the exclude starts (touching but
    not overlapping) MUST be kept — operator's exclude range is
    half-open."""
    from app.features.render.engine.pipeline.render_pipeline import _apply_clip_lock_exclude_filter
    scored = [_make_clip(10, 30), _make_clip(40, 60)]
    result = _apply_clip_lock_exclude_filter(
        scored,
        clip_lock=None,
        clip_exclude=[{"start_sec": 30, "end_sec": 40}],
    )
    # Both clips touch the exclude but don't overlap — both kept.
    assert [c["start"] for c in result] == [10.0, 40.0]


def test_filter_drops_against_multiple_exclude_ranges():
    """Each clip must be checked against ALL exclude ranges; the
    first overlapping range is sufficient to drop."""
    from app.features.render.engine.pipeline.render_pipeline import _apply_clip_lock_exclude_filter
    scored = [
        _make_clip(0, 30),     # kept
        _make_clip(40, 70),    # overlaps [50, 60]
        _make_clip(100, 130),  # overlaps [110, 120]
        _make_clip(150, 180),  # kept
    ]
    result = _apply_clip_lock_exclude_filter(
        scored,
        clip_lock=None,
        clip_exclude=[
            {"start_sec": 50, "end_sec": 60},
            {"start_sec": 110, "end_sec": 120},
        ],
    )
    assert [c["start"] for c in result] == [0.0, 150.0]


def test_filter_silently_skips_malformed_exclude_entries():
    """Malformed exclude entries are silently dropped from the
    range list — they MUST not cause the entire filter to abort."""
    from app.features.render.engine.pipeline.render_pipeline import _apply_clip_lock_exclude_filter
    scored = [_make_clip(40, 70)]
    result = _apply_clip_lock_exclude_filter(
        scored,
        clip_lock=None,
        clip_exclude=[
            None,
            {"start_sec": -1, "end_sec": 5},      # negative — skipped
            {"start_sec": "x", "end_sec": 5},     # non-numeric — skipped
            {"start_sec": 50, "end_sec": 60},     # valid
        ],
    )
    # The clip [40, 70] overlaps [50, 60] — dropped.
    assert result == []


# ---------------------------------------------------------------------------
# 4. Lock-coverage warning behaviour.
# ---------------------------------------------------------------------------


def test_filter_emits_uncovered_lock_warning():
    """When no surviving clip overlaps a lock range, the filter
    emits a 'render.plan.lock_uncovered_warning' event so operators
    can see the gap."""
    from app.features.render.engine.pipeline import render_pipeline as rp

    scored = [_make_clip(0, 30)]
    events: list[dict] = []

    def _capture_event(**kw):
        events.append(kw)

    with patch.object(rp, "_emit_render_event", side_effect=_capture_event), \
         patch.object(rp, "_job_log"):
        result = rp._apply_clip_lock_exclude_filter(
            scored,
            clip_lock=[{"start_sec": 100, "end_sec": 150}],
            clip_exclude=None,
            channel_code="t-strategic-1b",
            job_id="job-s1b",
        )

    # Clip unchanged (lock is informational, doesn't drop clips).
    assert result == scored
    # Warning event emitted.
    lock_events = [e for e in events if e.get("event") == "render.plan.lock_uncovered_warning"]
    assert len(lock_events) == 1
    assert lock_events[0]["level"] == "WARNING"
    assert lock_events[0]["context"]["lock_start_sec"] == 100.0
    assert lock_events[0]["context"]["lock_end_sec"] == 150.0


def test_filter_skips_warning_when_lock_is_covered():
    """When at least one surviving clip overlaps the lock range, no
    warning fires."""
    from app.features.render.engine.pipeline import render_pipeline as rp

    scored = [_make_clip(0, 30), _make_clip(110, 140)]
    events: list[dict] = []

    def _capture_event(**kw):
        events.append(kw)

    with patch.object(rp, "_emit_render_event", side_effect=_capture_event), \
         patch.object(rp, "_job_log"):
        rp._apply_clip_lock_exclude_filter(
            scored,
            clip_lock=[{"start_sec": 100, "end_sec": 150}],
            clip_exclude=None,
            channel_code="t-strategic-1b",
            job_id="job-s1b",
        )

    lock_events = [e for e in events if e.get("event") == "render.plan.lock_uncovered_warning"]
    assert lock_events == []


def test_filter_lock_coverage_runs_against_post_exclude_clips():
    """The lock-coverage check MUST use the POST-EXCLUDE clip set,
    not the pre-filter list. If an exclude pass dropped the only
    clip that would have covered the lock, the lock is now
    uncovered and should warn."""
    from app.features.render.engine.pipeline import render_pipeline as rp

    # Clip [100, 150] would cover lock [120, 140] BUT also overlaps
    # exclude [130, 145] — it gets dropped first.
    scored = [_make_clip(0, 30), _make_clip(100, 150)]
    events: list[dict] = []

    def _capture_event(**kw):
        events.append(kw)

    with patch.object(rp, "_emit_render_event", side_effect=_capture_event), \
         patch.object(rp, "_job_log"):
        result = rp._apply_clip_lock_exclude_filter(
            scored,
            clip_lock=[{"start_sec": 120, "end_sec": 140}],
            clip_exclude=[{"start_sec": 130, "end_sec": 145}],
            channel_code="t-strategic-1b",
            job_id="job-s1b",
        )

    # Exclude dropped the lock-covering clip.
    assert [c["start"] for c in result] == [0.0]
    # Lock now uncovered — warning emitted.
    lock_events = [e for e in events if e.get("event") == "render.plan.lock_uncovered_warning"]
    assert len(lock_events) == 1


# ---------------------------------------------------------------------------
# 5. Defence-in-depth — filter never raises.
# ---------------------------------------------------------------------------


def test_filter_does_not_raise_on_unexpected_scored_shape():
    """If a future refactor changes scored entries to not be dicts,
    the filter must NOT propagate the exception into the render
    pipeline. Sacred Contract #3 spirit applies."""
    from app.features.render.engine.pipeline.render_pipeline import _apply_clip_lock_exclude_filter
    # Scored entries are strings — the for-loop will hit AttributeError
    # on .get(). The outer try/except in the filter catches and
    # returns the input unchanged.
    bad_scored = ["clip-1", "clip-2"]
    result = _apply_clip_lock_exclude_filter(
        bad_scored,
        clip_lock=None,
        clip_exclude=[{"start_sec": 0, "end_sec": 10}],
    )
    assert result is bad_scored


# ---------------------------------------------------------------------------
# 6. Orchestrator wiring — source-level guard.
# ---------------------------------------------------------------------------


def test_render_pipeline_calls_filter_after_scored_derivation():
    """A refactor that drops the
    ``_apply_clip_lock_exclude_filter`` call from render_pipeline.py
    reverts Strategic-1b — the prompt still has the LLM-facing
    sections (Strategic-1) but the BE no longer enforces the rules
    locally. The filter is the trust-but-verify counterpart."""
    from pathlib import Path
    import re

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "pipeline" / "render_pipeline.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    assert re.search(
        r"_apply_clip_lock_exclude_filter\(\s*scored\s*,",
        source,
    ), (
        "Strategic-1b regression — render_pipeline.py no longer calls "
        "_apply_clip_lock_exclude_filter after _scored_from_render_plan. "
        "The local enforcement disappears even though the LLM prompt "
        "still has the lock/exclude sections."
    )
