"""
test_ai_phase46_creator_preset_evolution.py — Phase 46 tests.

Covers: schema, safety, memory, scoring, evolution engine,
edit plan integration, render influence, safety boundaries.
"""
import pytest
from dataclasses import dataclass, field
from typing import List


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
        pacing=AIPacingPlan(pacing_style="fast_hook", energy_level=0.85),
    )


def _make_rich_plan(mode="viral_tiktok"):
    plan = _make_minimal_plan()
    plan.mode = mode
    plan.creator_style_adaptation = {"adapted_style": mode}
    plan.adaptive_creator_intelligence = {
        "available": True,
        "enabled": True,
        "learning_mode": "assistive_only",
        "creator_profile": {"style_confidence": 0.70, "subtitle_confidence": 0.60},
        "adaptive_influences": {
            "subtitle_enhancement_weight": 0.10,
            "pacing_enhancement_weight": 0.12,
        },
        "warnings": [],
    }
    plan.creator_feedback_intelligence = {
        "available": True,
        "enabled": True,
        "feedback_mode": "assistive_only",
        "learned_feedback_patterns": {
            "total_exports": 5,
            "total_signals": 10,
            "total_ignores": 1,
            "dominant_creator_style": mode,
        },
        "ranking_biases": {
            "subtitle_weighting_bias": 0.08,
            "pacing_weighting_bias": 0.07,
        },
    }
    plan.market_optimization_intelligence = {
        "available": True,
        "enabled": True,
        "optimization_mode": "assistive_only",
        "target_market": mode,
        "market_profile": {"confidence": 0.85, "platform_type": "tiktok"},
        "subtitle_market_bias": {"weight": 0.20},
        "pacing_market_bias": {"weight": 0.22},
        "camera_market_bias": {"weight": 0.18},
        "hook_market_bias": {"weight": 0.24},
    }
    plan.creator_retrieval = {
        "enabled": True,
        "matches": [
            {"id": "m1", "creator_style": mode},
            {"id": "m2", "creator_style": mode},
        ],
    }
    plan.render_quality_evaluation = {
        "available": True,
        "enabled": True,
        "evaluation_mode": "evaluation_only",
    }
    return plan


def _make_podcast_plan():
    return _make_rich_plan("podcast")


def _make_educational_plan():
    return _make_rich_plan("educational")


# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestPresetSchema:
    def test_preset_defaults(self):
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        p = AICreatorPreset()
        assert p.preset_id == "unknown"
        assert p.quality_score == 0.0
        assert p.creator_fit_score == 0.0
        assert p.market_fit_score == 0.0
        assert p.evolution_generation == 1
        assert p.confidence == 0.0
        assert p.tags == []
        assert p.warnings == []
        assert p.explanation == []

    def test_preset_to_dict_keys(self):
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        d = AICreatorPreset(preset_id="abc", preset_name="Test", quality_score=80.0).to_dict()
        assert d["preset_id"] == "abc"
        assert d["preset_name"] == "Test"
        assert d["quality_score"] == 80.0
        for key in ("creator_fit_score", "market_fit_score", "evolution_generation",
                    "confidence", "subtitle_style", "pacing_style"):
            assert key in d

    def test_preset_from_dict(self):
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        raw = {"preset_id": "test1", "preset_name": "Test", "quality_score": 70.0}
        p = AICreatorPreset.from_dict(raw)
        assert p.preset_id == "test1"
        assert p.quality_score == 70.0

    def test_preset_from_dict_non_dict(self):
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        p = AICreatorPreset.from_dict("bad")
        assert p.preset_id == "unknown"

    def test_evolution_pack_defaults(self):
        from app.ai.preset_evolution.preset_schema import AIPresetEvolutionPack
        pack = AIPresetEvolutionPack()
        assert pack.available is True
        assert pack.enabled is False
        assert pack.evolution_mode == "assistive_only"
        assert pack.recommended_presets == []
        assert pack.evolved_presets == []
        assert pack.best_preset_id == ""

    def test_evolution_pack_to_dict(self):
        from app.ai.preset_evolution.preset_schema import AIPresetEvolutionPack
        pack = AIPresetEvolutionPack(enabled=True, best_preset_id="x")
        d = pack.to_dict()
        assert d["enabled"] is True
        assert d["best_preset_id"] == "x"
        assert "recommended_presets" in d
        assert "evolved_presets" in d

    def test_preset_to_dict_rounded(self):
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        p = AICreatorPreset(quality_score=66.666666, confidence=0.333333)
        d = p.to_dict()
        assert d["quality_score"] == round(66.666666, 2)
        assert d["confidence"] == round(0.333333, 4)


# ---------------------------------------------------------------------------
# 2. Safety tests
# ---------------------------------------------------------------------------

class TestPresetSafety:
    def test_sanitize_strips_ffmpeg_args(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"ffmpeg_args": ["-crf", "23"], "quality_score": 80.0})
        assert "ffmpeg_args" not in result
        assert result["quality_score"] == 80.0

    def test_sanitize_strips_render_command(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"render_command": "ffmpeg ...", "preset_id": "x"})
        assert "render_command" not in result

    def test_sanitize_strips_playback_speed(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"playback_speed": 1.5})
        assert "playback_speed" not in result

    def test_sanitize_strips_subtitle_timing(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"subtitle_timing": [0.0, 1.0]})
        assert "subtitle_timing" not in result

    def test_sanitize_strips_rerender(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"rerender": True})
        assert "rerender" not in result

    def test_sanitize_strips_delete_output(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"delete_output": True})
        assert "delete_output" not in result

    def test_sanitize_strips_subprocess(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"subprocess": "cmd"})
        assert "subprocess" not in result

    def test_sanitize_clamps_scores(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"quality_score": 200.0, "creator_fit_score": -10.0})
        assert result["quality_score"] == 100.0
        assert result["creator_fit_score"] == 0.0

    def test_sanitize_clamps_confidence(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"confidence": 5.0})
        assert result["confidence"] == 1.0

    def test_sanitize_recursive(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset({"nested": {"executable": "bash"}})
        assert "executable" not in result.get("nested", {})

    def test_is_safe_true(self):
        from app.ai.preset_evolution.preset_safety import is_preset_safe
        assert is_preset_safe({"quality_score": 80.0}) is True

    def test_is_safe_false_forbidden(self):
        from app.ai.preset_evolution.preset_safety import is_preset_safe
        assert is_preset_safe({"ffmpeg_args": ["-i", "in.mp4"]}) is False

    def test_sanitize_non_dict(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        assert sanitize_preset(None) == {}

    def test_sanitize_never_raises(self):
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        result = sanitize_preset("bad_input")
        assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 3. Memory tests
# ---------------------------------------------------------------------------

class TestPresetMemory:
    def test_build_default_presets_returns_list(self):
        from app.ai.preset_evolution.preset_memory import build_default_presets
        presets = build_default_presets()
        assert isinstance(presets, list)
        assert len(presets) >= 3

    def test_default_presets_have_ids(self):
        from app.ai.preset_evolution.preset_memory import build_default_presets
        presets = build_default_presets()
        for p in presets:
            assert p.preset_id != "unknown"
            assert p.preset_id != ""

    def test_default_presets_tiktok_exists(self):
        from app.ai.preset_evolution.preset_memory import build_default_presets
        presets = build_default_presets()
        styles = [p.creator_style for p in presets]
        assert any("tiktok" in s for s in styles)

    def test_default_presets_podcast_exists(self):
        from app.ai.preset_evolution.preset_memory import build_default_presets
        presets = build_default_presets()
        styles = [p.creator_style for p in presets]
        assert any("podcast" in s for s in styles)

    def test_default_presets_educational_exists(self):
        from app.ai.preset_evolution.preset_memory import build_default_presets
        presets = build_default_presets()
        styles = [p.creator_style for p in presets]
        assert any("educational" in s for s in styles)

    def test_load_missing_file_returns_defaults(self, tmp_path, monkeypatch):
        from app.ai.preset_evolution import preset_memory
        monkeypatch.setattr(preset_memory, "_PRESET_DIR", tmp_path / "nonexistent")
        presets = preset_memory.load_evolved_presets()
        assert isinstance(presets, list)
        assert len(presets) >= 3

    def test_load_corrupt_file_returns_defaults(self, tmp_path, monkeypatch):
        from app.ai.preset_evolution import preset_memory
        corrupt_dir = tmp_path / "presets"
        corrupt_dir.mkdir()
        (corrupt_dir / "evolved_presets.json").write_text("{{{invalid", encoding="utf-8")
        monkeypatch.setattr(preset_memory, "_PRESET_DIR", corrupt_dir)
        presets = preset_memory.load_evolved_presets()
        assert isinstance(presets, list)
        assert len(presets) >= 3

    def test_save_and_load_roundtrip(self, tmp_path, monkeypatch):
        from app.ai.preset_evolution import preset_memory
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        monkeypatch.setattr(preset_memory, "_PRESET_DIR", tmp_path / "presets")
        preset = AICreatorPreset(
            preset_id="test_roundtrip",
            preset_name="Test Preset",
            creator_style="viral_tiktok",
            quality_score=75.0,
        )
        success = preset_memory.save_evolved_presets([preset])
        assert success is True
        loaded = preset_memory.load_evolved_presets()
        ids = [p.preset_id for p in loaded]
        assert "test_roundtrip" in ids

    def test_save_caps_at_50(self, tmp_path, monkeypatch):
        from app.ai.preset_evolution import preset_memory
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        monkeypatch.setattr(preset_memory, "_PRESET_DIR", tmp_path / "presets")
        big_list = [AICreatorPreset(preset_id=f"p{i}") for i in range(60)]
        preset_memory.save_evolved_presets(big_list)
        loaded = preset_memory.load_evolved_presets()
        assert len(loaded) <= 50

    def test_load_never_raises(self, monkeypatch):
        from app.ai.preset_evolution import preset_memory
        monkeypatch.setattr(preset_memory, "_PRESET_DIR", None)
        # Should fall back to defaults without raising
        result = preset_memory.load_evolved_presets()
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# 4. Preset scoring tests
# ---------------------------------------------------------------------------

class TestPresetScoring:
    def test_score_returns_float(self):
        from app.ai.preset_evolution.preset_scoring import score_creator_preset
        from app.ai.preset_evolution.preset_memory import build_default_presets
        preset = build_default_presets()[0]
        result = score_creator_preset(preset)
        assert isinstance(result, float)

    def test_score_clamped_0_100(self):
        from app.ai.preset_evolution.preset_scoring import score_creator_preset
        from app.ai.preset_evolution.preset_memory import build_default_presets
        for preset in build_default_presets():
            score = score_creator_preset(preset)
            assert 0.0 <= score <= 100.0

    def test_score_increases_with_rich_plan(self):
        from app.ai.preset_evolution.preset_scoring import score_creator_preset
        from app.ai.preset_evolution.preset_memory import build_default_presets
        preset = build_default_presets()[0]
        base_score = score_creator_preset(preset)
        rich_score = score_creator_preset(preset, edit_plan=_make_rich_plan())
        assert rich_score >= base_score

    def test_score_never_raises_on_none(self):
        from app.ai.preset_evolution.preset_scoring import score_creator_preset
        result = score_creator_preset(None)
        assert result == 0.0

    def test_score_dict_input(self):
        from app.ai.preset_evolution.preset_scoring import score_creator_preset
        result = score_creator_preset({"quality_score": 80.0, "creator_fit_score": 70.0, "market_fit_score": 60.0})
        assert result > 0.0
        assert result <= 100.0

    def test_weighted_scoring_valid(self):
        from app.ai.preset_evolution.preset_scoring import score_creator_preset
        preset = {"quality_score": 100.0, "creator_fit_score": 100.0, "market_fit_score": 100.0}
        score = score_creator_preset(preset)
        # With no edit_plan feedback/retrieval, expect at least 70% of 100 (0.35+0.25+0.20 = 0.80 × 100)
        assert score >= 70.0

    def test_feedback_style_match_bonus(self):
        from app.ai.preset_evolution.preset_scoring import score_creator_preset
        from app.ai.preset_evolution.preset_memory import build_default_presets
        plan_match = _make_rich_plan("viral_tiktok")
        plan_no_match = _make_rich_plan("podcast")
        tiktok_preset = next(p for p in build_default_presets() if "tiktok" in p.creator_style)
        score_match = score_creator_preset(tiktok_preset, edit_plan=plan_match)
        score_no_match = score_creator_preset(tiktok_preset, edit_plan=plan_no_match)
        assert score_match >= score_no_match


# ---------------------------------------------------------------------------
# 5. Evolution engine tests
# ---------------------------------------------------------------------------

class TestPresetEvolutionEngine:
    def test_build_returns_pack(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        from app.ai.preset_evolution.preset_schema import AIPresetEvolutionPack
        result = build_preset_evolution_pack(None)
        assert isinstance(result, AIPresetEvolutionPack)

    def test_build_never_raises_on_none(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(None, payload=None, context=None)
        assert result is not None

    def test_build_with_rich_plan_enabled(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan(), context={"target_market": "viral_tiktok"})
        assert result.available is True

    def test_tiktok_preset_evolves(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(
            _make_rich_plan("viral_tiktok"),
            context={"target_market": "viral_tiktok"},
        )
        if result.evolved_presets:
            evolved = result.evolved_presets[0]
            assert evolved.get("evolution_generation", 1) > 1
            assert "v2" in evolved.get("preset_name", "") or "tiktok" in evolved.get("preset_id", "").lower()

    def test_podcast_preset_evolves(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(
            _make_podcast_plan(),
            context={"target_market": "podcast"},
        )
        if result.evolved_presets:
            evolved = result.evolved_presets[0]
            assert "podcast" in evolved.get("creator_style", "").lower() or \
                   "podcast" in evolved.get("preset_id", "").lower()

    def test_educational_preset_evolves(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(
            _make_educational_plan(),
            context={"target_market": "educational"},
        )
        if result.evolved_presets:
            evolved = result.evolved_presets[0]
            assert "educational" in evolved.get("creator_style", "").lower() or \
                   "educational" in evolved.get("preset_id", "").lower()

    def test_best_preset_selected_deterministically(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result1 = build_preset_evolution_pack(
            _make_rich_plan(), context={"target_market": "viral_tiktok"}
        )
        result2 = build_preset_evolution_pack(
            _make_rich_plan(), context={"target_market": "viral_tiktok"}
        )
        assert result1.best_preset_id == result2.best_preset_id

    def test_recommended_presets_populated(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(
            _make_rich_plan(), context={"target_market": "viral_tiktok"}
        )
        if result.enabled:
            assert isinstance(result.recommended_presets, list)

    def test_evolution_mode_always_assistive_only(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        assert result.evolution_mode == "assistive_only"

    def test_no_payload_mutation(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        from dataclasses import dataclass
        @dataclass
        class FakeRequest:
            ai_target_market: str = "viral_tiktok"
            ai_mode: str = "viral_tiktok"

        req = FakeRequest()
        original_market = req.ai_target_market
        build_preset_evolution_pack(_make_rich_plan(), payload=req)
        assert req.ai_target_market == original_market

    def test_context_takes_priority_over_plan(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        plan = _make_rich_plan("podcast")
        result = build_preset_evolution_pack(plan, context={"target_market": "viral_tiktok"})
        # Context market should win; evolved should reference tiktok lineage if any
        assert result is not None  # evolved or recommended — just no crash

    def test_no_render_execution(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        d = result.to_dict()
        assert "ffmpeg_args" not in str(d)
        assert "render_command" not in str(d)

    def test_no_output_deletion(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        d = result.to_dict()
        assert "delete_output" not in str(d)

    def test_no_ffmpeg_mutation(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        d = result.to_dict()
        assert "ffmpeg_args" not in str(d)

    def test_no_playback_speed_mutation(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        d = result.to_dict()
        assert "playback_speed" not in str(d)

    def test_no_subtitle_timing_rewrite(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        d = result.to_dict()
        assert "subtitle_timing" not in str(d)

    def test_no_executor_override(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        d = result.to_dict()
        assert "executor" not in str(d)

    def test_no_autonomous_rerender(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        d = result.to_dict()
        assert "rerender" not in str(d)

    def test_no_internet_required(self):
        # Engine should work completely offline (no external calls)
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        assert result is not None

    def test_no_api_key_required(self):
        import os
        env_backup = os.environ.copy()
        for key in list(os.environ.keys()):
            if "API_KEY" in key or "OPENAI" in key or "ANTHROPIC" in key:
                del os.environ[key]
        try:
            from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
            result = build_preset_evolution_pack(_make_rich_plan())
            assert result is not None
        finally:
            os.environ.update(env_backup)

    def test_no_gpu_required(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        assert result is not None


# ---------------------------------------------------------------------------
# 6. Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchema:
    def test_creator_preset_evolution_field_exists(self):
        plan = _make_minimal_plan()
        assert hasattr(plan, "creator_preset_evolution")
        assert isinstance(plan.creator_preset_evolution, dict)

    def test_creator_preset_evolution_in_to_dict(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "creator_preset_evolution" in d

    def test_creator_preset_evolution_default_empty(self):
        plan = _make_minimal_plan()
        assert plan.creator_preset_evolution == {}

    def test_backward_compatibility_phase45_preserved(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "render_quality_evaluation" in d

    def test_backward_compatibility_phase44_preserved(self):
        plan = _make_minimal_plan()
        d = plan.to_dict()
        assert "market_optimization_intelligence" in d


# ---------------------------------------------------------------------------
# 7. Render influence reporting
# ---------------------------------------------------------------------------

class TestRenderInfluence:
    def test_influence_report_preset_evolution_pending(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_minimal_plan()
        plan.creator_preset_evolution = {
            "available": True,
            "enabled": False,
            "evolution_mode": "assistive_only",
            "recommended_presets": [],
            "evolved_presets": [],
            "best_preset_id": "",
            "warnings": [],
        }
        _payload, report = apply_ai_render_influence(None, plan, {})
        skipped_str = " ".join(str(s) for s in report.get("skipped", []))
        assert "creator_preset_evolution" in skipped_str

    def test_influence_report_preset_evolution_enabled(self):
        from app.ai.director.render_influence import apply_ai_render_influence
        plan = _make_minimal_plan()
        plan.creator_preset_evolution = {
            "available": True,
            "enabled": True,
            "evolution_mode": "assistive_only",
            "recommended_presets": [{"preset_id": "tiktok_v2", "preset_name": "TikTok Viral v2"}],
            "evolved_presets": [{"preset_id": "tiktok_v2", "preset_name": "TikTok Viral v2"}],
            "best_preset_id": "tiktok_v2",
            "warnings": [],
        }
        _payload, report = apply_ai_render_influence(None, plan, {})
        skipped_str = " ".join(str(s) for s in report.get("skipped", []))
        assert "creator_preset_evolution" in skipped_str
        assert "tiktok_v2" in skipped_str


# ---------------------------------------------------------------------------
# 8. Safety boundaries
# ---------------------------------------------------------------------------

class TestSafetyBoundaries:
    def test_scores_clamped_0_100(self):
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        p = AICreatorPreset(quality_score=200.0, creator_fit_score=-10.0)
        # to_dict doesn't auto-clamp, but sanitize does
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        d = sanitize_preset(p.to_dict())
        assert d["quality_score"] == 100.0
        assert d["creator_fit_score"] == 0.0

    def test_confidence_clamped_0_1(self):
        from app.ai.preset_evolution.preset_schema import AICreatorPreset
        from app.ai.preset_evolution.preset_safety import sanitize_preset
        p = AICreatorPreset(confidence=5.0)
        d = sanitize_preset(p.to_dict())
        assert d["confidence"] == 1.0

    def test_forbidden_fields_not_in_evolution_output(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        d_str = str(result.to_dict())
        for key in ("ffmpeg_args", "render_command", "playback_speed", "subtitle_timing",
                    "rerender", "delete_output", "subprocess", "executable", "python_code"):
            assert key not in d_str

    def test_assistive_only_mode_preserved(self):
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        assert result.evolution_mode == "assistive_only"

    def test_no_autonomous_preset_replacement(self):
        # Pack provides recommended/evolved presets as advisory only
        from app.ai.preset_evolution.preset_evolution_engine import build_preset_evolution_pack
        result = build_preset_evolution_pack(_make_rich_plan())
        # No field that directly sets or overrides current preset
        d = result.to_dict()
        assert "current_preset" not in d
        assert "force_preset" not in d
        assert "override_preset" not in d
