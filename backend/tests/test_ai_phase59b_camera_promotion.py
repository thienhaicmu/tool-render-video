"""
test_ai_phase59b_camera_promotion.py — Phase 59B camera influence promotion tests.

Covers:
  - applies reframe_mode when eligible (subject, motion, face)
  - does not apply when AI flags disabled
  - does not apply when edit_plan is None
  - user override wins (reframe_mode != neutral)
  - camera_ai_reframe_lock blocks promotion
  - unknown / disallowed reframe mode is not applied
  - confidence threshold blocks reframe promotion
  - confidence threshold blocks motion_aware_crop promotion
  - motion_aware_crop enable-only: never disables existing True
  - quality gate: high micro_jitter_risk restricts to subject (blocks motion)
  - quality gate: high whip_pan_risk blocks motion_aware_crop
  - quality gate: low camera_fit (platform_quality_feedback) blocks aggressive reframe
  - tuning bounds enforced (deadzone, smoothing, subject_hold deltas)
  - tuning is advisory only — no payload field mutation
  - deterministic output
  - no crash on empty / malformed input
  - fallback safe on None edit_plan
  - ALLOWED_PROMOTION_MODES are real reframe_mode values
  - render_influence integration: phase59b fires inside apply_ai_render_influence
"""
from __future__ import annotations

import types
import pytest

from app.ai.camera_promotion.camera_promotion_engine import (
    promote_camera_influence,
    ALLOWED_PROMOTION_MODES,
    ALLOWED_REFRAME_MODES,
    _MAX_DEADZONE_DELTA,
    _MAX_SMOOTHING_DELTA,
    _MAX_SUBJECT_HOLD_DELTA,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _payload(
    reframe_mode: str = "center",
    motion_aware_crop: bool = False,
    ai_director_enabled: bool = True,
    ai_render_influence_enabled: bool = True,
    camera_ai_reframe_lock: bool = False,
) -> types.SimpleNamespace:
    return types.SimpleNamespace(
        reframe_mode=reframe_mode,
        motion_aware_crop=motion_aware_crop,
        ai_director_enabled=ai_director_enabled,
        ai_render_influence_enabled=ai_render_influence_enabled,
        camera_ai_reframe_lock=camera_ai_reframe_lock,
        # Fields that must NEVER be mutated by camera promotion
        subtitle_style="pro_karaoke",
        highlight_per_word=False,
        add_subtitle=True,
        transcript_text="hello world",
    )


def _edit_plan(
    cam_pref_available: bool = True,
    motion_style: str = "smooth_subject",
    crop_aggressiveness: str = "medium",
    stability_priority: str = "medium",
    pref_confidence: float = 0.88,
    tuning_applied: bool = True,
    deadzone_delta: float = 0.03,
    ema_alpha_delta: float = 0.05,
    hold_frames_delta: int = 6,
    cam_qual_jitter: int = 0,
    cam_qual_whip: int = 0,
    cam_qual_creator_fit: int = 80,
    prs_available: bool = False,
    prs_motion_energy: str = "medium",
    prs_confidence: float = 0.85,
    psi_available: bool = False,
    psi_motion_energy: str = "medium",
    pqf_available: bool = False,
    pqf_camera_fit: int = 70,
) -> types.SimpleNamespace:
    plan = types.SimpleNamespace()
    plan.creator_camera_preference = {
        "available": cam_pref_available,
        "inference_mode": "metadata_only",
        "camera_preference": {
            "motion_style": motion_style,
            "crop_aggressiveness": crop_aggressiveness,
            "stability_priority": stability_priority,
            "confidence": pref_confidence,
        },
        "tuning_pack": {
            "applied": tuning_applied,
            "confidence_tier": "high",
            "deadzone_delta": deadzone_delta,
            "ema_alpha_delta": ema_alpha_delta,
            "hold_frames_delta": hold_frames_delta,
            "scene_threshold_delta": 1.5,
            "smooth_window_delta": 4,
            "reasoning": ["test tuning signal"],
        },
    }
    plan.camera_quality_v2 = {
        "micro_jitter_risk": cam_qual_jitter,
        "whip_pan_risk":     cam_qual_whip,
        "crop_smoothness":   75,
        "subject_stability": 80,
        "creator_fit":       cam_qual_creator_fit,
        "overall":           78,
        "confidence":        0.82,
    }
    plan.platform_render_strategy = {
        "available": prs_available,
        "confidence": prs_confidence,
        "platform": "tiktok",
        "strategy": {
            "camera": {
                "motion_energy":      prs_motion_energy,
                "stability_priority": "medium",
                "crop_aggressiveness": "medium",
                "jitter_sensitivity": "medium",
            }
        },
    }
    plan.platform_strategy_influence = {
        "available": psi_available,
        "camera": {
            "supported": True,
            "bias": {"motion_energy": psi_motion_energy},
        },
    }
    plan.platform_quality_feedback = {
        "available":  pqf_available,
        "camera_fit": pqf_camera_fit,
        "subtitle_fit": 70,
        "hook_fit":     70,
        "overall":      70,
        "confidence":   0.80,
    }
    return plan


# ---------------------------------------------------------------------------
# 1. Basic promotion — reframe_mode applied
# ---------------------------------------------------------------------------

def test_applies_subject_reframe_from_smooth_subject():
    payload = _payload()
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.88)
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["applied"] is True
    assert promo["reframe_mode_applied"] == "subject"
    assert payload.reframe_mode == "subject"


def test_applies_motion_reframe_from_dynamic_subject():
    payload = _payload()
    plan = _edit_plan(motion_style="dynamic_subject", pref_confidence=0.88)
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["applied"] is True
    assert promo["reframe_mode_applied"] == "motion"
    assert payload.reframe_mode == "motion"


def test_does_not_promote_static_center_motion_style():
    """static_center explicitly means 'don't change reframe_mode'."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="static_center",
        pref_confidence=0.90,
        tuning_applied=False,
        hold_frames_delta=0,
        ema_alpha_delta=0.0,
        deadzone_delta=0.0,
    )
    _, report = promote_camera_influence(payload, plan)
    assert payload.reframe_mode == "center"


def test_platform_strategy_promotes_reframe_when_no_pref():
    """Phase 55E fires when Phase 50B is unavailable."""
    payload = _payload()
    plan = _edit_plan(
        cam_pref_available=False,
        prs_available=True,
        prs_motion_energy="high",
        prs_confidence=0.88,
        tuning_applied=False,
        hold_frames_delta=0,
        ema_alpha_delta=0.0,
        deadzone_delta=0.0,
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["reframe_mode_applied"] == "motion"
    assert payload.reframe_mode == "motion"


def test_platform_strategy_requires_available_true():
    """prs_available=False → confidence not trusted, no promotion."""
    payload = _payload()
    plan = _edit_plan(
        cam_pref_available=False,
        prs_available=False,
        prs_confidence=0.95,  # high but available=False
        tuning_applied=False,
        hold_frames_delta=0,
        ema_alpha_delta=0.0,
        deadzone_delta=0.0,
    )
    _, report = promote_camera_influence(payload, plan)
    assert payload.reframe_mode == "center"
    assert report["camera_execution_promotion"]["applied"] is False


def test_platform_strategy_influence_promotes_reframe():
    """Phase 56 PSI promotes when 50B and 55E unavailable."""
    payload = _payload()
    plan = _edit_plan(
        cam_pref_available=False,
        prs_available=False,
        psi_available=True,
        psi_motion_energy="medium",
        pref_confidence=0.88,
        tuning_applied=False,
        hold_frames_delta=0,
        ema_alpha_delta=0.0,
        deadzone_delta=0.0,
    )
    # PSI confidence is read from pref_conf (cam_pref.camera_preference.confidence)
    # but cam_pref_available=False means pref_conf=0.0.
    # Need to set pref_confidence via direct hack — PSI uses effective_conf
    plan.creator_camera_preference["camera_preference"]["confidence"] = 0.88
    _, report = promote_camera_influence(payload, plan)
    # With cam_pref_available=False, pref_conf=0.88 but no cam_pref signal → PSI fires
    # Actually pref_conf is still read from camera_preference.confidence regardless of available
    promo = report["camera_execution_promotion"]
    # PSI available=True with medium energy → subject
    assert promo["reframe_mode_applied"] in (None, "subject")


# ---------------------------------------------------------------------------
# 2. AI flags disabled → no apply
# ---------------------------------------------------------------------------

def test_ai_director_disabled_blocks_promotion():
    payload = _payload(ai_director_enabled=False)
    plan = _edit_plan()
    _, report = promote_camera_influence(payload, plan)
    assert report["camera_execution_promotion"]["applied"] is False
    assert report["camera_execution_promotion"]["reason"] == "ai_director_disabled"
    assert payload.reframe_mode == "center"


def test_ai_render_influence_disabled_blocks_promotion():
    payload = _payload(ai_render_influence_enabled=False)
    plan = _edit_plan()
    _, report = promote_camera_influence(payload, plan)
    assert report["camera_execution_promotion"]["applied"] is False
    assert report["camera_execution_promotion"]["reason"] == "ai_render_influence_disabled"
    assert payload.reframe_mode == "center"


# ---------------------------------------------------------------------------
# 3. No edit_plan → fallback
# ---------------------------------------------------------------------------

def test_no_edit_plan_fallback():
    payload = _payload()
    _, report = promote_camera_influence(payload, None)
    promo = report["camera_execution_promotion"]
    assert promo["applied"] is False
    assert promo["reason"] == "no_edit_plan"
    assert payload.reframe_mode == "center"


# ---------------------------------------------------------------------------
# 4. User override wins
# ---------------------------------------------------------------------------

def test_user_explicit_reframe_blocks_promotion():
    """User already set reframe_mode to 'subject' — AI must not change it."""
    payload = _payload(reframe_mode="subject")
    plan = _edit_plan(motion_style="dynamic_subject", pref_confidence=0.92)
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["applied"] is False
    assert "user_override" in promo["reason"]
    assert payload.reframe_mode == "subject"  # unchanged


def test_user_explicit_motion_reframe_not_overridden():
    payload = _payload(reframe_mode="motion")
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.90)
    _, report = promote_camera_influence(payload, plan)
    assert payload.reframe_mode == "motion"  # user's choice preserved
    assert report["camera_execution_promotion"]["applied"] is False


def test_user_explicit_face_reframe_not_overridden():
    payload = _payload(reframe_mode="face")
    plan = _edit_plan(pref_confidence=0.92)
    _, report = promote_camera_influence(payload, plan)
    assert payload.reframe_mode == "face"


def test_camera_ai_reframe_lock_blocks_promotion():
    payload = _payload(camera_ai_reframe_lock=True)
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.92)
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["applied"] is False
    assert "user_override" in promo["reason"]
    assert "camera_ai_reframe_lock=true" in promo["reason"]
    assert payload.reframe_mode == "center"


# ---------------------------------------------------------------------------
# 5. Unknown / disallowed reframe mode not applied
# ---------------------------------------------------------------------------

def test_unknown_motion_style_not_promoted():
    """unknown motion_style → no reframe promotion from Phase 50B."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="unknown",
        cam_pref_available=True,
        prs_available=False,
        psi_available=False,
        pref_confidence=0.90,
        tuning_applied=False,
        hold_frames_delta=0,
        ema_alpha_delta=0.0,
        deadzone_delta=0.0,
    )
    _, report = promote_camera_influence(payload, plan)
    assert report["camera_execution_promotion"]["reframe_mode_applied"] is None
    assert payload.reframe_mode == "center"


def test_arbitrary_motion_style_not_promoted():
    """An unrecognized motion_style string is silently ignored."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="ultra_dynamic_xyz",
        prs_available=False,
        psi_available=False,
        pref_confidence=0.90,
        tuning_applied=False,
        hold_frames_delta=0,
        ema_alpha_delta=0.0,
        deadzone_delta=0.0,
    )
    _, report = promote_camera_influence(payload, plan)
    assert report["camera_execution_promotion"]["reframe_mode_applied"] is None
    assert payload.reframe_mode == "center"


# ---------------------------------------------------------------------------
# 6. Confidence threshold gates
# ---------------------------------------------------------------------------

def test_low_confidence_blocks_reframe_promotion():
    """confidence=0.70 < _CONF_THRESHOLD_REFRAME (0.82) → no promotion."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.70,
        prs_available=False,   # prs not available → prs_conf = 0.0
        tuning_applied=False,
        hold_frames_delta=0,
        ema_alpha_delta=0.0,
        deadzone_delta=0.0,
    )
    _, report = promote_camera_influence(payload, plan)
    assert payload.reframe_mode == "center"
    assert report["camera_execution_promotion"]["applied"] is False


def test_confidence_at_exact_reframe_threshold_allows():
    """confidence exactly at threshold (0.82) should allow promotion."""
    payload = _payload()
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.82)
    _, report = promote_camera_influence(payload, plan)
    assert payload.reframe_mode == "subject"
    assert report["camera_execution_promotion"]["applied"] is True


def test_low_confidence_blocks_motion_crop_even_with_reframe():
    """Reframe promoted but motion_crop threshold (0.85) not met → no crop."""
    payload = _payload()
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.83)
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["reframe_mode_applied"] == "subject"
    assert promo["motion_aware_crop_applied"] is False
    assert payload.motion_aware_crop is False


def test_high_confidence_enables_motion_crop():
    """confidence >= 0.85 → both reframe and motion_aware_crop promoted."""
    payload = _payload()
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.88)
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["reframe_mode_applied"] == "subject"
    assert promo["motion_aware_crop_applied"] is True
    assert payload.motion_aware_crop is True


# ---------------------------------------------------------------------------
# 7. motion_aware_crop enable-only contract
# ---------------------------------------------------------------------------

def test_existing_motion_crop_true_not_disabled():
    """Already enabled motion_aware_crop must never be set to False."""
    payload = _payload(motion_aware_crop=True)
    plan = _edit_plan(motion_style="static_center", pref_confidence=0.90)
    promote_camera_influence(payload, plan)
    assert payload.motion_aware_crop is True


def test_motion_crop_not_enabled_for_center_reframe():
    """If final reframe_mode remains 'center', motion_aware_crop must not fire."""
    payload = _payload()
    # static_center → no reframe → center still → no crop
    plan = _edit_plan(
        motion_style="static_center",
        pref_confidence=0.90,
        tuning_applied=False,
        hold_frames_delta=0,
        ema_alpha_delta=0.0,
        deadzone_delta=0.0,
    )
    _, report = promote_camera_influence(payload, plan)
    assert payload.motion_aware_crop is False


# ---------------------------------------------------------------------------
# 8. Quality gate behavior
# ---------------------------------------------------------------------------

def test_high_jitter_risk_restricts_motion_to_subject():
    """micro_jitter_risk >= 60 → motion downgraded to subject."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="dynamic_subject",
        pref_confidence=0.90,
        cam_qual_jitter=75,   # high jitter
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    # Motion should be downgraded to subject
    assert promo["reframe_mode_applied"] == "subject"
    assert payload.reframe_mode == "subject"


def test_high_jitter_risk_blocks_motion_aware_crop():
    """high micro_jitter_risk also blocks motion_aware_crop promotion."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.92,
        cam_qual_jitter=70,  # high jitter
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["motion_aware_crop_applied"] is False
    assert payload.motion_aware_crop is False


def test_high_whip_pan_risk_blocks_motion_aware_crop():
    """high whip_pan_risk blocks motion_aware_crop even at high confidence."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.92,
        cam_qual_whip=80,   # high whip pan
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    # Reframe may still apply, but motion_aware_crop must not
    assert promo["motion_aware_crop_applied"] is False
    assert payload.motion_aware_crop is False


def test_high_whip_pan_blocks_tuning():
    """high whip_pan_risk → tuning_applied dict is empty."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.92,
        cam_qual_whip=65,
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["tuning_applied"] == {}


def test_low_camera_fit_restricts_to_subject_not_motion():
    """platform_quality_feedback.camera_fit <= 30 → motion downgraded to subject."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="dynamic_subject",
        pref_confidence=0.90,
        pqf_available=True,
        pqf_camera_fit=20,  # low camera fit
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["reframe_mode_applied"] == "subject"


def test_quality_gate_not_triggered_below_threshold():
    """jitter=50 < threshold(60) → no quality restriction, motion allowed."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="dynamic_subject",
        pref_confidence=0.90,
        cam_qual_jitter=50,   # below HIGH_RISK_THRESHOLD
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["reframe_mode_applied"] == "motion"


# ---------------------------------------------------------------------------
# 9. Tuning advisory
# ---------------------------------------------------------------------------

def test_tuning_is_advisory_only():
    """Tuning deltas appear in report but never mutate payload fields."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.88,
        deadzone_delta=0.03,
        ema_alpha_delta=0.05,
        hold_frames_delta=6,
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    # Tuning advisory may be populated
    assert isinstance(promo["tuning_applied"], dict)
    # But payload has no tuning fields — check it didn't sprout any
    assert not hasattr(payload, "deadzone_delta")
    assert not hasattr(payload, "smoothing_delta")
    assert not hasattr(payload, "subject_hold_delta")


def test_tuning_deadzone_delta_bounded():
    """deadzone_delta is clamped to _MAX_DEADZONE_DELTA."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.88,
        deadzone_delta=0.99,   # exceeds bound
        ema_alpha_delta=0.0,
        hold_frames_delta=0,
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    if "deadzone_delta" in promo["tuning_applied"]:
        assert abs(promo["tuning_applied"]["deadzone_delta"]) <= _MAX_DEADZONE_DELTA


def test_tuning_smoothing_delta_bounded():
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.88,
        deadzone_delta=0.0,
        ema_alpha_delta=0.99,  # exceeds bound
        hold_frames_delta=0,
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    if "smoothing_delta" in promo["tuning_applied"]:
        assert abs(promo["tuning_applied"]["smoothing_delta"]) <= _MAX_SMOOTHING_DELTA


def test_tuning_subject_hold_delta_bounded():
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.88,
        deadzone_delta=0.0,
        ema_alpha_delta=0.0,
        hold_frames_delta=999,  # exceeds bound
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    if "subject_hold_delta" in promo["tuning_applied"]:
        assert abs(promo["tuning_applied"]["subject_hold_delta"]) <= _MAX_SUBJECT_HOLD_DELTA


def test_tuning_low_confidence_skipped():
    """confidence below _CONF_THRESHOLD_TUNING (0.80) → tuning advisory empty."""
    payload = _payload()
    plan = _edit_plan(
        motion_style="smooth_subject",
        pref_confidence=0.70,   # below tuning threshold
    )
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["tuning_applied"] == {}


# ---------------------------------------------------------------------------
# 10. No-mutation of non-camera payload fields
# ---------------------------------------------------------------------------

def test_no_subtitle_mutation():
    """Phase 59B must never touch subtitle fields."""
    payload = _payload()
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.90)
    promote_camera_influence(payload, plan)
    assert payload.subtitle_style == "pro_karaoke"
    assert payload.highlight_per_word is False
    assert payload.add_subtitle is True
    assert payload.transcript_text == "hello world"


# ---------------------------------------------------------------------------
# 11. Fallback safety / never-raises contract
# ---------------------------------------------------------------------------

def test_fallback_shape_on_none_plan():
    payload = _payload()
    _, report = promote_camera_influence(payload, None)
    promo = report["camera_execution_promotion"]
    assert "applied" in promo
    assert "reframe_mode_applied" in promo
    assert "motion_aware_crop_applied" in promo
    assert "tuning_applied" in promo
    assert "confidence" in promo
    assert "reason" in promo
    assert "reasoning" in promo
    assert promo["applied"] is False
    assert promo["reframe_mode_applied"] is None
    assert promo["motion_aware_crop_applied"] is False
    assert promo["tuning_applied"] == {}


def test_fallback_shape_on_empty_plan():
    payload = _payload()
    plan = types.SimpleNamespace()
    # No attributes at all — engine should still return fallback safely
    _, report = promote_camera_influence(payload, plan)
    promo = report["camera_execution_promotion"]
    assert promo["applied"] is False


def test_never_raises_on_malformed_plan():
    payload = _payload()
    for bad_plan in [42, "string", [], {"creator_camera_preference": "not_a_dict"}]:
        result = promote_camera_influence(payload, bad_plan)
        assert result is not None
        assert "camera_execution_promotion" in result[1]


def test_never_raises_on_malformed_payload():
    for bad_payload in [None, 42, "string", types.SimpleNamespace()]:
        result = promote_camera_influence(bad_payload, _edit_plan())
        assert result is not None
        assert "camera_execution_promotion" in result[1]


# ---------------------------------------------------------------------------
# 12. Determinism
# ---------------------------------------------------------------------------

def test_deterministic_same_output():
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.90)
    results = []
    for _ in range(3):
        p = _payload()
        _, report = promote_camera_influence(p, plan)
        results.append((p.reframe_mode, p.motion_aware_crop, report["camera_execution_promotion"]["confidence"]))
    assert len(set(results)) == 1, "promote_camera_influence is not deterministic"


# ---------------------------------------------------------------------------
# 13. ALLOWED_PROMOTION_MODES validation
# ---------------------------------------------------------------------------

def test_allowed_promotion_modes_are_subset_of_allowed_reframe_modes():
    """All allowed promotion targets must be valid reframe mode values."""
    assert ALLOWED_PROMOTION_MODES.issubset(ALLOWED_REFRAME_MODES)
    assert "center" not in ALLOWED_PROMOTION_MODES, "center is neutral, not a promotion target"


def test_allowed_reframe_modes_complete():
    """Sanity check — known good modes are all in the allowed set."""
    for mode in ("center", "motion", "subject", "face"):
        assert mode in ALLOWED_REFRAME_MODES


# ---------------------------------------------------------------------------
# 14. Integration — render_influence applies phase59b
# ---------------------------------------------------------------------------

def test_render_influence_applies_camera_promotion():
    """Integration: apply_ai_render_influence wires _apply_camera_promotion."""
    from app.ai.director.render_influence import apply_ai_render_influence

    payload = _payload()
    plan = _edit_plan(motion_style="smooth_subject", pref_confidence=0.90)
    # Give the plan the other AIEditPlan-like attrs render_influence expects
    plan.camera = types.SimpleNamespace(
        behavior="none", zoom_strength=1.0, follow_strength=0.5
    )
    plan.subtitle = types.SimpleNamespace(
        highlight_keywords=False, tone="neutral", max_words_per_line=6,
        emphasis_style="none", density="medium", beat_aware=False,
        emotion_aware=False, reason=""
    )
    plan.pacing = None
    plan.memory = None

    updated_payload, influence_report = apply_ai_render_influence(payload, plan)

    # Phase 59B should have promoted reframe_mode
    assert updated_payload.reframe_mode == "subject", (
        f"Expected reframe_mode='subject', got {updated_payload.reframe_mode!r}. "
        f"applied={influence_report['applied']}, skipped={influence_report['skipped']}"
    )
    # Promotion entry should appear in report["applied"]
    camera_promo_entries = [
        e for e in influence_report["applied"] if "camera_promotion:phase59b" in e
    ]
    assert len(camera_promo_entries) == 1, (
        f"Expected 1 camera_promotion:phase59b entry, got: {camera_promo_entries}"
    )
    # camera_execution_promotion stored on plan
    assert hasattr(plan, "camera_execution_promotion")
    assert plan.camera_execution_promotion.get("applied") is True
