"""
test_ai_phase50c_subtitle_influence.py — Phase 50C Subtitle Preference Safe Influence Tests.

Coverage:
- Confidence gate (low / medium / high tiers)
- All six influence dimensions
- Bounded tuning values (no out-of-range output)
- Deterministic output (same input → same output always)
- Soft tier multiplier (medium confidence → halved adjustments)
- Missing / malformed input handling (never raises)
- No unsafe fields in output
- Render influence reporting format
- Schema dataclass contract
- AISubtitleInfluencePack.to_dict() correctness
"""
from __future__ import annotations

import pytest

from app.ai.creator_subtitle.subtitle_influence_engine import compute_subtitle_influence
from app.ai.creator_subtitle.subtitle_influence_schema import (
    AISubtitleInfluencePack,
    ALLOWED_PRESET_BIAS, ALLOWED_DENSITY_NUDGE, ALLOWED_MOTION_STYLE_BIAS,
    ALLOWED_CONFIDENCE_TIERS,
    EMPHASIS_DELTA_MIN, EMPHASIS_DELTA_MAX,
    PRESET_BIAS_MIN, PRESET_BIAS_MAX,
    MOBILE_NUDGE_MIN, MOBILE_NUDGE_MAX,
    LINE_COUNT_BIAS_MIN, LINE_COUNT_BIAS_MAX,
    SOFT_TIER_MULTIPLIER,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal valid preference packs
# ---------------------------------------------------------------------------

def _pack(
    style="clean_pro",
    density="medium",
    line_count=2,
    uppercase="mixed",
    keyword_emphasis="moderate",
    motion_style="clean",
    caption_box="minimal",
    readability_priority="high",
    mobile_safe=True,
    confidence=0.90,
):
    return {
        "available": True,
        "inference_mode": "metadata_only",
        "subtitle_preference": {
            "style": style,
            "density": density,
            "line_count": line_count,
            "uppercase": uppercase,
            "keyword_emphasis": keyword_emphasis,
            "motion_style": motion_style,
            "caption_box": caption_box,
            "readability_priority": readability_priority,
            "mobile_safe": mobile_safe,
            "confidence": confidence,
            "signals": [],
        },
        "warnings": [],
    }


def _low()    -> dict: return _pack(confidence=0.50)
def _medium() -> dict: return _pack(confidence=0.80)
def _high()   -> dict: return _pack(confidence=0.92)


# ===========================================================================
# 1. TestConfidenceGate — gate at 0.75 / 0.88
# ===========================================================================

class TestConfidenceGate:

    def test_below_threshold_returns_unavailable(self):
        result = compute_subtitle_influence(_low())
        assert result.available is False

    def test_below_threshold_tier_is_low(self):
        result = compute_subtitle_influence(_low())
        assert result.confidence_tier == "low"

    def test_at_threshold_medium_tier(self):
        result = compute_subtitle_influence(_pack(confidence=0.75))
        assert result.confidence_tier == "medium"

    def test_just_below_threshold_no_influence(self):
        result = compute_subtitle_influence(_pack(confidence=0.74))
        assert result.available is False
        assert result.confidence_tier == "low"

    def test_above_high_threshold_is_high_tier(self):
        result = compute_subtitle_influence(_pack(confidence=0.89))
        assert result.confidence_tier == "high"

    def test_at_high_threshold_boundary(self):
        # Engine uses >= 0.88 for high, so exactly 0.88 is "high"
        result = compute_subtitle_influence(_pack(confidence=0.88))
        assert result.confidence_tier == "high"
        result2 = compute_subtitle_influence(_pack(confidence=0.87))
        assert result2.confidence_tier == "medium"

    def test_zero_confidence_no_influence(self):
        result = compute_subtitle_influence(_pack(confidence=0.0))
        assert result.available is False

    def test_none_pack_returns_safe_default(self):
        result = compute_subtitle_influence(None)
        assert result.available is False
        assert result.confidence_tier == "low"


# ===========================================================================
# 2. TestPresetBias
# ===========================================================================

class TestPresetBias:

    def test_clean_pro_style_sets_preset_bias(self):
        result = compute_subtitle_influence(_high())
        assert result.preset_bias == "clean_pro"
        assert result.preset_bias_strength > 0.0

    def test_viral_bold_style_sets_preset_bias(self):
        result = compute_subtitle_influence(_pack(style="viral_bold", confidence=0.92))
        assert result.preset_bias == "viral_bold"

    def test_boxed_caption_style_sets_preset_bias(self):
        result = compute_subtitle_influence(_pack(style="boxed_caption", confidence=0.92))
        assert result.preset_bias == "boxed_caption"

    def test_unknown_style_no_preset_bias(self):
        result = compute_subtitle_influence(_pack(style="unknown", confidence=0.92))
        assert result.preset_bias in ("unknown", "none")
        assert result.preset_bias_strength == 0.0

    def test_preset_bias_strength_bounded_max(self):
        result = compute_subtitle_influence(_high())
        assert result.preset_bias_strength <= PRESET_BIAS_MAX

    def test_preset_bias_strength_bounded_min(self):
        result = compute_subtitle_influence(_high())
        assert result.preset_bias_strength >= PRESET_BIAS_MIN

    def test_medium_tier_lower_strength_than_high(self):
        r_medium = compute_subtitle_influence(_medium())
        r_high   = compute_subtitle_influence(_high())
        # Same style → medium tier strength should be lower
        assert r_medium.preset_bias_strength <= r_high.preset_bias_strength

    def test_preset_bias_value_in_allowed_set(self):
        for style in ("viral_bold", "clean_pro", "boxed_caption", "unknown"):
            result = compute_subtitle_influence(_pack(style=style, confidence=0.92))
            assert result.preset_bias in ALLOWED_PRESET_BIAS

    def test_low_confidence_no_bias_strength(self):
        result = compute_subtitle_influence(_low())
        assert result.preset_bias_strength == 0.0


# ===========================================================================
# 3. TestDensityNudge
# ===========================================================================

class TestDensityNudge:

    def test_dense_produces_reduce_nudge(self):
        result = compute_subtitle_influence(_pack(density="dense", confidence=0.92))
        assert result.density_nudge == "reduce"

    def test_medium_density_no_nudge(self):
        result = compute_subtitle_influence(_pack(density="medium", confidence=0.92))
        assert result.density_nudge == "none"

    def test_light_density_no_nudge(self):
        result = compute_subtitle_influence(_pack(density="light", confidence=0.92))
        assert result.density_nudge == "none"

    def test_unknown_density_no_nudge(self):
        result = compute_subtitle_influence(_pack(density="unknown", confidence=0.92))
        assert result.density_nudge == "none"

    def test_density_nudge_in_allowed_set(self):
        for density in ("dense", "medium", "light", "unknown"):
            result = compute_subtitle_influence(_pack(density=density, confidence=0.92))
            assert result.density_nudge in ALLOWED_DENSITY_NUDGE

    def test_low_confidence_no_reduce(self):
        # Below confidence threshold → density_nudge must be "none"
        result = compute_subtitle_influence(_pack(density="dense", confidence=0.50))
        assert result.density_nudge == "none"


# ===========================================================================
# 4. TestEmphasisDelta
# ===========================================================================

class TestEmphasisDelta:

    def test_none_emphasis_gives_negative_delta(self):
        result = compute_subtitle_influence(_pack(keyword_emphasis="none", confidence=0.92))
        assert result.emphasis_delta < 0.0

    def test_subtle_emphasis_gives_small_negative_delta(self):
        result = compute_subtitle_influence(_pack(keyword_emphasis="subtle", confidence=0.92))
        assert result.emphasis_delta < 0.0

    def test_moderate_emphasis_gives_positive_delta(self):
        result = compute_subtitle_influence(_pack(keyword_emphasis="moderate", confidence=0.92))
        assert result.emphasis_delta > 0.0

    def test_strong_emphasis_gives_larger_positive_delta(self):
        r_moderate = compute_subtitle_influence(_pack(keyword_emphasis="moderate", confidence=0.92))
        r_strong   = compute_subtitle_influence(_pack(keyword_emphasis="strong",   confidence=0.92))
        assert r_strong.emphasis_delta >= r_moderate.emphasis_delta

    def test_emphasis_delta_bounded_min(self):
        result = compute_subtitle_influence(_pack(keyword_emphasis="none", confidence=0.92))
        assert result.emphasis_delta >= EMPHASIS_DELTA_MIN

    def test_emphasis_delta_bounded_max(self):
        result = compute_subtitle_influence(_pack(keyword_emphasis="strong", confidence=0.92))
        assert result.emphasis_delta <= EMPHASIS_DELTA_MAX

    def test_medium_tier_halves_emphasis_delta(self):
        r_m = compute_subtitle_influence(_pack(keyword_emphasis="strong", confidence=0.80))
        r_h = compute_subtitle_influence(_pack(keyword_emphasis="strong", confidence=0.92))
        # Medium tier uses SOFT_TIER_MULTIPLIER=0.5
        assert abs(r_m.emphasis_delta) <= abs(r_h.emphasis_delta) + 1e-9

    def test_unknown_emphasis_style_fallback(self):
        # viral_bold style with unknown emphasis should give positive delta
        result = compute_subtitle_influence(
            _pack(style="viral_bold", keyword_emphasis="unknown", confidence=0.92)
        )
        assert result.emphasis_delta > 0.0

    def test_clean_pro_unknown_emphasis_gives_negative_delta(self):
        result = compute_subtitle_influence(
            _pack(style="clean_pro", keyword_emphasis="unknown", confidence=0.92)
        )
        assert result.emphasis_delta < 0.0


# ===========================================================================
# 5. TestLineCountBias
# ===========================================================================

class TestLineCountBias:

    def test_line_count_1_gives_negative_bias(self):
        result = compute_subtitle_influence(_pack(line_count=1, confidence=0.92))
        assert result.line_count_bias == -1

    def test_line_count_2_gives_zero_bias(self):
        result = compute_subtitle_influence(_pack(line_count=2, confidence=0.92))
        assert result.line_count_bias == 0

    def test_line_count_3_gives_positive_bias(self):
        result = compute_subtitle_influence(_pack(line_count=3, confidence=0.92))
        assert result.line_count_bias == 1

    def test_line_count_bias_within_bounds(self):
        for lc in (1, 2, 3, 4, 5):
            result = compute_subtitle_influence(_pack(line_count=lc, confidence=0.92))
            assert LINE_COUNT_BIAS_MIN <= result.line_count_bias <= LINE_COUNT_BIAS_MAX

    def test_low_confidence_still_computes_zero_bias(self):
        # Low confidence → no tuning → line_count_bias=0
        result = compute_subtitle_influence(_pack(line_count=1, confidence=0.50))
        assert result.line_count_bias == 0


# ===========================================================================
# 6. TestMotionStyleBias
# ===========================================================================

class TestMotionStyleBias:

    def test_clean_motion_style_maps_correctly(self):
        result = compute_subtitle_influence(_pack(motion_style="clean", confidence=0.92))
        assert result.motion_style_bias == "clean"

    def test_bounce_motion_style_maps_correctly(self):
        result = compute_subtitle_influence(_pack(motion_style="bounce", confidence=0.92))
        assert result.motion_style_bias == "bounce"

    def test_karaoke_motion_style_maps_correctly(self):
        result = compute_subtitle_influence(_pack(motion_style="karaoke", confidence=0.92))
        assert result.motion_style_bias == "karaoke"

    def test_unknown_motion_style_maps_to_unknown(self):
        result = compute_subtitle_influence(_pack(motion_style="unknown", confidence=0.92))
        assert result.motion_style_bias == "unknown"

    def test_motion_style_bias_in_allowed_set(self):
        for ms in ("clean", "bounce", "karaoke", "unknown"):
            result = compute_subtitle_influence(_pack(motion_style=ms, confidence=0.92))
            assert result.motion_style_bias in ALLOWED_MOTION_STYLE_BIAS

    def test_low_confidence_no_motion_bias(self):
        result = compute_subtitle_influence(_pack(motion_style="bounce", confidence=0.50))
        assert result.motion_style_bias == "unknown"


# ===========================================================================
# 7. TestMobileReadabilityNudge
# ===========================================================================

class TestMobileReadabilityNudge:

    def test_high_readability_mobile_safe_gives_nudge(self):
        result = compute_subtitle_influence(
            _pack(readability_priority="high", mobile_safe=True, confidence=0.92)
        )
        assert result.mobile_readability_nudge > 0.0

    def test_high_readability_not_mobile_safe_still_nudge(self):
        result = compute_subtitle_influence(
            _pack(readability_priority="high", mobile_safe=False, confidence=0.92)
        )
        assert result.mobile_readability_nudge > 0.0

    def test_low_readability_not_mobile_safe_zero_nudge(self):
        result = compute_subtitle_influence(
            _pack(readability_priority="low", mobile_safe=False, confidence=0.92)
        )
        assert result.mobile_readability_nudge == 0.0

    def test_mobile_safe_only_gives_small_nudge(self):
        result = compute_subtitle_influence(
            _pack(readability_priority="medium", mobile_safe=True, confidence=0.92)
        )
        assert result.mobile_readability_nudge > 0.0

    def test_nudge_bounded_max(self):
        result = compute_subtitle_influence(
            _pack(readability_priority="high", mobile_safe=True, confidence=0.92)
        )
        assert result.mobile_readability_nudge <= MOBILE_NUDGE_MAX

    def test_nudge_bounded_min(self):
        result = compute_subtitle_influence(_high())
        assert result.mobile_readability_nudge >= MOBILE_NUDGE_MIN

    def test_medium_tier_halves_nudge(self):
        r_m = compute_subtitle_influence(
            _pack(readability_priority="high", mobile_safe=True, confidence=0.80)
        )
        r_h = compute_subtitle_influence(
            _pack(readability_priority="high", mobile_safe=True, confidence=0.92)
        )
        assert r_m.mobile_readability_nudge <= r_h.mobile_readability_nudge + 1e-9


# ===========================================================================
# 8. TestSoftTierMultiplier
# ===========================================================================

class TestSoftTierMultiplier:

    def test_medium_tier_multiplier_is_half(self):
        assert SOFT_TIER_MULTIPLIER == 0.5

    def test_medium_tier_preset_strength_is_halved(self):
        r_m = compute_subtitle_influence(_medium())   # conf=0.80
        r_h = compute_subtitle_influence(_high())     # conf=0.92
        # Both have same style — medium strength should be exactly half of high
        expected_ratio = SOFT_TIER_MULTIPLIER
        if r_h.preset_bias_strength > 0:
            actual_ratio = r_m.preset_bias_strength / r_h.preset_bias_strength
            assert abs(actual_ratio - expected_ratio) < 1e-6

    def test_medium_tier_mobile_nudge_is_halved(self):
        r_m = compute_subtitle_influence(
            _pack(readability_priority="high", mobile_safe=False, confidence=0.80)
        )
        r_h = compute_subtitle_influence(
            _pack(readability_priority="high", mobile_safe=False, confidence=0.92)
        )
        if r_h.mobile_readability_nudge > 0:
            ratio = r_m.mobile_readability_nudge / r_h.mobile_readability_nudge
            assert abs(ratio - SOFT_TIER_MULTIPLIER) < 1e-6

    def test_medium_tier_emphasis_delta_is_halved(self):
        r_m = compute_subtitle_influence(_pack(keyword_emphasis="strong", confidence=0.80))
        r_h = compute_subtitle_influence(_pack(keyword_emphasis="strong", confidence=0.92))
        if abs(r_h.emphasis_delta) > 0:
            ratio = abs(r_m.emphasis_delta) / abs(r_h.emphasis_delta)
            assert abs(ratio - SOFT_TIER_MULTIPLIER) < 1e-6


# ===========================================================================
# 9. TestDeterministicOutput
# ===========================================================================

class TestDeterministicOutput:

    def test_same_input_same_output(self):
        pack = _high()
        r1 = compute_subtitle_influence(pack)
        r2 = compute_subtitle_influence(pack)
        assert r1.to_dict() == r2.to_dict()

    def test_identical_pack_produces_identical_dict(self):
        pack_a = _pack(confidence=0.85, style="viral_bold", density="dense")
        pack_b = _pack(confidence=0.85, style="viral_bold", density="dense")
        assert compute_subtitle_influence(pack_a).to_dict() == compute_subtitle_influence(pack_b).to_dict()

    def test_different_confidence_produces_different_output(self):
        r_low  = compute_subtitle_influence(_low())
        r_high = compute_subtitle_influence(_high())
        assert r_low.available != r_high.available or r_low.confidence_tier != r_high.confidence_tier


# ===========================================================================
# 10. TestBoundedTuning
# ===========================================================================

class TestBoundedTuning:

    def _all_styles_and_emphases(self):
        return [
            (s, e)
            for s in ("viral_bold", "clean_pro", "boxed_caption", "unknown")
            for e in ("none", "subtle", "moderate", "strong", "unknown")
        ]

    def test_emphasis_delta_never_exceeds_max(self):
        for style, emphasis in self._all_styles_and_emphases():
            r = compute_subtitle_influence(_pack(style=style, keyword_emphasis=emphasis, confidence=0.95))
            assert r.emphasis_delta <= EMPHASIS_DELTA_MAX, f"Exceeded max for {style}/{emphasis}"

    def test_emphasis_delta_never_below_min(self):
        for style, emphasis in self._all_styles_and_emphases():
            r = compute_subtitle_influence(_pack(style=style, keyword_emphasis=emphasis, confidence=0.95))
            assert r.emphasis_delta >= EMPHASIS_DELTA_MIN, f"Below min for {style}/{emphasis}"

    def test_preset_bias_strength_always_bounded(self):
        for style in ("viral_bold", "clean_pro", "boxed_caption", "unknown"):
            r = compute_subtitle_influence(_pack(style=style, confidence=0.95))
            assert PRESET_BIAS_MIN <= r.preset_bias_strength <= PRESET_BIAS_MAX

    def test_mobile_nudge_always_bounded(self):
        for readability in ("low", "medium", "high", "unknown"):
            for mobile_safe in (True, False):
                r = compute_subtitle_influence(
                    _pack(readability_priority=readability, mobile_safe=mobile_safe, confidence=0.95)
                )
                assert MOBILE_NUDGE_MIN <= r.mobile_readability_nudge <= MOBILE_NUDGE_MAX

    def test_line_count_bias_always_bounded(self):
        for lc in range(0, 6):
            r = compute_subtitle_influence(_pack(line_count=lc, confidence=0.95))
            assert LINE_COUNT_BIAS_MIN <= r.line_count_bias <= LINE_COUNT_BIAS_MAX


# ===========================================================================
# 11. TestNoCrashEdgeInputs
# ===========================================================================

class TestNoCrashEdgeInputs:

    def test_none_input_does_not_raise(self):
        result = compute_subtitle_influence(None)
        assert isinstance(result, AISubtitleInfluencePack)

    def test_empty_dict_does_not_raise(self):
        result = compute_subtitle_influence({})
        assert isinstance(result, AISubtitleInfluencePack)

    def test_available_false_does_not_raise(self):
        result = compute_subtitle_influence({"available": False})
        assert isinstance(result, AISubtitleInfluencePack)

    def test_missing_subtitle_preference_key(self):
        result = compute_subtitle_influence({"available": True})
        assert isinstance(result, AISubtitleInfluencePack)

    def test_string_input_does_not_raise(self):
        result = compute_subtitle_influence("not a dict")
        assert isinstance(result, AISubtitleInfluencePack)

    def test_int_input_does_not_raise(self):
        result = compute_subtitle_influence(42)
        assert isinstance(result, AISubtitleInfluencePack)

    def test_negative_confidence_does_not_raise(self):
        result = compute_subtitle_influence(_pack(confidence=-1.0))
        assert isinstance(result, AISubtitleInfluencePack)
        assert result.available is False

    def test_confidence_above_1_does_not_raise(self):
        result = compute_subtitle_influence(_pack(confidence=999.0))
        assert isinstance(result, AISubtitleInfluencePack)

    def test_null_style_does_not_raise(self):
        pack = _pack(confidence=0.92)
        pack["subtitle_preference"]["style"] = None
        result = compute_subtitle_influence(pack)
        assert isinstance(result, AISubtitleInfluencePack)

    def test_null_line_count_defaults_gracefully(self):
        pack = _pack(confidence=0.92)
        pack["subtitle_preference"]["line_count"] = None
        result = compute_subtitle_influence(pack)
        assert isinstance(result, AISubtitleInfluencePack)


# ===========================================================================
# 12. TestNoUnsafeFields
# ===========================================================================

class TestNoUnsafeFields:

    FORBIDDEN_KEYS = {
        "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
        "subprocess", "executable", "python_code", "shell", "powershell",
        "api_key", "auth_token", "queue_priority", "output_path", "rerender",
        "delete_output", "crop_coordinates", "direct_transform",
    }

    def _check_no_forbidden(self, d: dict) -> None:
        for key in d:
            assert key.lower() not in self.FORBIDDEN_KEYS, f"Forbidden key in output: {key!r}"
            if isinstance(d[key], dict):
                self._check_no_forbidden(d[key])

    def test_no_forbidden_keys_in_high_confidence_output(self):
        result = compute_subtitle_influence(_high()).to_dict()
        self._check_no_forbidden(result)

    def test_no_forbidden_keys_in_medium_confidence_output(self):
        result = compute_subtitle_influence(_medium()).to_dict()
        self._check_no_forbidden(result)

    def test_no_forbidden_keys_in_low_confidence_output(self):
        result = compute_subtitle_influence(_low()).to_dict()
        self._check_no_forbidden(result)

    def test_no_forbidden_keys_in_none_input_output(self):
        result = compute_subtitle_influence(None).to_dict()
        self._check_no_forbidden(result)


# ===========================================================================
# 13. TestSchemaDataclass
# ===========================================================================

class TestSchemaDataclass:

    def test_default_construction(self):
        pack = AISubtitleInfluencePack()
        assert pack.available is False
        assert pack.confidence_tier == "low"
        assert pack.preset_bias == "unknown"
        assert pack.preset_bias_strength == 0.0
        assert pack.density_nudge == "none"
        assert pack.emphasis_delta == 0.0
        assert pack.line_count_bias == 0
        assert pack.motion_style_bias == "unknown"
        assert pack.mobile_readability_nudge == 0.0
        assert pack.reasoning == []
        assert pack.warnings == []

    def test_to_dict_contains_all_keys(self):
        d = AISubtitleInfluencePack().to_dict()
        expected = {
            "available", "confidence_tier", "preset_bias", "preset_bias_strength",
            "density_nudge", "emphasis_delta", "line_count_bias", "motion_style_bias",
            "mobile_readability_nudge", "reasoning", "warnings",
        }
        assert set(d.keys()) == expected

    def test_to_dict_types_correct(self):
        d = compute_subtitle_influence(_high()).to_dict()
        assert isinstance(d["available"],                bool)
        assert isinstance(d["confidence_tier"],          str)
        assert isinstance(d["preset_bias"],              str)
        assert isinstance(d["preset_bias_strength"],     float)
        assert isinstance(d["density_nudge"],            str)
        assert isinstance(d["emphasis_delta"],           float)
        assert isinstance(d["line_count_bias"],          int)
        assert isinstance(d["motion_style_bias"],        str)
        assert isinstance(d["mobile_readability_nudge"], float)
        assert isinstance(d["reasoning"],                list)
        assert isinstance(d["warnings"],                 list)

    def test_reasoning_capped_at_five(self):
        result = compute_subtitle_influence(_high())
        assert len(result.reasoning) <= 5

    def test_warnings_capped_at_five(self):
        result = compute_subtitle_influence(_high())
        assert len(result.warnings) <= 5

    def test_confidence_tier_in_allowed_set(self):
        for pack in (_low(), _medium(), _high(), None):
            result = compute_subtitle_influence(pack)
            assert result.confidence_tier in ALLOWED_CONFIDENCE_TIERS

    def test_density_nudge_in_allowed_set_always(self):
        for density in ("dense", "medium", "light", "unknown", None):
            pack = _pack(density=density or "unknown", confidence=0.92)
            result = compute_subtitle_influence(pack)
            assert result.density_nudge in ALLOWED_DENSITY_NUDGE

    def test_motion_style_bias_in_allowed_set_always(self):
        for ms in ("clean", "bounce", "karaoke", "unknown", "garbage"):
            pack = _pack(motion_style=ms, confidence=0.92)
            result = compute_subtitle_influence(pack)
            assert result.motion_style_bias in ALLOWED_MOTION_STYLE_BIAS


# ===========================================================================
# 14. TestRenderInfluenceReporting
# ===========================================================================

class TestRenderInfluenceReporting:
    """Smoke-test the render_influence integration."""

    def _fake_edit_plan(self, influence_dict):
        class _Plan:
            creator_subtitle_influence = influence_dict
        return _Plan()

    def _run_report(self, plan):
        from app.ai.director.render_influence import _report_creator_subtitle_influence
        report = {"skipped": [], "applied": [], "warnings": []}
        _report_creator_subtitle_influence(None, plan, report)
        return report

    def test_no_attribute_reports_skipped(self):
        class _Empty: pass
        report = self._run_report(_Empty())
        assert any("creator_subtitle_influence" in s for s in report["skipped"])

    def test_unavailable_influence_reports_skipped(self):
        plan = self._fake_edit_plan({"available": False, "confidence_tier": "low"})
        report = self._run_report(plan)
        assert any("unavailable" in s for s in report["skipped"])

    def test_available_influence_reports_influence_ready(self):
        influence = compute_subtitle_influence(_high()).to_dict()
        plan = self._fake_edit_plan(influence)
        report = self._run_report(plan)
        assert any("influence_ready_phase50c" in s for s in report["skipped"])

    def test_influence_report_contains_tier(self):
        influence = compute_subtitle_influence(_high()).to_dict()
        plan = self._fake_edit_plan(influence)
        report = self._run_report(plan)
        skipped_str = " ".join(report["skipped"])
        assert "tier=" in skipped_str

    def test_influence_never_reports_to_applied(self):
        influence = compute_subtitle_influence(_high()).to_dict()
        plan = self._fake_edit_plan(influence)
        report = self._run_report(plan)
        assert report["applied"] == []
