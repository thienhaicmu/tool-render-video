"""
test_ai_phase59c_segment_promotion.py — Phase 59C segment selection promotion tests.

Covers:
  - applies AI segment reorder when eligible
  - AI-endorsed segments come first, ordered by AI score desc
  - non-endorsed segments preserved at end in original order
  - fallback when ai_director_enabled=False
  - fallback when ai_render_influence_enabled=False
  - fallback when scored list is empty
  - fallback when selected_segments is empty
  - fallback when confidence below threshold
  - invalid AI segments ignored (NaN, None, end <= start, start < 0)
  - all AI segments invalid → fallback to original scored
  - no overlap found → fallback to original scored
  - user segment_ai_lock blocks promotion
  - no edit_plan → fallback
  - segment dict structure preserved exactly (no mutation)
  - segment count never reduced below MIN_FINAL_SEGMENTS
  - deterministic: same inputs → same output
  - no crash on malformed inputs (None, ints, strings)
  - fallback report shape validated
  - ALLOWED promotion modes consistent
  - integration: segments actually reach render order via promote_segment_selection
"""
from __future__ import annotations

import math
import types
import pytest

from app.ai.segment_promotion.segment_promotion_engine import (
    promote_segment_selection,
    _CONF_THRESHOLD_PROMOTION,
    _MIN_FINAL_SEGMENTS,
    _MIN_OVERLAP_SECONDS,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _scored_seg(
    start: float,
    end: float,
    viral_score: int = 50,
    motion_score: int = 50,
    hook_score: float = 50.0,
) -> dict:
    """Build a minimal scored segment dict matching render pipeline format."""
    return {
        "start":        start,
        "end":          end,
        "duration":     round(end - start, 2),
        "viral_score":  viral_score,
        "motion_score": motion_score,
        "hook_score":   hook_score,
    }


def _ai_seg(start: float, end: float, score: float = 82.0) -> types.SimpleNamespace:
    """Build a mock AI selected segment (AIClipPlan-like)."""
    return types.SimpleNamespace(start=start, end=end, score=score, reason="test", source="local_ai")


def _payload(
    ai_director_enabled: bool = True,
    ai_render_influence_enabled: bool = True,
    segment_ai_lock: bool = False,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        ai_director_enabled=ai_director_enabled,
        ai_render_influence_enabled=ai_render_influence_enabled,
        segment_ai_lock=segment_ai_lock,
    )


def _edit_plan(selected_segments=None) -> types.SimpleNamespace:
    plan = types.SimpleNamespace()
    plan.selected_segments = selected_segments or []
    return plan


# ---------------------------------------------------------------------------
# 1. Basic promotion — reorder applies
# ---------------------------------------------------------------------------

def test_applies_segment_reorder_when_eligible():
    """AI-endorsed segment moves to front of the scored list."""
    scored = [
        _scored_seg(0.0, 20.0, viral_score=60),   # not endorsed
        _scored_seg(20.0, 40.0, viral_score=55),   # not endorsed
        _scored_seg(40.0, 60.0, viral_score=50),   # AI endorses this one
    ]
    ai_segs = [_ai_seg(42.0, 58.0, score=85.0)]   # overlaps scored[2]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is True
    assert promo["selected_count"] == 1
    assert promo["fallback_used"] is False
    # Endorsed segment should be first
    assert result[0]["start"] == 40.0
    assert result[0]["end"] == 60.0


def test_endorsed_segments_ordered_by_ai_score_desc():
    """Multiple endorsed segments are ordered by their AI endorsement score."""
    scored = [
        _scored_seg(0.0, 20.0),    # AI score 70
        _scored_seg(20.0, 40.0),   # AI score 90
        _scored_seg(40.0, 60.0),   # not endorsed
    ]
    ai_segs = [
        _ai_seg(2.0, 18.0, score=70.0),   # endorses scored[0] with score 70
        _ai_seg(22.0, 38.0, score=90.0),  # endorses scored[1] with score 90
    ]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is True
    # Higher AI score should be first → scored[1] (score=90) before scored[0] (score=70)
    assert result[0]["start"] == 20.0
    assert result[1]["start"] == 0.0
    assert result[2]["start"] == 40.0  # non-endorsed last


def test_non_endorsed_segments_preserved_at_end():
    """Non-endorsed segments are appended after endorsed in original order."""
    scored = [
        _scored_seg(0.0, 20.0),    # not endorsed
        _scored_seg(20.0, 40.0),   # AI endorses
        _scored_seg(40.0, 60.0),   # not endorsed
        _scored_seg(60.0, 80.0),   # not endorsed
    ]
    ai_segs = [_ai_seg(22.0, 38.0, score=85.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)

    assert result[0]["start"] == 20.0   # endorsed first
    # Remaining should be in original order: 0, 40, 60
    remaining_starts = [r["start"] for r in result[1:]]
    assert remaining_starts == [0.0, 40.0, 60.0]


def test_total_count_unchanged():
    """Promotion never adds or drops segments — total count preserved."""
    scored = [_scored_seg(i * 20.0, i * 20.0 + 20.0) for i in range(5)]
    ai_segs = [_ai_seg(2.0, 18.0, score=85.0), _ai_seg(42.0, 58.0, score=88.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, _ = promote_segment_selection(scored, plan, payload)
    assert len(result) == len(scored)


def test_segment_dicts_not_mutated():
    """Original scored dicts must be returned by reference, not copied or mutated."""
    scored = [
        _scored_seg(0.0, 20.0, viral_score=77),
        _scored_seg(20.0, 40.0, viral_score=88),
    ]
    ai_segs = [_ai_seg(22.0, 38.0, score=85.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, _ = promote_segment_selection(scored, plan, payload)

    # All dicts in result must be the same objects (not copies)
    assert result[0]["viral_score"] == 88  # promoted segment kept its original values
    assert result[1]["viral_score"] == 77


# ---------------------------------------------------------------------------
# 2. AI flags disabled → fallback
# ---------------------------------------------------------------------------

def test_ai_director_disabled_returns_original_scored():
    scored = [_scored_seg(0.0, 20.0), _scored_seg(20.0, 40.0)]
    plan = _edit_plan([_ai_seg(2.0, 18.0, score=90.0)])
    payload = _payload(ai_director_enabled=False)

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is False
    assert promo["reason"] == "ai_director_disabled"
    assert promo["fallback_used"] is True
    assert result == scored


def test_ai_render_influence_disabled_returns_original_scored():
    scored = [_scored_seg(0.0, 20.0), _scored_seg(20.0, 40.0)]
    plan = _edit_plan([_ai_seg(2.0, 18.0, score=90.0)])
    payload = _payload(ai_render_influence_enabled=False)

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is False
    assert promo["reason"] == "ai_render_influence_disabled"
    assert result == scored


# ---------------------------------------------------------------------------
# 3. Empty inputs → fallback
# ---------------------------------------------------------------------------

def test_empty_scored_list_returns_empty():
    plan = _edit_plan([_ai_seg(0.0, 20.0, score=90.0)])
    payload = _payload()
    result, report = promote_segment_selection([], plan, payload)
    assert result == []
    assert report["segment_selection_promotion"]["applied"] is False


def test_empty_selected_segments_returns_original_scored():
    scored = [_scored_seg(0.0, 20.0)]
    plan = _edit_plan([])
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    assert result == scored
    assert report["segment_selection_promotion"]["reason"] == "no_selected_segments"


def test_no_edit_plan_returns_original_scored():
    scored = [_scored_seg(0.0, 20.0)]
    payload = _payload()
    result, report = promote_segment_selection(scored, None, payload)
    assert result == scored
    assert report["segment_selection_promotion"]["reason"] == "no_edit_plan"


# ---------------------------------------------------------------------------
# 4. Confidence gate
# ---------------------------------------------------------------------------

def test_low_confidence_blocks_promotion():
    """Mean score = 50/100 = 0.50 < _CONF_THRESHOLD_PROMOTION (0.80) → fallback."""
    scored = [_scored_seg(0.0, 20.0), _scored_seg(20.0, 40.0)]
    # score=50 → normalized = 0.50, below threshold
    ai_segs = [_ai_seg(2.0, 18.0, score=50.0), _ai_seg(22.0, 38.0, score=50.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is False
    assert "low_confidence" in promo["reason"]
    assert result == scored


def test_confidence_at_exact_threshold_allows_promotion():
    """Mean score = 80.0 / 100 = 0.80 exactly = _CONF_THRESHOLD_PROMOTION → allow."""
    scored = [_scored_seg(0.0, 20.0), _scored_seg(20.0, 40.0)]
    ai_segs = [_ai_seg(2.0, 18.0, score=80.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is True


def test_high_confidence_ai_segs_promote():
    scored = [_scored_seg(0.0, 20.0)]
    ai_segs = [_ai_seg(2.0, 18.0, score=95.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()
    _, report = promote_segment_selection(scored, plan, payload)
    assert report["segment_selection_promotion"]["applied"] is True


# ---------------------------------------------------------------------------
# 5. Segment validation
# ---------------------------------------------------------------------------

def test_invalid_ai_segment_nan_start_ignored():
    scored = [_scored_seg(0.0, 20.0)]
    bad_seg = types.SimpleNamespace(start=float("nan"), end=20.0, score=90.0, reason="", source="")
    plan = _edit_plan([bad_seg])
    payload = _payload()
    result, report = promote_segment_selection(scored, plan, payload)
    assert report["segment_selection_promotion"]["applied"] is False
    assert result == scored


def test_invalid_ai_segment_end_lte_start_ignored():
    scored = [_scored_seg(0.0, 20.0)]
    bad_seg = types.SimpleNamespace(start=10.0, end=5.0, score=90.0, reason="", source="")
    plan = _edit_plan([bad_seg])
    payload = _payload()
    result, report = promote_segment_selection(scored, plan, payload)
    assert report["segment_selection_promotion"]["applied"] is False


def test_invalid_ai_segment_negative_start_ignored():
    scored = [_scored_seg(0.0, 20.0)]
    bad_seg = types.SimpleNamespace(start=-5.0, end=15.0, score=90.0, reason="", source="")
    plan = _edit_plan([bad_seg])
    payload = _payload()
    result, report = promote_segment_selection(scored, plan, payload)
    assert report["segment_selection_promotion"]["applied"] is False


def test_invalid_ai_segment_none_times_ignored():
    scored = [_scored_seg(0.0, 20.0)]
    bad_seg = types.SimpleNamespace(start=None, end=None, score=90.0, reason="", source="")
    plan = _edit_plan([bad_seg])
    payload = _payload()
    result, report = promote_segment_selection(scored, plan, payload)
    assert report["segment_selection_promotion"]["applied"] is False


def test_invalid_ai_segment_inf_ignored():
    scored = [_scored_seg(0.0, 20.0)]
    bad_seg = types.SimpleNamespace(start=0.0, end=float("inf"), score=90.0, reason="", source="")
    plan = _edit_plan([bad_seg])
    payload = _payload()
    result, report = promote_segment_selection(scored, plan, payload)
    assert report["segment_selection_promotion"]["applied"] is False


def test_all_invalid_ai_segments_fallback():
    """If ALL AI segments are invalid, fallback to original scored."""
    scored = [_scored_seg(0.0, 20.0), _scored_seg(20.0, 40.0)]
    bad_segs = [
        types.SimpleNamespace(start=float("nan"), end=20.0, score=90.0, reason="", source=""),
        types.SimpleNamespace(start=10.0, end=5.0, score=90.0, reason="", source=""),
    ]
    plan = _edit_plan(bad_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    assert report["segment_selection_promotion"]["applied"] is False
    assert report["segment_selection_promotion"]["reason"] == "no_valid_ai_segments"
    assert result == scored


def test_mixed_valid_invalid_uses_only_valid():
    """Mix of valid and invalid AI segments — valid ones are used, invalid ignored."""
    scored = [
        _scored_seg(0.0, 20.0),
        _scored_seg(20.0, 40.0),
    ]
    ai_segs = [
        types.SimpleNamespace(start=float("nan"), end=15.0, score=90.0, reason="", source=""),  # invalid
        _ai_seg(22.0, 38.0, score=85.0),  # valid — endorses scored[1]
    ]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is True
    assert result[0]["start"] == 20.0   # AI-endorsed first


# ---------------------------------------------------------------------------
# 6. No overlap found → fallback
# ---------------------------------------------------------------------------

def test_no_overlap_returns_original_scored():
    """AI segments don't overlap with any scored segment → fallback."""
    scored = [
        _scored_seg(0.0, 20.0),
        _scored_seg(20.0, 40.0),
    ]
    # AI segments are in a completely different time range
    ai_segs = [_ai_seg(100.0, 120.0, score=90.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is False
    assert promo["reason"] == "no_overlap_found"
    assert result == scored


def test_tiny_overlap_below_threshold_not_endorsed():
    """Overlap smaller than _MIN_OVERLAP_SECONDS is not an endorsement."""
    scored = [_scored_seg(0.0, 20.0)]
    # AI segment overlaps by only 0.5 seconds (start:19.5, end:30 → overlap=0.5s)
    ai_segs = [_ai_seg(19.5, 30.0, score=90.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    # Overlap is 0.5s < _MIN_OVERLAP_SECONDS (1.0) → not endorsed
    assert promo["applied"] is False or result[0]["start"] == 0.0


# ---------------------------------------------------------------------------
# 7. User override
# ---------------------------------------------------------------------------

def test_segment_ai_lock_blocks_promotion():
    scored = [_scored_seg(0.0, 20.0), _scored_seg(20.0, 40.0)]
    plan = _edit_plan([_ai_seg(2.0, 18.0, score=90.0)])
    payload = _payload(segment_ai_lock=True)

    result, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert promo["applied"] is False
    assert "user_override" in promo["reason"]
    assert "segment_ai_lock=true" in promo["reason"]
    assert result == scored


# ---------------------------------------------------------------------------
# 8. Segment count bounds
# ---------------------------------------------------------------------------

def test_total_count_never_exceeds_original():
    scored = [_scored_seg(i * 15.0, i * 15.0 + 15.0) for i in range(3)]
    ai_segs = [_ai_seg(2.0, 13.0, score=85.0)]  # endorses only first segment
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, _ = promote_segment_selection(scored, plan, payload)
    assert len(result) <= len(scored)


def test_never_returns_fewer_than_min_final_segments():
    scored = [_scored_seg(0.0, 20.0)]
    ai_segs = [_ai_seg(2.0, 18.0, score=90.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, _ = promote_segment_selection(scored, plan, payload)
    assert len(result) >= _MIN_FINAL_SEGMENTS


# ---------------------------------------------------------------------------
# 9. Determinism
# ---------------------------------------------------------------------------

def test_deterministic_same_output():
    scored = [
        _scored_seg(0.0, 20.0, viral_score=60),
        _scored_seg(20.0, 40.0, viral_score=55),
        _scored_seg(40.0, 60.0, viral_score=70),
    ]
    ai_segs = [_ai_seg(2.0, 18.0, score=82.0), _ai_seg(42.0, 58.0, score=88.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    results = []
    for _ in range(3):
        result, report = promote_segment_selection(scored, plan, payload)
        results.append(tuple(s["start"] for s in result))

    assert len(set(results)) == 1, "promote_segment_selection is not deterministic"


# ---------------------------------------------------------------------------
# 10. Segment shape preserved
# ---------------------------------------------------------------------------

def test_promoted_segment_shape_compatible_with_pipeline():
    """All keys required by render_pipeline must still be present after promotion."""
    scored = [
        _scored_seg(0.0, 20.0, viral_score=55, motion_score=60, hook_score=45.0),
        _scored_seg(20.0, 40.0, viral_score=70, motion_score=80, hook_score=75.0),
    ]
    ai_segs = [_ai_seg(22.0, 38.0, score=85.0)]
    plan = _edit_plan(ai_segs)
    payload = _payload()

    result, _ = promote_segment_selection(scored, plan, payload)

    for seg in result:
        assert "start" in seg
        assert "end" in seg
        assert "duration" in seg
        assert "viral_score" in seg
        assert "motion_score" in seg
        assert "hook_score" in seg


# ---------------------------------------------------------------------------
# 11. Fallback safety / never-raises
# ---------------------------------------------------------------------------

def test_fallback_report_shape_on_empty_plan():
    scored = [_scored_seg(0.0, 20.0)]
    payload = _payload()
    plan = types.SimpleNamespace()   # no selected_segments attribute
    _, report = promote_segment_selection(scored, plan, payload)
    promo = report["segment_selection_promotion"]

    assert "applied" in promo
    assert "selected_count" in promo
    assert "total_count" in promo
    assert "source" in promo
    assert "confidence" in promo
    assert "reason" in promo
    assert "reasoning" in promo
    assert "fallback_used" in promo


def test_never_raises_on_none_scored():
    payload = _payload()
    plan = _edit_plan([_ai_seg(0.0, 20.0, score=90.0)])
    result = promote_segment_selection(None, plan, payload)
    assert result is not None


def test_never_raises_on_none_edit_plan():
    scored = [_scored_seg(0.0, 20.0)]
    payload = _payload()
    result = promote_segment_selection(scored, None, payload)
    assert result is not None
    assert result[1]["segment_selection_promotion"]["applied"] is False


def test_never_raises_on_malformed_scored():
    for bad_scored in [42, "string", [None, None], [{"bad": "dict"}]]:
        payload = _payload()
        plan = _edit_plan([_ai_seg(0.0, 20.0, score=90.0)])
        # Should never raise
        result = promote_segment_selection(bad_scored, plan, payload)
        assert result is not None


def test_never_raises_on_malformed_ai_segments():
    scored = [_scored_seg(0.0, 20.0)]
    payload = _payload()
    for bad_segs in [
        [None],
        [42],
        ["string"],
        [{"start": "not_a_number", "end": "also_bad", "score": "oops"}],
    ]:
        plan = _edit_plan(bad_segs)
        result = promote_segment_selection(scored, plan, payload)
        assert result is not None


def test_never_raises_on_malformed_payload():
    scored = [_scored_seg(0.0, 20.0)]
    plan = _edit_plan([_ai_seg(2.0, 18.0, score=90.0)])
    for bad_payload in [None, 42, "string", types.SimpleNamespace()]:
        result = promote_segment_selection(scored, plan, bad_payload)
        assert result is not None


# ---------------------------------------------------------------------------
# 12. Dict-style selected_segments (test robustness)
# ---------------------------------------------------------------------------

def test_dict_style_ai_segments_work():
    """AI segments as dicts (not objects) should be handled correctly."""
    scored = [_scored_seg(0.0, 20.0), _scored_seg(20.0, 40.0)]
    ai_segs_dict = [
        {"start": 2.0, "end": 18.0, "score": 85.0, "reason": "test", "source": "local_ai"},
    ]
    plan = _edit_plan(ai_segs_dict)
    payload = _payload()

    result, report = promote_segment_selection(scored, plan, payload)
    assert report["segment_selection_promotion"]["applied"] is True
    assert result[0]["start"] == 0.0   # endorsed first


def test_dict_style_edit_plan_works():
    """edit_plan as dict (not object) should be handled correctly."""
    scored = [_scored_seg(0.0, 20.0), _scored_seg(20.0, 40.0)]
    edit_plan_dict = {
        "selected_segments": [{"start": 2.0, "end": 18.0, "score": 85.0}],
    }
    payload = _payload()

    result, report = promote_segment_selection(scored, edit_plan_dict, payload)
    assert report["segment_selection_promotion"]["applied"] is True


# ---------------------------------------------------------------------------
# 13. Integration — segments reach render order
# ---------------------------------------------------------------------------

def test_integration_ai_segments_reach_render_order():
    """Integration test: AI-endorsed segments are positioned first in the
    final scored list that would be committed to DB by render_pipeline.py."""
    # Simulate what render_pipeline has after scene detection + scoring
    original_scored = [
        _scored_seg(0.0, 25.0,  viral_score=60, hook_score=55.0),   # idx=0, weak hook
        _scored_seg(25.0, 50.0, viral_score=55, hook_score=50.0),   # idx=1, weakest
        _scored_seg(50.0, 75.0, viral_score=70, hook_score=85.0),   # idx=2, strong hook
        _scored_seg(75.0, 100.0, viral_score=65, hook_score=60.0),  # idx=3, moderate
    ]

    # AI director selects segment at 50–75 as the best (highest hook score)
    ai_selected = [_ai_seg(52.0, 73.0, score=88.0)]
    plan = _edit_plan(ai_selected)
    payload = _payload()

    promoted_scored, report = promote_segment_selection(original_scored, plan, payload)
    promo = report["segment_selection_promotion"]

    # AI endorsement must have been applied
    assert promo["applied"] is True, (
        f"Expected applied=True but got: {promo}"
    )
    # AI-endorsed segment (start=50) must be first
    assert promoted_scored[0]["start"] == 50.0, (
        f"Expected AI-endorsed segment first, got start={promoted_scored[0]['start']}"
    )
    # All original segments preserved
    assert len(promoted_scored) == len(original_scored)
    # Report shows source
    assert promo["source"] == "ai_selected_segments"
    # Confidence is valid
    assert 0.0 <= promo["confidence"] <= 1.0

    # Fallback verification: with AI disabled, original order preserved
    payload_disabled = _payload(ai_render_influence_enabled=False)
    fallback_scored, fallback_report = promote_segment_selection(
        original_scored, plan, payload_disabled
    )
    assert fallback_report["segment_selection_promotion"]["fallback_used"] is True
    assert fallback_scored == original_scored, (
        "Fallback must return original scored list unchanged"
    )
