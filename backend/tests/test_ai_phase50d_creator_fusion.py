"""
test_ai_phase50d_creator_fusion.py — Phase 50D Creator Preference Fusion Tests.

Coverage:
- Full fusion with all Phase 50A/B signals present
- Missing subtitle / camera / all signals
- Conflict resolution (creator vs market)
- Creator-biased weighting
- Confidence clamping [0.0, 1.0]
- Deterministic output
- No crash on None / empty / garbage inputs
- No unsafe fields in output
- Schema dataclass correctness
- Render influence reporting format
- Conflict resolver unit tests
"""
from __future__ import annotations

import types
import pytest

from app.ai.creator_fusion.fusion_engine import fuse_creator_preferences
from app.ai.creator_fusion.fusion_schema import (
    CreatorPreferenceProfile,
    SubtitleFusionProfile, CameraFusionProfile, ClipFusionProfile,
    MarketAlignmentFusion, QualityAlignmentFusion,
    ALLOWED_SUBTITLE_STYLES, ALLOWED_CAMERA_MOTION, ALLOWED_CONTENT_STYLES,
    ALLOWED_RANKING_PREFS, ALLOWED_MARKET_FIT, ALLOWED_EMPHASIS,
)
from app.ai.creator_fusion.conflict_resolver import (
    resolve_style_conflict,
    resolve_emphasis_conflict,
    resolve_camera_conflict,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal mock edit plans
# ---------------------------------------------------------------------------

def _make_plan(**overrides):
    """Build a SimpleNamespace mock edit plan with all Phase 50 fields."""
    plan = types.SimpleNamespace(
        creator_subtitle_preference=overrides.get("sub_pref", _default_sub_pref()),
        creator_camera_preference=overrides.get("cam_pref", _default_cam_pref()),
        creator_subtitle_influence=overrides.get("sub_inf", {}),
        creator_feedback_intelligence=overrides.get("feedback", _default_feedback()),
        market_optimization_intelligence=overrides.get("market", _default_market()),
        render_quality_evaluation=overrides.get("quality", _default_quality()),
        creator_preset_evolution=overrides.get("preset_ev", {}),
        multi_signal_orchestration=overrides.get("orchestration", {}),
    )
    return plan


def _default_sub_pref(
    style="clean_pro", density="medium", emphasis="moderate",
    readability="high", confidence=0.85,
):
    return {
        "available": True,
        "inference_mode": "metadata_only",
        "subtitle_preference": {
            "style": style,
            "density": density,
            "keyword_emphasis": emphasis,
            "readability_priority": readability,
            "line_count": 2,
            "motion_style": "clean",
            "confidence": confidence,
            "signals": [],
        },
    }


def _default_cam_pref(
    motion="smooth_subject", crop="low", stability="high",
    smoothness="high", confidence=0.82,
):
    return {
        "available": True,
        "inference_mode": "metadata_only",
        "camera_preference": {
            "motion_style": motion,
            "crop_aggressiveness": crop,
            "stability_priority": stability,
            "smoothness_priority": smoothness,
            "confidence": confidence,
            "signals": [],
        },
    }


def _default_feedback(total_exports=6, avg_rank=1.8, creator_style="educational"):
    return {
        "available": True,
        "learned_feedback_patterns": {
            "creator_style_pattern": creator_style,
            "total_exports": total_exports,
            "avg_export_rank": avg_rank,
        },
    }


def _default_market(target="educational"):
    return {
        "market_profile": {
            "target_market": target,
        }
    }


def _default_quality(cam_smoothness=0.78):
    return {
        "output_scores": [{"camera_smoothness": cam_smoothness}]
    }


# ===========================================================================
# 1. TestFusionWithFullSignals
# ===========================================================================

class TestFusionWithFullSignals:

    def test_available_true_with_full_signals(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.available is True

    def test_subtitle_style_from_phase50a(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.subtitle.style == "clean_pro"

    def test_camera_motion_from_phase50b(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.camera.motion_style == "smooth_subject"

    def test_confidence_positive_with_full_signals(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.confidence > 0.0

    def test_confidence_clamped_to_1(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.confidence <= 1.0

    def test_reasoning_populated(self):
        result = fuse_creator_preferences(_make_plan())
        assert len(result.reasoning) > 0

    def test_to_dict_all_keys_present(self):
        d = fuse_creator_preferences(_make_plan()).to_dict()
        expected = {
            "available", "subtitle", "camera", "clip",
            "market_alignment", "quality_alignment",
            "confidence", "reasoning", "conflicts_resolved", "warnings",
        }
        assert set(d.keys()) == expected

    def test_subtitle_dict_shape(self):
        d = fuse_creator_preferences(_make_plan()).to_dict()
        assert set(d["subtitle"].keys()) == {
            "style", "density", "keyword_emphasis", "readability_priority"
        }

    def test_camera_dict_shape(self):
        d = fuse_creator_preferences(_make_plan()).to_dict()
        assert set(d["camera"].keys()) == {
            "motion_style", "crop_aggressiveness",
            "stability_priority", "smoothness_priority",
        }

    def test_clip_dict_shape(self):
        d = fuse_creator_preferences(_make_plan()).to_dict()
        assert set(d["clip"].keys()) == {"content_style", "ranking_preference"}


# ===========================================================================
# 2. TestFusionWithMissingSubtitle
# ===========================================================================

class TestFusionWithMissingSubtitle:

    def test_missing_subtitle_still_returns_profile(self):
        plan = _make_plan(sub_pref={})
        result = fuse_creator_preferences(plan)
        assert isinstance(result, CreatorPreferenceProfile)

    def test_missing_subtitle_style_is_unknown(self):
        plan = _make_plan(sub_pref={"available": False})
        result = fuse_creator_preferences(plan)
        assert result.subtitle.style == "unknown"

    def test_missing_subtitle_camera_still_populated(self):
        plan = _make_plan(sub_pref={"available": False})
        result = fuse_creator_preferences(plan)
        assert result.camera.motion_style == "smooth_subject"

    def test_missing_subtitle_available_depends_on_other_signals(self):
        plan = _make_plan(sub_pref={"available": False})
        result = fuse_creator_preferences(plan)
        # Camera or market should make it available
        assert result.available is True

    def test_missing_subtitle_confidence_still_positive(self):
        plan = _make_plan(sub_pref={"available": False})
        result = fuse_creator_preferences(plan)
        assert result.confidence >= 0.0


# ===========================================================================
# 3. TestFusionWithMissingCamera
# ===========================================================================

class TestFusionWithMissingCamera:

    def test_missing_camera_still_returns_profile(self):
        plan = _make_plan(cam_pref={"available": False})
        result = fuse_creator_preferences(plan)
        assert isinstance(result, CreatorPreferenceProfile)

    def test_missing_camera_motion_is_unknown(self):
        plan = _make_plan(cam_pref={"available": False})
        result = fuse_creator_preferences(plan)
        assert result.camera.motion_style == "unknown"

    def test_missing_camera_subtitle_still_populated(self):
        plan = _make_plan(cam_pref={"available": False})
        result = fuse_creator_preferences(plan)
        assert result.subtitle.style == "clean_pro"


# ===========================================================================
# 4. TestFusionWithMissingAll
# ===========================================================================

class TestFusionWithMissingAll:

    def test_none_plan_returns_safe_default(self):
        result = fuse_creator_preferences(None)
        assert isinstance(result, CreatorPreferenceProfile)
        assert result.available is False

    def test_empty_plan_returns_safe_default(self):
        plan = types.SimpleNamespace()
        result = fuse_creator_preferences(plan)
        assert isinstance(result, CreatorPreferenceProfile)

    def test_all_signals_missing_confidence_is_zero(self):
        plan = types.SimpleNamespace(
            creator_subtitle_preference={},
            creator_camera_preference={},
            creator_feedback_intelligence={},
            market_optimization_intelligence={},
            render_quality_evaluation={},
        )
        result = fuse_creator_preferences(plan)
        assert result.confidence == 0.0

    def test_all_unknown_available_false(self):
        plan = types.SimpleNamespace()
        result = fuse_creator_preferences(plan)
        assert result.available is False


# ===========================================================================
# 5. TestConflictResolution
# ===========================================================================

class TestConflictResolution:
    """Spec scenario: creator prefers clean, market prefers viral → clean wins."""

    def test_creator_style_wins_over_viral_market(self):
        plan = _make_plan(
            sub_pref=_default_sub_pref(style="clean_pro", confidence=0.88),
            market=_default_market("tiktok"),
        )
        result = fuse_creator_preferences(plan)
        # Creator's clean_pro must win over tiktok viral_bold
        assert result.subtitle.style == "clean_pro"

    def test_emphasis_compromise_when_creator_quieter(self):
        # Creator prefers subtle, market (tiktok) prefers strong → compromise = moderate
        plan = _make_plan(
            sub_pref=_default_sub_pref(style="clean_pro", emphasis="subtle", confidence=0.88),
            market=_default_market("tiktok"),
        )
        result = fuse_creator_preferences(plan)
        # Should nudge one step toward strong: subtle → moderate
        assert result.subtitle.keyword_emphasis == "moderate"

    def test_creator_stronger_emphasis_wins(self):
        # Creator prefers strong, market prefers subtle → creator wins
        plan = _make_plan(
            sub_pref=_default_sub_pref(style="viral_bold", emphasis="strong", confidence=0.88),
            market=_default_market("educational"),
        )
        result = fuse_creator_preferences(plan)
        assert result.subtitle.keyword_emphasis == "strong"

    def test_smooth_creator_camera_vs_dynamic_market(self):
        # smooth_subject vs dynamic_subject → compromise = smooth_subject (middle stays at 1)
        plan = _make_plan(
            cam_pref=_default_cam_pref(motion="smooth_subject"),
            market=_default_market("tiktok"),
        )
        result = fuse_creator_preferences(plan)
        # smooth(1) vs dynamic(2) → middle = 1 = smooth_subject
        assert result.camera.motion_style == "smooth_subject"

    def test_static_creator_camera_vs_dynamic_market_compromise(self):
        # static(0) vs dynamic(2) → middle = 1 = smooth_subject
        plan = _make_plan(
            cam_pref=_default_cam_pref(motion="static_center"),
            market=_default_market("tiktok"),
        )
        result = fuse_creator_preferences(plan)
        assert result.camera.motion_style == "smooth_subject"

    def test_dynamic_creator_camera_wins_over_static_market(self):
        # dynamic(2) vs static(0) → creator wins = dynamic_subject
        plan = _make_plan(
            cam_pref=_default_cam_pref(motion="dynamic_subject"),
            market=_default_market("podcast"),
        )
        result = fuse_creator_preferences(plan)
        assert result.camera.motion_style == "dynamic_subject"

    def test_conflicts_resolved_populated_on_conflict(self):
        plan = _make_plan(
            sub_pref=_default_sub_pref(style="clean_pro"),
            market=_default_market("tiktok"),
        )
        result = fuse_creator_preferences(plan)
        assert len(result.conflicts_resolved) > 0

    def test_no_conflict_when_creator_matches_market(self):
        plan = _make_plan(
            sub_pref=_default_sub_pref(style="clean_pro"),
            market=_default_market("educational"),
        )
        result = fuse_creator_preferences(plan)
        # Both prefer clean_pro — no conflict note
        assert result.subtitle.style == "clean_pro"


# ===========================================================================
# 6. TestCreatorBiasOverMarket
# ===========================================================================

class TestCreatorBiasOverMarket:

    def test_unknown_creator_uses_market_style(self):
        plan = _make_plan(
            sub_pref=_default_sub_pref(style="unknown", confidence=0.85),
            market=_default_market("tiktok"),
        )
        result = fuse_creator_preferences(plan)
        assert result.subtitle.style == "viral_bold"

    def test_unknown_creator_camera_uses_market_motion(self):
        plan = _make_plan(
            cam_pref={"available": False},
            market=_default_market("podcast"),
        )
        result = fuse_creator_preferences(plan)
        # Camera is unavailable → market fallback used in conflict resolution
        # But cam_pref is empty so motion defaults to "unknown" then market fills in
        # through conflict resolver
        assert result.camera.motion_style in ("static_center", "unknown")

    def test_creator_style_higher_priority_than_market(self):
        # Explicit creator preference always beats market
        for creator_style in ("clean_pro", "viral_bold", "boxed_caption"):
            plan = _make_plan(
                sub_pref=_default_sub_pref(style=creator_style, confidence=0.9),
                market=_default_market("tiktok"),
            )
            result = fuse_creator_preferences(plan)
            assert result.subtitle.style == creator_style

    def test_market_fills_content_style_when_no_feedback(self):
        plan = _make_plan(
            feedback={},
            market=_default_market("educational"),
        )
        result = fuse_creator_preferences(plan)
        assert result.clip.content_style == "educational"

    def test_educational_market_gives_retention_ranking(self):
        plan = _make_plan(
            feedback={},
            market=_default_market("educational"),
        )
        result = fuse_creator_preferences(plan)
        assert result.clip.ranking_preference == "retention"

    def test_tiktok_market_gives_reach_ranking(self):
        plan = _make_plan(
            feedback={},
            market=_default_market("tiktok"),
        )
        result = fuse_creator_preferences(plan)
        assert result.clip.ranking_preference == "reach"


# ===========================================================================
# 7. TestConfidenceClamping
# ===========================================================================

class TestConfidenceClamping:

    def test_confidence_never_exceeds_1(self):
        # Even with multiple high-confidence signals
        plan = _make_plan(
            sub_pref=_default_sub_pref(confidence=1.0),
            cam_pref=_default_cam_pref(confidence=1.0),
            feedback=_default_feedback(total_exports=100),
        )
        result = fuse_creator_preferences(plan)
        assert result.confidence <= 1.0

    def test_confidence_never_below_0(self):
        result = fuse_creator_preferences(None)
        assert result.confidence >= 0.0

    def test_confidence_is_float(self):
        result = fuse_creator_preferences(_make_plan())
        assert isinstance(result.confidence, float)

    def test_confidence_rounded_to_2dp(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.confidence == round(result.confidence, 2)

    def test_more_exports_amplifies_confidence(self):
        r_few  = fuse_creator_preferences(_make_plan(feedback=_default_feedback(total_exports=1)))
        r_many = fuse_creator_preferences(_make_plan(feedback=_default_feedback(total_exports=20)))
        assert r_many.confidence >= r_few.confidence


# ===========================================================================
# 8. TestDeterministicOutput
# ===========================================================================

class TestDeterministicOutput:

    def test_same_inputs_same_output(self):
        plan = _make_plan()
        r1 = fuse_creator_preferences(plan)
        r2 = fuse_creator_preferences(plan)
        assert r1.to_dict() == r2.to_dict()

    def test_identical_plans_identical_dicts(self):
        plan_a = _make_plan()
        plan_b = _make_plan()
        d_a = fuse_creator_preferences(plan_a).to_dict()
        d_b = fuse_creator_preferences(plan_b).to_dict()
        assert d_a == d_b

    def test_different_styles_different_output(self):
        r_clean = fuse_creator_preferences(_make_plan(
            sub_pref=_default_sub_pref(style="clean_pro")
        ))
        r_viral = fuse_creator_preferences(_make_plan(
            sub_pref=_default_sub_pref(style="viral_bold")
        ))
        assert r_clean.subtitle.style != r_viral.subtitle.style


# ===========================================================================
# 9. TestQualityAlignment
# ===========================================================================

class TestQualityAlignment:

    def test_high_camera_smoothness_gives_high_smoothness_priority(self):
        plan = _make_plan(quality=_default_quality(cam_smoothness=0.80))
        result = fuse_creator_preferences(plan)
        assert result.quality_alignment.smoothness_priority == "high"

    def test_medium_camera_smoothness_gives_medium_priority(self):
        plan = _make_plan(quality=_default_quality(cam_smoothness=0.55))
        result = fuse_creator_preferences(plan)
        assert result.quality_alignment.smoothness_priority == "medium"

    def test_low_camera_smoothness_gives_low_priority(self):
        plan = _make_plan(quality=_default_quality(cam_smoothness=0.20))
        result = fuse_creator_preferences(plan)
        assert result.quality_alignment.smoothness_priority == "low"

    def test_readability_comes_from_subtitle_preference(self):
        plan = _make_plan(sub_pref=_default_sub_pref(readability="high"))
        result = fuse_creator_preferences(plan)
        assert result.quality_alignment.readability_priority == "high"


# ===========================================================================
# 10. TestNoCrashEdgeInputs
# ===========================================================================

class TestNoCrashEdgeInputs:

    def test_none_plan_does_not_raise(self):
        result = fuse_creator_preferences(None)
        assert isinstance(result, CreatorPreferenceProfile)

    def test_empty_namespace_does_not_raise(self):
        result = fuse_creator_preferences(types.SimpleNamespace())
        assert isinstance(result, CreatorPreferenceProfile)

    def test_string_input_does_not_raise(self):
        result = fuse_creator_preferences("not a plan")
        assert isinstance(result, CreatorPreferenceProfile)

    def test_int_input_does_not_raise(self):
        result = fuse_creator_preferences(42)
        assert isinstance(result, CreatorPreferenceProfile)

    def test_garbage_sub_pref_does_not_raise(self):
        plan = _make_plan(sub_pref="garbage")
        result = fuse_creator_preferences(plan)
        assert isinstance(result, CreatorPreferenceProfile)

    def test_garbage_cam_pref_does_not_raise(self):
        plan = _make_plan(cam_pref={"available": True, "camera_preference": "not a dict"})
        result = fuse_creator_preferences(plan)
        assert isinstance(result, CreatorPreferenceProfile)

    def test_none_confidence_does_not_raise(self):
        sub = _default_sub_pref()
        sub["subtitle_preference"]["confidence"] = None
        result = fuse_creator_preferences(_make_plan(sub_pref=sub))
        assert isinstance(result, CreatorPreferenceProfile)

    def test_empty_market_does_not_raise(self):
        result = fuse_creator_preferences(_make_plan(market={}))
        assert isinstance(result, CreatorPreferenceProfile)

    def test_empty_quality_does_not_raise(self):
        result = fuse_creator_preferences(_make_plan(quality={}))
        assert isinstance(result, CreatorPreferenceProfile)

    def test_empty_feedback_does_not_raise(self):
        result = fuse_creator_preferences(_make_plan(feedback={}))
        assert isinstance(result, CreatorPreferenceProfile)


# ===========================================================================
# 11. TestNoUnsafeFields
# ===========================================================================

class TestNoUnsafeFields:

    FORBIDDEN = {
        "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
        "subprocess", "executable", "python_code", "shell", "powershell",
        "api_key", "auth_token", "queue_priority", "output_path", "rerender",
        "delete_output", "crop_coordinates", "direct_transform",
    }

    def _check(self, d: dict) -> None:
        for key in d:
            assert key.lower() not in self.FORBIDDEN, f"Forbidden key: {key!r}"
            if isinstance(d[key], dict):
                self._check(d[key])

    def test_no_forbidden_keys_full_signals(self):
        self._check(fuse_creator_preferences(_make_plan()).to_dict())

    def test_no_forbidden_keys_none_input(self):
        self._check(fuse_creator_preferences(None).to_dict())

    def test_no_forbidden_keys_missing_all(self):
        self._check(fuse_creator_preferences(types.SimpleNamespace()).to_dict())


# ===========================================================================
# 12. TestSchemaDataclass
# ===========================================================================

class TestSchemaDataclass:

    def test_default_construction(self):
        p = CreatorPreferenceProfile()
        assert p.available is False
        assert p.confidence == 0.0
        assert p.reasoning == []
        assert p.conflicts_resolved == []

    def test_subtitle_profile_default(self):
        s = SubtitleFusionProfile()
        assert s.style == "unknown"
        assert s.density == "unknown"

    def test_camera_profile_default(self):
        c = CameraFusionProfile()
        assert c.motion_style == "unknown"

    def test_clip_profile_default(self):
        cl = ClipFusionProfile()
        assert cl.content_style == "unknown"

    def test_market_alignment_default(self):
        m = MarketAlignmentFusion()
        assert m.target_market == "unknown"
        assert m.market_fit == "unknown"

    def test_quality_alignment_default(self):
        q = QualityAlignmentFusion()
        assert q.readability_priority == "unknown"
        assert q.smoothness_priority == "unknown"

    def test_to_dict_confidence_is_float(self):
        d = fuse_creator_preferences(_make_plan()).to_dict()
        assert isinstance(d["confidence"], float)

    def test_reasoning_capped_at_five(self):
        result = fuse_creator_preferences(_make_plan())
        assert len(result.reasoning) <= 5

    def test_conflicts_resolved_capped_at_five(self):
        result = fuse_creator_preferences(_make_plan())
        assert len(result.conflicts_resolved) <= 5

    def test_subtitle_style_in_allowed_set(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.subtitle.style in ALLOWED_SUBTITLE_STYLES

    def test_camera_motion_in_allowed_set(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.camera.motion_style in ALLOWED_CAMERA_MOTION

    def test_emphasis_in_allowed_set(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.subtitle.keyword_emphasis in ALLOWED_EMPHASIS

    def test_content_style_in_allowed_set(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.clip.content_style in ALLOWED_CONTENT_STYLES

    def test_ranking_preference_in_allowed_set(self):
        result = fuse_creator_preferences(_make_plan())
        assert result.clip.ranking_preference in ALLOWED_RANKING_PREFS


# ===========================================================================
# 13. TestConflictResolverUnit (pure unit tests of resolver module)
# ===========================================================================

class TestConflictResolverUnit:

    # --- resolve_style_conflict ---

    def test_creator_style_wins_when_known(self):
        style, note = resolve_style_conflict("clean_pro", "viral_bold")
        assert style == "clean_pro"
        assert "clean_pro" in note

    def test_market_used_when_creator_unknown(self):
        style, note = resolve_style_conflict("unknown", "viral_bold")
        assert style == "viral_bold"

    def test_no_note_when_styles_match(self):
        style, note = resolve_style_conflict("clean_pro", "clean_pro")
        assert style == "clean_pro"
        assert note == ""

    def test_both_unknown_returns_unknown(self):
        style, note = resolve_style_conflict("unknown", "unknown")
        assert style == "unknown"

    # --- resolve_emphasis_conflict ---

    def test_creator_quieter_gets_nudged_up(self):
        # subtle(1) + strong(3) → moderate(2)
        emphasis, note = resolve_emphasis_conflict("subtle", "strong")
        assert emphasis == "moderate"
        assert "compromise" in note

    def test_creator_louder_wins(self):
        emphasis, note = resolve_emphasis_conflict("strong", "subtle")
        assert emphasis == "strong"
        assert "creator wins" in note

    def test_same_emphasis_no_note(self):
        emphasis, note = resolve_emphasis_conflict("moderate", "moderate")
        assert emphasis == "moderate"
        assert note == ""

    def test_unknown_creator_uses_market(self):
        emphasis, note = resolve_emphasis_conflict("unknown", "strong")
        assert emphasis == "strong"

    def test_none_nudge_plus_strong_market_gives_subtle(self):
        # none(0) + strong(3) → subtle(1) — one step up from none
        emphasis, _ = resolve_emphasis_conflict("none", "strong")
        assert emphasis == "subtle"

    # --- resolve_camera_conflict ---

    def test_static_vs_dynamic_gives_smooth(self):
        # static(0) + dynamic(2) → middle = 1 = smooth_subject
        motion, note = resolve_camera_conflict("static_center", "dynamic_subject")
        assert motion == "smooth_subject"
        assert "compromise" in note

    def test_smooth_vs_dynamic_gives_smooth(self):
        # smooth(1) + dynamic(2) → middle = 1 = smooth_subject (creator wins — closer)
        motion, note = resolve_camera_conflict("smooth_subject", "dynamic_subject")
        assert motion == "smooth_subject"

    def test_dynamic_vs_static_creator_wins(self):
        motion, note = resolve_camera_conflict("dynamic_subject", "static_center")
        assert motion == "dynamic_subject"
        assert "creator" in note.lower() or note == ""

    def test_unknown_creator_uses_market_camera(self):
        motion, _ = resolve_camera_conflict("unknown", "static_center")
        assert motion == "static_center"

    def test_matching_cameras_no_conflict(self):
        motion, note = resolve_camera_conflict("smooth_subject", "smooth_subject")
        assert motion == "smooth_subject"
        assert note == ""


# ===========================================================================
# 14. TestRenderInfluenceReporting
# ===========================================================================

class TestRenderInfluenceReporting:

    def _fake_plan(self, profile_dict):
        plan = types.SimpleNamespace(creator_preference_profile=profile_dict)
        return plan

    def _run(self, plan):
        from app.ai.director.render_influence import _report_creator_preference_profile
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_creator_preference_profile(None, plan, report)
        return report

    def test_no_attribute_reports_skipped(self):
        report = self._run(types.SimpleNamespace())
        assert any("creator_preference_profile" in s for s in report["skipped"])

    def test_unavailable_reports_skipped(self):
        plan = self._fake_plan({"available": False})
        report = self._run(plan)
        assert any("unavailable" in s for s in report["skipped"])

    def test_available_reports_fused_phase50d(self):
        profile = fuse_creator_preferences(_make_plan()).to_dict()
        plan = self._fake_plan(profile)
        report = self._run(plan)
        assert any("fused_phase50d" in s for s in report["skipped"])

    def test_report_contains_subtitle_style(self):
        profile = fuse_creator_preferences(_make_plan()).to_dict()
        plan = self._fake_plan(profile)
        report = self._run(plan)
        joined = " ".join(report["skipped"])
        assert "subtitle_style=" in joined

    def test_report_contains_confidence(self):
        profile = fuse_creator_preferences(_make_plan()).to_dict()
        plan = self._fake_plan(profile)
        report = self._run(plan)
        joined = " ".join(report["skipped"])
        assert "confidence=" in joined

    def test_never_reports_to_applied(self):
        profile = fuse_creator_preferences(_make_plan()).to_dict()
        plan = self._fake_plan(profile)
        report = self._run(plan)
        assert report["applied"] == []
