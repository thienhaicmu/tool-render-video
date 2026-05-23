"""
test_render_pipeline_ai_visual_intensity.py — Phase 5.7 render pipeline integration tests.

Tests:
- AI disabled → visual config skipped, behavior unchanged
- no knowledge/hints → behavior unchanged
- valid "high" hint → config applied=True (Phase 5.7: safe injection point found)
- valid "low" hint → config applied=True (Phase 5.7: safe injection point found)
- invalid hint → rejected, behavior unchanged
- no FFmpeg command string generation by AI
- trace logs ai.visual_intensity_applied when processed
- trace logs rejection when not applied (user override, invalid hint)
- render_overrides contains only safe known keys (visual_intensity_hint in Phase 5.7)
- render_overrides must not contain effect_preset names or FFmpeg filter strings
- exception in visual mapping → fallback, render behavior unchanged
- render_pipeline does NOT mutate payload.effect_preset
- overlay compositor unchanged (does not receive visual_intensity_hint)

Phase 5.7 note:
  Safe injection point found. Valid hints now result in applied=True.
  render_overrides={"visual_intensity_hint": <value>} when applied=True.
  render_pipeline extracts this value and passes to renderer as visual_intensity_hint.
  Renderer OWNS the mapping from hint to preset — AI never picks a preset name.
"""
from __future__ import annotations

import json
import tempfile
import types
import pytest
from pathlib import Path
from unittest import mock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_exec_hints(intensity=None):
    """Build an execution hints dict for testing."""
    h = {}
    if intensity is not None:
        h["visual_intensity"] = intensity
    h["source_knowledge_ids"] = ["kb_vis_test_001"]
    return h


def _make_payload(effect_preset="slay_soft_01"):
    """Build a minimal payload-like namespace."""
    p = types.SimpleNamespace()
    p.effect_preset = effect_preset
    return p


# ---------------------------------------------------------------------------
# build_ai_visual_intensity_config — used by pipeline
# ---------------------------------------------------------------------------

class TestAIVisualIntensityConfigInPipeline:
    """Test that build_ai_visual_intensity_config behaves correctly for pipeline use cases."""

    def test_ai_disabled_produces_disabled_config(self):
        """When AI is disabled, no execution hints → config.enabled=False."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config(None)
        assert cfg.enabled is False
        assert cfg.applied is False

    def test_no_hints_produces_not_applied(self):
        """Empty hints dict → applied=False, behavior unchanged."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config({})
        assert cfg.applied is False

    def test_no_visual_intensity_hint_rejected(self):
        """Hints present but no visual_intensity → rejected."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config({
            "cut_interval_min": 2.0,
            "cut_interval_max": 5.0,
            "source_knowledge_ids": ["kb_001"],
        })
        assert cfg.applied is False
        assert cfg.rejected_reason == "no_visual_intensity_hint"

    def test_valid_high_hint_applied_phase57(self):
        """Valid 'high' hint → applied=True (Phase 5.7: safe injection point found)."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config(_make_exec_hints("high"))
        assert cfg.enabled is True
        assert cfg.visual_intensity == "high"
        # Phase 5.7: safe injection point found — applied=True
        assert cfg.applied is True
        assert cfg.rejected_reason is None
        assert cfg.render_overrides.get("visual_intensity_hint") == "high"

    def test_valid_low_hint_applied_phase57(self):
        """Valid 'low' hint → applied=True (Phase 5.7: safe injection point found)."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config(_make_exec_hints("low"))
        assert cfg.enabled is True
        assert cfg.visual_intensity == "low"
        assert cfg.applied is True
        assert cfg.rejected_reason is None
        assert cfg.render_overrides.get("visual_intensity_hint") == "low"

    def test_valid_medium_hint_applied_phase57(self):
        """Valid 'medium' hint → applied=True (Phase 5.7: safe injection point found)."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config(_make_exec_hints("medium"))
        assert cfg.applied is True
        assert cfg.rejected_reason is None
        assert cfg.render_overrides.get("visual_intensity_hint") == "medium"

    def test_invalid_hint_rejected_behavior_unchanged(self):
        """Invalid hint → rejected=invalid_visual_intensity, applied=False."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config(_make_exec_hints("ultra_intense"))
        assert cfg.applied is False
        assert cfg.rejected_reason == "invalid_visual_intensity"

    def test_user_effect_preset_preserved(self):
        """AI hint config does not change payload.effect_preset."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        payload = _make_payload(effect_preset="slay_pop_01")
        cfg = build_ai_visual_intensity_config(_make_exec_hints("high"), payload=payload)
        # User override → rejected, effect_preset unchanged
        assert cfg.applied is False
        assert cfg.rejected_reason == "user_visual_override"
        # payload.effect_preset must not have been mutated
        assert payload.effect_preset == "slay_pop_01"


# ---------------------------------------------------------------------------
# No FFmpeg command string generation by AI
# ---------------------------------------------------------------------------

class TestNoFFmpegChanges:
    def test_visual_hints_does_not_import_ffmpeg(self):
        """visual_hints.py must not import ffmpeg or subprocess."""
        import inspect
        import app.ai.visual_hints as m
        src = inspect.getsource(m)
        import_lines = [
            line.strip()
            for line in src.splitlines()
            if line.strip().startswith(("import ", "from "))
        ]
        for line in import_lines:
            assert "ffmpeg" not in line.lower(), f"Unexpected ffmpeg import: {line}"
            assert "subprocess" not in line.lower(), f"Unexpected subprocess import: {line}"

    def test_render_overrides_contains_no_ffmpeg_strings(self):
        """render_overrides must not contain raw FFmpeg filter strings."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        for intensity in ("low", "medium", "high"):
            cfg = build_ai_visual_intensity_config(_make_exec_hints(intensity))
            for key, val in cfg.render_overrides.items():
                val_str = str(val) if val is not None else ""
                # FFmpeg filter patterns that must not appear
                assert "eq=" not in val_str, f"FFmpeg eq filter found in render_overrides[{key}]"
                assert "unsharp=" not in val_str, f"FFmpeg unsharp filter found in render_overrides[{key}]"
                assert "hqdn3d=" not in val_str, f"FFmpeg hqdn3d filter found in render_overrides[{key}]"
                assert "scale=" not in val_str, f"FFmpeg scale filter found in render_overrides[{key}]"

    def test_render_overrides_contains_hint_in_phase57(self):
        """Phase 5.7: render_overrides={"visual_intensity_hint": <value>} when applied=True."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        for intensity in ("low", "medium", "high"):
            cfg = build_ai_visual_intensity_config(_make_exec_hints(intensity))
            assert cfg.applied is True, f"Expected applied=True for intensity={intensity!r}"
            assert "visual_intensity_hint" in cfg.render_overrides, (
                f"render_overrides must contain 'visual_intensity_hint' for intensity={intensity!r}"
            )
            assert cfg.render_overrides["visual_intensity_hint"] == intensity

    def test_render_overrides_does_not_contain_effect_preset_name(self):
        """render_overrides must not contain effect_preset names (AI does not pick presets)."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        _preset_names = {"slay_soft_01", "slay_pop_01", "story_clean_01",
                         "social_bright", "cinematic_soft", "high_contrast"}
        for intensity in ("low", "medium", "high"):
            cfg = build_ai_visual_intensity_config(_make_exec_hints(intensity))
            for key, val in cfg.render_overrides.items():
                assert key != "effect_preset", "render_overrides must not contain 'effect_preset'"
                assert val not in _preset_names, (
                    f"render_overrides value must not be a preset name: {val!r}"
                )


# ---------------------------------------------------------------------------
# Trace logger — visual intensity applied/rejected
# ---------------------------------------------------------------------------

class TestTraceLoggerVisualIntensity:
    def test_trace_logs_visual_intensity_applied_event(self, tmp_path):
        """Tracer writes ai.visual_intensity_applied event with applied=True in Phase 5.7."""
        from app.ai.tracing import AITraceLogger
        from app.ai.visual_hints import build_ai_visual_intensity_config

        tracer = AITraceLogger("job_test_vis_123", log_dir=tmp_path)
        cfg = build_ai_visual_intensity_config(_make_exec_hints("high"))
        assert cfg.applied is True  # Phase 5.7: applied=True when valid hint

        tracer.log_visual_intensity_applied(
            {**cfg.to_dict(), "reason": "applied" if cfg.applied else str(cfg.rejected_reason)}
        )

        log_file = tmp_path / "job_test_vis_123_ai_trace.jsonl"
        assert log_file.exists()
        records = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
        assert any(r["event"] == "ai.visual_intensity_applied" for r in records)
        applied_rec = next(r for r in records if r["event"] == "ai.visual_intensity_applied")
        assert applied_rec["applied"] is True  # Phase 5.7: applied=True now possible

    def test_trace_logs_rejection_for_user_override(self, tmp_path):
        """Tracer writes ai.decision_rejected for user_visual_override."""
        from app.ai.tracing import AITraceLogger
        from app.ai.visual_hints import build_ai_visual_intensity_config

        tracer = AITraceLogger("job_test_vis_456", log_dir=tmp_path)
        payload = _make_payload(effect_preset="slay_pop_01")
        cfg = build_ai_visual_intensity_config(_make_exec_hints("high"), payload=payload)
        assert cfg.rejected_reason == "user_visual_override"

        tracer.log_decision_rejected(
            cfg.rejected_reason,
            detail={"hint": "visual_intensity", "value": cfg.visual_intensity, "phase": "5.7"},
        )

        log_file = tmp_path / "job_test_vis_456_ai_trace.jsonl"
        records = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
        assert any(r["event"] == "ai.decision_rejected" for r in records)
        rejection_record = next(r for r in records if r["event"] == "ai.decision_rejected")
        assert rejection_record["reason"] == "user_visual_override"

    def test_trace_logs_rejection_when_no_hint(self, tmp_path):
        """Tracer writes decision_rejected when config.applied=False (no hint)."""
        from app.ai.tracing import AITraceLogger
        from app.ai.visual_hints import build_ai_visual_intensity_config

        tracer = AITraceLogger("job_test_vis_789", log_dir=tmp_path)
        cfg = build_ai_visual_intensity_config(None)  # no hints → not applied
        assert cfg.applied is False

        tracer.log_decision_rejected(
            str(cfg.rejected_reason or "no_visual_intensity_hint"),
            detail={"hint": "visual_intensity", "phase": "5.6"},
        )

        log_file = tmp_path / "job_test_vis_789_ai_trace.jsonl"
        records = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
        assert any(r["event"] == "ai.decision_rejected" for r in records)

    def test_trace_visual_intensity_applied_has_required_fields(self, tmp_path):
        """ai.visual_intensity_applied record has all required payload fields."""
        from app.ai.tracing import AITraceLogger

        tracer = AITraceLogger("job_test_vis_req", log_dir=tmp_path)
        tracer.log_visual_intensity_applied({
            "applied": False,
            "visual_intensity": "medium",
            "source_knowledge_ids": ["k1", "k2"],
            "render_overrides": {},
            "reason": "no_safe_visual_injection_point",
        })

        log_file = tmp_path / "job_test_vis_req_ai_trace.jsonl"
        record = json.loads(
            log_file.read_text(encoding="utf-8").strip().splitlines()[0]
        )
        for field in ("applied", "visual_intensity", "source_knowledge_ids", "render_overrides", "reason"):
            assert field in record, f"Missing field: {field}"

    def test_ai_disabled_logs_ai_disabled_rejection(self, tmp_path):
        """When AI is disabled, decision_rejected with 'ai_disabled' is logged."""
        from app.ai.tracing import AITraceLogger

        tracer = AITraceLogger("job_ai_disabled", log_dir=tmp_path)
        tracer.log_decision_rejected(
            "ai_disabled",
            detail={"hint": "visual_intensity", "phase": "5.6"},
        )

        log_file = tmp_path / "job_ai_disabled_ai_trace.jsonl"
        records = [
            json.loads(line)
            for line in log_file.read_text(encoding="utf-8").strip().splitlines()
            if line.strip()
        ]
        assert any(r["event"] == "ai.decision_rejected" for r in records)
        rejection = next(r for r in records if r["event"] == "ai.decision_rejected")
        assert rejection["reason"] == "ai_disabled"


# ---------------------------------------------------------------------------
# render_overrides safe keys check
# ---------------------------------------------------------------------------

class TestRenderOverridesSafeKeys:
    _UNSAFE_KEYS = frozenset({
        "ffmpeg_filter", "vf_chain", "vf_parts", "filter_complex",
        "filter_graph", "ass_filter", "drawtext", "eq_filter",
        "unsharp_filter", "hqdn3d_filter",
        "effect_preset",  # AI must not pick effect_preset directly
    })

    def test_render_overrides_contains_no_unsafe_keys(self):
        """render_overrides must not contain raw FFmpeg command or filter keys."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        for intensity in ("low", "medium", "high"):
            cfg = build_ai_visual_intensity_config(_make_exec_hints(intensity))
            for key in cfg.render_overrides:
                assert key not in self._UNSAFE_KEYS, (
                    f"Unsafe key '{key}' found in render_overrides for intensity={intensity}"
                )

    def test_render_overrides_is_always_dict(self):
        """render_overrides is always a dict regardless of input."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        for hints_input in [None, {}, _make_exec_hints("low"), _make_exec_hints("bad_value")]:
            cfg = build_ai_visual_intensity_config(hints_input)
            assert isinstance(cfg.render_overrides, dict)

    def test_render_overrides_safe_key_is_visual_intensity_hint(self):
        """Phase 5.7: render_overrides only safe key is 'visual_intensity_hint'."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        for intensity in ("low", "medium", "high"):
            cfg = build_ai_visual_intensity_config(_make_exec_hints(intensity))
            assert cfg.applied is True
            for key in cfg.render_overrides:
                assert key == "visual_intensity_hint", (
                    f"Unexpected key '{key}' in render_overrides for intensity={intensity}"
                )


# ---------------------------------------------------------------------------
# Exception safety — visual mapping error
# ---------------------------------------------------------------------------

class TestExceptionSafetyPipeline:
    def test_config_never_raises_in_pipeline_context(self):
        """Simulate pipeline context: any garbage input must not raise."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        for bad_input in [None, {}, [], 42, "string", {"random": True}]:
            cfg = build_ai_visual_intensity_config(bad_input)
            assert isinstance(cfg.applied, bool)
            assert isinstance(cfg.enabled, bool)

    def test_config_to_dict_always_valid(self):
        """to_dict() always returns a dict with required keys."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        required_keys = {
            "enabled", "applied", "visual_intensity",
            "source_knowledge_ids", "rejected_reason",
            "validation_fixups", "render_overrides",
        }
        for hints in [
            None, {}, {"visual_intensity": "high"},
            {"visual_intensity": "bad"}, {"visual_intensity": "low"},
        ]:
            cfg = build_ai_visual_intensity_config(hints)
            d = cfg.to_dict()
            assert isinstance(d, dict)
            for key in required_keys:
                assert key in d, f"Missing key '{key}' for hints={hints!r}"

    def test_build_with_exception_in_to_dict_no_raise(self):
        """Even if hints.to_dict() raises, no exception propagates."""
        class BrokenHints:
            def to_dict(self):
                raise RuntimeError("broken")

        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config(BrokenHints())
        assert isinstance(cfg.applied, bool)

    def test_exception_in_hints_normalisation_no_raise(self):
        """Malformed hints that trigger exceptions during normalisation do not raise."""
        from app.ai.visual_hints import build_ai_visual_intensity_config

        class WeirdHints:
            def to_dict(self):
                return {"visual_intensity": object(), "source_knowledge_ids": None}

        cfg = build_ai_visual_intensity_config(WeirdHints())
        assert isinstance(cfg, __import__("app.ai.visual_hints", fromlist=["AIVisualIntensityConfig"]).AIVisualIntensityConfig)


# ---------------------------------------------------------------------------
# Behavior: AI enabled vs disabled
# ---------------------------------------------------------------------------

class TestAIEnabledDisabledBehavior:
    def test_ai_disabled_no_hints_no_config(self):
        """When execution_hints is None (AI disabled), config is disabled."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config(None)
        assert cfg.enabled is False
        assert cfg.applied is False
        assert cfg.render_overrides == {}

    def test_ai_enabled_no_visual_hint_not_applied(self):
        """AI enabled but no visual_intensity in hints → applied=False."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config({
            "subtitle_emphasis_style": "strong",
            "source_knowledge_ids": ["kb1"],
        })
        assert cfg.applied is False
        assert cfg.rejected_reason == "no_visual_intensity_hint"

    def test_ai_enabled_valid_hint_applied_phase57(self):
        """AI enabled + valid hint → applied=True in Phase 5.7."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        cfg = build_ai_visual_intensity_config({"visual_intensity": "high", "source_knowledge_ids": []})
        assert cfg.enabled is True
        assert cfg.visual_intensity == "high"
        assert cfg.applied is True
        assert cfg.rejected_reason is None
        assert cfg.render_overrides.get("visual_intensity_hint") == "high"

    def test_render_behavior_change_phase57(self):
        """Phase 5.7: render_overrides={"visual_intensity_hint": <val>} — hint is passed to renderer."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        for intensity in ("low", "medium", "high"):
            cfg = build_ai_visual_intensity_config({"visual_intensity": intensity, "source_knowledge_ids": []})
            # Phase 5.7: applied=True, render_overrides contains the hint
            assert cfg.applied is True, f"Expected applied=True for intensity={intensity!r}"
            assert cfg.render_overrides.get("visual_intensity_hint") == intensity, (
                f"Expected visual_intensity_hint={intensity!r}, "
                f"got render_overrides={cfg.render_overrides}"
            )

    def test_payload_effect_preset_not_mutated(self):
        """payload.effect_preset must never be mutated by AI hint processing."""
        from app.ai.visual_hints import build_ai_visual_intensity_config
        payload = _make_payload(effect_preset="slay_soft_01")
        cfg = build_ai_visual_intensity_config(
            {"visual_intensity": "high", "source_knowledge_ids": []},
            payload=payload,
        )
        assert payload.effect_preset == "slay_soft_01", (
            "payload.effect_preset must not be mutated"
        )
        assert cfg.applied is True
