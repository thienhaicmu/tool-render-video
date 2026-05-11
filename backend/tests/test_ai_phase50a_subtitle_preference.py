"""
test_ai_phase50a_subtitle_preference.py — Tests for Phase 50A Deep Subtitle Preference Intelligence.

Coverage:
    - Full inference with rich mock data
    - Missing/empty data fallbacks
    - Confidence clamping [0.0, 1.0]
    - Deterministic output (same inputs → same outputs)
    - Allowed value normalization for all dimensions
    - Explainability signals (creator-facing strings, no debug output)
    - No crash on None/empty/garbage input
    - No unsafe internal fields in output
    - Schema dataclass contract
    - Safety module (sanitize + is_preference_safe)
    - Render influence reporting function
"""
from __future__ import annotations

import types
from unittest.mock import MagicMock

import pytest

# ── Helpers ────────────────────────────────────────────────────────────────────

def _make_plan(**kwargs):
    """Return a SimpleNamespace edit plan with given attribute overrides."""
    defaults = dict(
        subtitle_text_apply={},
        subtitle_execution={},
        adaptive_creator_intelligence={},
        creator_feedback_intelligence={},
        market_optimization_intelligence={},
        render_quality_evaluation={},
        creator_preset_evolution={},
        safe_influence_pack={},
        multi_signal_orchestration={},
        creator_subtitle_preference={},
    )
    defaults.update(kwargs)
    return types.SimpleNamespace(**defaults)


def _make_market(target_market: str, subtitle_style: str = "", density: str = "") -> dict:
    return {
        "available": True,
        "market_profile": {
            "target_market": target_market,
            "subtitle_style": subtitle_style,
            "density": density,
        },
    }


def _make_feedback(subtitle_style_pattern: str = "", total_exports: int = 0) -> dict:
    return {
        "available": True,
        "total_exports": total_exports,
        "learned_patterns": {
            "subtitle_style_pattern": subtitle_style_pattern,
            "subtitle_style_count": total_exports,
        },
    }


def _make_influence(style_bias: str = "", density_bias: str = "", tier: str = "strong") -> dict:
    return {
        "available": True,
        "enabled": True,
        "gate": {"passed": True, "tier": tier},
        "safe_influence": {
            "subtitle_style_bias": style_bias,
            "subtitle_density_bias": density_bias,
        },
    }


def _make_orchestration(subtitle_style: str = "", subtitle_density: str = "") -> dict:
    return {
        "available": True,
        "enabled": True,
        "recommended_strategy": {
            "subtitle_style": subtitle_style,
            "subtitle_density": subtitle_density,
        },
    }


def _make_quality(scores: list) -> dict:
    return {
        "available": True,
        "output_scores": scores,
    }


# ── Import helpers ─────────────────────────────────────────────────────────────

from app.ai.creator_subtitle.subtitle_preference_inference import (
    infer_subtitle_preference,
    _map_style,
    _map_density,
    _map_emphasis,
)
from app.ai.creator_subtitle.subtitle_preference_schema import (
    ALLOWED_STYLES, ALLOWED_DENSITIES, ALLOWED_UPPERCASE,
    ALLOWED_EMPHASIS, ALLOWED_MOTION, ALLOWED_CAPTION_BOX, ALLOWED_READABILITY,
    AISubtitlePreference, AISubtitlePreferencePack,
)
from app.ai.creator_subtitle.subtitle_preference_safety import (
    sanitize_preference_data, is_preference_safe,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Class 1 — Full inference (rich data)
# ═══════════════════════════════════════════════════════════════════════════════

class TestFullInference:
    """Verify inference produces expected values given rich signal data."""

    def test_returns_available_true_with_signals(self):
        plan = _make_plan(
            market_optimization_intelligence=_make_market("viral_tiktok", subtitle_style="compact"),
        )
        result = infer_subtitle_preference(plan)
        assert result["available"] is True

    def test_subtitle_preference_key_always_present(self):
        result = infer_subtitle_preference(_make_plan())
        assert "subtitle_preference" in result

    def test_feedback_style_takes_priority_over_market(self):
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback(subtitle_style_pattern="clean_pro"),
            market_optimization_intelligence=_make_market("viral_tiktok", subtitle_style="viral_bold"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["style"] == "clean_pro"

    def test_influence_style_used_when_no_feedback(self):
        plan = _make_plan(
            safe_influence_pack=_make_influence(style_bias="viral_bold"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["style"] == "viral_bold"

    def test_orchestration_style_used_when_no_feedback_or_influence(self):
        plan = _make_plan(
            multi_signal_orchestration=_make_orchestration(subtitle_style="clean_pro"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["style"] == "clean_pro"

    def test_influence_density_lighter_maps_to_light(self):
        plan = _make_plan(
            safe_influence_pack=_make_influence(density_bias="lighter"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["density"] == "light"

    def test_market_tiktok_sets_uppercase_and_motion(self):
        plan = _make_plan(
            market_optimization_intelligence=_make_market("viral_tiktok"),
        )
        result = infer_subtitle_preference(plan)
        pref = result["subtitle_preference"]
        assert pref["uppercase"] == "uppercase"
        assert pref["motion_style"] == "bounce"

    def test_market_podcast_sets_readability_high(self):
        plan = _make_plan(
            market_optimization_intelligence=_make_market("podcast"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["readability_priority"] == "high"

    def test_market_podcast_mobile_safe_false(self):
        plan = _make_plan(
            market_optimization_intelligence=_make_market("podcast"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["mobile_safe"] is False

    def test_tiktok_mobile_safe_true(self):
        plan = _make_plan(
            market_optimization_intelligence=_make_market("viral_tiktok"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["mobile_safe"] is True

    def test_viral_bold_sets_caption_box_none(self):
        plan = _make_plan(
            safe_influence_pack=_make_influence(style_bias="viral_bold"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["caption_box"] == "none"

    def test_clean_pro_sets_caption_box_minimal(self):
        plan = _make_plan(
            safe_influence_pack=_make_influence(style_bias="clean_pro"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["caption_box"] == "minimal"

    def test_boxed_caption_style_sets_caption_box_boxed(self):
        plan = _make_plan(
            safe_influence_pack=_make_influence(style_bias="boxed_caption"),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["caption_box"] == "boxed"

    def test_quality_scores_high_readability(self):
        plan = _make_plan(
            render_quality_evaluation=_make_quality([
                {"subtitle_readability": 0.80},
                {"subtitle_readability": 0.85},
            ]),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["readability_priority"] == "high"

    def test_quality_scores_low_readability(self):
        plan = _make_plan(
            render_quality_evaluation=_make_quality([
                {"subtitle_readability": 0.20},
                {"subtitle_readability": 0.25},
            ]),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["readability_priority"] == "low"

    def test_quality_scores_medium_readability(self):
        plan = _make_plan(
            render_quality_evaluation=_make_quality([
                {"subtitle_readability": 0.55},
            ]),
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["readability_priority"] == "medium"


# ═══════════════════════════════════════════════════════════════════════════════
# Class 2 — Missing / empty data fallbacks
# ═══════════════════════════════════════════════════════════════════════════════

class TestMissingDataFallback:
    """All fields fall back gracefully when data is absent."""

    def test_none_plan_returns_available_false(self):
        result = infer_subtitle_preference(None)
        assert result["available"] is False

    def test_empty_plan_returns_available_true_with_unknowns(self):
        result = infer_subtitle_preference(_make_plan())
        assert result["available"] is True
        pref = result["subtitle_preference"]
        assert pref["style"] == "unknown"
        assert pref["density"] == "unknown"
        assert pref["uppercase"] == "unknown"
        assert pref["keyword_emphasis"] == "unknown"
        assert pref["motion_style"] == "unknown"
        assert pref["caption_box"] == "unknown"
        assert pref["readability_priority"] == "unknown"

    def test_empty_plan_mobile_safe_defaults_true(self):
        result = infer_subtitle_preference(_make_plan())
        assert result["subtitle_preference"]["mobile_safe"] is True

    def test_empty_plan_line_count_defaults_two(self):
        result = infer_subtitle_preference(_make_plan())
        assert result["subtitle_preference"]["line_count"] == 2

    def test_empty_plan_signals_empty_list(self):
        result = infer_subtitle_preference(_make_plan())
        assert result["subtitle_preference"]["signals"] == []

    def test_empty_plan_confidence_zero(self):
        result = infer_subtitle_preference(_make_plan())
        assert result["subtitle_preference"]["confidence"] == 0.0

    def test_plan_with_none_fields_does_not_crash(self):
        plan = _make_plan(
            subtitle_text_apply=None,
            market_optimization_intelligence=None,
            safe_influence_pack=None,
        )
        result = infer_subtitle_preference(plan)
        assert "subtitle_preference" in result

    def test_plan_without_some_attrs_does_not_crash(self):
        plan = types.SimpleNamespace(subtitle_text_apply={})
        result = infer_subtitle_preference(plan)
        assert result["available"] is True

    def test_garbage_dict_values_dont_crash(self):
        plan = _make_plan(
            market_optimization_intelligence={"market_profile": {"target_market": 12345}},
            safe_influence_pack={"safe_influence": {"subtitle_style_bias": None}},
        )
        result = infer_subtitle_preference(plan)
        assert result["available"] is True

    def test_missing_quality_scores_no_crash(self):
        plan = _make_plan(render_quality_evaluation={"available": True, "output_scores": []})
        result = infer_subtitle_preference(plan)
        assert result["available"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# Class 3 — Confidence clamping
# ═══════════════════════════════════════════════════════════════════════════════

class TestConfidenceClamping:
    """Confidence must always be in [0.0, 1.0] and rounded to 2 dp."""

    def test_confidence_not_negative(self):
        result = infer_subtitle_preference(_make_plan())
        assert result["subtitle_preference"]["confidence"] >= 0.0

    def test_confidence_not_above_one(self):
        # Feed all possible signals to try to exceed 1.0
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=100),
            safe_influence_pack=_make_influence(style_bias="clean_pro", density_bias="lighter"),
            multi_signal_orchestration=_make_orchestration("clean_pro", "medium"),
            market_optimization_intelligence=_make_market("viral_tiktok", "compact"),
            render_quality_evaluation=_make_quality([{"subtitle_readability": 0.9}]),
            adaptive_creator_intelligence={
                "adaptive_influences": {"subtitle_enhancement_weight": 0.99},
                "creator_profile": {},
            },
        )
        result = infer_subtitle_preference(plan)
        assert result["subtitle_preference"]["confidence"] <= 1.0

    def test_confidence_rounded_to_two_decimal_places(self):
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=5),
        )
        result = infer_subtitle_preference(plan)
        conf = result["subtitle_preference"]["confidence"]
        assert conf == round(conf, 2)

    def test_confidence_increases_with_more_signals(self):
        empty_plan = _make_plan()
        rich_plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=5),
            safe_influence_pack=_make_influence(density_bias="lighter"),
            market_optimization_intelligence=_make_market("viral_tiktok"),
        )
        empty_conf = infer_subtitle_preference(empty_plan)["subtitle_preference"]["confidence"]
        rich_conf = infer_subtitle_preference(rich_plan)["subtitle_preference"]["confidence"]
        assert rich_conf > empty_conf


# ═══════════════════════════════════════════════════════════════════════════════
# Class 4 — Deterministic output
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeterministicOutput:
    """Identical inputs must produce identical outputs."""

    def _make_rich_plan(self):
        return _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=3),
            safe_influence_pack=_make_influence(density_bias="lighter"),
            market_optimization_intelligence=_make_market("viral_tiktok", "compact"),
            render_quality_evaluation=_make_quality([{"subtitle_readability": 0.75}]),
        )

    def test_same_inputs_produce_same_output(self):
        r1 = infer_subtitle_preference(self._make_rich_plan())
        r2 = infer_subtitle_preference(self._make_rich_plan())
        assert r1 == r2

    def test_empty_plan_always_same(self):
        r1 = infer_subtitle_preference(_make_plan())
        r2 = infer_subtitle_preference(_make_plan())
        assert r1 == r2

    def test_style_inference_stable_across_calls(self):
        plan = _make_plan(
            safe_influence_pack=_make_influence(style_bias="viral_bold"),
        )
        styles = [infer_subtitle_preference(plan)["subtitle_preference"]["style"] for _ in range(5)]
        assert len(set(styles)) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# Class 5 — Allowed value normalization
# ═══════════════════════════════════════════════════════════════════════════════

class TestAllowedValueNormalization:
    """Every dimension must return only its allowed values."""

    def _pref(self, **kwargs):
        return infer_subtitle_preference(_make_plan(**kwargs))["subtitle_preference"]

    def test_style_always_in_allowed_set(self):
        for style_input in ["compact", "viral_bold", "clean_pro", "garbage", "", "VIRAL"]:
            plan = _make_plan(
                safe_influence_pack=_make_influence(style_bias=style_input),
            )
            style = infer_subtitle_preference(plan)["subtitle_preference"]["style"]
            assert style in ALLOWED_STYLES, f"style={style!r} not in ALLOWED_STYLES"

    def test_density_always_in_allowed_set(self):
        for density_input in ["high", "low", "medium", "lighter", "unknown", "garbage"]:
            plan = _make_plan(subtitle_execution={"density": density_input})
            density = infer_subtitle_preference(plan)["subtitle_preference"]["density"]
            assert density in ALLOWED_DENSITIES, f"density={density!r} not in ALLOWED_DENSITIES"

    def test_uppercase_always_in_allowed_set(self):
        for market in ["viral_tiktok", "podcast", "educational", "youtube_shorts", ""]:
            plan = _make_plan(market_optimization_intelligence=_make_market(market))
            uc = infer_subtitle_preference(plan)["subtitle_preference"]["uppercase"]
            assert uc in ALLOWED_UPPERCASE, f"uppercase={uc!r} not in ALLOWED_UPPERCASE"

    def test_keyword_emphasis_always_in_allowed_set(self):
        for emphasis_input in ["none", "subtle", "moderate", "strong", "garbage", ""]:
            plan = _make_plan(subtitle_text_apply={"emphasis_style": emphasis_input})
            ke = infer_subtitle_preference(plan)["subtitle_preference"]["keyword_emphasis"]
            assert ke in ALLOWED_EMPHASIS, f"keyword_emphasis={ke!r} not in ALLOWED_EMPHASIS"

    def test_motion_style_always_in_allowed_set(self):
        for market in ["viral_tiktok", "podcast", "youtube_shorts", ""]:
            plan = _make_plan(market_optimization_intelligence=_make_market(market))
            ms = infer_subtitle_preference(plan)["subtitle_preference"]["motion_style"]
            assert ms in ALLOWED_MOTION, f"motion_style={ms!r} not in ALLOWED_MOTION"

    def test_caption_box_always_in_allowed_set(self):
        for style in ["viral_bold", "clean_pro", "boxed_caption", "unknown"]:
            plan = _make_plan(safe_influence_pack=_make_influence(style_bias=style))
            cb = infer_subtitle_preference(plan)["subtitle_preference"]["caption_box"]
            assert cb in ALLOWED_CAPTION_BOX, f"caption_box={cb!r} not in ALLOWED_CAPTION_BOX"

    def test_readability_priority_always_in_allowed_set(self):
        for score in [0.10, 0.50, 0.80, 0.0]:
            plan = _make_plan(
                render_quality_evaluation=_make_quality([{"subtitle_readability": score}]),
            )
            rp = infer_subtitle_preference(plan)["subtitle_preference"]["readability_priority"]
            assert rp in ALLOWED_READABILITY, f"readability={rp!r} not in ALLOWED_READABILITY"

    def test_line_count_in_range_1_to_3(self):
        for max_words in [3, 6, 12, None]:
            plan = _make_plan(subtitle_execution={"max_words_per_line": max_words})
            lc = infer_subtitle_preference(plan)["subtitle_preference"]["line_count"]
            assert 1 <= lc <= 3, f"line_count={lc} out of expected range"

    def test_mobile_safe_is_boolean(self):
        for market in ["viral_tiktok", "podcast", ""]:
            plan = _make_plan(market_optimization_intelligence=_make_market(market))
            ms = infer_subtitle_preference(plan)["subtitle_preference"]["mobile_safe"]
            assert isinstance(ms, bool)


# ═══════════════════════════════════════════════════════════════════════════════
# Class 6 — Explainability metadata
# ═══════════════════════════════════════════════════════════════════════════════

class TestExplainabilityMetadata:
    """Signals list must be creator-facing strings — no debug output."""

    def test_signals_is_list(self):
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=3),
        )
        result = infer_subtitle_preference(plan)
        assert isinstance(result["subtitle_preference"]["signals"], list)

    def test_signals_bounded_at_five(self):
        # Feed many signals simultaneously
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=10),
            safe_influence_pack=_make_influence(density_bias="lighter"),
            market_optimization_intelligence=_make_market("viral_tiktok", "compact"),
            render_quality_evaluation=_make_quality([{"subtitle_readability": 0.9}]),
            subtitle_execution={"max_words_per_line": 5},
        )
        result = infer_subtitle_preference(plan)
        assert len(result["subtitle_preference"]["signals"]) <= 5

    def test_signals_are_strings(self):
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=3),
            market_optimization_intelligence=_make_market("viral_tiktok"),
        )
        result = infer_subtitle_preference(plan)
        for sig in result["subtitle_preference"]["signals"]:
            assert isinstance(sig, str), f"Signal is not a string: {sig!r}"

    def test_signals_not_empty_when_data_available(self):
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=3),
        )
        result = infer_subtitle_preference(plan)
        assert len(result["subtitle_preference"]["signals"]) > 0

    def test_no_debug_prefixes_in_signals(self):
        """Signals must not expose internal error strings."""
        bad_prefixes = ("error:", "traceback", "exception", "unavailable", "fallback")
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=3),
            market_optimization_intelligence=_make_market("viral_tiktok"),
        )
        result = infer_subtitle_preference(plan)
        for sig in result["subtitle_preference"]["signals"]:
            for prefix in bad_prefixes:
                assert not sig.lower().startswith(prefix), (
                    f"Signal exposes debug output: {sig!r}"
                )

    def test_signals_contain_no_class_names(self):
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro"),
        )
        result = infer_subtitle_preference(plan)
        for sig in result["subtitle_preference"]["signals"]:
            assert "AISubtitle" not in sig
            assert "inference_error" not in sig

    def test_inference_mode_is_metadata_only(self):
        result = infer_subtitle_preference(_make_plan())
        assert result.get("inference_mode") == "metadata_only"


# ═══════════════════════════════════════════════════════════════════════════════
# Class 7 — No crash on edge inputs
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoCrashEdgeInputs:
    """Engine must never raise — always return a usable dict."""

    def test_none_input(self):
        result = infer_subtitle_preference(None)
        assert isinstance(result, dict)
        assert "subtitle_preference" in result

    def test_empty_dict_input(self):
        result = infer_subtitle_preference({})
        assert isinstance(result, dict)

    def test_empty_string_input(self):
        result = infer_subtitle_preference("")
        assert isinstance(result, dict)

    def test_integer_input(self):
        result = infer_subtitle_preference(42)
        assert isinstance(result, dict)

    def test_list_input(self):
        result = infer_subtitle_preference([1, 2, 3])
        assert isinstance(result, dict)

    def test_all_none_field_values(self):
        plan = types.SimpleNamespace(**{
            attr: None for attr in [
                "subtitle_text_apply", "subtitle_execution",
                "adaptive_creator_intelligence", "creator_feedback_intelligence",
                "market_optimization_intelligence", "render_quality_evaluation",
                "creator_preset_evolution", "safe_influence_pack",
                "multi_signal_orchestration",
            ]
        })
        result = infer_subtitle_preference(plan)
        assert isinstance(result, dict)
        assert "subtitle_preference" in result

    def test_deeply_nested_none_values(self):
        plan = _make_plan(
            safe_influence_pack={"safe_influence": None},
            multi_signal_orchestration={"recommended_strategy": None},
            market_optimization_intelligence={"market_profile": None},
        )
        result = infer_subtitle_preference(plan)
        assert isinstance(result, dict)

    def test_malformed_quality_scores(self):
        plan = _make_plan(
            render_quality_evaluation={"output_scores": [None, "bad", 42, {"subtitle_readability": "x"}]},
        )
        result = infer_subtitle_preference(plan)
        assert isinstance(result, dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Class 8 — No unsafe internal fields
# ═══════════════════════════════════════════════════════════════════════════════

class TestNoUnsafeFields:
    """Output must not expose dangerous or internal fields."""

    _FORBIDDEN = {
        "ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
        "subprocess", "executable", "python_code", "shell", "powershell",
        "api_key", "auth_token", "queue_priority", "output_path",
        "rerender", "delete_output",
    }

    def _all_keys(self, d, prefix=""):
        """Recursively collect all dict keys."""
        keys = set()
        if isinstance(d, dict):
            for k, v in d.items():
                keys.add(k)
                keys |= self._all_keys(v, prefix=k)
        return keys

    def test_no_forbidden_keys_in_output(self):
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro", total_exports=5),
            market_optimization_intelligence=_make_market("viral_tiktok"),
        )
        result = infer_subtitle_preference(plan)
        found_keys = self._all_keys(result)
        for forbidden in self._FORBIDDEN:
            assert forbidden not in found_keys, (
                f"Forbidden key {forbidden!r} found in output"
            )

    def test_no_forbidden_keys_empty_plan(self):
        result = infer_subtitle_preference(_make_plan())
        found_keys = self._all_keys(result)
        for forbidden in self._FORBIDDEN:
            assert forbidden not in found_keys

    def test_output_is_serializable(self):
        import json
        plan = _make_plan(
            creator_feedback_intelligence=_make_feedback("clean_pro"),
            market_optimization_intelligence=_make_market("viral_tiktok"),
        )
        result = infer_subtitle_preference(plan)
        # Must not raise
        serialized = json.dumps(result)
        assert len(serialized) > 0


# ═══════════════════════════════════════════════════════════════════════════════
# Class 9 — Schema dataclass contract
# ═══════════════════════════════════════════════════════════════════════════════

class TestSchemaDataclasses:
    """AISubtitlePreference and AISubtitlePreferencePack dataclass contract."""

    def test_preference_defaults(self):
        pref = AISubtitlePreference()
        assert pref.style == "unknown"
        assert pref.density == "unknown"
        assert pref.line_count == 2
        assert pref.uppercase == "unknown"
        assert pref.keyword_emphasis == "unknown"
        assert pref.motion_style == "unknown"
        assert pref.caption_box == "unknown"
        assert pref.readability_priority == "unknown"
        assert pref.mobile_safe is True
        assert pref.confidence == 0.0
        assert pref.signals == []

    def test_preference_to_dict_all_keys(self):
        pref = AISubtitlePreference()
        d = pref.to_dict()
        expected_keys = {
            "style", "density", "line_count", "uppercase", "keyword_emphasis",
            "motion_style", "caption_box", "readability_priority",
            "mobile_safe", "confidence", "signals",
        }
        assert expected_keys == set(d.keys())

    def test_preference_to_dict_confidence_rounded(self):
        pref = AISubtitlePreference(confidence=0.12345678)
        d = pref.to_dict()
        assert d["confidence"] == 0.12

    def test_pack_defaults(self):
        pack = AISubtitlePreferencePack()
        assert pack.available is False
        assert pack.inference_mode == "metadata_only"
        assert pack.warnings == []

    def test_pack_to_dict_all_keys(self):
        pack = AISubtitlePreferencePack(available=True)
        d = pack.to_dict()
        assert "available" in d
        assert "inference_mode" in d
        assert "subtitle_preference" in d
        assert "warnings" in d

    def test_pack_inference_mode_always_metadata_only(self):
        pack = AISubtitlePreferencePack(available=True)
        assert pack.to_dict()["inference_mode"] == "metadata_only"

    def test_allowed_sets_non_empty(self):
        assert len(ALLOWED_STYLES) > 0
        assert len(ALLOWED_DENSITIES) > 0
        assert len(ALLOWED_UPPERCASE) > 0
        assert len(ALLOWED_EMPHASIS) > 0
        assert len(ALLOWED_MOTION) > 0
        assert len(ALLOWED_CAPTION_BOX) > 0
        assert len(ALLOWED_READABILITY) > 0

    def test_unknown_in_every_allowed_set(self):
        assert "unknown" in ALLOWED_STYLES
        assert "unknown" in ALLOWED_DENSITIES
        assert "unknown" in ALLOWED_UPPERCASE
        assert "unknown" in ALLOWED_EMPHASIS
        assert "unknown" in ALLOWED_MOTION
        assert "unknown" in ALLOWED_CAPTION_BOX
        assert "unknown" in ALLOWED_READABILITY


# ═══════════════════════════════════════════════════════════════════════════════
# Class 10 — Safety module
# ═══════════════════════════════════════════════════════════════════════════════

class TestSafetyModule:
    """sanitize_preference_data and is_preference_safe coverage."""

    def test_sanitize_strips_ffmpeg_args(self):
        result = sanitize_preference_data({"ffmpeg_args": "bad", "style": "clean_pro"})
        assert "ffmpeg_args" not in result
        assert result["style"] == "clean_pro"

    def test_sanitize_strips_render_command(self):
        result = sanitize_preference_data({"render_command": "exec", "density": "medium"})
        assert "render_command" not in result

    def test_sanitize_strips_playback_speed(self):
        result = sanitize_preference_data({"playback_speed": 1.5, "style": "viral_bold"})
        assert "playback_speed" not in result

    def test_sanitize_strips_subtitle_timing(self):
        result = sanitize_preference_data({"subtitle_timing": {}, "density": "light"})
        assert "subtitle_timing" not in result

    def test_sanitize_strips_api_key(self):
        result = sanitize_preference_data({"api_key": "secret", "uppercase": "mixed"})
        assert "api_key" not in result

    def test_sanitize_preserves_safe_keys(self):
        safe = {"style": "clean_pro", "density": "medium", "confidence": 0.7}
        result = sanitize_preference_data(safe)
        assert result == safe

    def test_sanitize_handles_non_dict(self):
        assert sanitize_preference_data(None) == {}
        assert sanitize_preference_data("string") == {}
        assert sanitize_preference_data(42) == {}

    def test_sanitize_nested_forbidden_keys(self):
        data = {"subtitle_preference": {"ffmpeg_args": "bad", "style": "clean_pro"}}
        result = sanitize_preference_data(data)
        assert "ffmpeg_args" not in result["subtitle_preference"]
        assert result["subtitle_preference"]["style"] == "clean_pro"

    def test_is_preference_safe_clean_data(self):
        assert is_preference_safe({"style": "clean_pro", "density": "medium"}) is True

    def test_is_preference_safe_forbidden_key(self):
        assert is_preference_safe({"ffmpeg_args": "bad"}) is False

    def test_is_preference_safe_nested_forbidden(self):
        assert is_preference_safe({"pref": {"render_command": "exec"}}) is False

    def test_is_preference_safe_empty(self):
        assert is_preference_safe({}) is True

    def test_is_preference_safe_non_dict_returns_true(self):
        assert is_preference_safe(None) is True
        assert is_preference_safe("string") is True


# ═══════════════════════════════════════════════════════════════════════════════
# Class 11 — Normalisation helper functions
# ═══════════════════════════════════════════════════════════════════════════════

class TestNormalisationHelpers:
    """_map_style, _map_density, _map_emphasis normalisation contracts."""

    def test_map_style_compact_to_clean_pro(self):
        assert _map_style("compact") == "clean_pro"

    def test_map_style_viral_to_viral_bold(self):
        assert _map_style("viral") == "viral_bold"

    def test_map_style_boxed_to_boxed_caption(self):
        assert _map_style("boxed") == "boxed_caption"

    def test_map_style_unknown_passthrough(self):
        assert _map_style("unknown") == "unknown"

    def test_map_style_garbage_to_unknown(self):
        assert _map_style("garbage_style") == "unknown"

    def test_map_style_empty_to_unknown(self):
        assert _map_style("") == "unknown"

    def test_map_density_high_to_dense(self):
        assert _map_density("high") == "dense"

    def test_map_density_low_to_light(self):
        assert _map_density("low") == "light"

    def test_map_density_normal_to_medium(self):
        assert _map_density("normal") == "medium"

    def test_map_density_garbage_to_unknown(self):
        assert _map_density("super_dense_ultra") == "unknown"

    def test_map_emphasis_none_values(self):
        for v in ("none", "off", "disabled"):
            assert _map_emphasis(v) == "none"

    def test_map_emphasis_subtle_values(self):
        for v in ("subtle", "light", "soft"):
            assert _map_emphasis(v) == "subtle"

    def test_map_emphasis_moderate_values(self):
        for v in ("moderate", "medium", "bold"):
            assert _map_emphasis(v) == "moderate"

    def test_map_emphasis_strong_values(self):
        for v in ("strong", "heavy", "aggressive"):
            assert _map_emphasis(v) == "strong"

    def test_map_emphasis_garbage_to_unknown(self):
        assert _map_emphasis("super_vibrant_ultra") == "unknown"


# ═══════════════════════════════════════════════════════════════════════════════
# Class 12 — Render influence reporting
# ═══════════════════════════════════════════════════════════════════════════════

class TestRenderInfluenceReporting:
    """_report_creator_subtitle_preference reports to skipped, never applied."""

    def _get_report_fn(self):
        from app.ai.director.render_influence import _report_creator_subtitle_preference
        return _report_creator_subtitle_preference

    def _make_report(self):
        return {"enabled": True, "applied": [], "skipped": [], "warnings": []}

    def test_no_plan_attr_reports_skipped(self):
        fn = self._get_report_fn()
        plan = types.SimpleNamespace()
        report = self._make_report()
        fn(None, plan, report)
        assert any("creator_subtitle_preference" in s for s in report["skipped"])
        assert report["applied"] == []

    def test_unavailable_plan_reports_skipped(self):
        fn = self._get_report_fn()
        plan = types.SimpleNamespace(creator_subtitle_preference={"available": False})
        report = self._make_report()
        fn(None, plan, report)
        assert any("creator_subtitle_preference" in s for s in report["skipped"])
        assert report["applied"] == []

    def test_available_plan_reports_skipped_not_applied(self):
        fn = self._get_report_fn()
        pref = {
            "available": True,
            "inference_mode": "metadata_only",
            "subtitle_preference": {
                "style": "clean_pro", "density": "medium", "confidence": 0.72,
                "keyword_emphasis": "subtle", "signals": ["Test signal"],
            },
            "warnings": [],
        }
        plan = types.SimpleNamespace(creator_subtitle_preference=pref)
        report = self._make_report()
        fn(None, plan, report)
        assert any("inference_only_phase50a" in s for s in report["skipped"])
        assert report["applied"] == []

    def test_reports_style_and_density(self):
        fn = self._get_report_fn()
        pref = {
            "available": True,
            "inference_mode": "metadata_only",
            "subtitle_preference": {
                "style": "viral_bold", "density": "dense", "confidence": 0.85,
                "keyword_emphasis": "strong", "signals": [],
            },
        }
        plan = types.SimpleNamespace(creator_subtitle_preference=pref)
        report = self._make_report()
        fn(None, plan, report)
        skipped_str = " ".join(report["skipped"])
        assert "viral_bold" in skipped_str
        assert "dense" in skipped_str
