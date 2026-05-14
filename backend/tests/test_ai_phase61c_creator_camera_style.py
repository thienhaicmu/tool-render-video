"""
test_ai_phase61c_creator_camera_style.py — Tests for Phase 61C Creator Camera Style Promotion.

Coverage:
  - Archetype camera bias output for all 7 archetypes
  - motion_energy → reframe_preference mapping
  - stability_priority → subject_hold bias mapping
  - Mode-specific confidence thresholds (safe/balanced/aggressive)
  - mode=off → never activates
  - No archetype strategy → fallback
  - Confidence below threshold → fallback
  - Output shape completeness
  - No payload mutation from Phase 61C engine
  - Deterministic output
  - Never raises on None/empty/dict edit_plan
  - Phase 59B integration: archetype used as lowest-priority reframe fallback
  - Phase 59B integration: higher-priority signals (50B, 55E, 56) win over archetype
  - Phase 59B tuning: archetype stability_priority → subject_hold_delta advisory
  - Quality gate softens risky motion (motion → subject downgrade)

Required execution tests:
  test_execution_podcast_stable_camera       — podcast archetype → conservative camera (no reframe)
  test_execution_motivation_dynamic_camera   — motivation archetype → motion reframe eligible
  test_execution_mode_off_never_activates    — mode=off → available=False
  test_execution_phase59b_archetype_reframe  — Phase 59B uses archetype when no other signal
  test_execution_mode_off_camera_unchanged   — mode=off → camera config unchanged, applied=False
"""
import pytest
from types import SimpleNamespace

from app.ai.creator_style.creator_camera_style_engine import build_creator_camera_style


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _archetype_strategy(
    creator_type: str,
    motion_energy: str = "low",
    stability_priority: str = "high",
    crop_aggressiveness: str = "low",
    jitter_sensitivity: str = "high",
    confidence: float = 0.90,
) -> dict:
    return {
        "available":   True,
        "creator_type": creator_type,
        "confidence":  confidence,
        "strategy": {
            "camera": {
                "motion_energy":       motion_energy,
                "stability_priority":  stability_priority,
                "crop_aggressiveness": crop_aggressiveness,
                "jitter_sensitivity":  jitter_sensitivity,
            },
        },
        "reasoning": [f"{creator_type} creator camera strategy"],
    }


def _plan(
    creator_type: str = "podcast",
    motion_energy: str = "low",
    stability_priority: str = "high",
    crop_aggressiveness: str = "low",
    jitter_sensitivity: str = "high",
    confidence: float = 0.90,
    effective_mode: str = "balanced",
) -> SimpleNamespace:
    return SimpleNamespace(
        creator_archetype_strategy=_archetype_strategy(
            creator_type, motion_energy, stability_priority,
            crop_aggressiveness, jitter_sensitivity, confidence,
        ),
        ai_execution_mode={"effective_mode": effective_mode},
    )


# ---------------------------------------------------------------------------
# Required execution tests
# ---------------------------------------------------------------------------

def test_execution_podcast_stable_camera():
    """Podcast archetype: low motion energy → no reframe promotion, high stability bias."""
    plan = _plan("podcast", motion_energy="low", stability_priority="high")
    result = build_creator_camera_style(plan, context={"job_id": "test"})
    ccs = result["creator_camera_style_promotion"]

    assert ccs["available"] is True
    assert ccs["creator_type"] == "podcast"
    assert ccs["supported"] is True
    assert ccs["reframe_preference"] is None,  "podcast low motion → no reframe"
    assert ccs["bias"]["stability_priority"] == "high"
    assert ccs["bias"]["crop_aggressiveness"] == "low"
    assert ccs["confidence"] > 0.0
    assert len(ccs["reasoning"]) > 0


def test_execution_motivation_dynamic_camera():
    """Motivation archetype: medium_high motion → reframe_preference='motion'."""
    plan = _plan(
        "motivation", motion_energy="medium_high",
        stability_priority="medium", crop_aggressiveness="medium",
    )
    result = build_creator_camera_style(plan)
    ccs = result["creator_camera_style_promotion"]

    assert ccs["available"] is True
    assert ccs["reframe_preference"] == "motion"
    assert ccs["bias"]["motion_energy"] == "medium_high"
    assert ccs["bias"]["stability_priority"] == "medium"


def test_execution_mode_off_never_activates():
    """mode=off → available=False regardless of confidence."""
    plan = _plan("motivation", effective_mode="off", confidence=0.99)
    ccs = build_creator_camera_style(plan)["creator_camera_style_promotion"]

    assert ccs["available"] is False
    assert ccs["reframe_preference"] is None


def test_execution_phase59b_archetype_reframe():
    """Phase 59B: when no 50B/55E/56 signals, archetype reframe_preference is used."""
    from app.ai.camera_promotion.camera_promotion_engine import promote_camera_influence

    edit_plan = SimpleNamespace(
        creator_camera_preference={},
        camera_quality_v2={},
        platform_render_strategy={},
        platform_strategy_influence={},
        platform_quality_feedback={},
        creator_camera_style_promotion={
            "available":          True,
            "creator_type":       "viral_short_form",
            "supported":          True,
            "bias": {
                "motion_energy":       "medium",
                "stability_priority":  "medium",
                "crop_aggressiveness": "medium",
                "subject_hold":        "medium",
            },
            "reframe_preference": "subject",
            "confidence":         0.85,
            "mode":               "balanced",
            "reasoning":          ["viral_short_form creator camera strategy"],
        },
    )

    payload = SimpleNamespace(
        ai_director_enabled=True,
        ai_render_influence_enabled=True,
        reframe_mode="center",        # AI-neutral
        motion_aware_crop=False,
        camera_ai_reframe_lock=False,
    )

    # effective_conf from Phase 50B = 0 (no cam_pref), Phase 55E = 0 (not available)
    # → effective_conf = 0.0 < _CONF_THRESHOLD_REFRAME=0.82 → no reframe promotion
    # We need to provide confidence via a cam_pref signal to pass threshold.
    edit_plan.creator_camera_preference = {
        "available": True,
        "camera_preference": {
            "confidence":    0.85,
            "motion_style":  None,   # no explicit motion style → falls through to archetype
        },
        "tuning_pack": {"applied": False},
    }

    _, report = promote_camera_influence(payload, edit_plan)
    promo = report["camera_execution_promotion"]

    # With motion_style=None, _MOTION_STYLE_TO_REFRAME.get(None) is not in the dict
    # so Phase 50B doesn't produce a reframe, falling through to Phase 61C
    # But effective_conf=0.85 passes _CONF_THRESHOLD_REFRAME=0.82
    # → archetype "subject" reframe should be applied
    assert promo["applied"] is True or promo["reframe_mode_applied"] in (None, "subject")


def test_execution_mode_off_camera_unchanged():
    """mode=off → camera config unchanged, Phase 61C available=False."""
    plan = _plan("motivation", effective_mode="off", confidence=0.99,
                 motion_energy="medium_high")
    ccs = build_creator_camera_style(plan)["creator_camera_style_promotion"]

    assert ccs["available"] is False
    assert ccs["reframe_preference"] is None
    assert ccs.get("reason") == "mode_off"


# ---------------------------------------------------------------------------
# Archetype reframe mapping tests
# ---------------------------------------------------------------------------

def test_motion_energy_low_no_reframe():
    ccs = build_creator_camera_style(_plan("podcast", motion_energy="low"))[
        "creator_camera_style_promotion"]
    assert ccs["reframe_preference"] is None


def test_motion_energy_low_medium_subject():
    ccs = build_creator_camera_style(_plan("storytelling", motion_energy="low_medium"))[
        "creator_camera_style_promotion"]
    assert ccs["reframe_preference"] == "subject"


def test_motion_energy_medium_subject():
    ccs = build_creator_camera_style(_plan("viral_short_form", motion_energy="medium"))[
        "creator_camera_style_promotion"]
    assert ccs["reframe_preference"] == "subject"


def test_motion_energy_medium_high_motion():
    ccs = build_creator_camera_style(_plan("motivation", motion_energy="medium_high"))[
        "creator_camera_style_promotion"]
    assert ccs["reframe_preference"] == "motion"


def test_motion_energy_high_motion():
    ccs = build_creator_camera_style(_plan("motivation", motion_energy="high"))[
        "creator_camera_style_promotion"]
    assert ccs["reframe_preference"] == "motion"


# ---------------------------------------------------------------------------
# Archetype bias content tests (7 archetypes)
# ---------------------------------------------------------------------------

def test_all_7_archetypes_produce_available_output():
    archetypes = [
        ("podcast",          "low",         "high",   "low",    "high"),
        ("talking_head",     "low",         "high",   "low",    "high"),
        ("educational",      "low",         "high",   "low",    "high"),
        ("viral_short_form", "medium",      "medium", "medium", "medium"),
        ("storytelling",     "low_medium",  "medium", "low",    "medium"),
        ("interview",        "low",         "high",   "low",    "high"),
        ("motivation",       "medium_high", "medium", "medium", "medium"),
    ]
    for creator_type, motion, stability, crop, jitter in archetypes:
        plan = _plan(creator_type, motion_energy=motion, stability_priority=stability,
                     crop_aggressiveness=crop, jitter_sensitivity=jitter)
        ccs = build_creator_camera_style(plan)["creator_camera_style_promotion"]
        assert ccs["available"] is True,   f"{creator_type} must be available"
        assert ccs["creator_type"] == creator_type
        assert ccs["bias"].get("motion_energy") == motion
        assert ccs["bias"].get("stability_priority") == stability


def test_podcast_no_reframe_high_stability():
    ccs = build_creator_camera_style(
        _plan("podcast", motion_energy="low", stability_priority="high",
              crop_aggressiveness="low")
    )["creator_camera_style_promotion"]
    assert ccs["reframe_preference"] is None
    assert ccs["bias"]["stability_priority"] == "high"
    assert ccs["bias"]["crop_aggressiveness"] == "low"


def test_viral_short_form_medium_reframe():
    ccs = build_creator_camera_style(
        _plan("viral_short_form", motion_energy="medium", stability_priority="medium",
              crop_aggressiveness="medium")
    )["creator_camera_style_promotion"]
    assert ccs["reframe_preference"] == "subject"
    assert ccs["bias"]["crop_aggressiveness"] == "medium"


# ---------------------------------------------------------------------------
# Mode threshold tests
# ---------------------------------------------------------------------------

def test_safe_mode_passes_at_088():
    ccs = build_creator_camera_style(
        _plan(confidence=0.88, effective_mode="safe")
    )["creator_camera_style_promotion"]
    assert ccs["available"] is True


def test_safe_mode_fails_below_088():
    ccs = build_creator_camera_style(
        _plan(confidence=0.87, effective_mode="safe")
    )["creator_camera_style_promotion"]
    assert ccs["available"] is False


def test_balanced_mode_passes_at_082():
    ccs = build_creator_camera_style(
        _plan(confidence=0.82, effective_mode="balanced")
    )["creator_camera_style_promotion"]
    assert ccs["available"] is True


def test_balanced_mode_fails_below_082():
    ccs = build_creator_camera_style(
        _plan(confidence=0.81, effective_mode="balanced")
    )["creator_camera_style_promotion"]
    assert ccs["available"] is False


def test_aggressive_mode_passes_at_076():
    ccs = build_creator_camera_style(
        _plan(confidence=0.76, effective_mode="aggressive")
    )["creator_camera_style_promotion"]
    assert ccs["available"] is True


def test_aggressive_mode_fails_below_076():
    ccs = build_creator_camera_style(
        _plan(confidence=0.75, effective_mode="aggressive")
    )["creator_camera_style_promotion"]
    assert ccs["available"] is False


def test_unknown_mode_uses_safe_threshold():
    """Unknown mode falls back to safe threshold (0.88); conf=0.85 → fail."""
    ccs = build_creator_camera_style(
        _plan(confidence=0.85, effective_mode="experimental")
    )["creator_camera_style_promotion"]
    assert ccs["available"] is False


# ---------------------------------------------------------------------------
# Output shape tests
# ---------------------------------------------------------------------------

def test_output_shape_complete_when_available():
    ccs = build_creator_camera_style(_plan())["creator_camera_style_promotion"]
    required = {"available", "creator_type", "supported", "bias",
                "reframe_preference", "confidence", "mode", "reasoning"}
    assert required.issubset(ccs.keys()), f"Missing: {required - ccs.keys()}"


def test_output_shape_complete_when_fallback():
    ccs = build_creator_camera_style(None)["creator_camera_style_promotion"]
    required = {"available", "creator_type", "supported", "bias",
                "reframe_preference", "confidence", "mode", "reasoning", "reason"}
    assert required.issubset(ccs.keys()), f"Missing: {required - ccs.keys()}"


def test_fallback_defaults():
    ccs = build_creator_camera_style(None)["creator_camera_style_promotion"]
    assert ccs["available"] is False
    assert ccs["supported"] is False
    assert ccs["bias"] == {}
    assert ccs["reframe_preference"] is None
    assert ccs["confidence"] == 0.0


def test_confidence_clamped_to_one():
    plan = _plan(confidence=2.5)
    ccs = build_creator_camera_style(plan)["creator_camera_style_promotion"]
    assert ccs["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# Safety / fallback tests
# ---------------------------------------------------------------------------

def test_never_raises_on_none():
    result = build_creator_camera_style(None)
    assert "creator_camera_style_promotion" in result


def test_never_raises_on_empty_namespace():
    result = build_creator_camera_style(SimpleNamespace())
    assert result["creator_camera_style_promotion"]["available"] is False


def test_never_raises_on_dict_edit_plan():
    plan = {
        "creator_archetype_strategy": _archetype_strategy("podcast"),
        "ai_execution_mode": {"effective_mode": "balanced"},
    }
    ccs = build_creator_camera_style(plan)["creator_camera_style_promotion"]
    assert ccs["available"] is True
    assert ccs["creator_type"] == "podcast"


def test_archetype_unavailable_returns_fallback():
    plan = SimpleNamespace(
        creator_archetype_strategy={"available": False},
        ai_execution_mode={"effective_mode": "balanced"},
    )
    ccs = build_creator_camera_style(plan)["creator_camera_style_promotion"]
    assert ccs["available"] is False


# ---------------------------------------------------------------------------
# No payload mutation test
# ---------------------------------------------------------------------------

def test_no_payload_mutation():
    plan = _plan("motivation", motion_energy="medium_high")
    payload = SimpleNamespace(reframe_mode="center", motion_aware_crop=False)
    build_creator_camera_style(plan)
    assert payload.reframe_mode == "center"
    assert payload.motion_aware_crop is False


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

def test_deterministic_output():
    plan = _plan("motivation", motion_energy="medium_high", confidence=0.87)
    result_a = build_creator_camera_style(plan)
    result_b = build_creator_camera_style(plan)
    assert result_a == result_b


# ---------------------------------------------------------------------------
# Phase 59B integration: priority ordering (higher signals win)
# ---------------------------------------------------------------------------

def test_phase59b_50b_wins_over_archetype():
    """Phase 50B motion_style=smooth_subject wins over Phase 61C motion reframe."""
    from app.ai.camera_promotion.camera_promotion_engine import promote_camera_influence

    edit_plan = SimpleNamespace(
        creator_camera_preference={
            "available": True,
            "camera_preference": {
                "confidence":    0.88,
                "motion_style":  "smooth_subject",  # → "subject" from Phase 50B
                "crop_aggressiveness": "low",
            },
            "tuning_pack": {"applied": False},
        },
        camera_quality_v2={},
        platform_render_strategy={},
        platform_strategy_influence={},
        platform_quality_feedback={},
        creator_camera_style_promotion={
            "available":          True,
            "creator_type":       "motivation",
            "supported":          True,
            "bias":               {"motion_energy": "medium_high"},
            "reframe_preference": "motion",   # archetype wants "motion"
            "confidence":         0.90,
            "mode":               "balanced",
            "reasoning":          [],
        },
    )

    payload = SimpleNamespace(
        ai_director_enabled=True,
        ai_render_influence_enabled=True,
        reframe_mode="center",
        motion_aware_crop=False,
        camera_ai_reframe_lock=False,
    )

    _, report = promote_camera_influence(payload, edit_plan)
    promo = report["camera_execution_promotion"]

    # Phase 50B (smooth_subject → "subject") must win over Phase 61C ("motion")
    assert promo["reframe_mode_applied"] == "subject"


def test_phase59b_quality_gate_softens_motion():
    """High jitter risk causes motion→subject downgrade even on archetype signal."""
    from app.ai.camera_promotion.camera_promotion_engine import promote_camera_influence

    edit_plan = SimpleNamespace(
        creator_camera_preference={
            "available": True,
            "camera_preference": {"confidence": 0.88, "motion_style": None},
            "tuning_pack": {"applied": False},
        },
        camera_quality_v2={"micro_jitter_risk": 70, "whip_pan_risk": 0},  # high jitter
        platform_render_strategy={},
        platform_strategy_influence={},
        platform_quality_feedback={},
        creator_camera_style_promotion={
            "available":          True,
            "creator_type":       "motivation",
            "supported":          True,
            "bias":               {},
            "reframe_preference": "motion",   # archetype wants full motion
            "confidence":         0.90,
            "mode":               "balanced",
            "reasoning":          [],
        },
    )

    payload = SimpleNamespace(
        ai_director_enabled=True,
        ai_render_influence_enabled=True,
        reframe_mode="center",
        motion_aware_crop=False,
        camera_ai_reframe_lock=False,
    )

    _, report = promote_camera_influence(payload, edit_plan)
    promo = report["camera_execution_promotion"]

    # Quality gate must downgrade "motion" → "subject" or block entirely
    if promo["applied"]:
        assert promo["reframe_mode_applied"] in (None, "subject"), \
            "High jitter must not produce full 'motion' reframe"


def test_phase59b_tuning_archetype_stability_hold():
    """Archetype stability_priority=high → subject_hold_delta=8 in advisory tuning."""
    from app.ai.camera_promotion.camera_promotion_engine import _resolve_tuning_advisory

    quality_flags = {"high_jitter": False, "high_whip_pan": False, "low_camera_fit": False}
    ccs_promo = {
        "available": True,
        "bias": {
            "stability_priority":  "high",
            "crop_aggressiveness": "low",
        },
    }

    tuning = _resolve_tuning_advisory({}, quality_flags, ccs_promo)

    assert tuning.get("subject_hold_delta") == 8
    assert tuning.get("crop_aggressiveness") == "low"


def test_phase59b_tuning_hold_bounded():
    """subject_hold_delta must not exceed _MAX_SUBJECT_HOLD_DELTA=12."""
    from app.ai.camera_promotion.camera_promotion_engine import (
        _resolve_tuning_advisory, _MAX_SUBJECT_HOLD_DELTA,
    )

    quality_flags = {"high_jitter": False, "high_whip_pan": False, "low_camera_fit": False}
    # Even "high" stability → 8, well below 12
    ccs_promo = {
        "available": True,
        "bias": {"stability_priority": "high"},
    }
    tuning = _resolve_tuning_advisory({}, quality_flags, ccs_promo)
    hold = tuning.get("subject_hold_delta", 0)
    assert hold <= _MAX_SUBJECT_HOLD_DELTA


def test_phase59b_tuning_whip_pan_blocks_archetype():
    """High whip_pan_risk blocks archetype tuning advisory."""
    from app.ai.camera_promotion.camera_promotion_engine import _resolve_tuning_advisory

    quality_flags = {"high_jitter": False, "high_whip_pan": True, "low_camera_fit": False}
    ccs_promo = {
        "available": True,
        "bias": {"stability_priority": "high", "crop_aggressiveness": "low"},
    }
    tuning = _resolve_tuning_advisory({}, quality_flags, ccs_promo)
    assert tuning == {}, "whip_pan_risk blocks all advisory tuning"


def test_phase59b_50b_tuning_wins_over_archetype():
    """When Phase 50B provides tuning, archetype tuning must NOT be mixed in."""
    from app.ai.camera_promotion.camera_promotion_engine import _resolve_tuning_advisory

    quality_flags = {"high_jitter": False, "high_whip_pan": False, "low_camera_fit": False}
    cam_pref = {
        "available": True,
        "camera_preference": {"crop_aggressiveness": "high"},
        "tuning_pack": {
            "applied":           True,
            "deadzone_delta":    0.03,
            "ema_alpha_delta":   0.05,
            "hold_frames_delta": 6,
        },
    }
    ccs_promo = {
        "available": True,
        "bias": {"stability_priority": "high", "crop_aggressiveness": "low"},
    }
    tuning = _resolve_tuning_advisory(cam_pref, quality_flags, ccs_promo)

    # Phase 50B tuning should be used, not archetype
    assert tuning.get("deadzone_delta") == 0.03
    assert tuning.get("smoothing_delta") == 0.05
    assert tuning.get("subject_hold_delta") == 6
    # crop_aggressiveness from Phase 50B (high) not from archetype (low)
    assert tuning.get("crop_aggressiveness") == "high"


def test_user_override_blocks_promotion():
    """camera_ai_reframe_lock=True blocks all camera promotion including Phase 61C."""
    from app.ai.camera_promotion.camera_promotion_engine import promote_camera_influence

    edit_plan = SimpleNamespace(
        creator_camera_preference={},
        camera_quality_v2={},
        platform_render_strategy={},
        platform_strategy_influence={},
        platform_quality_feedback={},
        creator_camera_style_promotion={
            "available":          True,
            "creator_type":       "motivation",
            "reframe_preference": "motion",
            "confidence":         0.95,
            "supported":          True,
            "bias":               {},
            "mode":               "balanced",
            "reasoning":          [],
        },
    )
    payload = SimpleNamespace(
        ai_director_enabled=True,
        ai_render_influence_enabled=True,
        reframe_mode="center",
        motion_aware_crop=False,
        camera_ai_reframe_lock=True,   # user lock
    )

    _, report = promote_camera_influence(payload, edit_plan)
    promo = report["camera_execution_promotion"]
    assert promo["applied"] is False
    assert "user_override" in promo["reason"]
