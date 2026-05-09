"""
test_ai_phase44_market_optimization.py — Phase 44 tests.

Covers: schema, safety, profiles, optimizer, edit plan integration,
render influence, safety boundaries, environment requirements.
"""
import pytest
from dataclasses import dataclass, field
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
        pacing=AIPacingPlan(pacing_style="fast_hook", energy_level=0.85),
    )


def _make_rich_plan(mode="viral_tiktok"):
    plan = _make_minimal_plan()
    plan.creator_style_adaptation = {"adapted_style": mode}
    plan.subtitle_text_apply = {"subtitle_style": "compact"}
    plan.camera_motion_apply = {"camera_behavior": "dynamic_safe"}
    plan.adaptive_creator_intelligence = {
        "available": True,
        "enabled": True,
        "learning_mode": "assistive_only",
        "adaptive_influences": {
            "subtitle_enhancement_weight": 0.10,
            "pacing_enhancement_weight": 0.12,
            "camera_enhancement_weight": 0.09,
            "assistive_only": True,
        },
        "creator_profile": {},
        "learned_preferences": {},
        "warnings": [],
    }
    plan.creator_feedback_intelligence = {
        "available": True,
        "enabled": True,
        "feedback_mode": "assistive_only",
        "feedback_signals": [],
        "learned_feedback_patterns": {},
        "ranking_biases": {
            "subtitle_weighting_bias": 0.08,
            "pacing_weighting_bias": 0.07,
            "camera_weighting_bias": 0.06,
            "assistive_only": True,
        },
        "warnings": [],
    }
    return plan


@dataclass
class _MockRequest:
    ai_director_enabled: bool = True
    ai_mode: str = "viral_tiktok"
    ai_target_market: Optional[str] = None


# ---------------------------------------------------------------------------
# 1. Schema tests
# ---------------------------------------------------------------------------

class TestMarketSchema:
    def test_market_profile_defaults(self):
        from app.ai.market.market_schema import AIMarketOptimizationProfile
        p = AIMarketOptimizationProfile()
        assert p.market_id == "default"
        assert p.platform_type == ""
        assert p.subtitle_density_bias == 0.0
        assert p.confidence == 0.0
        assert p.tags == []
        assert p.warnings == []

    def test_market_profile_to_dict(self):
        from app.ai.market.market_schema import AIMarketOptimizationProfile
        p = AIMarketOptimizationProfile(
            market_id="viral_tiktok",
            platform_type="tiktok",
            subtitle_density_bias=0.70,
            confidence=0.90,
        )
        d = p.to_dict()
        assert d["market_id"] == "viral_tiktok"
        assert d["platform_type"] == "tiktok"
        assert d["subtitle_density_bias"] == pytest.approx(0.70, abs=1e-4)

    def test_market_optimization_pack_defaults(self):
        from app.ai.market.market_schema import AIMarketOptimizationPack
        pack = AIMarketOptimizationPack()
        assert pack.available is True
        assert pack.enabled is False
        assert pack.optimization_mode == "assistive_only"
        assert pack.target_market == ""
        assert pack.subtitle_market_bias == {}

    def test_market_optimization_pack_to_dict(self):
        from app.ai.market.market_schema import AIMarketOptimizationPack
        pack = AIMarketOptimizationPack(enabled=True, target_market="tiktok")
        d = pack.to_dict()
        assert d["enabled"] is True
        assert d["optimization_mode"] == "assistive_only"
        assert d["target_market"] == "tiktok"


# ---------------------------------------------------------------------------
# 2. Safety tests
# ---------------------------------------------------------------------------

class TestMarketSafety:
    def test_sanitize_strips_forbidden_keys(self):
        from app.ai.market.market_safety import sanitize_market_profile
        data = {
            "preferred_style": "compact",
            "ffmpeg_args": "-c:v h264",
            "playback_speed": 2.0,
            "subtitle_timing": [0, 1],
            "render_command": "ffmpeg ...",
            "output_path": "/tmp/x.mp4",
            "python_code": "import os",
            "subprocess": "run",
            "executable": "/bin/sh",
            "queue_priority": 1,
        }
        result = sanitize_market_profile(data)
        assert "preferred_style" in result
        for k in ("ffmpeg_args", "playback_speed", "subtitle_timing", "render_command",
                   "output_path", "python_code", "subprocess", "executable", "queue_priority"):
            assert k not in result

    def test_sanitize_nested_forbidden(self):
        from app.ai.market.market_safety import sanitize_market_profile
        data = {"meta": {"playback_speed": 2.0, "style": "compact"}}
        result = sanitize_market_profile(data)
        assert "playback_speed" not in result["meta"]
        assert result["meta"]["style"] == "compact"

    def test_sanitize_empty_dict(self):
        from app.ai.market.market_safety import sanitize_market_profile
        assert sanitize_market_profile({}) == {}

    def test_sanitize_non_dict_returns_empty(self):
        from app.ai.market.market_safety import sanitize_market_profile
        assert sanitize_market_profile(None) == {}

    def test_is_safe_clean_data(self):
        from app.ai.market.market_safety import is_market_profile_safe
        assert is_market_profile_safe({"style": "compact", "weight": 0.5}) is True

    def test_is_safe_forbidden_key(self):
        from app.ai.market.market_safety import is_market_profile_safe
        assert is_market_profile_safe({"ffmpeg_args": "-c:v"}) is False
        assert is_market_profile_safe({"playback_speed": 1.5}) is False

    def test_is_safe_never_raises(self):
        from app.ai.market.market_safety import is_market_profile_safe
        assert is_market_profile_safe(None) is True
        assert is_market_profile_safe(42) is True


# ---------------------------------------------------------------------------
# 3. Profile tests
# ---------------------------------------------------------------------------

class TestMarketProfiles:
    def test_tiktok_profile_loads(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("viral_tiktok")
        assert p.market_id == "viral_tiktok"
        assert p.platform_type == "tiktok"
        assert p.subtitle_density_bias > 0.5
        assert p.pacing_energy_bias > 0.7
        assert p.hook_strength_bias > 0.8
        assert p.confidence >= 0.80

    def test_tiktok_alias_loads(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("tiktok")
        assert p.platform_type == "tiktok"

    def test_youtube_shorts_profile_loads(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("youtube_shorts")
        assert p.market_id == "youtube_shorts"
        assert p.platform_type == "youtube_shorts"
        assert p.confidence >= 0.80

    def test_shorts_alias_loads(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("shorts")
        assert p.platform_type == "youtube_shorts"

    def test_facebook_reels_profile_loads(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("facebook_reels")
        assert p.market_id == "facebook_reels"
        assert p.platform_type == "facebook_reels"

    def test_reels_alias_loads(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("reels")
        assert p.platform_type == "facebook_reels"

    def test_podcast_profile_loads(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("podcast")
        assert p.market_id == "podcast"
        assert p.pacing_energy_bias < 0.5
        assert p.preferred_pacing_style == "calm_storytelling"

    def test_educational_profile_loads(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("educational")
        assert p.market_id == "educational"
        assert p.pacing_energy_bias < 0.5
        assert "readability" in p.preferred_subtitle_style or "clean" in p.preferred_subtitle_style

    def test_unknown_market_returns_generic(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile("completely_unknown_xyz_platform_abc")
        assert p.market_id != ""
        assert p.confidence <= 0.60

    def test_list_market_profiles(self):
        from app.ai.market.market_profiles import list_market_profiles
        profiles = list_market_profiles()
        assert isinstance(profiles, list)
        assert len(profiles) >= 5
        assert "viral_tiktok" in profiles
        assert "podcast" in profiles
        assert "educational" in profiles

    def test_get_profile_never_raises(self):
        from app.ai.market.market_profiles import get_market_profile
        p = get_market_profile(None)
        assert p is not None
        p = get_market_profile("")
        assert p is not None


# ---------------------------------------------------------------------------
# 4. Optimizer tests
# ---------------------------------------------------------------------------

class TestMarketOptimizer:
    def test_deterministic_optimization(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        pack1 = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        pack2 = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        assert pack1.optimization_mode == pack2.optimization_mode == "assistive_only"
        assert pack1.target_market == pack2.target_market

    def test_tiktok_optimization_applied(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan("viral_tiktok")
        pack = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        assert pack.enabled is True
        assert pack.target_market == "viral_tiktok"
        assert pack.subtitle_market_bias.get("preferred_style") == "compact"
        assert pack.hook_market_bias.get("weight", 0) > 0

    def test_podcast_optimization_applied(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_minimal_plan()
        pack = build_market_optimization_pack(plan, context={"target_market": "podcast"})
        assert pack.enabled is True
        assert pack.pacing_market_bias.get("preferred_style") == "calm_storytelling"
        assert pack.subtitle_market_bias.get("density_bias", 1.0) < 0.5

    def test_educational_optimization_applied(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_minimal_plan()
        pack = build_market_optimization_pack(plan, context={"target_market": "educational"})
        assert pack.enabled is True
        assert "readability" in pack.subtitle_market_bias.get("preferred_style", "") or \
               "clean" in pack.subtitle_market_bias.get("preferred_style", "")

    def test_subtitle_market_bias_valid(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        pack = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        bias = pack.subtitle_market_bias
        assert isinstance(bias, dict)
        assert bias.get("assistive_only") is True
        assert 0.0 <= bias.get("weight", 0.0) <= 0.30

    def test_pacing_market_bias_valid(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        pack = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        bias = pack.pacing_market_bias
        assert isinstance(bias, dict)
        assert bias.get("assistive_only") is True
        assert 0.0 <= bias.get("weight", 0.0) <= 0.30

    def test_camera_market_bias_valid(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        pack = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        bias = pack.camera_market_bias
        assert isinstance(bias, dict)
        assert bias.get("assistive_only") is True
        assert 0.0 <= bias.get("weight", 0.0) <= 0.30

    def test_hook_market_bias_valid(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        pack = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        bias = pack.hook_market_bias
        assert isinstance(bias, dict)
        assert bias.get("assistive_only") is True
        assert 0.0 <= bias.get("weight", 0.0) <= 0.30

    def test_forbidden_fields_stripped(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        pack = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        d_str = str(pack.to_dict())
        for forbidden in ("ffmpeg_args", "playback_speed", "subtitle_timing",
                          "render_command", "output_path", "python_code"):
            assert forbidden not in d_str

    def test_no_payload_mutation(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        req = _MockRequest(ai_mode="viral_tiktok")
        original_mode = req.ai_mode
        original_segs = len(plan.selected_segments)

        build_market_optimization_pack(plan, payload=req)

        assert req.ai_mode == original_mode
        assert len(plan.selected_segments) == original_segs

    def test_assistive_only_preserved(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        pack = build_market_optimization_pack(plan, context={"target_market": "viral_tiktok"})
        assert pack.optimization_mode == "assistive_only"
        for bias_dict in (
            pack.subtitle_market_bias,
            pack.pacing_market_bias,
            pack.camera_market_bias,
            pack.hook_market_bias,
        ):
            assert bias_dict.get("assistive_only") is True

    def test_never_raises_on_none_plan(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(None)
        assert pack is not None
        assert pack.optimization_mode == "assistive_only"

    def test_adaptive_amplification_raises_weight(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan_no_adaptive = _make_minimal_plan()
        plan_with_adaptive = _make_rich_plan()

        pack_base = build_market_optimization_pack(
            plan_no_adaptive, context={"target_market": "viral_tiktok"}
        )
        pack_amplified = build_market_optimization_pack(
            plan_with_adaptive, context={"target_market": "viral_tiktok"}
        )

        base_sub = pack_base.subtitle_market_bias.get("weight", 0.0)
        amp_sub = pack_amplified.subtitle_market_bias.get("weight", 0.0)
        assert amp_sub >= base_sub

    def test_market_resolved_from_payload(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_minimal_plan()
        req = _MockRequest(ai_target_market="podcast")
        pack = build_market_optimization_pack(plan, payload=req)
        assert pack.target_market == "podcast"

    def test_market_resolved_from_plan_mode(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_minimal_plan()
        plan.mode = "podcast"
        pack = build_market_optimization_pack(plan)
        assert "podcast" in pack.target_market


# ---------------------------------------------------------------------------
# 5. Edit plan schema integration
# ---------------------------------------------------------------------------

class TestEditPlanSchemaIntegration:
    def test_backward_compatibility_preserved(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan, AIClipPlan
        plan = AIEditPlan(
            enabled=True, mode="balanced",
            selected_segments=[AIClipPlan(start=0.0, end=5.0, score=70.0)],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "market_optimization_intelligence" in d
        assert d["market_optimization_intelligence"] == {}

    def test_field_default_empty(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="balanced",
            selected_segments=[], subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert plan.market_optimization_intelligence == {}

    def test_all_prior_phase_fields_present(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="balanced",
            selected_segments=[], subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for f in (
            "creator_retrieval",
            "adaptive_creator_intelligence",
            "creator_feedback_intelligence",
            "market_optimization_intelligence",
        ):
            assert f in d, f"backward compat broken: missing {f!r}"


# ---------------------------------------------------------------------------
# 6. Render influence tests
# ---------------------------------------------------------------------------

class TestRenderInfluence:
    def _plan_with_market(self, enabled=True, market="viral_tiktok"):
        plan = _make_rich_plan()
        plan.market_optimization_intelligence = {
            "available": True,
            "enabled": enabled,
            "optimization_mode": "assistive_only",
            "target_market": market,
            "market_profile": {"platform_type": "tiktok", "market_id": market},
            "subtitle_market_bias": {"preferred_style": "compact", "weight": 0.12, "assistive_only": True},
            "pacing_market_bias": {"preferred_style": "fast_hook", "weight": 0.14, "assistive_only": True},
            "camera_market_bias": {"preferred_style": "dynamic_safe", "weight": 0.10, "assistive_only": True},
            "hook_market_bias": {"preferred_style": "aggressive_question", "weight": 0.13, "assistive_only": True},
            "warnings": [],
        }
        return plan

    def test_market_influence_goes_to_skipped(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            add_subtitle: bool = True
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            highlight_per_word: bool = False
            ai_beat_execution_enabled: bool = False

        plan = self._plan_with_market(enabled=True)
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)
        moi_entries = [e for e in report["skipped"] if "market_optimization_intelligence" in e]
        assert moi_entries, "Expected market_optimization_intelligence in skipped"

    def test_market_does_not_mutate_ffmpeg(self):
        from app.ai.director.render_influence import apply_ai_render_influence

        @dataclass
        class _P:
            add_subtitle: bool = True
            motion_aware_crop: bool = False
            reframe_mode: str = "center"
            highlight_per_word: bool = False
            ai_beat_execution_enabled: bool = False

        plan = self._plan_with_market()
        payload = _P()
        _, report = apply_ai_render_influence(payload, plan)
        all_text = str(report["applied"]) + str(report["skipped"]) + str(report["warnings"])
        assert "ffmpeg_args" not in all_text
        assert "playback_speed" not in all_text
        assert "subtitle_timing" not in all_text

    def test_no_market_field_reports_skipped(self):
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
        moi_entries = [e for e in report["skipped"] if "market_optimization_intelligence" in e]
        assert moi_entries


# ---------------------------------------------------------------------------
# 7. Safety boundary tests
# ---------------------------------------------------------------------------

class TestSafetyBoundaries:
    def test_no_render_execution(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(_make_rich_plan(), context={"target_market": "viral_tiktok"})
        assert not hasattr(pack, "render_executed")
        assert not hasattr(pack, "ffmpeg_command")

    def test_no_ffmpeg_mutation(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(_make_rich_plan(), context={"target_market": "viral_tiktok"})
        d_str = str(pack.to_dict())
        assert "ffmpeg_args" not in d_str
        assert "render_command" not in d_str

    def test_no_playback_speed_mutation(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(_make_rich_plan(), context={"target_market": "viral_tiktok"})
        assert "playback_speed" not in str(pack.to_dict())

    def test_no_subtitle_timing_rewrite(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(_make_rich_plan(), context={"target_market": "viral_tiktok"})
        assert "subtitle_timing" not in str(pack.to_dict())

    def test_no_executor_override(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(_make_rich_plan(), context={"target_market": "viral_tiktok"})
        assert pack.optimization_mode == "assistive_only"

    def test_no_api_key_required(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(_make_minimal_plan())
        assert pack is not None

    def test_no_gpu_required(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(_make_minimal_plan())
        assert pack is not None

    def test_no_internet_required(self, monkeypatch):
        import socket
        def _no_connect(self, *args, **kwargs):
            raise AssertionError("Internet access attempted — must not happen")
        monkeypatch.setattr(socket.socket, "connect", _no_connect)

        from app.ai.market.market_optimizer import build_market_optimization_pack
        pack = build_market_optimization_pack(_make_minimal_plan())
        assert pack is not None

    def test_bias_weights_bounded(self):
        from app.ai.market.market_optimizer import build_market_optimization_pack
        plan = _make_rich_plan()
        for market in ("viral_tiktok", "youtube_shorts", "facebook_reels", "podcast", "educational"):
            pack = build_market_optimization_pack(plan, context={"target_market": market})
            for bias_dict, name in (
                (pack.subtitle_market_bias, "subtitle"),
                (pack.pacing_market_bias, "pacing"),
                (pack.camera_market_bias, "camera"),
                (pack.hook_market_bias, "hook"),
            ):
                w = bias_dict.get("weight", 0.0)
                assert 0.0 <= w <= 0.30, f"market={market} {name} weight={w} out of bounds"

    def test_backward_compatibility_all_prior_phases(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="balanced",
            selected_segments=[], subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for f in ("story", "retention", "creator_style_adaptation", "output_ranking",
                   "creator_retrieval", "adaptive_creator_intelligence",
                   "creator_feedback_intelligence", "market_optimization_intelligence"):
            assert f in d, f"backward compat broken: missing {f!r}"
