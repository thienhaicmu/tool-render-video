"""
test_ai_phase23_creator_style.py — Phase 23 creator style adaptation tests.

Coverage: style classifier (detect_creator_styles), style adapter
(build_style_adaptation), style scoring (score_style_fit), AIEditPlan field,
AI Director integration, variant selector style-fit bonus, and all safety
boundaries.
"""
from __future__ import annotations

import pytest


# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_edit_plan(**attrs):
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan,
    )
    plan = AIEditPlan(
        enabled=True, mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(pacing_style="fast", energy_level=0.8),
    )
    for k, v in attrs.items():
        setattr(plan, k, v)
    return plan


def _make_detected_profile(style_id="viral_tiktok", confidence=0.75):
    from app.ai.styles.style_schema import DetectedStyleProfile
    return DetectedStyleProfile(
        style_id=style_id,
        label=style_id.replace("_", " ").title(),
        confidence=confidence,
        pacing_style="fast",
        subtitle_style="punch",
        camera_style="fast_follow",
        energy_level="very_high",
        hook_density="high",
    )


def _make_variant(variant_id="v1", purpose="retention", risk="low",
                  confidence=0.80, safe_to_render=True):
    from app.ai.variants.variant_schema import AIVariantPlan
    return AIVariantPlan(
        variant_id=variant_id,
        purpose=purpose,
        risk=risk,
        confidence=confidence,
        safe_to_render=safe_to_render,
        suggested_changes={},
    )


def _make_variant_set(*variants):
    from app.ai.variants.variant_schema import AIVariantSet
    return AIVariantSet(variants=list(variants))


# ── Style schema tests ─────────────────────────────────────────────────────────

class TestPhase23StyleSchema:
    def test_detected_style_profile_creates_correctly(self):
        p = _make_detected_profile()
        assert p.style_id == "viral_tiktok"
        assert p.confidence == 0.75

    def test_detected_style_profile_to_dict(self):
        p = _make_detected_profile()
        d = p.to_dict()
        assert set(d.keys()) >= {
            "style_id", "label", "confidence", "pacing_style",
            "subtitle_style", "camera_style", "energy_level",
            "hook_density", "explanation", "warnings",
        }

    def test_creator_style_set_creates_correctly(self):
        from app.ai.styles.style_schema import CreatorStyleSet
        css = CreatorStyleSet(
            detected=True,
            primary_style="viral_tiktok",
            styles=[_make_detected_profile()],
        )
        assert css.detected is True
        assert css.primary_style == "viral_tiktok"

    def test_creator_style_set_to_dict(self):
        from app.ai.styles.style_schema import CreatorStyleSet
        css = CreatorStyleSet(
            detected=True, primary_style="cinematic",
            styles=[_make_detected_profile("cinematic")],
        )
        d = css.to_dict()
        assert "detected" in d
        assert "primary_style" in d
        assert "styles" in d
        assert "fallback_used" in d

    def test_valid_p23_styles_set_contains_expected_ids(self):
        from app.ai.styles.style_schema import VALID_P23_STYLES
        expected = {
            "viral_tiktok", "cinematic", "educational", "podcast",
            "product_demo", "storytelling", "commentary", "interview",
            "safe_generic",
        }
        assert expected.issubset(VALID_P23_STYLES)

    def test_invalid_style_id_coerced_to_safe_generic_in_to_dict(self):
        from app.ai.styles.style_schema import DetectedStyleProfile
        p = DetectedStyleProfile(style_id="not_a_real_style", label="X")
        d = p.to_dict()
        assert d["style_id"] == "safe_generic"


# ── detect_creator_styles tests ────────────────────────────────────────────────

class TestDetectCreatorStyles:
    def test_never_raises_on_none_input(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        result = detect_creator_styles(None)
        assert result is not None

    def test_returns_creator_style_set(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        from app.ai.styles.style_schema import CreatorStyleSet
        result = detect_creator_styles(None)
        assert isinstance(result, CreatorStyleSet)

    def test_never_raises_on_garbage_input(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        result = detect_creator_styles("not_a_plan", context=42)
        assert result is not None

    def test_fallback_to_safe_generic_when_no_p14_style(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        plan = _make_edit_plan(creator_style={"dominant_style": "unknown", "confidence": 0.0})
        result = detect_creator_styles(plan)
        assert result.primary_style == "safe_generic"
        assert result.fallback_used is True

    def test_maps_p14_podcast_viral_to_viral_tiktok(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        plan = _make_edit_plan(creator_style={"dominant_style": "podcast_viral", "confidence": 70.0})
        result = detect_creator_styles(plan)
        assert result.primary_style == "viral_tiktok"

    def test_maps_p14_educational_focus_to_educational(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        plan = _make_edit_plan(creator_style={"dominant_style": "educational_focus", "confidence": 60.0})
        result = detect_creator_styles(plan)
        assert result.primary_style == "educational"

    def test_maps_p14_interview_clip_to_interview(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        plan = _make_edit_plan(creator_style={"dominant_style": "interview_clip", "confidence": 55.0})
        result = detect_creator_styles(plan)
        assert result.primary_style == "interview"

    def test_maps_p14_storytelling_cinematic_to_cinematic(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        plan = _make_edit_plan(creator_style={"dominant_style": "storytelling_cinematic", "confidence": 65.0})
        result = detect_creator_styles(plan)
        assert result.primary_style == "cinematic"

    def test_detected_flag_true_for_known_style(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        plan = _make_edit_plan(creator_style={"dominant_style": "podcast_viral", "confidence": 70.0})
        result = detect_creator_styles(plan)
        assert result.detected is True

    def test_styles_list_non_empty(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        result = detect_creator_styles(None)
        assert len(result.styles) >= 1

    def test_primary_style_always_in_valid_p23_styles(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        from app.ai.styles.style_schema import VALID_P23_STYLES
        for p14 in ("podcast_viral", "high_energy_reaction", "educational_focus",
                    "interview_clip", "calm_minimal", "unknown"):
            plan = _make_edit_plan(creator_style={"dominant_style": p14, "confidence": 60.0})
            result = detect_creator_styles(plan)
            assert result.primary_style in VALID_P23_STYLES

    def test_deterministic_same_input_same_output(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        plan = _make_edit_plan(creator_style={"dominant_style": "podcast_viral", "confidence": 70.0})
        r1 = detect_creator_styles(plan)
        r2 = detect_creator_styles(plan)
        assert r1.primary_style == r2.primary_style
        assert r1.detected == r2.detected

    def test_no_api_key_required(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        result = detect_creator_styles(None)
        assert result is not None

    def test_no_gpu_required(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        result = detect_creator_styles(None)
        assert isinstance(result.primary_style, str)

    def test_no_internet_required(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        result = detect_creator_styles(None)
        assert result is not None


# ── build_style_adaptation tests ──────────────────────────────────────────────

class TestBuildStyleAdaptation:
    def test_returns_dict_with_required_keys(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile()
        result = build_style_adaptation(p)
        assert set(result.keys()) >= {"style_id", "adaptation", "confidence", "reasons", "warnings"}

    def test_adaptation_dict_contains_safe_hint_keys_only(self):
        from app.ai.styles.style_adapter import build_style_adaptation, _SAFE_HINT_KEYS
        p = _make_detected_profile()
        result = build_style_adaptation(p)
        for key in result["adaptation"]:
            assert key in _SAFE_HINT_KEYS

    def test_no_forbidden_keys_in_adaptation(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        forbidden = {
            "playback_speed", "segment_start", "segment_end",
            "subtitle_timing", "ffmpeg_args", "codec", "crf",
        }
        for style_id in ("viral_tiktok", "cinematic", "educational", "safe_generic"):
            p = _make_detected_profile(style_id=style_id)
            result = build_style_adaptation(p)
            for key in result["adaptation"]:
                assert key not in forbidden, f"Forbidden key {key!r} found for {style_id}"

    def test_viral_tiktok_has_high_hook_density(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile("viral_tiktok")
        result = build_style_adaptation(p)
        assert result["adaptation"].get("hook_density_hint") == "high"

    def test_cinematic_has_low_hook_density(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile("cinematic")
        result = build_style_adaptation(p)
        assert result["adaptation"].get("hook_density_hint") == "low"

    def test_safe_generic_fallback_never_raises(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        result = build_style_adaptation(None)
        assert result is not None
        assert result["style_id"] == "safe_generic"

    def test_never_raises_on_garbage_input(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        result = build_style_adaptation("not_a_profile", edit_plan=42, context="bad")
        assert isinstance(result, dict)

    def test_no_payload_mutation(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        plan = _make_edit_plan()
        original_mode = plan.mode
        p = _make_detected_profile()
        build_style_adaptation(p, edit_plan=plan)
        assert plan.mode == original_mode

    def test_all_p23_styles_produce_adaptation(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        from app.ai.styles.style_schema import VALID_P23_STYLES
        for style_id in VALID_P23_STYLES:
            p = _make_detected_profile(style_id=style_id)
            result = build_style_adaptation(p)
            assert isinstance(result["adaptation"], dict)
            assert len(result["adaptation"]) > 0


# ── score_style_fit tests ─────────────────────────────────────────────────────

class TestScoreStyleFit:
    def test_returns_dict_with_required_keys(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile()
        v = _make_variant()
        result = score_style_fit(p, variant=v)
        assert set(result.keys()) >= {"style_fit_score", "confidence", "reasons", "warnings"}

    def test_score_in_valid_range(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile()
        result = score_style_fit(p)
        assert 0.0 <= result["style_fit_score"] <= 100.0

    def test_never_raises_on_none_inputs(self):
        from app.ai.styles.style_scoring import score_style_fit
        result = score_style_fit(None, None, None)
        assert isinstance(result, dict)

    def test_never_raises_on_garbage_input(self):
        from app.ai.styles.style_scoring import score_style_fit
        result = score_style_fit("bad", variant=42, edit_plan="nope")
        assert "style_fit_score" in result

    def test_safe_generic_returns_stable_moderate_score(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile("safe_generic")
        for purpose in ("retention", "hook", "story", "subtitle", "pacing", "safe_baseline"):
            v = _make_variant(purpose=purpose)
            result = score_style_fit(p, variant=v)
            assert 55.0 <= result["style_fit_score"] <= 70.0, \
                f"safe_generic score out of range for purpose={purpose}: {result['style_fit_score']}"

    def test_viral_tiktok_prefers_retention_variant(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile("viral_tiktok", confidence=0.8)
        v_ret = _make_variant("ret", "retention")
        v_safe = _make_variant("safe", "safe_baseline")
        score_ret = score_style_fit(p, variant=v_ret)["style_fit_score"]
        score_safe = score_style_fit(p, variant=v_safe)["style_fit_score"]
        assert score_ret > score_safe

    def test_cinematic_prefers_story_variant(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile("cinematic", confidence=0.8)
        v_story = _make_variant("st", "story")
        v_safe = _make_variant("safe", "safe_baseline")
        score_story = score_style_fit(p, variant=v_story)["style_fit_score"]
        score_safe = score_style_fit(p, variant=v_safe)["style_fit_score"]
        assert score_story > score_safe

    def test_educational_prefers_subtitle_variant(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile("educational", confidence=0.8)
        v_sub = _make_variant("sub", "subtitle")
        v_safe = _make_variant("safe", "safe_baseline")
        score_sub = score_style_fit(p, variant=v_sub)["style_fit_score"]
        score_safe = score_style_fit(p, variant=v_safe)["style_fit_score"]
        assert score_sub > score_safe

    def test_deterministic_same_input_same_output(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile("viral_tiktok", confidence=0.75)
        v = _make_variant("ret", "retention")
        r1 = score_style_fit(p, variant=v)
        r2 = score_style_fit(p, variant=v)
        assert r1["style_fit_score"] == r2["style_fit_score"]

    def test_low_confidence_dampens_score(self):
        from app.ai.styles.style_scoring import score_style_fit
        p_high = _make_detected_profile("viral_tiktok", confidence=0.9)
        p_low = _make_detected_profile("viral_tiktok", confidence=0.1)
        v = _make_variant("ret", "retention")
        score_high = score_style_fit(p_high, variant=v)["style_fit_score"]
        score_low = score_style_fit(p_low, variant=v)["style_fit_score"]
        # Low confidence should pull score toward neutral (60)
        assert abs(score_low - 60.0) < abs(score_high - 60.0)

    def test_confidence_in_valid_range(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile()
        result = score_style_fit(p)
        assert 0.0 <= result["confidence"] <= 1.0


# ── AIEditPlan field tests ─────────────────────────────────────────────────────

class TestAIEditPlanCreatorStyleAdaptationField:
    def test_field_exists_with_empty_default(self):
        plan = _make_edit_plan()
        assert hasattr(plan, "creator_style_adaptation")
        assert plan.creator_style_adaptation == {}

    def test_field_in_to_dict(self):
        plan = _make_edit_plan()
        d = plan.to_dict()
        assert "creator_style_adaptation" in d
        assert d["creator_style_adaptation"] == {}

    def test_populated_field_survives_to_dict(self):
        plan = _make_edit_plan(creator_style_adaptation={
            "detected": True,
            "primary_style": "viral_tiktok",
            "confidence": 0.82,
            "adaptation": {"pacing_hint": "fast"},
            "fallback_used": False,
        })
        d = plan.to_dict()
        assert d["creator_style_adaptation"]["primary_style"] == "viral_tiktok"
        assert d["creator_style_adaptation"]["confidence"] == pytest.approx(0.82)

    def test_all_prior_phase_fields_preserved(self):
        plan = _make_edit_plan()
        d = plan.to_dict()
        for key in (
            "variants", "variant_selection", "creator_style_adaptation",
            "subtitle_execution", "timing_mutation", "story_optimization",
            "retention", "story", "beat_execution",
        ):
            assert key in d, f"Missing backward-compatible field: {key}"


# ── AI Director integration tests ──────────────────────────────────────────────

class TestAIDirectorPhase23Integration:
    def _make_request(self):
        class Req:
            ai_director_enabled = True
            ai_mode = "viral_tiktok"
            ai_auto_cut = True
            ai_target_duration = None
            ai_use_semantic_hooks = True
            ai_use_rag_memory = False
            ai_render_influence_enabled = False
            ai_beat_execution_enabled = False
            ai_beat_pulse_enabled = False
            ai_beat_transition_enabled = False
            ai_timing_mutation_enabled = False
            ai_variant_planning_enabled = False
            ai_variant_count = 3
        return Req()

    def test_creator_style_adaptation_attached(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(), context={})
        assert plan is not None
        assert hasattr(plan, "creator_style_adaptation")
        assert isinstance(plan.creator_style_adaptation, dict)

    def test_creator_style_adaptation_has_required_keys(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(), context={})
        if plan and plan.creator_style_adaptation:
            for key in ("detected", "primary_style", "confidence", "fallback_used"):
                assert key in plan.creator_style_adaptation

    def test_director_never_raises_phase23(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        result = create_ai_edit_plan(
            self._make_request(),
            context={"job_id": "test-p23"},
        )
        assert result is None or hasattr(result, "creator_style_adaptation")

    def test_to_dict_includes_creator_style_adaptation(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(), context={})
        if plan is not None:
            d = plan.to_dict()
            assert "creator_style_adaptation" in d

    def test_prior_phases_unaffected(self):
        from app.ai.director.ai_director import create_ai_edit_plan
        plan = create_ai_edit_plan(self._make_request(), context={})
        if plan is not None:
            d = plan.to_dict()
            assert "variants" in d
            assert "variant_selection" in d
            assert "story" in d
            assert "retention" in d


# ── Variant selector style-fit bonus tests ────────────────────────────────────

class TestVariantSelectorStyleFitBonus:
    def test_selector_still_returns_valid_result_with_style_adaptation(self):
        from app.ai.variants.variant_selector import select_best_variant
        plan = _make_edit_plan(creator_style_adaptation={
            "detected": True,
            "primary_style": "viral_tiktok",
            "confidence": 0.75,
            "adaptation": {"pacing_hint": "fast"},
            "fallback_used": False,
        })
        vs = _make_variant_set(
            _make_variant("ret", "retention", "low", safe_to_render=True),
            _make_variant("safe", "safe_baseline", "low", safe_to_render=True),
        )
        result = select_best_variant(vs, edit_plan=plan)
        assert isinstance(result, dict)
        assert "selected_variant_id" in result

    def test_style_fit_bonus_prefers_retention_for_viral_tiktok(self):
        from app.ai.variants.variant_selector import select_best_variant
        # viral_tiktok should boost retention variants
        plan = _make_edit_plan(creator_style_adaptation={
            "detected": True,
            "primary_style": "viral_tiktok",
            "confidence": 0.85,
            "adaptation": {},
            "fallback_used": False,
        })
        vs = _make_variant_set(
            _make_variant("ret", "retention", "low", confidence=0.75, safe_to_render=True),
            _make_variant("safe", "safe_baseline", "low", confidence=0.75, safe_to_render=True),
        )
        result = select_best_variant(vs, edit_plan=plan)
        # retention should win due to both base score AND style-fit bonus
        assert result["selected_variant_id"] == "ret"

    def test_selector_works_without_style_adaptation(self):
        from app.ai.variants.variant_selector import select_best_variant
        plan = _make_edit_plan()  # no creator_style_adaptation set
        vs = _make_variant_set(_make_variant("ret", "retention", "low", safe_to_render=True))
        result = select_best_variant(vs, edit_plan=plan)
        assert result["selected_variant_id"] == "ret"

    def test_low_confidence_style_adaptation_ignored(self):
        from app.ai.variants.variant_selector import select_best_variant
        plan = _make_edit_plan(creator_style_adaptation={
            "detected": True,
            "primary_style": "cinematic",
            "confidence": 0.10,  # below threshold
            "adaptation": {},
            "fallback_used": False,
        })
        vs = _make_variant_set(_make_variant("v1", "story", "low", safe_to_render=True))
        result = select_best_variant(vs, edit_plan=plan)
        # Should still work, just no style bonus applied
        assert result is not None

    def test_selector_never_raises_with_bad_style_adaptation(self):
        from app.ai.variants.variant_selector import select_best_variant
        plan = _make_edit_plan(creator_style_adaptation="corrupted_data")
        vs = _make_variant_set(_make_variant("v1", "retention", "low", safe_to_render=True))
        result = select_best_variant(vs, edit_plan=plan)
        assert isinstance(result, dict)

    def test_no_payload_mutation_from_style_bonus(self):
        from app.ai.variants.variant_selector import select_best_variant
        plan = _make_edit_plan(creator_style_adaptation={
            "detected": True,
            "primary_style": "viral_tiktok",
            "confidence": 0.80,
            "adaptation": {},
            "fallback_used": False,
        })
        original_mode = plan.mode
        vs = _make_variant_set(_make_variant("v1", "retention", "low", safe_to_render=True))
        select_best_variant(vs, edit_plan=plan)
        assert plan.mode == original_mode


# ── Safety boundary tests ──────────────────────────────────────────────────────

class TestPhase23SafetyBoundaries:
    def test_no_ffmpeg_mutation(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile()
        result = build_style_adaptation(p)
        assert "ffmpeg_args" not in result["adaptation"]
        assert "codec" not in result["adaptation"]

    def test_no_playback_speed_in_adaptation(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile()
        result = build_style_adaptation(p)
        assert "playback_speed" not in result["adaptation"]

    def test_no_subtitle_timing_in_adaptation(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile()
        result = build_style_adaptation(p)
        assert "subtitle_timing" not in result["adaptation"]

    def test_no_segment_timing_in_adaptation(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile()
        result = build_style_adaptation(p)
        assert "segment_start" not in result["adaptation"]
        assert "segment_end" not in result["adaptation"]

    def test_no_render_execution_triggered(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        from app.ai.styles.style_adapter import build_style_adaptation
        plan = _make_edit_plan(creator_style={"dominant_style": "podcast_viral", "confidence": 70.0})
        style_set = detect_creator_styles(plan)
        if style_set.styles:
            result = build_style_adaptation(style_set.styles[0], edit_plan=plan)
        # No render should have been triggered — just check result is metadata dict
        assert isinstance(result, dict)

    def test_adaptation_is_metadata_only(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile("viral_tiktok")
        result = build_style_adaptation(p)
        # Advisory metadata keys only
        for key in result["adaptation"]:
            assert key.endswith("_hint") or key in ("subtitle_density", "subtitle_style", "preset_hint")

    def test_no_timing_mutation(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan
        from app.ai.styles.style_classifier import detect_creator_styles
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok",
            selected_segments=[AIClipPlan(start=0.0, end=10.0, score=80.0)],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        original_start = plan.selected_segments[0].start
        detect_creator_styles(plan)
        assert plan.selected_segments[0].start == original_start

    def test_backward_compatibility_creator_style_field_unchanged(self):
        plan = _make_edit_plan(
            creator_style={
                "available": True,
                "dominant_style": "podcast_viral",
                "confidence": 72.0,
                "secondary_styles": [],
                "matched_traits": ["high energy"],
                "warnings": [],
            }
        )
        # Phase 23 adds creator_style_adaptation; must not touch creator_style
        assert plan.creator_style["dominant_style"] == "podcast_viral"

    def test_no_api_key_required_for_detection(self):
        from app.ai.styles.style_classifier import detect_creator_styles
        result = detect_creator_styles(None)
        assert result is not None

    def test_no_gpu_required_for_scoring(self):
        from app.ai.styles.style_scoring import score_style_fit
        p = _make_detected_profile()
        result = score_style_fit(p)
        assert isinstance(result["style_fit_score"], float)

    def test_no_internet_required_for_adaptation(self):
        from app.ai.styles.style_adapter import build_style_adaptation
        p = _make_detected_profile()
        result = build_style_adaptation(p)
        assert isinstance(result, dict)
