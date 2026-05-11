"""
test_ai_phase51a_strategy_variants.py — Phase 51A Safe Strategy Variant Generator Tests.

Coverage:
- Full variant generation with complete signals
- Missing creator profile fallback
- Missing market data
- Missing quality data
- Deterministic output order (creator_safe always first)
- Allowed value normalization
- Max 3 variants never exceeded
- Valid variant IDs only
- No unsafe fields in output
- No crash on empty / None inputs
- Schema dataclass correctness
- Render influence reporting format
- Market variant mapping correctness
- Quality variant score derivation
"""
from __future__ import annotations

import types
import pytest

from app.ai.strategy_variants.variant_generator import generate_strategy_variants
from app.ai.strategy_variants.variant_schema import (
    StrategyVariant,
    StrategyVariantPack,
    StrategyVariantSubtitle,
    StrategyVariantCamera,
    StrategyVariantRanking,
    ALLOWED_SUBTITLE_STYLES,
    ALLOWED_SUBTITLE_DENSITY,
    ALLOWED_KEYWORD_EMPHASIS,
    ALLOWED_CAMERA_MOTION,
    ALLOWED_STABILITY_PRIORITY,
    ALLOWED_CROP_AGGRESSIVENESS,
    ALLOWED_RANKING_PRIORITY,
    VALID_VARIANT_IDS,
)


# ---------------------------------------------------------------------------
# Forbidden field names — must not appear anywhere in variant output
# ---------------------------------------------------------------------------

_FORBIDDEN_KEYS = {
    "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
    "subprocess", "executable", "python_code", "shell", "api_key",
    "auth_token", "queue_priority", "output_path", "rerender",
    "segment_start", "segment_end", "delete_output", "overwrite_output",
}


# ---------------------------------------------------------------------------
# Helpers — build mock edit plans
# ---------------------------------------------------------------------------

def _make_plan(**overrides):
    """Build a SimpleNamespace mock edit plan with all Phase 51A-relevant fields."""
    return types.SimpleNamespace(
        creator_preference_profile=overrides.get("profile", _default_profile()),
        market_optimization_intelligence=overrides.get("market", _default_market()),
        render_quality_evaluation=overrides.get("quality", _default_quality()),
    )


def _default_profile(
    style="clean_pro", density="medium", emphasis="moderate",
    motion="smooth_subject", stability="high", crop="low",
    ranking_pref="retention", confidence=0.84,
):
    return {
        "available": True,
        "subtitle": {
            "style": style,
            "density": density,
            "keyword_emphasis": emphasis,
            "readability_priority": "high",
        },
        "camera": {
            "motion_style": motion,
            "stability_priority": stability,
            "crop_aggressiveness": crop,
        },
        "clip": {
            "content_style": "educational",
            "ranking_preference": ranking_pref,
        },
        "confidence": confidence,
        "reasoning": [],
        "conflicts_resolved": [],
        "warnings": [],
    }


def _default_market(target="educational", confidence=0.75):
    return {
        "market_profile": {
            "target_market": target,
            "confidence": confidence,
        }
    }


def _default_quality(sub_r=0.80, cam_s=0.75):
    return {
        "output_scores": [
            {"subtitle_readability": sub_r, "camera_smoothness": cam_s}
        ]
    }


def _all_variant_keys(pack_dict: dict) -> set:
    """Flatten all keys across all variants recursively."""
    keys: set = set()
    for v in pack_dict.get("strategy_variants") or []:
        for k, val in v.items():
            keys.add(k)
            if isinstance(val, dict):
                keys.update(val.keys())
    return keys


# ===========================================================================
# 1. TestFullSignalGeneration — all three signals present
# ===========================================================================

class TestFullSignalGeneration:

    def test_returns_pack_instance(self):
        result = generate_strategy_variants(_make_plan())
        assert isinstance(result, StrategyVariantPack)

    def test_available_true_with_full_signals(self):
        result = generate_strategy_variants(_make_plan())
        assert result.available is True

    def test_generates_three_variants(self):
        result = generate_strategy_variants(_make_plan())
        assert result.variant_count == 3
        assert len(result.strategy_variants) == 3

    def test_first_variant_is_creator_safe(self):
        result = generate_strategy_variants(_make_plan())
        assert result.strategy_variants[0].id == "creator_safe"

    def test_second_variant_is_market_balanced(self):
        result = generate_strategy_variants(_make_plan())
        assert result.strategy_variants[1].id == "market_balanced"

    def test_third_variant_is_quality_focused(self):
        result = generate_strategy_variants(_make_plan())
        assert result.strategy_variants[2].id == "quality_focused"

    def test_generation_mode_is_candidate_only(self):
        result = generate_strategy_variants(_make_plan())
        assert result.generation_mode == "candidate_only"

    def test_to_dict_available_true(self):
        d = generate_strategy_variants(_make_plan()).to_dict()
        assert d["available"] is True

    def test_to_dict_has_strategy_variants_list(self):
        d = generate_strategy_variants(_make_plan()).to_dict()
        assert isinstance(d["strategy_variants"], list)
        assert len(d["strategy_variants"]) == 3

    def test_to_dict_variant_count_matches(self):
        d = generate_strategy_variants(_make_plan()).to_dict()
        assert d["variant_count"] == len(d["strategy_variants"])


# ===========================================================================
# 2. TestCreatorSafeVariant
# ===========================================================================

class TestCreatorSafeVariant:

    def _variant(self, **kwargs):
        result = generate_strategy_variants(_make_plan(**kwargs))
        return result.strategy_variants[0]

    def test_id_is_creator_safe(self):
        assert self._variant().id == "creator_safe"

    def test_label_is_creator_safe(self):
        assert self._variant().label == "Creator Safe"

    def test_intent_preserves_creator(self):
        assert "creator" in self._variant().intent.lower()

    def test_subtitle_style_from_profile(self):
        assert self._variant().subtitle.style == "clean_pro"

    def test_subtitle_density_from_profile(self):
        assert self._variant().subtitle.density == "medium"

    def test_keyword_emphasis_from_profile(self):
        assert self._variant().subtitle.keyword_emphasis == "moderate"

    def test_camera_motion_from_profile(self):
        assert self._variant().camera.motion_style == "smooth_subject"

    def test_camera_stability_from_profile(self):
        assert self._variant().camera.stability_priority == "high"

    def test_camera_crop_from_profile(self):
        assert self._variant().camera.crop_aggressiveness == "low"

    def test_ranking_reflects_clip_preference(self):
        # Default clip ranking_preference is "retention"
        assert self._variant().ranking.priority == "retention"

    def test_unknown_ranking_falls_back_to_creator_fit(self):
        profile = _default_profile(ranking_pref="unknown")
        plan = _make_plan(profile=profile)
        v = generate_strategy_variants(plan).strategy_variants[0]
        assert v.ranking.priority == "creator_fit"

    def test_confidence_from_profile(self):
        v = self._variant()
        assert abs(v.confidence - 0.84) < 0.01

    def test_has_reasoning(self):
        assert len(self._variant().reasoning) > 0

    def test_to_dict_confidence_rounded(self):
        d = generate_strategy_variants(_make_plan()).to_dict()
        conf = d["strategy_variants"][0]["confidence"]
        assert isinstance(conf, float)
        assert 0.0 <= conf <= 1.0


# ===========================================================================
# 3. TestMarketBalancedVariant
# ===========================================================================

class TestMarketBalancedVariant:

    def _variant(self, target="educational"):
        plan = _make_plan(market=_default_market(target=target))
        variants = generate_strategy_variants(plan).strategy_variants
        for v in variants:
            if v.id == "market_balanced":
                return v
        return None

    def test_market_balanced_present(self):
        assert self._variant() is not None

    def test_id_is_market_balanced(self):
        assert self._variant().id == "market_balanced"

    def test_label_is_market_balanced(self):
        assert self._variant().label == "Market Balanced"

    def test_tiktok_gives_viral_bold(self):
        v = self._variant(target="tiktok")
        assert v.subtitle.style == "viral_bold"

    def test_tiktok_gives_dense_density(self):
        v = self._variant(target="tiktok")
        assert v.subtitle.density == "dense"

    def test_tiktok_gives_strong_emphasis(self):
        v = self._variant(target="tiktok")
        assert v.subtitle.keyword_emphasis == "strong"

    def test_tiktok_gives_dynamic_camera(self):
        v = self._variant(target="tiktok")
        assert v.camera.motion_style == "dynamic_subject"

    def test_educational_gives_clean_pro(self):
        v = self._variant(target="educational")
        assert v.subtitle.style == "clean_pro"

    def test_educational_gives_light_density(self):
        v = self._variant(target="educational")
        assert v.subtitle.density == "light"

    def test_educational_gives_subtle_emphasis(self):
        v = self._variant(target="educational")
        assert v.subtitle.keyword_emphasis == "subtle"

    def test_educational_gives_static_camera(self):
        v = self._variant(target="educational")
        assert v.camera.motion_style == "static_center"

    def test_youtube_gives_clean_pro(self):
        v = self._variant(target="youtube")
        assert v.subtitle.style == "clean_pro"

    def test_youtube_gives_smooth_camera(self):
        v = self._variant(target="youtube")
        assert v.camera.motion_style == "smooth_subject"

    def test_market_variant_stability_is_medium(self):
        assert self._variant().camera.stability_priority == "medium"

    def test_market_variant_crop_is_medium(self):
        assert self._variant().camera.crop_aggressiveness == "medium"

    def test_confidence_is_discounted_from_market(self):
        v = self._variant()
        # Market confidence 0.75 → 0.70 after 0.05 discount
        assert v.confidence <= 0.75

    def test_no_market_variant_when_no_market(self):
        plan = _make_plan(market={})
        variants = generate_strategy_variants(plan).strategy_variants
        ids = [v.id for v in variants]
        assert "market_balanced" not in ids

    def test_no_market_variant_when_target_unknown(self):
        plan = _make_plan(market={"market_profile": {"target_market": "unknown"}})
        ids = [v.id for v in generate_strategy_variants(plan).strategy_variants]
        assert "market_balanced" not in ids


# ===========================================================================
# 4. TestQualityFocusedVariant
# ===========================================================================

class TestQualityFocusedVariant:

    def _variant(self, sub_r=0.80, cam_s=0.75):
        plan = _make_plan(quality=_default_quality(sub_r=sub_r, cam_s=cam_s))
        for v in generate_strategy_variants(plan).strategy_variants:
            if v.id == "quality_focused":
                return v
        return None

    def test_quality_focused_present(self):
        assert self._variant() is not None

    def test_id_is_quality_focused(self):
        assert self._variant().id == "quality_focused"

    def test_high_readability_gives_clean_pro(self):
        v = self._variant(sub_r=0.80)
        assert v.subtitle.style == "clean_pro"

    def test_high_readability_gives_light_density(self):
        v = self._variant(sub_r=0.80)
        assert v.subtitle.density == "light"

    def test_high_readability_gives_subtle_emphasis(self):
        v = self._variant(sub_r=0.80)
        assert v.subtitle.keyword_emphasis == "subtle"

    def test_low_readability_gives_unknown_style(self):
        v = self._variant(sub_r=0.40)
        assert v.subtitle.style == "unknown"

    def test_good_cam_gives_smooth_subject(self):
        v = self._variant(cam_s=0.75)
        assert v.camera.motion_style == "smooth_subject"

    def test_low_cam_gives_static_center(self):
        v = self._variant(cam_s=0.20)
        assert v.camera.motion_style == "static_center"

    def test_stability_priority_is_high(self):
        assert self._variant().camera.stability_priority == "high"

    def test_crop_aggressiveness_is_low(self):
        assert self._variant().camera.crop_aggressiveness == "low"

    def test_ranking_priority_is_readability(self):
        assert self._variant().ranking.priority == "readability"

    def test_confidence_from_quality_scores(self):
        v = self._variant(sub_r=0.80, cam_s=0.70)
        assert v.confidence > 0.0

    def test_confidence_clamped_to_one(self):
        v = self._variant(sub_r=1.0, cam_s=1.0)
        assert v.confidence <= 1.0

    def test_no_quality_variant_when_no_scores(self):
        plan = _make_plan(quality={})
        ids = [v.id for v in generate_strategy_variants(plan).strategy_variants]
        assert "quality_focused" not in ids

    def test_no_quality_variant_when_empty_scores(self):
        plan = _make_plan(quality={"output_scores": []})
        ids = [v.id for v in generate_strategy_variants(plan).strategy_variants]
        assert "quality_focused" not in ids


# ===========================================================================
# 5. TestFallbackBehavior — missing / unavailable creator profile
# ===========================================================================

class TestFallbackBehavior:

    def test_unavailable_profile_gives_fallback_creator_safe(self):
        plan = _make_plan(profile={"available": False})
        result = generate_strategy_variants(plan)
        assert result.strategy_variants[0].id == "creator_safe"
        assert result.strategy_variants[0].confidence == 0.0

    def test_empty_profile_gives_fallback_creator_safe(self):
        plan = _make_plan(profile={})
        result = generate_strategy_variants(plan)
        assert result.strategy_variants[0].id == "creator_safe"

    def test_fallback_intent_contains_fallback(self):
        plan = _make_plan(profile={"available": False})
        v = generate_strategy_variants(plan).strategy_variants[0]
        assert "fallback" in v.intent.lower() or "conservative" in v.intent.lower()

    def test_fallback_warning_in_warnings(self):
        plan = _make_plan(profile={"available": False})
        result = generate_strategy_variants(plan)
        assert any("fallback" in w for w in result.warnings)

    def test_none_plan_returns_unavailable_pack(self):
        result = generate_strategy_variants(None)
        assert result.available is False

    def test_none_plan_still_returns_pack(self):
        result = generate_strategy_variants(None)
        assert isinstance(result, StrategyVariantPack)

    def test_fallback_ranking_is_balanced(self):
        plan = _make_plan(profile={"available": False})
        v = generate_strategy_variants(plan).strategy_variants[0]
        assert v.ranking.priority == "balanced"

    def test_no_crash_on_garbage_plan(self):
        result = generate_strategy_variants("garbage")
        assert isinstance(result, StrategyVariantPack)

    def test_no_crash_on_empty_namespace(self):
        result = generate_strategy_variants(types.SimpleNamespace())
        assert isinstance(result, StrategyVariantPack)


# ===========================================================================
# 6. TestAllowedValues — every variant field within frozenset allowlists
# ===========================================================================

class TestAllowedValues:

    def _all_variants(self):
        return generate_strategy_variants(_make_plan()).strategy_variants

    def test_subtitle_styles_allowed(self):
        for v in self._all_variants():
            assert v.subtitle.style in ALLOWED_SUBTITLE_STYLES

    def test_subtitle_density_allowed(self):
        for v in self._all_variants():
            assert v.subtitle.density in ALLOWED_SUBTITLE_DENSITY

    def test_keyword_emphasis_allowed(self):
        for v in self._all_variants():
            assert v.subtitle.keyword_emphasis in ALLOWED_KEYWORD_EMPHASIS

    def test_camera_motion_allowed(self):
        for v in self._all_variants():
            assert v.camera.motion_style in ALLOWED_CAMERA_MOTION

    def test_stability_priority_allowed(self):
        for v in self._all_variants():
            assert v.camera.stability_priority in ALLOWED_STABILITY_PRIORITY

    def test_crop_aggressiveness_allowed(self):
        for v in self._all_variants():
            assert v.camera.crop_aggressiveness in ALLOWED_CROP_AGGRESSIVENESS

    def test_ranking_priority_allowed(self):
        for v in self._all_variants():
            assert v.ranking.priority in ALLOWED_RANKING_PRIORITY

    def test_variant_ids_valid(self):
        for v in self._all_variants():
            assert v.id in VALID_VARIANT_IDS

    def test_arbitrary_profile_style_normalized_to_unknown(self):
        profile = _default_profile(style="INVALID_STYLE_XYZ")
        plan = _make_plan(profile=profile)
        v = generate_strategy_variants(plan).strategy_variants[0]
        assert v.subtitle.style == "unknown"

    def test_arbitrary_camera_normalized_to_unknown(self):
        profile = _default_profile(motion="INVALID_MOTION_XYZ")
        plan = _make_plan(profile=profile)
        v = generate_strategy_variants(plan).strategy_variants[0]
        assert v.camera.motion_style == "unknown"


# ===========================================================================
# 7. TestMaxVariants
# ===========================================================================

class TestMaxVariants:

    def test_max_three_with_all_signals(self):
        result = generate_strategy_variants(_make_plan())
        assert len(result.strategy_variants) <= 3

    def test_to_dict_max_three(self):
        d = generate_strategy_variants(_make_plan()).to_dict()
        assert len(d["strategy_variants"]) <= 3

    def test_variant_count_matches_list_length(self):
        result = generate_strategy_variants(_make_plan())
        assert result.variant_count == len(result.strategy_variants)


# ===========================================================================
# 8. TestDeterminism
# ===========================================================================

class TestDeterminism:

    def test_same_input_same_output(self):
        plan = _make_plan()
        r1 = generate_strategy_variants(plan).to_dict()
        r2 = generate_strategy_variants(plan).to_dict()
        assert r1 == r2

    def test_same_input_same_variant_order(self):
        plan = _make_plan()
        ids1 = [v.id for v in generate_strategy_variants(plan).strategy_variants]
        ids2 = [v.id for v in generate_strategy_variants(plan).strategy_variants]
        assert ids1 == ids2

    def test_creator_safe_always_first(self):
        plan = _make_plan()
        for _ in range(3):
            result = generate_strategy_variants(plan)
            assert result.strategy_variants[0].id == "creator_safe"


# ===========================================================================
# 9. TestNoUnsafeFields
# ===========================================================================

class TestNoUnsafeFields:

    def test_no_forbidden_keys_full_signals(self):
        d = generate_strategy_variants(_make_plan()).to_dict()
        assert not _FORBIDDEN_KEYS.intersection(_all_variant_keys(d))

    def test_no_forbidden_keys_fallback(self):
        d = generate_strategy_variants(_make_plan(profile={})).to_dict()
        assert not _FORBIDDEN_KEYS.intersection(_all_variant_keys(d))

    def test_no_forbidden_keys_none_input(self):
        d = generate_strategy_variants(None).to_dict()
        assert not _FORBIDDEN_KEYS.intersection(_all_variant_keys(d))

    def test_generation_mode_is_candidate_only(self):
        d = generate_strategy_variants(_make_plan()).to_dict()
        assert d["generation_mode"] == "candidate_only"


# ===========================================================================
# 10. TestSchemaDataclass
# ===========================================================================

class TestSchemaDataclass:

    def test_strategy_variant_default_construction(self):
        v = StrategyVariant(id="creator_safe", label="Creator Safe", intent="test")
        assert v.confidence == 0.0
        assert v.reasoning == []

    def test_strategy_variant_pack_default(self):
        p = StrategyVariantPack()
        assert p.available is False
        assert p.strategy_variants == []
        assert p.variant_count == 0

    def test_variant_to_dict_has_required_keys(self):
        v = StrategyVariant(id="creator_safe", label="Creator Safe", intent="test")
        d = v.to_dict()
        for k in ("id", "label", "intent", "subtitle", "camera", "ranking", "confidence", "reasoning"):
            assert k in d

    def test_pack_to_dict_has_required_keys(self):
        p = StrategyVariantPack()
        d = p.to_dict()
        for k in ("available", "strategy_variants", "variant_count", "generation_mode", "warnings"):
            assert k in d

    def test_confidence_clamped_below_zero(self):
        v = StrategyVariant(id="creator_safe", label="L", intent="t", confidence=-0.5)
        assert v.to_dict()["confidence"] == 0.0

    def test_confidence_clamped_above_one(self):
        v = StrategyVariant(id="creator_safe", label="L", intent="t", confidence=1.5)
        assert v.to_dict()["confidence"] == 1.0

    def test_reasoning_capped_at_three(self):
        v = StrategyVariant(
            id="creator_safe", label="L", intent="t",
            reasoning=["a", "b", "c", "d", "e"],
        )
        assert len(v.to_dict()["reasoning"]) <= 3

    def test_pack_to_dict_variants_capped_at_three(self):
        variants = [
            StrategyVariant(id=f"creator_safe", label="L", intent="t")
            for _ in range(5)
        ]
        p = StrategyVariantPack(available=True, strategy_variants=variants, variant_count=5)
        assert len(p.to_dict()["strategy_variants"]) <= 3

    def test_subtitle_to_dict_keys(self):
        s = StrategyVariantSubtitle()
        d = s.to_dict()
        assert set(d.keys()) == {"style", "density", "keyword_emphasis"}

    def test_camera_to_dict_keys(self):
        c = StrategyVariantCamera()
        d = c.to_dict()
        assert set(d.keys()) == {"motion_style", "stability_priority", "crop_aggressiveness"}

    def test_ranking_to_dict_keys(self):
        r = StrategyVariantRanking()
        d = r.to_dict()
        assert set(d.keys()) == {"priority"}


# ===========================================================================
# 11. TestRenderInfluenceReporting
# ===========================================================================

class TestRenderInfluenceReporting:

    def _make_edit_plan_with_sv(self, sv_dict):
        return types.SimpleNamespace(strategy_variants=sv_dict)

    def _run_report(self, sv_dict):
        from app.ai.director.render_influence import _report_strategy_variants
        report = {"applied": [], "skipped": [], "warnings": []}
        plan = self._make_edit_plan_with_sv(sv_dict)
        _report_strategy_variants(None, plan, report)
        return report

    def test_unavailable_reports_not_generated(self):
        report = self._run_report({"available": False})
        assert any("not_generated_phase51a" in s for s in report["skipped"])

    def test_empty_dict_reports_not_generated(self):
        report = self._run_report({})
        assert any("not_generated_phase51a" in s for s in report["skipped"])

    def test_no_attribute_reports_not_generated(self):
        from app.ai.director.render_influence import _report_strategy_variants
        report = {"applied": [], "skipped": [], "warnings": []}
        plan = types.SimpleNamespace()
        _report_strategy_variants(None, plan, report)
        assert any("not_generated_phase51a" in s for s in report["skipped"])

    def test_available_reports_generated_phase51a(self):
        sv = generate_strategy_variants(_make_plan()).to_dict()
        report = self._run_report(sv)
        assert any("generated_phase51a" in s for s in report["skipped"])

    def test_report_contains_count(self):
        sv = generate_strategy_variants(_make_plan()).to_dict()
        report = self._run_report(sv)
        entry = next(s for s in report["skipped"] if "generated_phase51a" in s)
        assert "count=" in entry

    def test_report_contains_ids(self):
        sv = generate_strategy_variants(_make_plan()).to_dict()
        report = self._run_report(sv)
        entry = next(s for s in report["skipped"] if "generated_phase51a" in s)
        assert "ids=" in entry

    def test_never_reports_to_applied(self):
        sv = generate_strategy_variants(_make_plan()).to_dict()
        report = self._run_report(sv)
        assert report["applied"] == []
