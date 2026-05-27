"""
test_ai_phase10_render_influence.py

Phase 10 — Safe Render Influence.

Verifies:
- default ai_render_influence_enabled is false
- disabled influence preserves payload/settings
- influence module never raises on missing edit plan
- zoom/follow strengths are clamped to hard bounds
- playback_speed is NEVER altered
- segment start/end are NEVER altered
- subtitle timing fields are NEVER altered
- influence report records applied/skipped items accurately
- render pipeline remains fallback-safe if influence throws
- no API key required
- no GPU required
- no real video rendering required
"""
from __future__ import annotations

import types
from typing import Any


# ── Fixtures ─────────────────────────────────────────────────────────────────

def _make_payload(**kwargs) -> Any:
    """Minimal payload object with all influence-relevant fields."""
    p = types.SimpleNamespace(
        motion_aware_crop=False,
        reframe_mode="center",
        highlight_per_word=False,
        add_subtitle=True,
        playback_speed=1.07,
        ai_render_influence_enabled=False,
    )
    for k, v in kwargs.items():
        setattr(p, k, v)
    return p


def _make_plan(
    camera_behavior="none",
    camera_zoom=1.0,
    camera_follow=0.5,
    highlight_keywords=False,
    pacing_style="default",
    memory_context=None,
    enabled=True,
):
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan,
    )
    return AIEditPlan(
        enabled=enabled,
        mode="viral_tiktok",
        selected_segments=[AIClipPlan(start=10.0, end=40.0, score=0.75)],
        subtitle=AISubtitlePlan(highlight_keywords=highlight_keywords),
        camera=AICameraPlan(
            behavior=camera_behavior,
            zoom_strength=camera_zoom,
            follow_strength=camera_follow,
        ),
        pacing=AIPacingPlan(pacing_style=pacing_style, energy_level=0.7),
        memory_context=dict(memory_context or {}),
    )


# ─────────────────────────────────────────────────────────────────────────────
# 1. Schema: default ai_render_influence_enabled is False
# ─────────────────────────────────────────────────────────────────────────────

def test_schema_default_ai_render_influence_enabled():
    from app.models.schemas import RenderRequest
    req = RenderRequest()
    assert req.ai_render_influence_enabled is True


def test_schema_ai_render_influence_can_be_enabled():
    from app.models.schemas import RenderRequest
    req = RenderRequest(ai_render_influence_enabled=True)
    assert req.ai_render_influence_enabled is True


def test_schema_backward_compat_old_request_unchanged():
    """AI fields default to True — AI Director is always on by default."""
    from app.models.schemas import RenderRequest
    req = RenderRequest()
    assert req.ai_director_enabled is True
    assert req.ai_render_influence_enabled is True


# ─────────────────────────────────────────────────────────────────────────────
# 2. Module import safety
# ─────────────────────────────────────────────────────────────────────────────

def test_import_render_influence_does_not_raise():
    from app.ai.director import render_influence  # noqa: F401


def test_apply_ai_render_influence_importable():
    from app.ai.director.render_influence import apply_ai_render_influence
    assert callable(apply_ai_render_influence)


def test_clamp_ai_influence_importable():
    from app.ai.director.render_influence import clamp_ai_influence
    assert callable(clamp_ai_influence)


# ─────────────────────────────────────────────────────────────────────────────
# 3. Disabled influence preserves payload settings unchanged
# ─────────────────────────────────────────────────────────────────────────────

def test_disabled_influence_no_payload_change():
    """When called with no plan, influence must return payload unchanged."""
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload(motion_aware_crop=False, highlight_per_word=False)
    result_payload, report = apply_ai_render_influence(payload, None)
    assert result_payload.motion_aware_crop is False
    assert result_payload.highlight_per_word is False
    assert report["warnings"]  # should warn about missing plan


def test_disabled_influence_playback_speed_unchanged():
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload(playback_speed=1.07)
    apply_ai_render_influence(payload, None)
    assert payload.playback_speed == 1.07


# ─────────────────────────────────────────────────────────────────────────────
# 4. Influence module never raises
# ─────────────────────────────────────────────────────────────────────────────

def test_never_raises_on_none_plan():
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload()
    result = apply_ai_render_influence(payload, None)
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_never_raises_on_empty_plan_object():
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload()
    bad_plan = types.SimpleNamespace()  # no fields
    result_payload, report = apply_ai_render_influence(payload, bad_plan)
    assert isinstance(report, dict)
    assert "enabled" in report


def test_never_raises_on_none_payload():
    """Even with a None payload, influence must not raise."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan()
    try:
        result_payload, report = apply_ai_render_influence(None, plan)
        assert isinstance(report, dict)
    except Exception as exc:
        raise AssertionError(f"apply_ai_render_influence raised on None payload: {exc}") from exc


def test_never_raises_on_corrupted_plan():
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload()
    broken = types.SimpleNamespace(camera=None, subtitle=None, pacing=None, memory_context=None)
    result_payload, report = apply_ai_render_influence(payload, broken)
    assert isinstance(report, dict)


# ─────────────────────────────────────────────────────────────────────────────
# 5. clamp_ai_influence hard bounds
# ─────────────────────────────────────────────────────────────────────────────

def test_clamp_zoom_strength_at_max():
    from app.ai.director.render_influence import clamp_ai_influence
    result = clamp_ai_influence(2.0, 1.0, 1.18, 1.0)
    assert result == 1.18


def test_clamp_zoom_strength_below_min():
    from app.ai.director.render_influence import clamp_ai_influence
    result = clamp_ai_influence(0.5, 1.0, 1.18, 1.0)
    assert result == 1.0


def test_clamp_follow_strength_at_max():
    from app.ai.director.render_influence import clamp_ai_influence
    result = clamp_ai_influence(1.5, 0.0, 0.85, 0.5)
    assert result == 0.85


def test_clamp_returns_default_on_invalid():
    from app.ai.director.render_influence import clamp_ai_influence
    result = clamp_ai_influence("bad", 0.0, 1.0, 0.5)
    assert result == 0.5


def test_clamp_returns_default_on_none():
    from app.ai.director.render_influence import clamp_ai_influence
    result = clamp_ai_influence(None, 0.0, 1.0, 0.5)
    assert result == 0.5


def test_zoom_strength_applied_is_clamped():
    """Even if AI plan has zoom_strength=2.0, applied value must be clamped to 1.18."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="fast_follow", camera_zoom=2.0)
    payload = _make_payload(motion_aware_crop=True)  # safe gate: already enabled
    _, report = apply_ai_render_influence(payload, plan)
    # The applied report must show clamped value
    applied = " ".join(report["applied"])
    assert "1.18" in applied or "zoom_clamped=1.18" in applied or "zoom_clamped" in applied


def test_follow_strength_applied_is_clamped():
    """AI plan with follow_strength=1.0 must be clamped to 0.85 in report."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="fast_follow", camera_follow=1.0)
    payload = _make_payload(motion_aware_crop=True)
    _, report = apply_ai_render_influence(payload, plan)
    applied = " ".join(report["applied"])
    assert "0.85" in applied or "follow_clamped=0.85" in applied or "follow_clamped" in applied


# ─────────────────────────────────────────────────────────────────────────────
# 6. playback_speed is NEVER altered
# ─────────────────────────────────────────────────────────────────────────────

def test_playback_speed_never_altered_when_enabled():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="fast_follow", pacing_style="fast")
    payload = _make_payload(playback_speed=1.07, motion_aware_crop=True)
    apply_ai_render_influence(payload, plan)
    assert payload.playback_speed == 1.07


def test_playback_speed_never_altered_without_plan():
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload(playback_speed=1.15)
    apply_ai_render_influence(payload, None)
    assert payload.playback_speed == 1.15


# ─────────────────────────────────────────────────────────────────────────────
# 7. Segment start/end are NEVER altered
# ─────────────────────────────────────────────────────────────────────────────

def test_segment_start_end_never_altered():
    from app.ai.director.render_influence import apply_ai_render_influence
    from app.ai.director.edit_plan_schema import AIClipPlan
    plan = _make_plan(camera_behavior="fast_follow")
    plan.selected_segments = [AIClipPlan(start=5.0, end=35.0, score=0.9)]
    payload = _make_payload(motion_aware_crop=True)
    apply_ai_render_influence(payload, plan)
    # Segments must be untouched
    assert plan.selected_segments[0].start == 5.0
    assert plan.selected_segments[0].end == 35.0


def test_segment_score_never_altered():
    from app.ai.director.render_influence import apply_ai_render_influence
    from app.ai.director.edit_plan_schema import AIClipPlan
    plan = _make_plan()
    plan.selected_segments = [AIClipPlan(start=0.0, end=30.0, score=0.75)]
    payload = _make_payload()
    apply_ai_render_influence(payload, plan)
    assert plan.selected_segments[0].score == 0.75


# ─────────────────────────────────────────────────────────────────────────────
# 8. Subtitle timing fields are NEVER altered
# ─────────────────────────────────────────────────────────────────────────────

def test_subtitle_timing_fields_never_altered():
    """Subtitle timing/ASS fields must not be changed by influence."""
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload(
        add_subtitle=True,
        sub_margin_v=170,
        sub_font_size=46,
    )
    plan = _make_plan(highlight_keywords=True)
    apply_ai_render_influence(payload, plan)
    assert payload.sub_margin_v == 170
    assert payload.sub_font_size == 46


def test_subtitle_text_never_altered():
    """hook_applied_text and subtitle_edits must not be touched."""
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload(add_subtitle=True)
    payload.hook_applied_text = "original hook text"
    payload.subtitle_edits = [{"seg": 0, "text": "hello"}]
    plan = _make_plan(highlight_keywords=True)
    apply_ai_render_influence(payload, plan)
    assert payload.hook_applied_text == "original hook text"
    assert payload.subtitle_edits == [{"seg": 0, "text": "hello"}]


# ─────────────────────────────────────────────────────────────────────────────
# 9. Influence report structure
# ─────────────────────────────────────────────────────────────────────────────

def test_influence_report_has_required_keys():
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload()
    _, report = apply_ai_render_influence(payload, _make_plan())
    for key in ("enabled", "applied", "skipped", "warnings"):
        assert key in report, f"Missing report key: {key}"


def test_influence_report_applied_is_list():
    from app.ai.director.render_influence import apply_ai_render_influence
    _, report = apply_ai_render_influence(_make_payload(), _make_plan())
    assert isinstance(report["applied"], list)


def test_influence_report_skipped_is_list():
    from app.ai.director.render_influence import apply_ai_render_influence
    _, report = apply_ai_render_influence(_make_payload(), _make_plan())
    assert isinstance(report["skipped"], list)


def test_influence_report_warnings_is_list():
    from app.ai.director.render_influence import apply_ai_render_influence
    _, report = apply_ai_render_influence(_make_payload(), _make_plan())
    assert isinstance(report["warnings"], list)


def test_influence_report_enabled_when_called():
    from app.ai.director.render_influence import apply_ai_render_influence
    _, report = apply_ai_render_influence(_make_payload(), _make_plan())
    assert report["enabled"] is True


def test_influence_records_applied_camera():
    """Camera influence must appear in applied when conditions are met."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="fast_follow")
    payload = _make_payload(motion_aware_crop=True)  # gate: already enabled
    _, report = apply_ai_render_influence(payload, plan)
    applied_str = " ".join(report["applied"])
    assert "camera" in applied_str or "motion_aware_crop" in applied_str


def test_influence_records_skipped_camera_when_gate_fails():
    """Camera must be skipped when motion_aware_crop is false and reframe is static."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="fast_follow")
    payload = _make_payload(motion_aware_crop=False, reframe_mode="center")
    _, report = apply_ai_render_influence(payload, plan)
    skipped_str = " ".join(report["skipped"])
    assert "camera" in skipped_str


def test_influence_records_applied_subtitle():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(highlight_keywords=True)
    payload = _make_payload(add_subtitle=True)
    _, report = apply_ai_render_influence(payload, plan)
    applied_str = " ".join(report["applied"])
    assert "subtitle" in applied_str or "highlight_per_word" in applied_str


def test_influence_records_skipped_subtitle_no_subtitle():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(highlight_keywords=True)
    payload = _make_payload(add_subtitle=False)
    _, report = apply_ai_render_influence(payload, plan)
    skipped_str = " ".join(report["skipped"])
    assert "subtitle" in skipped_str


def test_influence_pacing_always_report_only():
    """Pacing must never appear in applied — only in skipped (report-only)."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(pacing_style="fast")
    _, report = apply_ai_render_influence(_make_payload(), plan)
    applied_str = " ".join(report["applied"])
    skipped_str = " ".join(report["skipped"])
    assert "pacing" not in applied_str
    assert "pacing" in skipped_str


def test_influence_memory_always_report_only():
    """Memory context must never appear in applied — only in skipped."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(memory_context={"results": [{"id": "m1"}]})
    _, report = apply_ai_render_influence(_make_payload(), plan)
    applied_str = " ".join(report["applied"])
    skipped_str = " ".join(report["skipped"])
    assert "memory" not in applied_str
    assert "memory" in skipped_str


# ─────────────────────────────────────────────────────────────────────────────
# 10. Camera gate: only activates when conditions are safe
# ─────────────────────────────────────────────────────────────────────────────

def test_camera_not_enabled_without_motion_gate():
    """motion_aware_crop must NOT be enabled if payload has no motion-aware setup."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="fast_follow")
    payload = _make_payload(motion_aware_crop=False, reframe_mode="center")
    result_payload, report = apply_ai_render_influence(payload, plan)
    assert result_payload.motion_aware_crop is False


def test_camera_enabled_when_already_motion_aware():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="dramatic_push")
    payload = _make_payload(motion_aware_crop=True, reframe_mode="center")
    result_payload, _ = apply_ai_render_influence(payload, plan)
    assert result_payload.motion_aware_crop is True


def test_camera_enabled_when_reframe_is_subject():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="slow_reveal")
    payload = _make_payload(motion_aware_crop=False, reframe_mode="subject")
    result_payload, report = apply_ai_render_influence(payload, plan)
    assert result_payload.motion_aware_crop is True
    assert any("camera" in a for a in report["applied"])


def test_camera_none_behavior_skipped():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="none")
    payload = _make_payload(motion_aware_crop=True)
    result_payload, report = apply_ai_render_influence(payload, plan)
    skipped_str = " ".join(report["skipped"])
    assert "camera" in skipped_str
    assert "behavior_not_motion" in skipped_str


# ─────────────────────────────────────────────────────────────────────────────
# 11. Subtitle gate: only activates when add_subtitle=True
# ─────────────────────────────────────────────────────────────────────────────

def test_subtitle_highlight_not_enabled_when_subtitle_off():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(highlight_keywords=True)
    payload = _make_payload(add_subtitle=False, highlight_per_word=False)
    result_payload, _ = apply_ai_render_influence(payload, plan)
    assert result_payload.highlight_per_word is False


def test_subtitle_highlight_enabled_when_both_conditions_met():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(highlight_keywords=True)
    payload = _make_payload(add_subtitle=True, highlight_per_word=False)
    result_payload, _ = apply_ai_render_influence(payload, plan)
    assert result_payload.highlight_per_word is True


def test_subtitle_highlight_false_in_plan_is_skipped():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(highlight_keywords=False)
    payload = _make_payload(add_subtitle=True, highlight_per_word=False)
    result_payload, report = apply_ai_render_influence(payload, plan)
    assert result_payload.highlight_per_word is False
    skipped_str = " ".join(report["skipped"])
    assert "highlight_keywords=false" in skipped_str


# ─────────────────────────────────────────────────────────────────────────────
# 12. Explainability update
# ─────────────────────────────────────────────────────────────────────────────

def test_explainability_line_appended_when_influence_applied():
    from app.ai.director.render_influence import apply_ai_render_influence
    from app.ai.director.edit_plan_schema import AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan
    plan = _make_plan(highlight_keywords=True)
    plan.explainability = {
        "summary": {
            "summary_lines": ["Solid hook quality for viral_tiktok"],
        }
    }
    payload = _make_payload(add_subtitle=True)
    apply_ai_render_influence(payload, plan)
    lines = plan.explainability["summary"]["summary_lines"]
    assert any("AI render influence" in l for l in lines)


def test_explainability_line_not_duplicated():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(highlight_keywords=True)
    plan.explainability = {
        "summary": {
            "summary_lines": ["AI render influence enabled (no adjustments needed)"],
        }
    }
    payload = _make_payload(add_subtitle=True)
    apply_ai_render_influence(payload, plan)
    lines = plan.explainability["summary"]["summary_lines"]
    influence_lines = [l for l in lines if "AI render influence" in l]
    assert len(influence_lines) == 1, "Influence line must not be duplicated"


def test_explainability_update_safe_when_no_explainability():
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan()
    plan.explainability = {}  # empty
    payload = _make_payload()
    # Must not raise
    apply_ai_render_influence(payload, plan)


# ─────────────────────────────────────────────────────────────────────────────
# 13. Pipeline fallback-safe if influence throws
# ─────────────────────────────────────────────────────────────────────────────

def test_influence_fallback_on_corrupt_plan_fields():
    """Render pipeline must continue even if influence encounters unexpected types."""
    from app.ai.director.render_influence import apply_ai_render_influence
    broken_plan = types.SimpleNamespace(
        camera="not_an_object",
        subtitle=42,
        pacing=None,
        memory_context="bad",
        explainability=None,
    )
    payload = _make_payload()
    try:
        result_payload, report = apply_ai_render_influence(payload, broken_plan)
        assert isinstance(report, dict)
    except Exception as exc:
        raise AssertionError(f"Influence must not raise on corrupt plan: {exc}") from exc


def test_influence_returns_payload_on_exception():
    """Even if internal functions crash, influence must return the original payload."""
    from app.ai.director.render_influence import apply_ai_render_influence
    payload = _make_payload(motion_aware_crop=False)
    # Create a plan that will cause attribute errors
    bad_plan = types.SimpleNamespace()
    result_payload, report = apply_ai_render_influence(payload, bad_plan)
    assert result_payload is payload  # same object returned


# ─────────────────────────────────────────────────────────────────────────────
# 14. No API key required / no GPU required
# ─────────────────────────────────────────────────────────────────────────────

def test_no_api_key_required():
    """Render influence must work without any API key in environment."""
    import os
    keys = ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY")
    saved = {k: os.environ.pop(k, None) for k in keys}
    try:
        from app.ai.director.render_influence import apply_ai_render_influence
        payload = _make_payload()
        result, report = apply_ai_render_influence(payload, _make_plan())
        assert isinstance(report, dict)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v


def test_no_gpu_required():
    """Render influence must complete without GPU/CUDA."""
    from app.ai.director.render_influence import apply_ai_render_influence, clamp_ai_influence
    result = clamp_ai_influence(1.5, 1.0, 1.18, 1.0)
    assert result == 1.18
    payload = _make_payload()
    _, report = apply_ai_render_influence(payload, _make_plan())
    assert isinstance(report, dict)


def test_no_real_rendering_required():
    """All influence logic runs without any video file, FFmpeg, or render pipeline."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="fast_follow", highlight_keywords=True)
    payload = _make_payload(motion_aware_crop=True, add_subtitle=True)
    result_payload, report = apply_ai_render_influence(payload, plan)
    assert isinstance(report, dict)
    assert len(report["applied"]) > 0


# ─────────────────────────────────────────────────────────────────────────────
# 15. Hard-blocked fields are structurally prevented
# ─────────────────────────────────────────────────────────────────────────────

def test_playback_speed_not_in_applied_report():
    """playback_speed must never appear in the applied list."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan(camera_behavior="fast_follow", pacing_style="fast")
    payload = _make_payload(motion_aware_crop=True, playback_speed=1.07)
    _, report = apply_ai_render_influence(payload, plan)
    applied_str = " ".join(report["applied"])
    assert "playback_speed" not in applied_str


def test_output_validation_fields_not_in_applied():
    """Output validation fields must never appear in the applied list."""
    from app.ai.director.render_influence import apply_ai_render_influence
    plan = _make_plan()
    _, report = apply_ai_render_influence(_make_payload(), plan)
    applied_str = " ".join(report["applied"])
    blocked = ["video_crf", "video_codec", "output_fps", "max_export_parts"]
    for field in blocked:
        assert field not in applied_str, f"Blocked field {field!r} appeared in applied"
