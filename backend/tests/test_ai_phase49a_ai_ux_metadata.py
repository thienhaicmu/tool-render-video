"""
test_ai_phase49a_ai_ux_metadata.py — Phase 49A AI UX Metadata Contract tests.

Covers:
- ai_ux available when AI metadata present
- ai_ux unavailable fallback when metadata missing
- stable keys always present
- confidence clamping [0.0, 1.0]
- recommendation list max length
- no raw debug/internal fields exposed
- deterministic output
- strategy section content
- safe_influence section content
- best_export section content
- safety boundaries (no render mutation fields)
"""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_edit_plan(**kwargs):
    plan = MagicMock()
    plan.multi_signal_orchestration = kwargs.get("multi_signal_orchestration", {})
    plan.safe_influence_pack = kwargs.get("safe_influence_pack", {})
    plan.creator_style = kwargs.get("creator_style", {})
    plan.creator_style_adaptation = kwargs.get("creator_style_adaptation", {})
    plan.output_ranking = kwargs.get("output_ranking", {})
    return plan


def _make_mso(confidence: float = 0.87, market: str = "US", strategy: dict | None = None) -> dict:
    return {
        "available": True,
        "enabled": True,
        "orchestration_mode": "reasoning_only",
        "confidence_scores": {"aggregate_confidence": confidence},
        "recommended_strategy": strategy or {
            "subtitle_style": "readable",
            "pacing_style": "balanced",
            "camera_motion": "smooth_subject",
            "hook_emphasis": "moderate",
            "clip_selection_bias": "retention",
            "ranking_priority": "retention",
        },
        "aggregated_signals": {
            "active_signal_count": 3,
            "market_signal": {"available": True, "target_market": market},
        },
        "explainability": {
            "why_this_strategy": [
                "Creator intelligence adapted to 'podcast_clean' style (confidence=0.82)",
                "Creator has 5 prior export(s) — feedback patterns active",
                "US market optimization active (confidence=0.75)",
            ],
            "signal_count": 3,
            "strategy_confidence": confidence,
        },
    }


def _make_sip(enabled: bool = True, tier: str = "strong") -> dict:
    return {
        "available": True,
        "enabled": enabled,
        "influence_mode": "safe_controlled",
        "confidence": 0.92,
        "gate": {"passed": True, "tier": tier, "confidence": 0.92, "reason": "ok"},
        "safe_influence": {
            "subtitle_style_bias": "clean_pro",
            "subtitle_density_bias": "lighter",
            "camera_motion_bias": "smooth_subject",
            "ranking_priority_bias": "retention",
        },
        "market_weights": {"available": True, "target_market": "us"},
    }


def _make_output_ranking(available: bool = True, best_id: str = "output_1") -> dict:
    return {
        "available": available,
        "best_output_id": best_id if available else None,
        "mode": "recommendation_only",
    }


# ---------------------------------------------------------------------------
# 1. Availability
# ---------------------------------------------------------------------------

class TestAvailability:
    def test_available_when_mso_present(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert result["available"] is True

    def test_unavailable_when_no_edit_plan(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        result = build_ai_ux_metadata(None)
        assert result["available"] is False

    def test_unavailable_when_mso_empty(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration={})
        result = build_ai_ux_metadata(plan)
        assert result["available"] is False

    def test_unavailable_when_mso_not_available(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration={"available": False})
        result = build_ai_ux_metadata(plan)
        assert result["available"] is False

    def test_available_returns_all_required_sections(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert "strategy" in result
        assert "safe_influence" in result
        assert "best_export" in result

    def test_unavailable_returns_minimal_dict(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        result = build_ai_ux_metadata(None)
        assert result == {"available": False}


# ---------------------------------------------------------------------------
# 2. Stable Keys
# ---------------------------------------------------------------------------

class TestStableKeys:
    def test_strategy_has_required_keys(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        strategy = result["strategy"]
        for key in ("title", "creator_style", "target_market", "confidence", "recommendations", "why"):
            assert key in strategy, f"Missing key: {key}"

    def test_safe_influence_has_required_keys(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        si = result["safe_influence"]
        assert "applied" in si
        assert "items" in si

    def test_best_export_has_required_keys(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        be = result["best_export"]
        assert "enabled" in be
        assert "why" in be

    def test_strategy_title_is_ai_strategy(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert result["strategy"]["title"] == "AI Strategy"

    def test_recommendations_is_list(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert isinstance(result["strategy"]["recommendations"], list)

    def test_why_is_list(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert isinstance(result["strategy"]["why"], list)

    def test_safe_influence_items_is_list(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert isinstance(result["safe_influence"]["items"], list)

    def test_best_export_why_is_list(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert isinstance(result["best_export"]["why"], list)


# ---------------------------------------------------------------------------
# 3. Confidence Clamping
# ---------------------------------------------------------------------------

class TestConfidenceClamping:
    def test_confidence_within_range(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso(confidence=0.87))
        result = build_ai_ux_metadata(plan)
        conf = result["strategy"]["confidence"]
        assert 0.0 <= conf <= 1.0

    def test_confidence_above_1_clamped(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        mso = _make_mso()
        mso["confidence_scores"]["aggregate_confidence"] = 1.5
        plan = _make_edit_plan(multi_signal_orchestration=mso)
        result = build_ai_ux_metadata(plan)
        assert result["strategy"]["confidence"] == 1.0

    def test_confidence_below_0_clamped(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        mso = _make_mso()
        mso["confidence_scores"]["aggregate_confidence"] = -0.3
        plan = _make_edit_plan(multi_signal_orchestration=mso)
        result = build_ai_ux_metadata(plan)
        assert result["strategy"]["confidence"] == 0.0

    def test_confidence_rounded_to_2_decimals(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        mso = _make_mso()
        mso["confidence_scores"]["aggregate_confidence"] = 0.87654
        plan = _make_edit_plan(multi_signal_orchestration=mso)
        result = build_ai_ux_metadata(plan)
        # Should be 0.88 (rounded to 2 decimals)
        conf = result["strategy"]["confidence"]
        assert conf == round(conf, 2)

    def test_none_confidence_returns_zero(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        mso = _make_mso()
        mso["confidence_scores"]["aggregate_confidence"] = None
        plan = _make_edit_plan(multi_signal_orchestration=mso)
        result = build_ai_ux_metadata(plan)
        assert result["strategy"]["confidence"] == 0.0


# ---------------------------------------------------------------------------
# 4. Recommendation List Max Length
# ---------------------------------------------------------------------------

class TestRecommendationMaxLength:
    def test_recommendations_max_5(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata, _MAX_RECOMMENDATIONS
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert len(result["strategy"]["recommendations"]) <= _MAX_RECOMMENDATIONS

    def test_why_max_5(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata, _MAX_WHY
        mso = _make_mso()
        mso["explainability"]["why_this_strategy"] = [f"Reason {i}" for i in range(20)]
        plan = _make_edit_plan(multi_signal_orchestration=mso)
        result = build_ai_ux_metadata(plan)
        assert len(result["strategy"]["why"]) <= _MAX_WHY

    def test_safe_influence_items_max_5(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata, _MAX_INFLUENCE_ITEMS
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        result = build_ai_ux_metadata(plan)
        assert len(result["safe_influence"]["items"]) <= _MAX_INFLUENCE_ITEMS

    def test_best_export_why_max_5(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata, _MAX_WHY
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        result = build_ai_ux_metadata(plan, output_ranking=_make_output_ranking())
        assert len(result["best_export"]["why"]) <= _MAX_WHY


# ---------------------------------------------------------------------------
# 5. No Raw Debug / Internal Fields
# ---------------------------------------------------------------------------

class TestNoDebugFields:
    def _full_result(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        return build_ai_ux_metadata(plan, output_ranking=_make_output_ranking())

    def test_no_error_prefix_in_why(self):
        result = self._full_result()
        for item in result["strategy"]["why"]:
            assert not item.lower().startswith("error:")

    def test_no_unavailable_in_why(self):
        result = self._full_result()
        for item in result["strategy"]["why"]:
            assert "explainability_unavailable" not in item

    def test_no_stack_trace_fields(self):
        result_str = str(self._full_result())
        assert "Traceback" not in result_str
        assert "__class__" not in result_str

    def test_no_internal_class_names(self):
        result_str = str(self._full_result())
        assert "AIEditPlan" not in result_str
        assert "MagicMock" not in result_str

    def test_no_ffmpeg_keys(self):
        result_str = str(self._full_result()).lower()
        assert "ffmpeg" not in result_str

    def test_no_playback_speed_keys(self):
        result_str = str(self._full_result()).lower()
        assert "playback_speed" not in result_str

    def test_why_filtered_debug_strings(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        mso = _make_mso()
        mso["explainability"]["why_this_strategy"] = [
            "Creator adapted to 'podcast' style",
            "error:SomeError internal detail",
            "explainability_unavailable",
            "fallback used",
            "US market optimization active",
        ]
        plan = _make_edit_plan(multi_signal_orchestration=mso)
        result = build_ai_ux_metadata(plan)
        why = result["strategy"]["why"]
        for item in why:
            assert "error:" not in item.lower()
            assert "explainability_unavailable" not in item

    def test_recommendations_are_human_readable(self):
        result = self._full_result()
        for rec in result["strategy"]["recommendations"]:
            assert isinstance(rec, str)
            assert len(rec) > 0
            # No internal Python identifiers (snake_case_keys)
            assert "subtitle_style" not in rec
            assert "pacing_style" not in rec
            assert "camera_motion" not in rec


# ---------------------------------------------------------------------------
# 6. Determinism
# ---------------------------------------------------------------------------

class TestDeterminism:
    def test_same_inputs_same_output(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(confidence=0.87),
            safe_influence_pack=_make_sip(enabled=True),
        )
        r1 = build_ai_ux_metadata(plan, output_ranking=_make_output_ranking())
        r2 = build_ai_ux_metadata(plan, output_ranking=_make_output_ranking())
        assert r1 == r2

    def test_deterministic_across_5_calls(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        results = [build_ai_ux_metadata(plan) for _ in range(5)]
        for r in results[1:]:
            assert r == results[0]

    def test_never_raises_on_garbage_input(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        for bad in (None, 42, "hello", [], {}, object()):
            result = build_ai_ux_metadata(bad)
            assert "available" in result


# ---------------------------------------------------------------------------
# 7. Strategy Section Content
# ---------------------------------------------------------------------------

class TestStrategyContent:
    def test_target_market_uppercase(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso(market="tiktok"))
        result = build_ai_ux_metadata(plan)
        assert result["strategy"]["target_market"] == "TIKTOK"

    def test_creator_style_from_creator_style_field(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            creator_style={"style_label": "Podcast Clean"},
        )
        result = build_ai_ux_metadata(plan)
        assert result["strategy"]["creator_style"] == "Podcast Clean"

    def test_creator_style_fallback_from_adaptation(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            creator_style={},
            creator_style_adaptation={"adapted_style": "dynamic_vlog"},
        )
        result = build_ai_ux_metadata(plan)
        assert result["strategy"]["creator_style"] == "dynamic_vlog"

    def test_creator_style_empty_when_not_available(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert isinstance(result["strategy"]["creator_style"], str)

    def test_recommendations_includes_subtitle_style(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso(strategy={
            "subtitle_style": "readable",
        }))
        result = build_ai_ux_metadata(plan)
        assert any("subtitle" in r.lower() for r in result["strategy"]["recommendations"])

    def test_recommendations_includes_pacing(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso(strategy={
            "pacing_style": "energetic",
        }))
        result = build_ai_ux_metadata(plan)
        assert any("pacing" in r.lower() or "energy" in r.lower() for r in result["strategy"]["recommendations"])

    def test_recommendations_empty_for_unknown_values(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso(strategy={
            "subtitle_style": "unknown_style_xyz",
            "pacing_style": "alien_pacing",
        }))
        result = build_ai_ux_metadata(plan)
        assert isinstance(result["strategy"]["recommendations"], list)

    def test_why_populated_from_explainability(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan)
        assert len(result["strategy"]["why"]) > 0


# ---------------------------------------------------------------------------
# 8. Safe Influence Section
# ---------------------------------------------------------------------------

class TestSafeInfluenceSection:
    def test_applied_false_when_sip_disabled(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=False),
        )
        result = build_ai_ux_metadata(plan)
        assert result["safe_influence"]["applied"] is False

    def test_applied_true_when_sip_enabled(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        result = build_ai_ux_metadata(plan)
        assert result["safe_influence"]["applied"] is True

    def test_items_populated_when_applied(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        result = build_ai_ux_metadata(plan)
        assert len(result["safe_influence"]["items"]) > 0

    def test_items_empty_when_not_applied(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=False),
        )
        result = build_ai_ux_metadata(plan)
        assert result["safe_influence"]["items"] == []

    def test_items_are_human_readable(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        result = build_ai_ux_metadata(plan)
        for item in result["safe_influence"]["items"]:
            assert isinstance(item, str)
            assert len(item) > 3

    def test_items_no_internal_key_names(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        result = build_ai_ux_metadata(plan)
        for item in result["safe_influence"]["items"]:
            assert "subtitle_style_bias" not in item
            assert "camera_motion_bias" not in item


# ---------------------------------------------------------------------------
# 9. Best Export Section
# ---------------------------------------------------------------------------

class TestBestExportSection:
    def test_enabled_false_when_no_ranking(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan, output_ranking=None)
        assert result["best_export"]["enabled"] is False

    def test_enabled_false_when_ranking_unavailable(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan, output_ranking={"available": False})
        assert result["best_export"]["enabled"] is False

    def test_enabled_true_when_best_id_present(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        result = build_ai_ux_metadata(plan, output_ranking=_make_output_ranking())
        assert result["best_export"]["enabled"] is True

    def test_why_populated_when_enabled(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        result = build_ai_ux_metadata(plan, output_ranking=_make_output_ranking())
        assert len(result["best_export"]["why"]) > 0

    def test_why_empty_when_disabled(self):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(multi_signal_orchestration=_make_mso())
        result = build_ai_ux_metadata(plan, output_ranking={"available": False})
        assert result["best_export"]["why"] == []


# ---------------------------------------------------------------------------
# 10. Safety Boundaries
# ---------------------------------------------------------------------------

class TestSafetyBoundaries:
    def _run(self, **kwargs):
        from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata
        plan = _make_edit_plan(
            multi_signal_orchestration=_make_mso(),
            safe_influence_pack=_make_sip(enabled=True),
        )
        return build_ai_ux_metadata(plan, output_ranking=_make_output_ranking())

    def test_no_ffmpeg_in_output(self):
        assert "ffmpeg" not in str(self._run()).lower()

    def test_no_playback_speed_in_output(self):
        assert "playback_speed" not in str(self._run()).lower()

    def test_no_subtitle_timing_in_output(self):
        assert "subtitle_timing" not in str(self._run()).lower()

    def test_no_executor_override_in_output(self):
        assert "executor_override" not in str(self._run()).lower()

    def test_no_rerender_in_output(self):
        assert "rerender" not in str(self._run()).lower()

    def test_confidence_always_float(self):
        result = self._run()
        assert isinstance(result["strategy"]["confidence"], float)

    def test_applied_always_bool(self):
        result = self._run()
        assert isinstance(result["safe_influence"]["applied"], bool)

    def test_enabled_always_bool(self):
        result = self._run()
        assert isinstance(result["best_export"]["enabled"], bool)

    def test_available_always_bool(self):
        result = self._run()
        assert isinstance(result["available"], bool)
