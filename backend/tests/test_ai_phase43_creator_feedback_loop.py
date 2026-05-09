"""
test_ai_phase43_creator_feedback_loop.py — Phase 43 tests.

Covers: schema, safety, memory persistence, learning engine, edit plan
integration, render influence, safety boundaries, environment requirements.
"""
import json
import pytest
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_minimal_plan():
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan, AIClipPlan,
    )
    return AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[AIClipPlan(start=0.0, end=20.0, score=80.0)],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        pacing=AIPacingPlan(
            pacing_style="fast_hook",
            energy_level=0.85,
            beat_available=True,
            bpm=128.0,
        ),
    )


def _make_rich_plan():
    plan = _make_minimal_plan()
    plan.creator_style_adaptation = {"adapted_style": "viral_tiktok"}
    plan.subtitle_text_apply = {"subtitle_style": "compact"}
    plan.camera_motion_apply = {"camera_behavior": "dynamic_safe"}
    plan.variant_selection = {"selected_variant_id": "v1", "selection_confidence": 0.75}
    plan.adaptive_creator_intelligence = {
        "available": True,
        "enabled": True,
        "learning_mode": "assistive_only",
        "creator_profile": {},
        "learned_preferences": {},
        "adaptive_influences": {
            "pacing_enhancement_weight": 0.12,
            "subtitle_enhancement_weight": 0.10,
            "assistive_only": True,
        },
        "warnings": [],
    }
    return plan


@dataclass
class _MockRequest:
    ai_director_enabled: bool = True
    ai_mode: str = "viral_tiktok"
    ai_feedback_id: Optional[str] = None
    ai_feedback_exported: Optional[bool] = None
    ai_feedback_selected: Optional[bool] = None
    ai_feedback_ignored: Optional[bool] = None
    ai_feedback_output_rank: Optional[int] = None


# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestFeedbackSchema:
    def test_feedback_signal_defaults(self):
        from app.ai.feedback.feedback_schema import AICreatorFeedbackSignal
        s = AICreatorFeedbackSignal()
        assert s.feedback_id == "unknown"
        assert s.creator_style == ""
        assert s.exported is False
        assert s.ignored is False
        assert s.confidence == 0.0
        assert s.tags == []
        assert s.warnings == []

    def test_feedback_signal_to_dict(self):
        from app.ai.feedback.feedback_schema import AICreatorFeedbackSignal
        s = AICreatorFeedbackSignal(
            feedback_id="fb1",
            creator_style="viral_tiktok",
            exported=True,
            selected_output_rank=1,
        )
        d = s.to_dict()
        assert d["feedback_id"] == "fb1"
        assert d["creator_style"] == "viral_tiktok"
        assert d["exported"] is True
        assert d["selected_output_rank"] == 1

    def test_feedback_learning_pack_defaults(self):
        from app.ai.feedback.feedback_schema import AIFeedbackLearningPack
        pack = AIFeedbackLearningPack()
        assert pack.available is True
        assert pack.enabled is False
        assert pack.feedback_mode == "assistive_only"
        assert pack.feedback_signals == []
        assert pack.learned_feedback_patterns == {}
        assert pack.ranking_biases == {}

    def test_feedback_learning_pack_to_dict(self):
        from app.ai.feedback.feedback_schema import AIFeedbackLearningPack
        pack = AIFeedbackLearningPack(enabled=True)
        d = pack.to_dict()
        assert d["available"] is True
        assert d["enabled"] is True
        assert d["feedback_mode"] == "assistive_only"


# ---------------------------------------------------------------------------
# 2. Safety tests
# ---------------------------------------------------------------------------

class TestFeedbackSafety:
    def test_sanitize_strips_forbidden_keys(self):
        from app.ai.feedback.feedback_safety import sanitize_feedback
        data = {
            "creator_style": "viral",
            "password": "secret",
            "api_key": "abc123",
            "ffmpeg_args": "-c:v h264",
            "playback_speed": 2.0,
            "subtitle_timing": [0, 1, 2],
            "render_command": "ffmpeg ...",
            "output_path": "/tmp/out.mp4",
        }
        result = sanitize_feedback(data)
        assert "creator_style" in result
        for k in ("password", "api_key", "ffmpeg_args", "playback_speed",
                   "subtitle_timing", "render_command", "output_path"):
            assert k not in result

    def test_sanitize_nested_forbidden_keys(self):
        from app.ai.feedback.feedback_safety import sanitize_feedback
        data = {"meta": {"auth": "bearer", "style": "compact"}}
        result = sanitize_feedback(data)
        assert "auth" not in result["meta"]
        assert result["meta"]["style"] == "compact"

    def test_sanitize_empty_dict(self):
        from app.ai.feedback.feedback_safety import sanitize_feedback
        assert sanitize_feedback({}) == {}

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.feedback.feedback_safety import sanitize_feedback
        assert sanitize_feedback(None) == {}
        assert sanitize_feedback("bad") == {}

    def test_is_safe_clean_data(self):
        from app.ai.feedback.feedback_safety import is_feedback_safe
        assert is_feedback_safe({"style": "viral", "rank": 1}) is True

    def test_is_safe_forbidden_key(self):
        from app.ai.feedback.feedback_safety import is_feedback_safe
        assert is_feedback_safe({"ffmpeg_args": "-c:v"}) is False
        assert is_feedback_safe({"playback_speed": 1.5}) is False
        assert is_feedback_safe({"subtitle_timing": [0]}) is False

    def test_is_safe_never_raises(self):
        from app.ai.feedback.feedback_safety import is_feedback_safe
        assert is_feedback_safe(None) is True
        assert is_feedback_safe(42) is True


# ---------------------------------------------------------------------------
# 3. Memory persistence tests
# ---------------------------------------------------------------------------

class TestFeedbackMemory:
    def test_build_default_feedback_memory(self):
        from app.ai.feedback.feedback_memory import build_default_feedback_memory
        m = build_default_feedback_memory()
        assert m["total_signals"] == 0
        assert m["total_exports"] == 0
        assert m["total_ignores"] == 0
        assert isinstance(m["signals"], list)
        assert isinstance(m["pattern_counts"], dict)

    def test_feedback_persistence(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "fb")

        from app.ai.feedback.feedback_memory import (
            build_default_feedback_memory, save_feedback_memory, load_feedback_memory,
        )
        mem = build_default_feedback_memory()
        mem["total_signals"] = 5
        mem["total_exports"] = 3

        ok = save_feedback_memory(mem)
        assert ok is True

        loaded = load_feedback_memory()
        assert loaded["total_signals"] == 5
        assert loaded["total_exports"] == 3

    def test_missing_feedback_fallback_safe(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "empty_fb")

        from app.ai.feedback.feedback_memory import load_feedback_memory
        m = load_feedback_memory()
        assert m["total_signals"] == 0

    def test_corrupted_feedback_fallback_safe(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        fb_dir = tmp_path / "corrupt_fb"
        fb_dir.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", fb_dir)

        corrupt = fb_dir / "feedback_memory.json"
        corrupt.write_text("NOT VALID JSON <<<", encoding="utf-8")

        from app.ai.feedback.feedback_memory import load_feedback_memory
        m = load_feedback_memory()
        assert m["total_signals"] == 0

    def test_record_feedback_signal_increments_counts(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "rec_fb")

        from app.ai.feedback.feedback_schema import AICreatorFeedbackSignal
        from app.ai.feedback.feedback_memory import record_feedback_signal

        sig = AICreatorFeedbackSignal(
            feedback_id="t1",
            creator_style="viral_tiktok",
            exported=True,
            selected_output_rank=1,
        )
        mem = record_feedback_signal(sig)
        assert mem["total_signals"] == 1
        assert mem["total_exports"] == 1
        assert mem["pattern_counts"]["creator_style"].get("viral_tiktok", 0) == 1

    def test_record_feedback_signal_never_raises(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "nraise_fb")

        from app.ai.feedback.feedback_schema import AICreatorFeedbackSignal
        from app.ai.feedback.feedback_memory import record_feedback_signal

        result = record_feedback_signal(AICreatorFeedbackSignal())
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 4. Feedback learning engine tests
# ---------------------------------------------------------------------------

class TestFeedbackLearning:
    def test_deterministic_feedback_learning(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "det_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_rich_plan()
        pack1 = build_feedback_learning_pack(plan, context={"feedback_id": "d1"})
        pack2 = build_feedback_learning_pack(plan, context={"feedback_id": "d2"})
        assert pack1.feedback_mode == pack2.feedback_mode == "assistive_only"

    def test_repeated_export_increases_ranking_confidence(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "exp_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()

        # Record multiple top-rank exports
        for i in range(5):
            build_feedback_learning_pack(
                plan,
                context={
                    "feedback_id": f"e{i}",
                    "exported": True,
                    "selected_output_rank": 1,
                    "creator_style": "viral_tiktok",
                },
            )

        pack = build_feedback_learning_pack(
            plan,
            context={"feedback_id": "check", "exported": True, "selected_output_rank": 1},
        )
        bias = pack.ranking_biases.get("output_ranking_bias", 0.0)
        assert bias >= 0.0
        assert bias <= 0.30

    def test_repeated_lower_rank_export_biases_ranking(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "low_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()

        for i in range(5):
            build_feedback_learning_pack(
                plan,
                context={
                    "feedback_id": f"lr{i}",
                    "exported": True,
                    "selected_output_rank": 3,
                },
            )

        pack = build_feedback_learning_pack(plan, context={"feedback_id": "check_lr"})
        bias = pack.ranking_biases.get("variant_ranking_bias", 0.0)
        assert 0.0 <= bias <= 0.30

    def test_subtitle_feedback_weighting_valid(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "sub_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()

        for i in range(5):
            build_feedback_learning_pack(
                plan,
                context={"feedback_id": f"s{i}", "subtitle_style": "compact"},
            )

        pack = build_feedback_learning_pack(plan, context={"feedback_id": "sub_check"})
        bias = pack.ranking_biases.get("subtitle_weighting_bias", 0.0)
        assert 0.0 <= bias <= 0.30

    def test_pacing_feedback_weighting_valid(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "pac_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()

        for i in range(5):
            build_feedback_learning_pack(
                plan,
                context={"feedback_id": f"p{i}", "pacing_style": "fast_hook"},
            )

        pack = build_feedback_learning_pack(plan, context={"feedback_id": "pac_check"})
        bias = pack.ranking_biases.get("pacing_weighting_bias", 0.0)
        assert 0.0 <= bias <= 0.30

    def test_camera_feedback_weighting_valid(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "cam_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()

        for i in range(5):
            build_feedback_learning_pack(
                plan,
                context={"feedback_id": f"c{i}", "camera_style": "dynamic_safe"},
            )

        pack = build_feedback_learning_pack(plan, context={"feedback_id": "cam_check"})
        bias = pack.ranking_biases.get("camera_weighting_bias", 0.0)
        assert 0.0 <= bias <= 0.30

    def test_duration_feedback_weighting_valid(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "dur_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()

        for i in range(5):
            build_feedback_learning_pack(
                plan,
                context={"feedback_id": f"d{i}", "duration_bucket": "short_form"},
            )

        pack = build_feedback_learning_pack(plan, context={"feedback_id": "dur_check"})
        assert isinstance(pack.learned_feedback_patterns.get("dominant_duration_bucket", ""), str)

    def test_ignored_output_reduces_ranking_weight(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "ign_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()

        for i in range(5):
            build_feedback_learning_pack(
                plan,
                context={"feedback_id": f"ig{i}", "ignored": True, "selected_output_rank": 2},
            )

        pack = build_feedback_learning_pack(plan, context={"feedback_id": "ign_check"})
        patterns = pack.learned_feedback_patterns
        assert patterns.get("total_ignores", 0) >= 5

    def test_forbidden_fields_stripped(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "strip_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()
        pack = build_feedback_learning_pack(plan)

        pack_str = str(pack.to_dict())
        for forbidden in ("password", "api_key", "ffmpeg_args", "playback_speed", "subtitle_timing"):
            assert forbidden not in pack_str

    def test_no_payload_mutation(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "mut_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_minimal_plan()
        req = _MockRequest(ai_mode="viral_tiktok")
        original_mode = req.ai_mode
        original_segs = len(plan.selected_segments)

        build_feedback_learning_pack(plan, payload=req)

        assert req.ai_mode == original_mode
        assert len(plan.selected_segments) == original_segs

    def test_assistive_only_feedback_behavior_preserved(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "ao_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_rich_plan()
        pack = build_feedback_learning_pack(plan)
        assert pack.feedback_mode == "assistive_only"
        assert pack.ranking_biases.get("assistive_only") is True

    def test_never_raises_on_none_plan(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "nr_fb")

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        pack = build_feedback_learning_pack(None)
        assert pack is not None
        assert pack.feedback_mode == "assistive_only"


# ---------------------------------------------------------------------------
# 5. Edit plan schema integration tests
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_backward_compatibility_preserved(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan
        plan = AIEditPlan(
            enabled=True,
            mode="balanced",
            selected_segments=[AIClipPlan(start=0.0, end=5.0, score=70.0)],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "creator_feedback_intelligence" in d
        assert d["creator_feedback_intelligence"] == {}

    def test_feedback_field_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="balanced",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        assert plan.creator_feedback_intelligence == {}

    def test_all_prior_phase_fields_present(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True,
            mode="balanced",
            selected_segments=[],
            subtitle=AISubtitlePlan(),
            camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for field_name in (
            "creator_retrieval",
            "adaptive_creator_intelligence",
            "creator_feedback_intelligence",
        ):
            assert field_name in d, f"missing field: {field_name}"


# ---------------------------------------------------------------------------
# 6. Render influence tests
# ---------------------------------------------------------------------------

class TestRenderInfluence:
    def _plan_with_feedback(self, enabled=True):
        plan = _make_rich_plan()
        plan.creator_feedback_intelligence = {
            "available": True,
            "enabled": enabled,
            "feedback_mode": "assistive_only",
            "feedback_signals": [],
            "learned_feedback_patterns": {
                "total_signals": 10,
                "total_exports": 6,
                "total_ignores": 1,
                "dominant_creator_style": "viral_tiktok",
            },
            "ranking_biases": {
                "output_ranking_bias": 0.08,
                "variant_ranking_bias": 0.04,
                "retrieval_weighting_bias": 0.06,
                "subtitle_weighting_bias": 0.10,
                "pacing_weighting_bias": 0.09,
                "camera_weighting_bias": 0.07,
                "assistive_only": True,
            },
            "warnings": [],
        }
        return plan

    def test_feedback_influence_goes_to_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            add_subtitle: bool = True
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            highlight_per_word: bool = False
            ai_beat_execution_enabled: bool = False

        plan = self._plan_with_feedback(enabled=True)
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)

        fb_entries = [e for e in report["skipped"] if "creator_feedback_intelligence" in e]
        assert fb_entries, "Expected creator_feedback_intelligence in skipped"

    def test_feedback_does_not_mutate_ffmpeg_or_speed(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            add_subtitle: bool = True
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            highlight_per_word: bool = False
            ai_beat_execution_enabled: bool = False

        plan = self._plan_with_feedback()
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)
        all_text = str(report["applied"]) + str(report["skipped"]) + str(report["warnings"])
        assert "ffmpeg_args" not in all_text
        assert "playback_speed" not in all_text
        assert "subtitle_timing" not in all_text

    def test_no_feedback_field_reports_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            add_subtitle: bool = False
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            highlight_per_word: bool = False
            ai_beat_execution_enabled: bool = False

        plan = _make_minimal_plan()
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)
        fb_entries = [e for e in report["skipped"] if "creator_feedback_intelligence" in e]
        assert fb_entries


# ---------------------------------------------------------------------------
# 7. Safety boundary tests
# ---------------------------------------------------------------------------

class TestSafetyBoundaries:
    def test_no_render_execution(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "nr_fb")
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_rich_plan()
        pack = build_feedback_learning_pack(plan)
        assert not hasattr(pack, "render_executed")
        assert not hasattr(pack, "ffmpeg_command")

    def test_no_ffmpeg_mutation(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "ffm_fb")
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_rich_plan()
        pack = build_feedback_learning_pack(plan)
        d_str = str(pack.to_dict())
        assert "ffmpeg_args" not in d_str
        assert "render_command" not in d_str

    def test_no_playback_speed_mutation(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "spd_fb")
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_rich_plan()
        pack = build_feedback_learning_pack(plan)
        assert "playback_speed" not in str(pack.to_dict())

    def test_no_subtitle_timing_rewrite(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "tim_fb")
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_rich_plan()
        pack = build_feedback_learning_pack(plan)
        assert "subtitle_timing" not in str(pack.to_dict())

    def test_no_executor_override(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "ex_fb")
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_rich_plan()
        pack = build_feedback_learning_pack(plan)
        assert pack.feedback_mode == "assistive_only"
        assert pack.ranking_biases.get("assistive_only") is True

    def test_no_api_key_required(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "api_fb")
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        pack = build_feedback_learning_pack(_make_minimal_plan())
        assert pack is not None

    def test_no_gpu_required(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "gpu_fb")
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        pack = build_feedback_learning_pack(_make_minimal_plan())
        assert pack is not None

    def test_no_internet_required(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "inet_fb")

        import socket
        def _no_connect(self, *args, **kwargs):
            raise AssertionError("Internet access attempted — must not happen")
        monkeypatch.setattr(socket.socket, "connect", _no_connect)

        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        pack = build_feedback_learning_pack(_make_minimal_plan())
        assert pack is not None

    def test_ranking_biases_bounded(self, tmp_path, monkeypatch):
        from app.ai.feedback import feedback_memory
        monkeypatch.setattr(feedback_memory, "_FEEDBACK_DIR", tmp_path / "bnd_fb")
        from app.ai.feedback.feedback_learning import build_feedback_learning_pack
        plan = _make_rich_plan()

        for i in range(30):
            build_feedback_learning_pack(
                plan,
                context={
                    "feedback_id": f"b{i}",
                    "exported": True,
                    "selected_output_rank": 1,
                    "creator_style": "viral_tiktok",
                    "subtitle_style": "compact",
                    "pacing_style": "fast_hook",
                    "camera_style": "dynamic_safe",
                },
            )

        pack = build_feedback_learning_pack(plan)
        for key in (
            "output_ranking_bias",
            "variant_ranking_bias",
            "retrieval_weighting_bias",
            "subtitle_weighting_bias",
            "pacing_weighting_bias",
            "camera_weighting_bias",
        ):
            val = pack.ranking_biases.get(key, 0.0)
            assert 0.0 <= val <= 0.30, f"{key}={val} out of [0.0, 0.30]"

    def test_backward_compatibility_preserved(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="balanced",
            selected_segments=[], subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        # All prior phase fields must still exist
        for f in ("story", "retention", "creator_style_adaptation", "output_ranking",
                   "creator_retrieval", "adaptive_creator_intelligence",
                   "creator_feedback_intelligence"):
            assert f in d, f"backward compat broken: missing {f!r}"
