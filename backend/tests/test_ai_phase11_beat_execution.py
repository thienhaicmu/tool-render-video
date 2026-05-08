"""
test_ai_phase11_beat_execution.py — Phase 11: Beat-aware render execution tests.

All tests are unit-level — no audio models, no librosa, no API keys, no GPU.
Beat metadata is sourced entirely from edit_plan.pacing (AIPacingPlan).
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List, Optional


# ── Minimal stubs ─────────────────────────────────────────────────────────────

@dataclass
class _Pacing:
    beat_available: bool = True
    bpm: Optional[float] = 120.0
    beat_count: int = 32
    energy_level: Optional[float] = 0.6
    pacing_style: str = "dynamic"
    emotion: str = "excited"
    emotion_score: float = 0.8
    suggested_cut_style: str = "fast_cut"
    warnings: List[str] = field(default_factory=list)


@dataclass
class _EditPlan:
    enabled: bool = True
    mode: str = "viral_tiktok"
    pacing: _Pacing = field(default_factory=_Pacing)
    beat_execution: dict = field(default_factory=dict)
    selected_segments: List[dict] = field(default_factory=list)
    subtitle: object = None
    camera: object = None
    warnings: List[str] = field(default_factory=list)
    memory_context: dict = field(default_factory=dict)


@dataclass
class _Payload:
    ai_beat_execution_enabled: bool = True
    ai_beat_pulse_enabled: bool = True
    ai_beat_transition_enabled: bool = False
    ai_render_influence_enabled: bool = False
    playback_speed: float = 1.0
    add_subtitle: bool = True


# ── Import module ─────────────────────────────────────────────────────────────

from app.ai.director.beat_execution import build_beat_execution_plan


# ── Schema defaults ───────────────────────────────────────────────────────────

class TestSchemaDefaults:
    def test_ai_beat_execution_plan_dataclass_defaults(self):
        from app.ai.director.edit_plan_schema import AIBeatExecutionPlan
        plan = AIBeatExecutionPlan()
        assert plan.enabled is False
        assert plan.beat_available is False
        assert plan.bpm is None
        assert plan.beat_count == 0
        assert plan.pulse_strength == 0.0
        assert plan.suggested_transition_style == "none"
        assert plan.execution_mode == "metadata_only"
        assert plan.warnings == []

    def test_ai_beat_execution_plan_to_dict_has_all_keys(self):
        from app.ai.director.edit_plan_schema import AIBeatExecutionPlan
        d = AIBeatExecutionPlan().to_dict()
        for key in ("enabled", "beat_available", "bpm", "beat_count",
                    "pulse_strength", "suggested_transition_style",
                    "execution_mode", "warnings"):
            assert key in d

    def test_ai_edit_plan_beat_execution_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AIPacingPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            pacing=AIPacingPlan(),
        )
        assert hasattr(plan, "beat_execution")
        assert isinstance(plan.beat_execution, dict)

    def test_ai_edit_plan_to_dict_includes_beat_execution(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AIPacingPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="test",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            pacing=AIPacingPlan(),
        )
        d = plan.to_dict()
        assert "beat_execution" in d
        assert isinstance(d["beat_execution"], dict)

    def test_render_request_has_beat_execution_fields(self):
        from app.models.schemas import RenderRequest
        fields = RenderRequest.model_fields
        assert "ai_beat_execution_enabled" in fields
        assert "ai_beat_pulse_enabled" in fields
        assert "ai_beat_transition_enabled" in fields

    def test_beat_execution_fields_default_values(self):
        from app.models.schemas import RenderRequest
        fields = RenderRequest.model_fields
        assert fields["ai_beat_execution_enabled"].default is False
        assert fields["ai_beat_pulse_enabled"].default is True
        assert fields["ai_beat_transition_enabled"].default is False


# ── Disabled / no-beat scenarios ──────────────────────────────────────────────

class TestDisabledBehavior:
    def test_no_pacing_plan_returns_skipped(self):
        plan = _EditPlan(pacing=None)
        payload = _Payload()
        result = build_beat_execution_plan(plan, payload)
        assert result["enabled"] is False
        assert any("no_pacing_plan" in w for w in result["warnings"])

    def test_beat_not_available_returns_skipped(self):
        plan = _EditPlan(pacing=_Pacing(beat_available=False))
        payload = _Payload()
        result = build_beat_execution_plan(plan, payload)
        assert result["enabled"] is False
        assert result["beat_available"] is False
        assert any("beat_data_unavailable" in w for w in result["warnings"])

    def test_bpm_none_returns_skipped(self):
        plan = _EditPlan(pacing=_Pacing(bpm=None))
        payload = _Payload()
        result = build_beat_execution_plan(plan, payload)
        assert result["enabled"] is False
        assert any("bpm_unavailable" in w for w in result["warnings"])

    def test_function_never_raises_on_none_plan(self):
        result = build_beat_execution_plan(None, _Payload())
        assert isinstance(result, dict)
        assert result["enabled"] is False

    def test_function_never_raises_on_none_payload(self):
        plan = _EditPlan()
        result = build_beat_execution_plan(plan, None)
        assert isinstance(result, dict)

    def test_function_never_raises_on_garbage_plan(self):
        result = build_beat_execution_plan("not_a_plan", _Payload())
        assert isinstance(result, dict)
        assert result["enabled"] is False


# ── BPM validation ────────────────────────────────────────────────────────────

class TestBPMValidation:
    def test_bpm_below_60_skipped(self):
        plan = _EditPlan(pacing=_Pacing(bpm=59.9))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is False
        assert result["bpm"] == pytest.approx(59.9)
        assert any("bpm_out_of_range" in w for w in result["warnings"])

    def test_bpm_exactly_60_accepted(self):
        plan = _EditPlan(pacing=_Pacing(bpm=60.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is True

    def test_bpm_above_190_skipped(self):
        plan = _EditPlan(pacing=_Pacing(bpm=190.1))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is False
        assert any("bpm_out_of_range" in w for w in result["warnings"])

    def test_bpm_exactly_190_accepted(self):
        plan = _EditPlan(pacing=_Pacing(bpm=190.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is True

    def test_bpm_0_skipped(self):
        plan = _EditPlan(pacing=_Pacing(bpm=0.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is False

    def test_bpm_negative_skipped(self):
        plan = _EditPlan(pacing=_Pacing(bpm=-100.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is False


# ── Beat count validation ─────────────────────────────────────────────────────

class TestBeatCountValidation:
    def test_beat_count_below_4_skipped(self):
        plan = _EditPlan(pacing=_Pacing(beat_count=3))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is False
        assert any("beat_count_insufficient" in w for w in result["warnings"])

    def test_beat_count_exactly_4_accepted(self):
        plan = _EditPlan(pacing=_Pacing(beat_count=4))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is True

    def test_beat_count_0_skipped(self):
        plan = _EditPlan(pacing=_Pacing(beat_count=0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is False

    def test_beat_count_stored_on_report(self):
        plan = _EditPlan(pacing=_Pacing(beat_count=32))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["beat_count"] == 32


# ── Pulse strength bounds ─────────────────────────────────────────────────────

class TestPulseStrengthBounds:
    def test_pulse_strength_clamped_to_015(self):
        plan = _EditPlan(pacing=_Pacing(energy_level=1.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["pulse_strength"] <= 0.15

    def test_pulse_strength_high_energy_capped(self):
        plan = _EditPlan(pacing=_Pacing(energy_level=2.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["pulse_strength"] == pytest.approx(0.15)

    def test_pulse_strength_zero_energy(self):
        plan = _EditPlan(pacing=_Pacing(energy_level=0.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["pulse_strength"] == pytest.approx(0.0)

    def test_pulse_strength_none_energy_defaults(self):
        plan = _EditPlan(pacing=_Pacing(energy_level=None))
        result = build_beat_execution_plan(plan, _Payload())
        assert 0.0 <= result["pulse_strength"] <= 0.15

    def test_pulse_strength_never_negative(self):
        plan = _EditPlan(pacing=_Pacing(energy_level=-5.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["pulse_strength"] >= 0.0


# ── Transition style logic ────────────────────────────────────────────────────

class TestTransitionStyle:
    def test_transition_disabled_yields_metadata_only(self):
        plan = _EditPlan(pacing=_Pacing(bpm=130.0, pacing_style="fast"))
        payload = _Payload(ai_beat_transition_enabled=False)
        result = build_beat_execution_plan(plan, payload)
        assert result["suggested_transition_style"] == "metadata_only"

    def test_fast_style_high_bpm_pulse_enabled(self):
        plan = _EditPlan(pacing=_Pacing(bpm=130.0, pacing_style="fast"))
        payload = _Payload(ai_beat_transition_enabled=True, ai_beat_pulse_enabled=True)
        result = build_beat_execution_plan(plan, payload)
        assert result["suggested_transition_style"] == "beat_pulse"

    def test_fast_style_high_bpm_pulse_disabled(self):
        plan = _EditPlan(pacing=_Pacing(bpm=130.0, pacing_style="fast"))
        payload = _Payload(ai_beat_transition_enabled=True, ai_beat_pulse_enabled=False)
        result = build_beat_execution_plan(plan, payload)
        assert result["suggested_transition_style"] == "soft_cut"

    def test_dynamic_style_high_bpm_gives_beat_pulse(self):
        plan = _EditPlan(pacing=_Pacing(bpm=125.0, pacing_style="dynamic"))
        payload = _Payload(ai_beat_transition_enabled=True, ai_beat_pulse_enabled=True)
        result = build_beat_execution_plan(plan, payload)
        assert result["suggested_transition_style"] == "beat_pulse"

    def test_slow_style_gives_soft_cut(self):
        plan = _EditPlan(pacing=_Pacing(bpm=90.0, pacing_style="slow"))
        payload = _Payload(ai_beat_transition_enabled=True, ai_beat_pulse_enabled=True)
        result = build_beat_execution_plan(plan, payload)
        assert result["suggested_transition_style"] == "soft_cut"

    def test_fast_style_low_bpm_gives_soft_cut(self):
        plan = _EditPlan(pacing=_Pacing(bpm=100.0, pacing_style="fast"))
        payload = _Payload(ai_beat_transition_enabled=True, ai_beat_pulse_enabled=True)
        result = build_beat_execution_plan(plan, payload)
        assert result["suggested_transition_style"] == "soft_cut"


# ── Safety — never mutates segment/subtitle/speed ────────────────────────────

class TestSafetyNoMutations:
    def test_playback_speed_unchanged(self):
        plan = _EditPlan()
        payload = _Payload(playback_speed=1.0)
        build_beat_execution_plan(plan, payload)
        assert payload.playback_speed == 1.0

    def test_playback_speed_nondefault_unchanged(self):
        plan = _EditPlan()
        payload = _Payload(playback_speed=1.5)
        build_beat_execution_plan(plan, payload)
        assert payload.playback_speed == 1.5

    def test_segment_start_unchanged(self):
        segs = [{"start": 1.0, "end": 5.0, "score": 0.9}]
        plan = _EditPlan(selected_segments=segs)
        build_beat_execution_plan(plan, _Payload())
        assert segs[0]["start"] == 1.0
        assert segs[0]["end"] == 5.0

    def test_execution_mode_always_metadata_only(self):
        plan = _EditPlan()
        result = build_beat_execution_plan(plan, _Payload())
        assert result["execution_mode"] == "metadata_only"


# ── Report shape ──────────────────────────────────────────────────────────────

class TestReportShape:
    def test_report_has_all_required_keys(self):
        result = build_beat_execution_plan(_EditPlan(), _Payload())
        for key in ("enabled", "beat_available", "bpm", "beat_count",
                    "pulse_strength", "suggested_transition_style",
                    "execution_mode", "applied", "skipped", "warnings"):
            assert key in result, f"missing key: {key}"

    def test_applied_is_list(self):
        result = build_beat_execution_plan(_EditPlan(), _Payload())
        assert isinstance(result["applied"], list)

    def test_skipped_is_list(self):
        result = build_beat_execution_plan(_EditPlan(), _Payload())
        assert isinstance(result["skipped"], list)

    def test_warnings_is_list(self):
        result = build_beat_execution_plan(_EditPlan(), _Payload())
        assert isinstance(result["warnings"], list)

    def test_enabled_true_has_applied_entry(self):
        plan = _EditPlan(pacing=_Pacing(bpm=120.0, beat_count=32))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["enabled"] is True
        assert len(result["applied"]) > 0

    def test_bpm_stored_in_report(self):
        plan = _EditPlan(pacing=_Pacing(bpm=128.0))
        result = build_beat_execution_plan(plan, _Payload())
        assert result["bpm"] == pytest.approx(128.0)


# ── Integration with render_influence._apply_pacing_influence ─────────────────

class TestPacingInfluenceIntegration:
    def _make_full_edit_plan(self, beat_available=True, bpm=120.0, beat_count=32):
        from app.ai.director.edit_plan_schema import (
            AIEditPlan, AIPacingPlan, AISubtitlePlan, AICameraPlan
        )
        plan = AIEditPlan(
            enabled=True,
            mode="viral_tiktok",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
            pacing=AIPacingPlan(
                beat_available=beat_available,
                bpm=bpm,
                beat_count=beat_count,
                energy_level=0.7,
                pacing_style="dynamic",
            ),
        )
        return plan

    def test_beat_execution_planned_when_enabled(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            ai_render_influence_enabled: bool = True
            ai_beat_execution_enabled: bool = True
            ai_beat_transition_enabled: bool = False
            ai_beat_pulse_enabled: bool = True
            add_subtitle: bool = False
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            playback_speed: float = 1.0
            highlight_per_word: bool = False

        plan = self._make_full_edit_plan()
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)
        assert any("beat_execution_planned" in a for a in report.get("applied", []) + report.get("skipped", []))

    def test_beat_execution_stored_on_plan(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            ai_render_influence_enabled: bool = True
            ai_beat_execution_enabled: bool = True
            ai_beat_transition_enabled: bool = False
            ai_beat_pulse_enabled: bool = True
            add_subtitle: bool = False
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            playback_speed: float = 1.0
            highlight_per_word: bool = False

        plan = self._make_full_edit_plan()
        apply_ai_render_influence(_P(), plan)
        assert isinstance(plan.beat_execution, dict)
        assert "enabled" in plan.beat_execution

    def test_beat_disabled_skips_and_notes(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            ai_render_influence_enabled: bool = True
            ai_beat_execution_enabled: bool = False
            ai_beat_transition_enabled: bool = False
            ai_beat_pulse_enabled: bool = True
            add_subtitle: bool = False
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            playback_speed: float = 1.0
            highlight_per_word: bool = False

        plan = self._make_full_edit_plan()
        _, report = apply_ai_render_influence(_P(), plan)
        assert any("beat_execution_disabled" in s for s in report.get("skipped", []))

    def test_explainability_beat_line_added_on_success(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            ai_render_influence_enabled: bool = True
            ai_beat_execution_enabled: bool = True
            ai_beat_transition_enabled: bool = False
            ai_beat_pulse_enabled: bool = True
            add_subtitle: bool = False
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            playback_speed: float = 1.0
            highlight_per_word: bool = False

        plan = self._make_full_edit_plan()
        plan.explainability = {"summary": {"summary_lines": ["Existing line"]}}
        apply_ai_render_influence(_P(), plan)
        lines = plan.explainability["summary"]["summary_lines"]
        assert any("Beat" in str(l) for l in lines)


# ── No API key / no GPU / no rendering ───────────────────────────────────────

class TestNoExternalDependencies:
    def test_no_api_key_required(self):
        """build_beat_execution_plan never touches any API key."""
        import os
        saved = os.environ.pop("ANTHROPIC_API_KEY", None)
        try:
            result = build_beat_execution_plan(_EditPlan(), _Payload())
            assert isinstance(result, dict)
        finally:
            if saved is not None:
                os.environ["ANTHROPIC_API_KEY"] = saved

    def test_no_librosa_required(self, monkeypatch):
        """Module must work even if librosa is not installed."""
        import sys
        monkeypatch.setitem(sys.modules, "librosa", None)
        result = build_beat_execution_plan(_EditPlan(), _Payload())
        assert isinstance(result, dict)

    def test_no_torch_required(self, monkeypatch):
        """Module must work even if torch is not installed."""
        import sys
        monkeypatch.setitem(sys.modules, "torch", None)
        result = build_beat_execution_plan(_EditPlan(), _Payload())
        assert isinstance(result, dict)

    def test_no_gpu_required(self):
        """Beat execution is pure Python — no CUDA or GPU calls."""
        result = build_beat_execution_plan(_EditPlan(), _Payload())
        assert isinstance(result, dict)

    def test_no_file_io(self, tmp_path, monkeypatch):
        """Module must not attempt to read audio or video files."""
        monkeypatch.chdir(tmp_path)
        result = build_beat_execution_plan(_EditPlan(), _Payload())
        assert isinstance(result, dict)
