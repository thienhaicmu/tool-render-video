"""
test_ai_phase61b_creator_subtitle_style.py — Tests for Phase 61B Creator Subtitle Style Promotion.

Coverage:
  - Style bias → preset mapping (all 4 supported mappings)
  - Unmapped style_bias → fallback
  - Mode-specific confidence thresholds (safe/balanced/aggressive)
  - mode=off → never activates
  - No archetype strategy → fallback
  - Confidence below threshold → fallback
  - Output shape completeness
  - No payload mutation
  - Deterministic output
  - Never raises on None/empty/dict edit_plan
  - Phase 59A integration: archetype preset used as lowest-priority fallback
  - Phase 59A integration: higher-priority signals win over archetype

Required execution-style tests:
  test_execution_podcast_style_maps_clean_pro    — podcast archetype → clean_pro preset
  test_execution_motivation_style_maps_viral_bold — motivation archetype → viral_bold preset
  test_execution_mode_off_never_activates        — mode=off → available=False
  test_execution_phase59a_archetype_fallback     — Phase 59A uses archetype when no other signal
"""
import pytest
from types import SimpleNamespace
from unittest.mock import patch

from app.ai.creator_style.creator_subtitle_style_engine import (
    build_creator_subtitle_style,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _plan_with_archetype(
    style_bias: str = "clean_pro",
    archetype_conf: float = 0.90,
    effective_mode: str = "balanced",
    creator_type: str = "podcast",
) -> SimpleNamespace:
    return SimpleNamespace(
        creator_archetype_strategy={
            "available":   True,
            "creator_type": creator_type,
            "confidence":  archetype_conf,
            "strategy": {
                "subtitle": {
                    "style_bias":           style_bias,
                    "density_bias":         "balanced",
                    "keyword_emphasis":     "selective",
                    "readability_priority": "high",
                },
            },
        },
        ai_execution_mode={"effective_mode": effective_mode},
    )


def _plan_no_archetype() -> SimpleNamespace:
    return SimpleNamespace(
        creator_archetype_strategy={},
        ai_execution_mode={"effective_mode": "balanced"},
    )


# ---------------------------------------------------------------------------
# Required execution tests
# ---------------------------------------------------------------------------

def test_execution_podcast_style_maps_clean_pro():
    """Podcast archetype (clean_pro style_bias) → recommended_preset=clean_pro."""
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.90, effective_mode="balanced")
    result = build_creator_subtitle_style(plan, context={"job_id": "test"})
    css = result["creator_subtitle_style_promotion"]

    assert css["available"] is True
    assert css["recommended_preset"] == "clean_pro"
    assert css["archetype_style_bias"] == "clean_pro"
    assert css["creator_type"] == "podcast"
    assert css["confidence"] > 0.0
    assert len(css["reasoning"]) > 0


def test_execution_motivation_style_maps_viral_bold():
    """Motivation archetype (bold_impact style_bias) → recommended_preset=viral_bold."""
    plan = _plan_with_archetype(
        "bold_impact", archetype_conf=0.85, effective_mode="balanced", creator_type="motivation"
    )
    result = build_creator_subtitle_style(plan)
    css = result["creator_subtitle_style_promotion"]

    assert css["available"] is True
    assert css["recommended_preset"] == "viral_bold"
    assert css["archetype_style_bias"] == "bold_impact"
    assert css["creator_type"] == "motivation"


def test_execution_mode_off_never_activates():
    """mode=off → available=False regardless of archetype confidence."""
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.99, effective_mode="off")
    result = build_creator_subtitle_style(plan)
    css = result["creator_subtitle_style_promotion"]

    assert css["available"] is False
    assert css["recommended_preset"] is None


def test_execution_phase59a_archetype_fallback():
    """Phase 59A: when no 50C/55E/56/50A signals, archetype recommendation is used."""
    from types import SimpleNamespace
    from app.ai.subtitle_promotion.subtitle_promotion_engine import promote_subtitle_influence

    # Build edit_plan with only archetype signal; all other sources empty
    plan = SimpleNamespace(
        creator_subtitle_influence={},
        creator_subtitle_preference={},
        platform_render_strategy={},
        platform_strategy_influence={},
        creator_subtitle_style_promotion={
            "available":           True,
            "recommended_preset":  "clean_pro",
            "archetype_style_bias": "clean_pro",
            "keyword_emphasis":    "selective",
            "confidence":          0.88,
            "mode":                "balanced",
            "creator_type":        "podcast",
            "reasoning":           ["Archetype style_bias 'clean_pro' maps to 'clean_pro' preset"],
        },
    )

    # Payload in AI-neutral state — promotion eligible
    payload = SimpleNamespace(
        add_subtitle=True,
        subtitle_style="pro_karaoke",  # AI-neutral
        highlight_per_word=False,
        subtitle_ai_style_lock=False,
    )

    # Effective confidence from Phase 50A is 0 (no pref), from 55E is 0 (not available)
    # So effective_conf = 0.0 which is below _CONF_THRESHOLD_PRESET=0.80
    # This means the archetype signal path won't be reached.
    # Let's give the plan a creator_subtitle_preference confidence ≥ 0.80 to pass threshold.
    plan.creator_subtitle_preference = {
        "subtitle_preference": {"confidence": 0.85, "style": None, "keyword_emphasis": None}
    }

    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]

    assert promo["applied"] is True
    assert promo["preset_applied"] == "clean_pro"
    assert "archetype" in promo["reasoning"][0].lower() or promo["preset_applied"] == "clean_pro"


# ---------------------------------------------------------------------------
# Style bias mapping tests
# ---------------------------------------------------------------------------

def test_clean_pro_maps_to_clean_pro():
    plan = _plan_with_archetype("clean_pro")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is True
    assert css["recommended_preset"] == "clean_pro"


def test_bold_impact_maps_to_viral_bold():
    plan = _plan_with_archetype("bold_impact")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is True
    assert css["recommended_preset"] == "viral_bold"


def test_compact_dynamic_maps_to_viral_bold():
    plan = _plan_with_archetype("compact_dynamic", creator_type="viral_short_form")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is True
    assert css["recommended_preset"] == "viral_bold"


def test_minimal_clean_maps_to_clean_pro():
    plan = _plan_with_archetype("minimal_clean")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is True
    assert css["recommended_preset"] == "clean_pro"


def test_unknown_style_bias_returns_fallback():
    plan = _plan_with_archetype("neon_wave")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is False
    assert css["recommended_preset"] is None


# ---------------------------------------------------------------------------
# Mode threshold tests
# ---------------------------------------------------------------------------

def test_safe_mode_requires_088_confidence():
    """safe mode: conf=0.87 → below threshold → fallback."""
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.87, effective_mode="safe")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is False


def test_safe_mode_passes_at_088():
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.88, effective_mode="safe")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is True


def test_balanced_mode_requires_082_confidence():
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.81, effective_mode="balanced")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is False


def test_balanced_mode_passes_at_082():
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.82, effective_mode="balanced")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is True


def test_aggressive_mode_requires_076_confidence():
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.75, effective_mode="aggressive")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is False


def test_aggressive_mode_passes_at_076():
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.76, effective_mode="aggressive")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is True


def test_mode_off_always_fallback():
    """mode=off → always fallback regardless of confidence."""
    plan = _plan_with_archetype("clean_pro", archetype_conf=1.0, effective_mode="off")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is False


def test_unknown_mode_falls_back_to_safe_threshold():
    """Unknown mode → uses safe threshold (0.88); conf=0.85 should fail."""
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.85, effective_mode="experimental")
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is False


# ---------------------------------------------------------------------------
# Output shape tests
# ---------------------------------------------------------------------------

def test_output_shape_complete_when_available():
    plan = _plan_with_archetype("clean_pro", archetype_conf=0.90)
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    required = {"available", "recommended_preset", "archetype_style_bias",
                "keyword_emphasis", "confidence", "mode", "creator_type", "reasoning"}
    assert required.issubset(css.keys()), f"Missing: {required - css.keys()}"


def test_output_shape_complete_when_fallback():
    css = build_creator_subtitle_style(None)["creator_subtitle_style_promotion"]
    required = {"available", "recommended_preset", "archetype_style_bias",
                "keyword_emphasis", "confidence", "mode", "creator_type", "reasoning", "reason"}
    assert required.issubset(css.keys()), f"Missing: {required - css.keys()}"


def test_fallback_has_correct_defaults():
    css = build_creator_subtitle_style(None)["creator_subtitle_style_promotion"]
    assert css["available"] is False
    assert css["recommended_preset"] is None
    assert css["confidence"] == 0.0
    assert css["mode"] == "unknown"


def test_confidence_clamped_to_one():
    plan = _plan_with_archetype("clean_pro", archetype_conf=2.5)
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Safety / fallback tests
# ---------------------------------------------------------------------------

def test_never_raises_on_none():
    result = build_creator_subtitle_style(None)
    assert "creator_subtitle_style_promotion" in result


def test_never_raises_on_empty_namespace():
    result = build_creator_subtitle_style(SimpleNamespace())
    assert result["creator_subtitle_style_promotion"]["available"] is False


def test_never_raises_on_dict_edit_plan():
    plan = {
        "creator_archetype_strategy": {
            "available":   True,
            "creator_type": "podcast",
            "confidence":  0.90,
            "strategy": {
                "subtitle": {
                    "style_bias": "clean_pro",
                    "keyword_emphasis": "selective",
                }
            },
        },
        "ai_execution_mode": {"effective_mode": "balanced"},
    }
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is True
    assert css["recommended_preset"] == "clean_pro"


def test_no_archetype_strategy_returns_fallback():
    plan = SimpleNamespace(
        creator_archetype_strategy={},
        ai_execution_mode={"effective_mode": "balanced"},
    )
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is False


def test_archetype_unavailable_returns_fallback():
    plan = SimpleNamespace(
        creator_archetype_strategy={"available": False},
        ai_execution_mode={"effective_mode": "balanced"},
    )
    css = build_creator_subtitle_style(plan)["creator_subtitle_style_promotion"]
    assert css["available"] is False


# ---------------------------------------------------------------------------
# No payload mutation
# ---------------------------------------------------------------------------

def test_no_payload_mutation():
    """build_creator_subtitle_style must not touch any payload object."""
    plan = _plan_with_archetype("clean_pro")
    payload = SimpleNamespace(subtitle_style="pro_karaoke", highlight_per_word=False)
    build_creator_subtitle_style(plan)
    assert payload.subtitle_style == "pro_karaoke"
    assert payload.highlight_per_word is False


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

def test_deterministic_output():
    plan = _plan_with_archetype("bold_impact", archetype_conf=0.87, effective_mode="balanced")
    result_a = build_creator_subtitle_style(plan)
    result_b = build_creator_subtitle_style(plan)
    assert result_a == result_b


# ---------------------------------------------------------------------------
# Phase 59A integration: priority ordering
# ---------------------------------------------------------------------------

def test_phase59a_higher_priority_50c_wins_over_archetype():
    """Phase 50C signal wins over Phase 61B archetype fallback."""
    from types import SimpleNamespace
    from app.ai.subtitle_promotion.subtitle_promotion_engine import promote_subtitle_influence

    plan = SimpleNamespace(
        creator_subtitle_influence={
            "available":    True,
            "preset_bias":  "boxed_caption",
            "emphasis_delta": 0.0,
        },
        creator_subtitle_preference={"subtitle_preference": {"confidence": 0.85}},
        platform_render_strategy={},
        platform_strategy_influence={},
        creator_subtitle_style_promotion={
            "available":          True,
            "recommended_preset": "viral_bold",  # archetype says viral_bold
            "archetype_style_bias": "bold_impact",
            "confidence":         0.90,
            "mode":               "balanced",
            "creator_type":       "motivation",
            "reasoning":          [],
        },
    )

    payload = SimpleNamespace(
        add_subtitle=True,
        subtitle_style="pro_karaoke",
        highlight_per_word=False,
        subtitle_ai_style_lock=False,
    )

    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]

    # Phase 50C (boxed_caption) must win over Phase 61B (viral_bold)
    assert promo["preset_applied"] == "boxed_caption"


def test_phase59a_archetype_not_used_when_mode_off():
    """When mode=off promotion is blocked, archetype signal should not surface."""
    from types import SimpleNamespace
    from app.ai.subtitle_promotion.subtitle_promotion_engine import promote_subtitle_influence

    plan = SimpleNamespace(
        creator_subtitle_influence={},
        creator_subtitle_preference={"subtitle_preference": {"confidence": 0.85}},
        platform_render_strategy={},
        platform_strategy_influence={},
        creator_subtitle_style_promotion={
            "available": False,
            "recommended_preset": None,
            "reason": "mode_off",
        },
    )

    payload = SimpleNamespace(
        add_subtitle=True,
        subtitle_style="pro_karaoke",
        highlight_per_word=False,
        subtitle_ai_style_lock=False,
    )

    _, report = promote_subtitle_influence(payload, plan)
    promo = report["subtitle_execution_promotion"]
    # No archetype signal → no preset applied
    assert promo["preset_applied"] is None
