"""
tests/test_ai_phase36_clip_segment_selection.py — Phase 36: AI Clip Segment Selection.

Tests:
- schema invariants (AIClipSegmentPlan, AIClipSegmentSelection)
- safety gates (clip_segment_safety)
- selector behavior (clip_segment_selector)
- edit plan schema backward compatibility
- render influence reporter
- end-to-end integration
- no API key / no GPU / no internet required
"""
from __future__ import annotations

import pytest


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_plan(**kwargs):
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan,
    )
    defaults = dict(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    defaults.update(kwargs)
    return AIEditPlan(**defaults)


def _make_plan_with_candidates(candidates: list[dict], **kwargs):
    """Build a plan whose clip_candidate_discovery already has candidates."""
    plan = _make_plan(**kwargs)
    plan.clip_candidate_discovery = {
        "available": True,
        "enabled": True,
        "mode": "discovery_only",
        "candidates": candidates,
        "recommended_candidate_id": candidates[0]["candidate_id"] if candidates else None,
        "warnings": [],
    }
    return plan


def _safe_candidate(candidate_id="c1", start=0.0, end=30.0, **overrides):
    c = {
        "candidate_id": candidate_id,
        "label": "test",
        "start_sec": start,
        "end_sec": end,
        "duration_sec": end - start,
        "confidence": 0.80,
        "retention_score": 70.0,
        "story_score": 65.0,
        "hook_score": 80.0,
        "pacing_score": 60.0,
        "creator_style_score": 55.0,
        "safe": True,
        "reasons": ["early_hook_window"],
        "warnings": [],
    }
    c.update(overrides)
    return c


class _FakePayload:
    def __init__(self, **kwargs):
        defaults = dict(
            ai_clip_segment_selection_enabled=True,
            ai_clip_target_count=3,
            ai_clip_min_duration_sec=15,
            ai_clip_max_duration_sec=60,
            playback_speed=1.0,
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestClipSegmentSchema:
    def test_segment_plan_defaults(self):
        from app.ai.clips.clip_segment_schema import AIClipSegmentPlan
        s = AIClipSegmentPlan(segment_id="s1")
        assert s.candidate_id == ""
        assert s.label == ""
        assert s.start_sec == 0.0
        assert s.end_sec == 0.0
        assert s.duration_sec == 0.0
        assert s.selected is False
        assert s.rank == 0
        assert s.confidence == 0.0
        assert s.score == 0.0
        assert s.source_scores == {}
        assert s.safe is False
        assert s.reasons == []
        assert s.warnings == []

    def test_segment_plan_to_dict_keys(self):
        from app.ai.clips.clip_segment_schema import AIClipSegmentPlan
        s = AIClipSegmentPlan(
            segment_id="s1", start_sec=5.0, end_sec=35.0, duration_sec=30.0,
        )
        d = s.to_dict()
        for key in (
            "segment_id", "candidate_id", "label", "start_sec", "end_sec",
            "duration_sec", "selected", "rank", "confidence", "score",
            "source_scores", "safe", "reasons", "warnings",
        ):
            assert key in d, f"Missing key: {key}"

    def test_selection_defaults(self):
        from app.ai.clips.clip_segment_schema import AIClipSegmentSelection
        sel = AIClipSegmentSelection()
        assert sel.available is True
        assert sel.enabled is False
        assert sel.mode == "selection_only"
        assert sel.selected_segments == []
        assert sel.rejected_candidates == []
        assert sel.warnings == []

    def test_selection_to_dict_keys(self):
        from app.ai.clips.clip_segment_schema import AIClipSegmentSelection
        sel = AIClipSegmentSelection()
        d = sel.to_dict()
        for key in ("available", "enabled", "mode", "selected_segments",
                    "rejected_candidates", "warnings"):
            assert key in d, f"Missing key: {key}"

    def test_selection_mode_always_selection_only(self):
        from app.ai.clips.clip_segment_schema import AIClipSegmentSelection
        sel = AIClipSegmentSelection(mode="selection_only")
        assert sel.to_dict()["mode"] == "selection_only"

    def test_source_scores_in_to_dict(self):
        from app.ai.clips.clip_segment_schema import AIClipSegmentPlan
        s = AIClipSegmentPlan(
            segment_id="s1",
            source_scores={"retention_score": 70.0, "hook_score": 80.0},
        )
        d = s.to_dict()
        assert d["source_scores"]["retention_score"] == 70.0
        assert d["source_scores"]["hook_score"] == 80.0


# ── Safety tests ──────────────────────────────────────────────────────────────

class TestClipSegmentSafety:
    def _base(self, **overrides):
        s = {
            "start_sec": 5.0,
            "end_sec": 35.0,
            "duration_sec": 30.0,
            "confidence": 0.8,
            "score": 70.0,
            "source_scores": {},
        }
        s.update(overrides)
        return s

    def test_valid_segment_passes(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        assert is_segment_plan_safe(self._base()) is True

    def test_negative_start_rejected(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        assert is_segment_plan_safe(self._base(start_sec=-1.0)) is False

    def test_negative_end_rejected(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        assert is_segment_plan_safe(self._base(end_sec=-5.0)) is False

    def test_end_lte_start_rejected(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        assert is_segment_plan_safe(self._base(start_sec=20.0, end_sec=10.0)) is False

    def test_equal_start_end_rejected(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        assert is_segment_plan_safe(self._base(start_sec=10.0, end_sec=10.0)) is False

    def test_nan_timing_rejected(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        assert is_segment_plan_safe(self._base(start_sec=float("nan"))) is False
        assert is_segment_plan_safe(self._base(end_sec=float("nan"))) is False

    def test_inf_timing_rejected(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        assert is_segment_plan_safe(self._base(end_sec=float("inf"))) is False

    def test_duration_below_min_rejected(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        ctx = {"min_duration_sec": 15, "max_duration_sec": 60}
        assert is_segment_plan_safe(
            self._base(start_sec=0.0, end_sec=10.0, duration_sec=10.0), ctx
        ) is False

    def test_duration_above_max_rejected(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        ctx = {"min_duration_sec": 15, "max_duration_sec": 60}
        assert is_segment_plan_safe(
            self._base(start_sec=0.0, end_sec=120.0, duration_sec=120.0), ctx
        ) is False

    def test_sanitize_confidence_clamped(self):
        from app.ai.clips.clip_segment_safety import sanitize_segment_plan
        s = sanitize_segment_plan(self._base(confidence=99.0))
        assert s["confidence"] <= 1.0

    def test_sanitize_score_clamped(self):
        from app.ai.clips.clip_segment_safety import sanitize_segment_plan
        s = sanitize_segment_plan(self._base(score=999.0))
        assert s["score"] == 100.0

    def test_sanitize_negative_score_zeroed(self):
        from app.ai.clips.clip_segment_safety import sanitize_segment_plan
        s = sanitize_segment_plan(self._base(score=-5.0))
        assert s["score"] == 0.0

    def test_sanitize_source_scores_clamped(self):
        from app.ai.clips.clip_segment_safety import sanitize_segment_plan
        s = sanitize_segment_plan(self._base(source_scores={"retention_score": 200.0}))
        assert s["source_scores"]["retention_score"] == 100.0

    def test_sanitize_never_raises_on_garbage(self):
        from app.ai.clips.clip_segment_safety import sanitize_segment_plan
        result = sanitize_segment_plan({"start_sec": "bad", "end_sec": None})
        assert isinstance(result, dict)

    def test_is_safe_never_raises(self):
        from app.ai.clips.clip_segment_safety import is_segment_plan_safe
        assert is_segment_plan_safe({}) is False
        assert is_segment_plan_safe(None) is False  # type: ignore[arg-type]
        assert is_segment_plan_safe({"start_sec": "abc"}) is False


# ── Selector tests ────────────────────────────────────────────────────────────

class TestClipSegmentSelector:
    def test_selection_disabled_by_default(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        plan = _make_plan()
        payload = _FakePayload(ai_clip_segment_selection_enabled=False)
        sel = select_clip_segments(plan, payload=payload)
        assert sel.enabled is False
        assert sel.mode == "selection_only"

    def test_selection_disabled_no_payload(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        plan = _make_plan()
        sel = select_clip_segments(plan)
        assert sel.enabled is False

    def test_selection_enabled_returns_selection(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        assert sel.enabled is True
        assert sel.mode == "selection_only"
        assert sel.available is True

    def test_selected_segments_respect_target_count(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [
            _safe_candidate(f"c{i}", float(i * 90), float(i * 90 + 30))
            for i in range(8)
        ]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload(ai_clip_target_count=3)
        sel = select_clip_segments(plan, payload=payload)
        assert len(sel.selected_segments) <= 3

    def test_selected_segments_respect_min_duration(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        # 10-sec window is below min=15
        candidates = [_safe_candidate("c1", 0.0, 10.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload(ai_clip_min_duration_sec=15, ai_clip_max_duration_sec=60)
        sel = select_clip_segments(plan, payload=payload)
        for s in sel.selected_segments:
            assert s.duration_sec >= 15.0

    def test_selected_segments_respect_max_duration(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        # 120-sec window exceeds max=60
        candidates = [_safe_candidate("c1", 0.0, 120.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload(ai_clip_min_duration_sec=15, ai_clip_max_duration_sec=60)
        sel = select_clip_segments(plan, payload=payload)
        for s in sel.selected_segments:
            assert s.duration_sec <= 60.0

    def test_invalid_timing_rejected(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        # end <= start → invalid
        bad = _safe_candidate("c1", start=30.0, end=10.0)
        plan = _make_plan_with_candidates([bad])
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        assert all(s.safe for s in sel.selected_segments)
        # bad candidate should be in rejected
        reasons = [r.get("reject_reason", "") for r in sel.rejected_candidates]
        assert any(r in ("safety_check_failed",) for r in reasons)

    def test_negative_timing_rejected(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        bad = _safe_candidate("c1", start=-5.0, end=25.0)
        plan = _make_plan_with_candidates([bad])
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        reasons = [r.get("reject_reason", "") for r in sel.rejected_candidates]
        assert any(r == "safety_check_failed" for r in reasons)

    def test_confidence_clamped_in_output(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate("c1", 0.0, 30.0, confidence=99.9)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        for s in sel.selected_segments:
            assert 0.0 <= s.confidence <= 1.0

    def test_score_clamped_in_output(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate("c1", 0.0, 30.0,
                                      retention_score=200.0, hook_score=300.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        for s in sel.selected_segments:
            assert 0.0 <= s.score <= 100.0
            for v in s.source_scores.values():
                assert 0.0 <= v <= 100.0

    def test_overlapping_candidates_handled_deterministically(self):
        """Two heavily overlapping candidates: only one selected, same result each run."""
        from app.ai.clips.clip_segment_selector import select_clip_segments
        # c1 and c2 share most of their window
        candidates = [
            _safe_candidate("c1", 0.0, 30.0, retention_score=80.0),
            _safe_candidate("c2", 5.0, 35.0, retention_score=75.0),
        ]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload(ai_clip_target_count=5)

        sel1 = select_clip_segments(plan, payload=payload)
        sel2 = select_clip_segments(plan, payload=payload)

        # Same result both times
        ids1 = [s.segment_id for s in sel1.selected_segments]
        ids2 = [s.segment_id for s in sel2.selected_segments]
        assert ids1 == ids2

        # At most one of the two overlapping candidates selected
        assert len(sel1.selected_segments) <= 1

        # The other should be in rejected with overlap reason
        reject_reasons = [r.get("reject_reason", "") for r in sel1.rejected_candidates]
        assert any(r == "overlap_with_selected" for r in reject_reasons)

    def test_rejected_candidates_include_reasons(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        # Only allow 1 candidate
        candidates = [
            _safe_candidate("c1", 0.0, 30.0),
            _safe_candidate("c2", 90.0, 120.0),
            _safe_candidate("c3", 180.0, 210.0),
        ]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload(ai_clip_target_count=1)
        sel = select_clip_segments(plan, payload=payload)
        assert len(sel.rejected_candidates) >= 1
        for rej in sel.rejected_candidates:
            assert "reject_reason" in rej
            assert isinstance(rej["reject_reason"], str)
            assert len(rej["reject_reason"]) > 0

    def test_fallback_safe_when_no_candidates_exist(self):
        """When no Phase 35 candidates exist, selector falls back to selected_segments."""
        from app.ai.clips.clip_segment_selector import select_clip_segments
        from app.ai.director.edit_plan_schema import AIClipPlan
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        plan.clip_candidate_discovery = {}  # no Phase 35 data
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        # Should not raise; should return a valid selection object
        assert isinstance(sel.selected_segments, list)
        assert sel.mode == "selection_only"

    def test_fallback_warns_when_truly_empty(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        plan = _make_plan()
        plan.clip_candidate_discovery = {}
        plan.selected_segments = []  # nothing at all
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        assert sel.enabled is True
        assert "no_candidates_available" in sel.warnings

    def test_deterministic_selection(self):
        """Same input always yields identical segment ordering."""
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [
            _safe_candidate("c1", 0.0, 30.0, retention_score=80.0),
            _safe_candidate("c2", 90.0, 120.0, retention_score=70.0),
            _safe_candidate("c3", 180.0, 210.0, retention_score=60.0),
        ]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload(ai_clip_target_count=5)
        sel1 = select_clip_segments(plan, payload=payload)
        sel2 = select_clip_segments(plan, payload=payload)
        assert [s.segment_id for s in sel1.selected_segments] == \
               [s.segment_id for s in sel2.selected_segments]

    def test_never_raises_on_none_plan(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        sel = select_clip_segments(None)  # type: ignore[arg-type]
        assert sel is not None

    def test_never_raises_on_broken_plan(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        sel = select_clip_segments(object())
        assert sel is not None

    def test_warning_penalty_applied(self):
        """Candidate with subtitle_overload warning scores lower and may be ranked below clean one."""
        from app.ai.clips.clip_segment_selector import select_clip_segments
        clean = _safe_candidate("c1", 0.0, 30.0,
                                retention_score=70.0, hook_score=70.0,
                                story_score=70.0, pacing_score=70.0,
                                creator_style_score=70.0)
        noisy = _safe_candidate("c2", 90.0, 120.0,
                                retention_score=72.0, hook_score=72.0,
                                story_score=72.0, pacing_score=72.0,
                                creator_style_score=72.0,
                                warnings=["subtitle_overload_detected"])
        plan = _make_plan_with_candidates([noisy, clean])
        payload = _FakePayload(ai_clip_target_count=5)
        sel = select_clip_segments(plan, payload=payload)
        if len(sel.selected_segments) >= 2:
            # clean (c1) should rank above noisy (c2) after penalty
            ids = [s.candidate_id for s in sel.selected_segments]
            assert ids.index("c1") < ids.index("c2")

    def test_selected_segments_are_all_safe(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate(f"c{i}", float(i * 60), float(i * 60 + 30))
                      for i in range(5)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        for s in sel.selected_segments:
            assert s.safe is True

    def test_rank_is_sequential(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate(f"c{i}", float(i * 60), float(i * 60 + 30))
                      for i in range(4)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload(ai_clip_target_count=4)
        sel = select_clip_segments(plan, payload=payload)
        for i, s in enumerate(sel.selected_segments, start=1):
            assert s.rank == i


# ── No mutation tests ─────────────────────────────────────────────────────────

class TestNoMutation:
    def test_no_payload_mutation(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        original_speed = payload.playback_speed
        select_clip_segments(plan, payload=payload)
        assert payload.playback_speed == original_speed

    def test_no_playback_speed_in_output(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        import json
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        as_str = json.dumps(sel.to_dict())
        assert "playback_speed" not in as_str

    def test_no_segment_reorder(self):
        """Source selected_segments on the plan are not reordered."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_segment_selector import select_clip_segments
        segs = [
            AIClipPlan(start=60.0, end=90.0, score=70.0),
            AIClipPlan(start=0.0, end=30.0, score=90.0),
        ]
        plan = _make_plan(selected_segments=segs)
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan.clip_candidate_discovery = {
            "available": True, "enabled": True, "mode": "discovery_only",
            "candidates": candidates, "recommended_candidate_id": "c1",
            "warnings": [],
        }
        payload = _FakePayload()
        select_clip_segments(plan, payload=payload)
        # Original order preserved
        assert plan.selected_segments[0].start == 60.0
        assert plan.selected_segments[1].start == 0.0

    def test_no_render_execution(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        assert sel.mode == "selection_only"

    def test_no_ffmpeg_in_output(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        import json
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        as_str = json.dumps(sel.to_dict())
        for forbidden in ("ffmpeg", "vf ", "-vf", "crop=", "setpts", "subprocess"):
            assert forbidden not in as_str.lower()

    def test_no_subtitle_timing_in_output(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        import json
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        as_str = json.dumps(sel.to_dict())
        for forbidden in ("subtitle_timestamp", "srt_rewrite", "timing_rewrite"):
            assert forbidden not in as_str.lower()


# ── Edit plan schema tests ────────────────────────────────────────────────────

class TestEditPlanSchemaPhase36:
    def test_clip_segment_selection_field_exists(self):
        plan = _make_plan()
        assert hasattr(plan, "clip_segment_selection")
        assert isinstance(plan.clip_segment_selection, dict)

    def test_clip_segment_selection_default_empty(self):
        plan = _make_plan()
        assert plan.clip_segment_selection == {}

    def test_to_dict_includes_clip_segment_selection(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "clip_segment_selection" in d
        assert isinstance(d["clip_segment_selection"], dict)

    def test_backward_compatibility_no_new_required_fields(self):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan,
        )
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[AIClipPlan(start=0.0, end=10.0, score=80.0)],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert plan.clip_segment_selection == {}
        assert "clip_segment_selection" in plan.to_dict()

    def test_prior_phase_fields_still_present(self):
        plan = _make_plan()
        d = plan.to_dict()
        for key in (
            "story", "retention", "clip_candidate_discovery",
            "timing_apply", "camera_motion_apply",
        ):
            assert key in d, f"Missing backward-compat key: {key}"


# ── Metadata attachment tests ─────────────────────────────────────────────────

class TestMetadataAttachment:
    def test_metadata_attached_correctly(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        sel_dict = sel.to_dict()
        plan.clip_segment_selection = sel_dict
        assert plan.clip_segment_selection["mode"] == "selection_only"
        assert "selected_segments" in plan.clip_segment_selection
        assert "rejected_candidates" in plan.clip_segment_selection

    def test_segment_plan_has_segment_id(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        for s in sel.selected_segments:
            assert s.segment_id.startswith("seg_")

    def test_segment_plan_links_to_candidate(self):
        from app.ai.clips.clip_segment_selector import select_clip_segments
        candidates = [_safe_candidate("c1", 0.0, 30.0)]
        plan = _make_plan_with_candidates(candidates)
        payload = _FakePayload()
        sel = select_clip_segments(plan, payload=payload)
        for s in sel.selected_segments:
            assert s.candidate_id == "c1"


# ── Render influence reporter tests ───────────────────────────────────────────

class TestRenderInfluencePhase36:
    def test_reporter_skips_when_no_result(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_plan()
        plan.clip_segment_selection = {}
        _, report = apply_ai_render_influence(object(), plan, context={"job_id": "test"})
        skipped = " ".join(report.get("skipped", []))
        assert "clip_segment_selection" in skipped

    def test_reporter_disabled_state(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_plan()
        plan.clip_segment_selection = {
            "available": True,
            "enabled": False,
            "mode": "selection_only",
            "selected_segments": [],
            "rejected_candidates": [],
            "warnings": ["selection_disabled"],
        }
        _, report = apply_ai_render_influence(object(), plan, context={"job_id": "test"})
        skipped = " ".join(report.get("skipped", []))
        assert "clip_segment_selection:disabled_phase36" in skipped

    def test_reporter_enabled_state(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_plan()
        plan.clip_segment_selection = {
            "available": True,
            "enabled": True,
            "mode": "selection_only",
            "selected_segments": [
                {"segment_id": "seg_01", "safe": True, "score": 72.0,
                 "start_sec": 0.0, "end_sec": 30.0, "duration_sec": 30.0}
            ],
            "rejected_candidates": [],
            "warnings": [],
        }
        _, report = apply_ai_render_influence(object(), plan, context={"job_id": "test"})
        skipped = " ".join(report.get("skipped", []))
        assert "clip_segment_selection:selection_only_phase36" in skipped

    def test_reporter_never_adds_to_applied(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_plan()
        plan.clip_segment_selection = {
            "available": True,
            "enabled": True,
            "mode": "selection_only",
            "selected_segments": [
                {"segment_id": "seg_01", "safe": True, "score": 95.0,
                 "start_sec": 0.0, "end_sec": 30.0, "duration_sec": 30.0}
            ],
            "rejected_candidates": [],
            "warnings": [],
        }
        _, report = apply_ai_render_influence(object(), plan, context={"job_id": "test"})
        applied = " ".join(report.get("applied", []))
        assert "clip_segment" not in applied


# ── Schemas request field tests ───────────────────────────────────────────────

class TestSchemasPhase36:
    def _make_request(self, **kwargs):
        from app.models.schemas import RenderRequest
        base = {
            "source_video_path": "/tmp/vid.mp4",
            "output_dir": "/tmp/out",
        }
        base.update(kwargs)
        return RenderRequest(**base)

    def test_selection_disabled_by_default(self):
        req = self._make_request()
        assert req.ai_clip_segment_selection_enabled is False

    def test_target_count_default(self):
        req = self._make_request()
        assert req.ai_clip_target_count == 3

    def test_target_count_clamped_low(self):
        req = self._make_request(ai_clip_target_count=0)
        assert req.ai_clip_target_count == 1

    def test_target_count_clamped_high(self):
        req = self._make_request(ai_clip_target_count=100)
        assert req.ai_clip_target_count == 20

    def test_defaults_preserve_old_behavior(self):
        req = self._make_request()
        assert req.ai_clip_segment_selection_enabled is False

    def test_min_max_duration_still_available(self):
        """Phase 35 duration fields are shared with Phase 36 selector."""
        req = self._make_request(
            ai_clip_min_duration_sec=20,
            ai_clip_max_duration_sec=90,
        )
        assert req.ai_clip_min_duration_sec == 20
        assert req.ai_clip_max_duration_sec == 90


# ── Environment requirement tests ─────────────────────────────────────────────

class TestEnvironmentRequirements:
    def test_schema_importable_no_api_key(self):
        import importlib
        importlib.import_module("app.ai.clips.clip_segment_schema")

    def test_safety_importable_no_api_key(self):
        import importlib
        importlib.import_module("app.ai.clips.clip_segment_safety")

    def test_selector_importable_no_api_key(self):
        import importlib
        importlib.import_module("app.ai.clips.clip_segment_selector")

    def test_no_gpu_in_schema(self):
        import inspect, app.ai.clips.clip_segment_schema as m
        src = inspect.getsource(m)
        for lib in ("torch", "tensorflow", "cuda", "cupy"):
            assert lib not in src

    def test_no_internet_in_selector(self):
        import inspect, app.ai.clips.clip_segment_selector as m
        src = inspect.getsource(m)
        for lib in ("requests", "httpx", "urllib.request", "openai", "anthropic", "boto3"):
            assert lib not in src

    def test_no_gpu_in_selector(self):
        import inspect, app.ai.clips.clip_segment_selector as m
        src = inspect.getsource(m)
        for lib in ("torch", "tensorflow", "cuda", "cupy"):
            assert lib not in src
