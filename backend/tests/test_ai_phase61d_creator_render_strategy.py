"""
test_ai_phase61d_creator_render_strategy.py — Tests for Phase 61D Creator Render Strategy Fusion.

Coverage:
  - Podcast fused strategy (full shape, correct conservative values)
  - Educational fused strategy (keyword emphasis, stable camera)
  - Viral short-form fused strategy (dynamic emphasis, medium motion)
  - Motivation fused strategy (bold, dynamic but bounded)
  - Unknown archetype → fallback
  - Platform refines emphasis for dynamic creators (non-trust-safe only)
  - Platform does NOT override trust-safe creator subtitle style
  - Quality risk (high jitter) → motion energy softened
  - Quality risk (high whip_pan) → motion energy reduced, crop capped
  - creator_preference_profile confidence contributes to output confidence
  - Confidence clamped to [0.0, 1.0]
  - Deterministic output
  - No execution flags in strategy output
  - No crash on None / empty / dict edit_plan
  - Advisory-only: no payload mutation, no render execution flags

Required execution tests:
  test_execution_podcast_fused_stable       — podcast → conservative stable strategy
  test_execution_viral_fused_dynamic        — viral → dynamic energy strategy
  test_execution_advisory_only_no_mutation  — Phase 61D produces NO execution/mutation flags
  test_execution_mode_off_fallback          — no archetype → fallback, strategy empty
"""
import pytest
from types import SimpleNamespace

from app.ai.creator_style.creator_render_strategy_engine import (
    build_creator_render_strategy,
    _fuse_subtitle, _fuse_camera, _fuse_hook, _fuse_ranking,
    _check_quality, _blend_confidence,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _archetype(
    creator_type: str,
    subtitle_style_bias: str = "clean_pro",
    subtitle_keyword_emphasis: str = "selective",
    camera_motion: str = "low",
    camera_stability: str = "high",
    camera_crop: str = "low",
    hook_energy: str = "moderate",
    curiosity_style: str = "soft_direct",
    ranking_priority: str = "retention_creator_fit",
    confidence: float = 0.90,
) -> dict:
    return {
        "available":   True,
        "creator_type": creator_type,
        "confidence":  confidence,
        "reasoning":   [f"{creator_type} creator style applied"],
        "strategy": {
            "subtitle": {
                "style_bias":           subtitle_style_bias,
                "density_bias":         "balanced",
                "keyword_emphasis":     subtitle_keyword_emphasis,
                "readability_priority": "high",
            },
            "camera": {
                "motion_energy":       camera_motion,
                "stability_priority":  camera_stability,
                "crop_aggressiveness": camera_crop,
                "jitter_sensitivity":  "high",
            },
            "hook": {
                "hook_energy":        hook_energy,
                "curiosity_style":    curiosity_style,
                "retention_priority": "medium_high",
            },
            "ranking": {"priority": ranking_priority},
        },
    }


def _plan(
    creator_type: str = "podcast",
    **arch_kwargs,
) -> SimpleNamespace:
    return SimpleNamespace(
        creator_archetype_strategy=_archetype(creator_type, **arch_kwargs),
        creator_preference_profile={"creator_type": creator_type, "confidence": 0.85},
        platform_render_strategy={},
        camera_quality_v2={},
        render_quality_v2={},
        platform_quality_feedback={},
        creator_benchmark_summary={},
    )


def _quality_flags(high_jitter=False, high_whip_pan=False, low_cam_fit=False):
    return {
        "high_jitter":   high_jitter,
        "high_whip_pan": high_whip_pan,
        "low_cam_fit":   low_cam_fit,
    }


# ---------------------------------------------------------------------------
# Required execution tests
# ---------------------------------------------------------------------------

def test_execution_podcast_fused_stable():
    """Podcast: full fused strategy with conservative stable values."""
    plan = _plan("podcast", camera_motion="low", camera_stability="high",
                 camera_crop="low", subtitle_style_bias="clean_pro")
    result = build_creator_render_strategy(plan, context={"job_id": "test"})
    crs = result["creator_render_strategy"]

    assert crs["available"] is True
    assert crs["creator_type"] == "podcast"
    assert crs["confidence"] > 0.0
    assert crs["confidence"] <= 1.0

    s = crs["strategy"]
    assert s["subtitle"]["style"] == "clean_pro"
    assert s["subtitle"]["readability_priority"] == "high"
    assert s["camera"]["motion_energy"] == "low"
    assert s["camera"]["stability_priority"] == "high"
    assert s["camera"]["crop_aggressiveness"] == "low"
    assert s["camera"]["subject_hold"] == "high"
    assert s["hook"]["hook_energy"] == "moderate"
    assert s["hook"]["curiosity_style"] == "soft_direct"
    assert s["ranking"]["priority"] == "retention_creator_fit"
    assert len(crs["reasoning"]) > 0


def test_execution_viral_fused_dynamic():
    """Viral short-form: fused strategy has medium motion and strong emphasis."""
    plan = _plan(
        "viral_short_form",
        subtitle_style_bias="compact_dynamic",
        subtitle_keyword_emphasis="strong",
        camera_motion="medium",
        camera_stability="medium",
        camera_crop="medium",
        hook_energy="high",
        curiosity_style="pattern_interrupt",
        ranking_priority="hook_strength_retention",
    )
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]

    assert crs["available"] is True
    assert crs["strategy"]["subtitle"]["keyword_emphasis"] == "strong"
    assert crs["strategy"]["camera"]["motion_energy"] == "medium"
    assert crs["strategy"]["hook"]["hook_energy"] == "high"
    assert crs["strategy"]["ranking"]["priority"] == "hook_strength_retention"


def test_execution_advisory_only_no_mutation():
    """Phase 61D produces ONLY advisory metadata — no execution/mutation flags."""
    plan = _plan("podcast")
    result = build_creator_render_strategy(plan)
    crs = result["creator_render_strategy"]

    # Verify no execution promotion flags in strategy
    strategy_str = str(crs.get("strategy", {}))
    forbidden_terms = (
        "highlight_per_word", "reframe_mode", "payload", "promote",
        "execute", "segment_selection", "apply_", "mutation",
        "ffmpeg", "subtitle_timing", "motion_crop",
    )
    for term in forbidden_terms:
        assert term not in strategy_str, \
            f"Execution term {term!r} must not appear in strategy"

    # Verify expected advisory-only fields are present
    assert "available" in crs
    assert "confidence" in crs
    assert "reasoning" in crs
    assert "strategy" in crs


def test_execution_no_archetype_fallback():
    """No archetype strategy → fallback with available=False and empty strategy."""
    plan = SimpleNamespace(
        creator_archetype_strategy={},
        creator_preference_profile={},
        platform_render_strategy={},
        camera_quality_v2={},
        render_quality_v2={},
        platform_quality_feedback={},
    )
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]

    assert crs["available"] is False
    assert crs["strategy"] == {}
    assert crs["confidence"] == 0.0


# ---------------------------------------------------------------------------
# Archetype strategy tests
# ---------------------------------------------------------------------------

def test_educational_strategy():
    plan = _plan(
        "educational",
        subtitle_keyword_emphasis="moderate",
        camera_motion="low",
        curiosity_style="curiosity_driven",
        ranking_priority="retention_readability",
    )
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    assert crs["strategy"]["subtitle"]["keyword_emphasis"] == "moderate"
    assert crs["strategy"]["camera"]["motion_energy"] == "low"
    assert crs["strategy"]["hook"]["curiosity_style"] == "curiosity_driven"
    assert crs["strategy"]["ranking"]["priority"] == "retention_readability"


def test_motivation_strategy():
    plan = _plan(
        "motivation",
        subtitle_style_bias="bold_impact",
        subtitle_keyword_emphasis="strong",
        camera_motion="medium_high",
        camera_stability="medium",
        camera_crop="medium",
        hook_energy="high",
        curiosity_style="emotional",
        ranking_priority="retention_emotional_moment",
    )
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    assert crs["strategy"]["subtitle"]["style"] == "bold_impact"
    assert crs["strategy"]["subtitle"]["keyword_emphasis"] == "strong"
    assert crs["strategy"]["camera"]["motion_energy"] == "medium_high"
    assert crs["strategy"]["hook"]["hook_energy"] == "high"
    assert crs["strategy"]["ranking"]["priority"] == "retention_emotional_moment"


def test_interview_strategy():
    plan = _plan(
        "interview",
        subtitle_keyword_emphasis="none",
        camera_motion="low",
        hook_energy="low_medium",
        curiosity_style="trust_curiosity",
        ranking_priority="trust_clarity",
    )
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    assert crs["strategy"]["subtitle"]["keyword_emphasis"] == "none"
    assert crs["strategy"]["camera"]["motion_energy"] == "low"
    assert crs["strategy"]["hook"]["curiosity_style"] == "trust_curiosity"
    assert crs["strategy"]["ranking"]["priority"] == "trust_clarity"


def test_storytelling_strategy():
    plan = _plan(
        "storytelling",
        camera_motion="low_medium",
        hook_energy="low_medium",
        curiosity_style="soft_direct",
        ranking_priority="retention_narrative",
    )
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    assert crs["strategy"]["camera"]["motion_energy"] == "low_medium"
    assert crs["strategy"]["ranking"]["priority"] == "retention_narrative"


# ---------------------------------------------------------------------------
# Platform refinement tests
# ---------------------------------------------------------------------------

def test_platform_raises_emphasis_for_viral():
    """Platform can raise keyword_emphasis for viral_short_form (non-trust-safe)."""
    plan = _plan(
        "viral_short_form",
        subtitle_keyword_emphasis="selective",  # archetype says selective
    )
    plan.platform_render_strategy = {
        "available": True,
        "platform":  "tiktok",
        "confidence": 0.80,
        "strategy": {
            "subtitle": {"keyword_emphasis": "strong"},  # platform wants strong
            "camera":   {},
            "hook":     {},
            "ranking":  {},
        },
    }
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    # Platform should raise from selective to strong
    assert crs["strategy"]["subtitle"]["keyword_emphasis"] == "strong"


def test_platform_does_not_override_podcast_subtitle():
    """Trust-safe creator (podcast) keeps archetype emphasis even if platform pushes higher."""
    plan = _plan("podcast", subtitle_keyword_emphasis="selective")
    plan.platform_render_strategy = {
        "available": True,
        "platform":  "tiktok",
        "confidence": 0.80,
        "strategy": {
            "subtitle": {"keyword_emphasis": "strong"},  # platform wants strong
            "camera":   {},
            "hook":     {},
            "ranking":  {},
        },
    }
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    # Podcast is trust-safe → stays selective
    assert crs["strategy"]["subtitle"]["keyword_emphasis"] == "selective"


def test_platform_raises_retention_priority():
    """Platform (short-form) can raise retention_priority in hook."""
    plan = _plan("motivation", hook_energy="high")
    plan.platform_render_strategy = {
        "available": True,
        "platform":  "tiktok",
        "confidence": 0.80,
        "strategy": {
            "subtitle": {},
            "camera":   {},
            "hook":     {"retention_priority": "high"},
            "ranking":  {},
        },
    }
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    assert crs["strategy"]["hook"]["retention_priority"] == "high"


# ---------------------------------------------------------------------------
# Quality risk tests
# ---------------------------------------------------------------------------

def test_quality_high_jitter_softens_motion():
    """High jitter risk reduces motion_energy above medium and raises stability."""
    plan = _plan("motivation", camera_motion="medium_high", camera_stability="medium")
    plan.camera_quality_v2 = {"micro_jitter_risk": 70, "whip_pan_risk": 0}

    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    cam = crs["strategy"]["camera"]
    # medium_high → reduced to medium
    assert cam["motion_energy"] in ("low", "low_medium", "medium")
    assert cam["stability_priority"] == "high"
    assert "jitter" in " ".join(crs["reasoning"]).lower()


def test_quality_whip_pan_reduces_motion():
    """High whip_pan_risk reduces motion_energy."""
    plan = _plan("motivation", camera_motion="high", camera_crop="high")
    plan.camera_quality_v2 = {"micro_jitter_risk": 0, "whip_pan_risk": 70}

    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    cam = crs["strategy"]["camera"]
    # "high" motion reduced by 1 to "medium_high"
    assert cam["motion_energy"] in ("low", "low_medium", "medium", "medium_high")
    # crop_aggressiveness=high → capped to medium when whip_pan risk
    assert cam["crop_aggressiveness"] in ("low", "medium")


def test_quality_risk_does_not_affect_stable_creators():
    """Even with quality risk, already-low motion_energy stays unchanged."""
    plan = _plan("podcast", camera_motion="low")
    plan.camera_quality_v2 = {"micro_jitter_risk": 80, "whip_pan_risk": 80}

    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    # Already low — nothing to reduce
    assert crs["strategy"]["camera"]["motion_energy"] == "low"


# ---------------------------------------------------------------------------
# Confidence tests
# ---------------------------------------------------------------------------

def test_confidence_blended_from_all_signals():
    """Higher profile and platform confidence → higher output confidence."""
    plan_low = _plan("podcast")
    plan_low.creator_preference_profile = {"confidence": 0.30, "creator_type": "podcast"}

    plan_high = _plan("podcast")
    plan_high.creator_preference_profile = {"confidence": 0.90, "creator_type": "podcast"}
    plan_high.platform_render_strategy = {
        "available": True, "confidence": 0.85,
        "strategy": {"subtitle": {}, "camera": {}, "hook": {}, "ranking": {}},
    }

    conf_low  = build_creator_render_strategy(plan_low)["creator_render_strategy"]["confidence"]
    conf_high = build_creator_render_strategy(plan_high)["creator_render_strategy"]["confidence"]
    assert conf_high > conf_low


def test_confidence_clamped_to_one():
    plan = SimpleNamespace(
        creator_archetype_strategy=_archetype("podcast", confidence=2.0),
        creator_preference_profile={"confidence": 2.0},
        platform_render_strategy={"available": True, "confidence": 3.0, "strategy": {}},
        camera_quality_v2={},
        render_quality_v2={"confidence": 2.0},
        platform_quality_feedback={},
    )
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    assert crs["confidence"] <= 1.0


def test_confidence_positive_for_known_archetype():
    plan = _plan("podcast")
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    assert crs["confidence"] > 0.0


# ---------------------------------------------------------------------------
# Unit tests for internal functions
# ---------------------------------------------------------------------------

def test_fuse_camera_jitter_reduces_medium_high():
    arch_cam = {"motion_energy": "medium_high", "stability_priority": "medium",
                "crop_aggressiveness": "medium"}
    flags = _quality_flags(high_jitter=True)
    result = _fuse_camera(arch_cam, {}, flags, "motivation")
    assert result["motion_energy"] in ("low", "low_medium", "medium")
    assert result["stability_priority"] == "high"


def test_fuse_camera_whip_pan_caps_crop():
    arch_cam = {"motion_energy": "high", "stability_priority": "medium",
                "crop_aggressiveness": "high"}
    flags = _quality_flags(high_whip_pan=True)
    result = _fuse_camera(arch_cam, {}, flags, "motivation")
    assert result["crop_aggressiveness"] in ("low", "medium")


def test_fuse_camera_trust_safe_not_raised_by_platform():
    arch_cam = {"motion_energy": "low", "stability_priority": "high",
                "crop_aggressiveness": "low"}
    flags = _quality_flags()
    prs = {
        "available": True,
        "strategy": {"camera": {"motion_energy": "high"}},
    }
    result = _fuse_camera(arch_cam, prs, flags, "podcast")  # trust-safe
    assert result["motion_energy"] == "low"  # platform can't raise


def test_fuse_camera_dynamic_raised_by_platform_capped_at_plus1():
    arch_cam = {"motion_energy": "medium", "stability_priority": "medium",
                "crop_aggressiveness": "medium"}
    flags = _quality_flags()
    prs = {
        "available": True,
        "strategy": {"camera": {"motion_energy": "high"}},   # platform wants "high"
    }
    result = _fuse_camera(arch_cam, prs, flags, "motivation")  # dynamic creator
    # Platform can raise by max 1 level: medium → medium_high (not high)
    assert result["motion_energy"] == "medium_high"


def test_fuse_subtitle_platform_cannot_lower_emphasis():
    arch_sub = {"style_bias": "clean_pro", "density_bias": "balanced",
                "keyword_emphasis": "moderate", "readability_priority": "high"}
    prs = {
        "available": True,
        "strategy": {"subtitle": {"keyword_emphasis": "none"}},  # platform wants less
    }
    result = _fuse_subtitle(arch_sub, prs, "storytelling")
    # Platform cannot lower emphasis — stays at moderate
    assert result["keyword_emphasis"] == "moderate"


def test_check_quality_risk_flags():
    cam_qual = {"micro_jitter_risk": 70, "whip_pan_risk": 30}
    flags = _check_quality(cam_qual, {})
    assert flags["high_jitter"] is True
    assert flags["high_whip_pan"] is False


def test_blend_confidence_missing_signals_lower_confidence():
    """Missing profile + platform should lower vs having all signals."""
    high = _blend_confidence(0.85, 0.90, 0.85, 0.90)
    low  = _blend_confidence(0.85, 0.0,  0.0,  0.0)
    assert high > low


# ---------------------------------------------------------------------------
# Output shape
# ---------------------------------------------------------------------------

def test_output_shape_complete():
    plan = _plan()
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    required = {"available", "creator_type", "strategy", "confidence", "reasoning"}
    assert required.issubset(crs.keys()), f"Missing: {required - crs.keys()}"

    strategy = crs["strategy"]
    assert set(strategy.keys()) == {"subtitle", "camera", "hook", "ranking"}
    sub = strategy["subtitle"]
    assert set(sub.keys()) == {"style", "density", "keyword_emphasis", "readability_priority"}
    cam = strategy["camera"]
    assert set(cam.keys()) == {"motion_energy", "stability_priority",
                               "crop_aggressiveness", "subject_hold"}
    hook = strategy["hook"]
    assert set(hook.keys()) == {"hook_energy", "curiosity_style", "retention_priority"}
    assert set(strategy["ranking"].keys()) == {"priority"}


def test_fallback_shape_complete():
    crs = build_creator_render_strategy(None)["creator_render_strategy"]
    required = {"available", "creator_type", "strategy", "confidence", "reasoning"}
    assert required.issubset(crs.keys())
    assert crs["strategy"] == {}


# ---------------------------------------------------------------------------
# Safety / fallback
# ---------------------------------------------------------------------------

def test_never_raises_on_none():
    result = build_creator_render_strategy(None)
    assert "creator_render_strategy" in result


def test_never_raises_on_empty_namespace():
    result = build_creator_render_strategy(SimpleNamespace())
    assert result["creator_render_strategy"]["available"] is False


def test_never_raises_on_dict_edit_plan():
    plan = {
        "creator_archetype_strategy": _archetype("podcast"),
        "creator_preference_profile": {"confidence": 0.85},
        "platform_render_strategy":   {},
        "camera_quality_v2":          {},
        "render_quality_v2":          {},
        "platform_quality_feedback":  {},
    }
    crs = build_creator_render_strategy(plan)["creator_render_strategy"]
    assert crs["available"] is True
    assert crs["creator_type"] == "podcast"


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

def test_deterministic_output():
    plan = _plan(
        "motivation",
        camera_motion="medium_high",
        subtitle_keyword_emphasis="strong",
    )
    plan.camera_quality_v2 = {"micro_jitter_risk": 40, "whip_pan_risk": 20}
    result_a = build_creator_render_strategy(plan)
    result_b = build_creator_render_strategy(plan)
    assert result_a == result_b
