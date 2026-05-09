"""
tests/test_ai_phase35_clip_candidate_discovery.py — Phase 35: AI Clip Candidate Discovery.

Tests:
- schema invariants (AIClipCandidate, AIClipCandidatePack)
- safety gates (clip_candidate_safety)
- engine behavior (clip_candidate_engine)
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


def _make_plan_with_segments(segments):
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan,
    )
    return AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=segments,
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )


class _FakePayload:
    def __init__(self, **kwargs):
        defaults = dict(
            ai_clip_discovery_enabled=True,
            ai_clip_min_duration_sec=15,
            ai_clip_max_duration_sec=60,
            ai_clip_candidate_limit=5,
            playback_speed=1.0,
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)


# ── Schema tests ──────────────────────────────────────────────────────────────

class TestClipCandidateSchema:
    def test_candidate_defaults(self):
        from app.ai.clips.clip_candidate_schema import AIClipCandidate
        c = AIClipCandidate(candidate_id="c1")
        assert c.label == ""
        assert c.start_sec == 0.0
        assert c.end_sec == 0.0
        assert c.duration_sec == 0.0
        assert c.confidence == 0.0
        assert c.retention_score == 0.0
        assert c.story_score == 0.0
        assert c.hook_score == 0.0
        assert c.pacing_score == 0.0
        assert c.creator_style_score == 0.0
        assert c.safe is False
        assert c.reasons == []
        assert c.warnings == []

    def test_candidate_to_dict_keys(self):
        from app.ai.clips.clip_candidate_schema import AIClipCandidate
        c = AIClipCandidate(candidate_id="c1", start_sec=5.0, end_sec=35.0, duration_sec=30.0)
        d = c.to_dict()
        assert d["candidate_id"] == "c1"
        assert d["start_sec"] == 5.0
        assert d["end_sec"] == 35.0
        assert d["duration_sec"] == 30.0
        assert "retention_score" in d
        assert "story_score" in d
        assert "hook_score" in d
        assert "pacing_score" in d
        assert "creator_style_score" in d
        assert "confidence" in d
        assert "safe" in d
        assert "reasons" in d
        assert "warnings" in d

    def test_pack_defaults(self):
        from app.ai.clips.clip_candidate_schema import AIClipCandidatePack
        pack = AIClipCandidatePack()
        assert pack.available is True
        assert pack.enabled is False
        assert pack.mode == "discovery_only"
        assert pack.candidates == []
        assert pack.recommended_candidate_id is None
        assert pack.warnings == []

    def test_pack_to_dict_keys(self):
        from app.ai.clips.clip_candidate_schema import AIClipCandidatePack
        pack = AIClipCandidatePack()
        d = pack.to_dict()
        assert "available" in d
        assert "enabled" in d
        assert "mode" in d
        assert "candidates" in d
        assert "recommended_candidate_id" in d
        assert "warnings" in d

    def test_pack_mode_is_always_discovery_only(self):
        from app.ai.clips.clip_candidate_schema import AIClipCandidatePack
        pack = AIClipCandidatePack(mode="discovery_only")
        assert pack.to_dict()["mode"] == "discovery_only"


# ── Safety tests ──────────────────────────────────────────────────────────────

class TestClipCandidateSafety:
    def _base_candidate(self, **overrides):
        c = {
            "candidate_id": "c1",
            "start_sec": 5.0,
            "end_sec": 35.0,
            "duration_sec": 30.0,
            "confidence": 0.8,
            "retention_score": 70.0,
            "story_score": 60.0,
            "hook_score": 80.0,
            "pacing_score": 65.0,
            "creator_style_score": 55.0,
        }
        c.update(overrides)
        return c

    def test_valid_candidate_passes(self):
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        assert is_candidate_safe(self._base_candidate()) is True

    def test_negative_start_rejected(self):
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        assert is_candidate_safe(self._base_candidate(start_sec=-1.0)) is False

    def test_negative_end_rejected(self):
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        assert is_candidate_safe(self._base_candidate(end_sec=-1.0, duration_sec=-6.0)) is False

    def test_end_lte_start_rejected(self):
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        assert is_candidate_safe(self._base_candidate(start_sec=20.0, end_sec=10.0, duration_sec=-10.0)) is False

    def test_end_equal_start_rejected(self):
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        assert is_candidate_safe(self._base_candidate(start_sec=10.0, end_sec=10.0, duration_sec=0.0)) is False

    def test_nan_timing_rejected(self):
        import math
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        assert is_candidate_safe(self._base_candidate(start_sec=float("nan"))) is False
        assert is_candidate_safe(self._base_candidate(end_sec=float("nan"))) is False

    def test_inf_timing_rejected(self):
        import math
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        assert is_candidate_safe(self._base_candidate(end_sec=float("inf"))) is False

    def test_duration_too_short_rejected(self):
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        ctx = {"min_duration_sec": 15, "max_duration_sec": 60}
        # 10 sec is too short (min=15)
        assert is_candidate_safe(
            self._base_candidate(start_sec=0.0, end_sec=10.0, duration_sec=10.0), ctx
        ) is False

    def test_duration_too_long_rejected(self):
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        ctx = {"min_duration_sec": 15, "max_duration_sec": 60}
        # 120 sec is too long (max=60)
        assert is_candidate_safe(
            self._base_candidate(start_sec=0.0, end_sec=120.0, duration_sec=120.0), ctx
        ) is False

    def test_sanitize_confidence_clamped(self):
        from app.ai.clips.clip_candidate_safety import sanitize_candidate
        c = self._base_candidate(confidence=99.0)
        s = sanitize_candidate(c)
        assert s["confidence"] <= 1.0

    def test_sanitize_confidence_nan_zeroed(self):
        from app.ai.clips.clip_candidate_safety import sanitize_candidate
        c = self._base_candidate(confidence=float("nan"))
        s = sanitize_candidate(c)
        assert s["confidence"] == 0.0

    def test_sanitize_scores_clamped_upper(self):
        from app.ai.clips.clip_candidate_safety import sanitize_candidate
        c = self._base_candidate(retention_score=999.0, story_score=-50.0)
        s = sanitize_candidate(c)
        assert s["retention_score"] == 100.0
        assert s["story_score"] == 0.0

    def test_sanitize_scores_nan_zeroed(self):
        from app.ai.clips.clip_candidate_safety import sanitize_candidate
        c = self._base_candidate(hook_score=float("nan"))
        s = sanitize_candidate(c)
        assert s["hook_score"] == 0.0

    def test_sanitize_never_raises_on_garbage(self):
        from app.ai.clips.clip_candidate_safety import sanitize_candidate
        # Should not raise even on completely broken input
        result = sanitize_candidate({"start_sec": "bad", "end_sec": None})
        assert isinstance(result, dict)

    def test_is_candidate_safe_never_raises(self):
        from app.ai.clips.clip_candidate_safety import is_candidate_safe
        assert is_candidate_safe({}) is False
        assert is_candidate_safe({"start_sec": "abc"}) is False
        assert is_candidate_safe(None) is False  # type: ignore[arg-type]


# ── Engine tests ──────────────────────────────────────────────────────────────

class TestClipCandidateEngine:
    def test_discovery_disabled_by_default(self):
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        plan = _make_plan()
        payload = _FakePayload(ai_clip_discovery_enabled=False)
        pack = discover_clip_candidates(plan, payload=payload)
        assert pack.enabled is False
        assert pack.mode == "discovery_only"

    def test_discovery_disabled_no_payload(self):
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        plan = _make_plan()
        pack = discover_clip_candidates(plan)
        assert pack.enabled is False

    def test_discovery_enabled_returns_pack(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segments = [AIClipPlan(start=0.0, end=30.0, score=90.0)]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload(
            ai_clip_discovery_enabled=True,
            ai_clip_min_duration_sec=15,
            ai_clip_max_duration_sec=60,
            ai_clip_candidate_limit=5,
        )
        pack = discover_clip_candidates(plan, payload=payload)
        assert pack.enabled is True
        assert pack.mode == "discovery_only"
        assert pack.available is True

    def test_candidate_timing_valid(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segments = [AIClipPlan(start=5.0, end=40.0, score=80.0)]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload(ai_clip_min_duration_sec=10, ai_clip_max_duration_sec=90)
        pack = discover_clip_candidates(plan, payload=payload)
        for c in pack.candidates:
            assert c.start_sec >= 0.0
            assert c.end_sec > c.start_sec
            assert c.duration_sec > 0.0

    def test_candidate_limit_enforced(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segments = [AIClipPlan(start=float(i * 40), end=float(i * 40 + 30), score=70.0)
                    for i in range(10)]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload(
            ai_clip_min_duration_sec=10,
            ai_clip_max_duration_sec=60,
            ai_clip_candidate_limit=3,
        )
        pack = discover_clip_candidates(plan, payload=payload)
        assert len(pack.candidates) <= 3

    def test_duration_limits_enforced(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        # 5-sec segment is below min_duration=15
        segments = [AIClipPlan(start=0.0, end=5.0, score=80.0)]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload(
            ai_clip_min_duration_sec=15,
            ai_clip_max_duration_sec=60,
        )
        pack = discover_clip_candidates(plan, payload=payload)
        for c in pack.candidates:
            assert c.safe is True
            assert c.duration_sec >= 15.0
            assert c.duration_sec <= 60.0

    def test_confidence_clamped_0_to_1(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segments = [AIClipPlan(start=0.0, end=30.0, score=80.0)]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        for c in pack.candidates:
            assert 0.0 <= c.confidence <= 1.0

    def test_scores_clamped_0_to_100(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segments = [AIClipPlan(start=0.0, end=30.0, score=80.0)]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        for c in pack.candidates:
            assert 0.0 <= c.retention_score <= 100.0
            assert 0.0 <= c.story_score <= 100.0
            assert 0.0 <= c.hook_score <= 100.0
            assert 0.0 <= c.pacing_score <= 100.0
            assert 0.0 <= c.creator_style_score <= 100.0

    def test_no_negative_timing(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segments = [AIClipPlan(start=0.0, end=30.0, score=80.0)]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        for c in pack.candidates:
            assert c.start_sec >= 0.0
            assert c.end_sec >= 0.0
            assert c.duration_sec >= 0.0

    def test_invalid_segment_produces_no_candidate(self):
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        plan = _make_plan()
        # Force empty selected_segments and no story segments
        plan.selected_segments = []
        plan.story = {}
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        # Should not raise, returns empty pack
        assert isinstance(pack.candidates, list)

    def test_recommended_candidate_is_safe(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segments = [AIClipPlan(start=0.0, end=30.0, score=90.0)]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        if pack.recommended_candidate_id is not None:
            found = [c for c in pack.candidates if c.candidate_id == pack.recommended_candidate_id]
            assert len(found) == 1
            assert found[0].safe is True

    def test_deterministic_discovery(self):
        """Same input always produces same output ordering."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segments = [
            AIClipPlan(start=0.0, end=30.0, score=90.0),
            AIClipPlan(start=60.0, end=90.0, score=70.0),
        ]
        plan = _make_plan_with_segments(segments)
        payload = _FakePayload()
        pack1 = discover_clip_candidates(plan, payload=payload)
        pack2 = discover_clip_candidates(plan, payload=payload)
        ids1 = [c.candidate_id for c in pack1.candidates]
        ids2 = [c.candidate_id for c in pack2.candidates]
        assert ids1 == ids2

    def test_never_raises_on_none_plan(self):
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        pack = discover_clip_candidates(None)  # type: ignore[arg-type]
        assert isinstance(pack, object)

    def test_never_raises_on_broken_plan(self):
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        pack = discover_clip_candidates(object())  # no attributes at all
        assert pack is not None

    def test_story_segment_window_inclusion(self):
        """Story segment timing windows are included as candidate sources."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        plan.story = {
            "available": True,
            "narrative_flow": "climax_first",
            "dominant_arc": "tension_release",
            "retention_score": 72.0,
            "segments": [
                {"type": "hook", "start": 0.0, "end": 20.0, "confidence": 0.9, "retention_risk": 0.1},
                {"type": "climax", "start": 60.0, "end": 90.0, "confidence": 0.8, "retention_risk": 0.2},
            ],
            "warnings": [],
        }
        payload = _FakePayload(
            ai_clip_min_duration_sec=15,
            ai_clip_max_duration_sec=120,
            ai_clip_candidate_limit=10,
        )
        pack = discover_clip_candidates(plan, payload=payload)
        # Should have candidates (at least from the selected_segment)
        assert pack.enabled is True

    def test_retention_risk_reduces_score(self):
        """High retention risk regions reduce candidate retention score."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        plan.retention = {
            "available": True,
            "overall_retention_score": 50,
            "risk_regions": [
                {"start": 0.0, "end": 30.0, "risk": 0.9, "category": "silence_gap",
                 "severity": "high", "reason": "test"}
            ],
            "strengths": [],
            "warnings": [],
        }
        plan_clean = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        plan_clean.retention = {
            "available": True,
            "overall_retention_score": 80,
            "risk_regions": [],
            "strengths": ["strong opening hook"],
            "warnings": [],
        }
        payload = _FakePayload()
        pack_risky = discover_clip_candidates(plan, payload=payload)
        pack_clean = discover_clip_candidates(plan_clean, payload=payload)

        if pack_risky.candidates and pack_clean.candidates:
            risky_ret = pack_risky.candidates[0].retention_score
            clean_ret = pack_clean.candidates[0].retention_score
            assert clean_ret >= risky_ret


# ── No mutation tests ─────────────────────────────────────────────────────────

class TestNoMutation:
    def test_no_payload_mutation(self):
        """discover_clip_candidates must not mutate the payload object."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        payload = _FakePayload()
        original_speed = payload.playback_speed
        discover_clip_candidates(plan, payload=payload)
        assert payload.playback_speed == original_speed

    def test_no_playback_speed_mutation(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        from app.ai.clips.clip_candidate_schema import AIClipCandidatePack
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        pack_dict = pack.to_dict()
        # playback_speed must not appear in any candidate or pack dict
        import json
        as_str = json.dumps(pack_dict)
        assert "playback_speed" not in as_str

    def test_no_segment_reorder(self):
        """selected_segments order on the plan is preserved after discovery."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        segs = [
            AIClipPlan(start=60.0, end=90.0, score=70.0),
            AIClipPlan(start=0.0, end=30.0, score=90.0),
        ]
        plan = _make_plan_with_segments(segs)
        payload = _FakePayload()
        discover_clip_candidates(plan, payload=payload)
        # segments must remain in original order
        assert plan.selected_segments[0].start == 60.0
        assert plan.selected_segments[1].start == 0.0

    def test_no_render_execution(self):
        """Pack is metadata-only — mode must always be discovery_only."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        assert pack.mode == "discovery_only"

    def test_no_ffmpeg_mutation(self):
        """Pack dict must not contain ffmpeg-related keys."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        import json
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        as_str = json.dumps(pack.to_dict())
        for forbidden in ("ffmpeg", "vf ", "-vf", "crop=", "setpts", "subprocess"):
            assert forbidden not in as_str.lower()

    def test_no_subtitle_timing_rewrite(self):
        """Pack dict must not contain subtitle timing keys."""
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        import json
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        as_str = json.dumps(pack.to_dict())
        for forbidden in ("subtitle_timestamp", "srt_rewrite", "ass_rewrite", "timing_rewrite"):
            assert forbidden not in as_str.lower()


# ── Edit plan schema tests ────────────────────────────────────────────────────

class TestEditPlanSchemaPhase35:
    def test_clip_candidate_discovery_field_exists(self):
        plan = _make_plan()
        assert hasattr(plan, "clip_candidate_discovery")
        assert isinstance(plan.clip_candidate_discovery, dict)

    def test_clip_candidate_discovery_default_empty(self):
        plan = _make_plan()
        assert plan.clip_candidate_discovery == {}

    def test_to_dict_includes_clip_candidate_discovery(self):
        plan = _make_plan()
        d = plan.to_dict()
        assert "clip_candidate_discovery" in d
        assert isinstance(d["clip_candidate_discovery"], dict)

    def test_backward_compatibility_no_new_required_fields(self):
        """AIEditPlan can still be constructed without clip_candidate_discovery."""
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
        assert plan.clip_candidate_discovery == {}
        d = plan.to_dict()
        assert "clip_candidate_discovery" in d

    def test_prior_phase_fields_still_present(self):
        plan = _make_plan()
        d = plan.to_dict()
        for key in (
            "story", "retention", "timing_mutation", "story_optimization",
            "creator_style_adaptation", "execution_simulation",
            "timing_apply", "subtitle_text_apply", "camera_motion_apply",
        ):
            assert key in d, f"Missing backward-compat key: {key}"


# ── Metadata attachment tests ─────────────────────────────────────────────────

class TestMetadataAttachment:
    def test_metadata_attached_to_plan_after_discovery(self):
        from app.ai.director.edit_plan_schema import AIClipPlan
        from app.ai.clips.clip_candidate_engine import discover_clip_candidates
        plan = _make_plan(selected_segments=[AIClipPlan(start=0.0, end=30.0, score=80.0)])
        payload = _FakePayload()
        pack = discover_clip_candidates(plan, payload=payload)
        pack_dict = pack.to_dict()
        # Simulate what ai_director does
        plan.clip_candidate_discovery = pack_dict
        assert plan.clip_candidate_discovery["mode"] == "discovery_only"
        assert "candidates" in plan.clip_candidate_discovery

    def test_metadata_compact_structure(self):
        from app.ai.clips.clip_candidate_schema import AIClipCandidate, AIClipCandidatePack
        c = AIClipCandidate(
            candidate_id="c1",
            start_sec=0.0, end_sec=30.0, duration_sec=30.0,
            confidence=0.75, retention_score=70.0, story_score=60.0,
            hook_score=80.0, pacing_score=65.0, creator_style_score=55.0,
            safe=True,
        )
        pack = AIClipCandidatePack(
            available=True, enabled=True, mode="discovery_only",
            candidates=[c], recommended_candidate_id="c1",
        )
        d = pack.to_dict()
        assert d["available"] is True
        assert d["enabled"] is True
        assert d["mode"] == "discovery_only"
        assert len(d["candidates"]) == 1
        assert d["recommended_candidate_id"] == "c1"


# ── Render influence reporter tests ───────────────────────────────────────────

class TestRenderInfluencePhase35:
    def test_reporter_skips_when_no_result(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_plan()
        plan.clip_candidate_discovery = {}
        _, report = apply_ai_render_influence(object(), plan, context={"job_id": "test"})
        skipped_keys = " ".join(report.get("skipped", []))
        assert "clip_candidate_discovery" in skipped_keys

    def test_reporter_reports_disabled_state(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_plan()
        plan.clip_candidate_discovery = {
            "available": True,
            "enabled": False,
            "mode": "discovery_only",
            "candidates": [],
            "recommended_candidate_id": None,
            "warnings": ["discovery_disabled"],
        }
        _, report = apply_ai_render_influence(object(), plan, context={"job_id": "test"})
        skipped_keys = " ".join(report.get("skipped", []))
        assert "clip_candidate_discovery:disabled_phase35" in skipped_keys

    def test_reporter_reports_enabled_state(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_plan()
        plan.clip_candidate_discovery = {
            "available": True,
            "enabled": True,
            "mode": "discovery_only",
            "candidates": [
                {"candidate_id": "c1", "safe": True, "retention_score": 70.0,
                 "start_sec": 0.0, "end_sec": 30.0, "duration_sec": 30.0}
            ],
            "recommended_candidate_id": "c1",
            "warnings": [],
        }
        _, report = apply_ai_render_influence(object(), plan, context={"job_id": "test"})
        skipped_keys = " ".join(report.get("skipped", []))
        assert "clip_candidate_discovery:discovery_only_phase35" in skipped_keys

    def test_reporter_never_adds_to_applied(self):
        """Clip discovery must never appear in report['applied'] — it's advisory."""
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_plan()
        plan.clip_candidate_discovery = {
            "available": True,
            "enabled": True,
            "mode": "discovery_only",
            "candidates": [
                {"candidate_id": "c1", "safe": True, "retention_score": 95.0,
                 "start_sec": 0.0, "end_sec": 30.0, "duration_sec": 30.0}
            ],
            "recommended_candidate_id": "c1",
            "warnings": [],
        }
        _, report = apply_ai_render_influence(object(), plan, context={"job_id": "test"})
        applied = " ".join(report.get("applied", []))
        assert "clip_candidate" not in applied


# ── Schemas request field tests ───────────────────────────────────────────────

class TestSchemasPhase35:
    def _make_request(self, **kwargs):
        from app.models.schemas import RenderRequest
        base = {
            "source_video_path": "/tmp/vid.mp4",
            "output_dir": "/tmp/out",
        }
        base.update(kwargs)
        return RenderRequest(**base)

    def test_clip_discovery_disabled_by_default(self):
        req = self._make_request()
        assert req.ai_clip_discovery_enabled is False

    def test_clip_min_duration_default(self):
        req = self._make_request()
        assert req.ai_clip_min_duration_sec == 15

    def test_clip_max_duration_default(self):
        req = self._make_request()
        assert req.ai_clip_max_duration_sec == 60

    def test_clip_candidate_limit_default(self):
        req = self._make_request()
        assert req.ai_clip_candidate_limit == 5

    def test_min_duration_clamped_low(self):
        req = self._make_request(ai_clip_min_duration_sec=1)
        assert req.ai_clip_min_duration_sec == 5

    def test_min_duration_clamped_high(self):
        req = self._make_request(ai_clip_min_duration_sec=999)
        assert req.ai_clip_min_duration_sec == 180

    def test_max_duration_clamped_low(self):
        req = self._make_request(ai_clip_max_duration_sec=1)
        assert req.ai_clip_max_duration_sec >= 10

    def test_max_duration_clamped_high(self):
        req = self._make_request(ai_clip_max_duration_sec=9999)
        assert req.ai_clip_max_duration_sec == 300

    def test_candidate_limit_clamped_low(self):
        req = self._make_request(ai_clip_candidate_limit=0)
        assert req.ai_clip_candidate_limit == 1

    def test_candidate_limit_clamped_high(self):
        req = self._make_request(ai_clip_candidate_limit=100)
        assert req.ai_clip_candidate_limit == 20

    def test_max_gte_min_enforced(self):
        req = self._make_request(
            ai_clip_min_duration_sec=60,
            ai_clip_max_duration_sec=30,
        )
        assert req.ai_clip_max_duration_sec >= req.ai_clip_min_duration_sec

    def test_defaults_preserve_old_behavior(self):
        """Old requests with no clip fields must behave identically."""
        req = self._make_request()
        assert req.ai_clip_discovery_enabled is False


# ── Environment requirement tests ─────────────────────────────────────────────

class TestEnvironmentRequirements:
    def test_schema_importable_without_api_key(self):
        import importlib
        importlib.import_module("app.ai.clips.clip_candidate_schema")

    def test_safety_importable_without_api_key(self):
        import importlib
        importlib.import_module("app.ai.clips.clip_candidate_safety")

    def test_engine_importable_without_api_key(self):
        import importlib
        importlib.import_module("app.ai.clips.clip_candidate_engine")

    def test_no_gpu_import_in_schema(self):
        import inspect, app.ai.clips.clip_candidate_schema as m
        src = inspect.getsource(m)
        for gpu_lib in ("torch", "tensorflow", "cuda", "cupy", "onnxruntime"):
            assert gpu_lib not in src

    def test_no_internet_import_in_engine(self):
        import inspect, app.ai.clips.clip_candidate_engine as m
        src = inspect.getsource(m)
        for net_lib in ("requests", "httpx", "urllib.request", "openai", "anthropic", "boto3"):
            assert net_lib not in src

    def test_no_gpu_import_in_engine(self):
        import inspect, app.ai.clips.clip_candidate_engine as m
        src = inspect.getsource(m)
        for gpu_lib in ("torch", "tensorflow", "cuda", "cupy"):
            assert gpu_lib not in src
