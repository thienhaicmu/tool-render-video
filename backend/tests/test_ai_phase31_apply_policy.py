"""
test_ai_phase31_apply_policy.py — Phase 31: AI Apply Policy Layer Foundation.

Invariants tested:
  - invalid policy falls back to conservative
  - deterministic policy generation
  - conservative policy is safest
  - balanced policy enables safe multivariant execution
  - aggressive policy still preserves hard blocks
  - experimental policy still preserves hard blocks
  - FFmpeg mutation always blocked
  - playback_speed mutation always blocked
  - subtitle timing rewrite always blocked
  - segment reorder always blocked
  - policy metadata attached correctly
  - downstream orchestration respects policy
  - no payload mutation
  - no executor override
  - backward compatibility preserved
  - no API key / GPU / internet required
"""
from __future__ import annotations

import pytest
from dataclasses import dataclass, field
from typing import List
from unittest.mock import MagicMock


# ---------------------------------------------------------------------------
# Helpers / stubs
# ---------------------------------------------------------------------------

@dataclass
class _FakeEditPlan:
    ai_apply_policy: dict = field(default_factory=dict)
    output_ranking: dict = field(default_factory=dict)
    multivariant_execution: dict = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    explainability: dict = field(default_factory=dict)


@dataclass
class _FakeRequest:
    ai_apply_policy: str = "conservative"


_HARD_BLOCKS = {
    "ffmpeg_mutation",
    "playback_speed_mutation",
    "subtitle_timing_rewrite",
    "segment_reorder",
    "executor_override",
    "validation_bypass",
    "autonomous_unlimited_rendering",
}


# ---------------------------------------------------------------------------
# Policy schema tests
# ---------------------------------------------------------------------------

class TestAIApplyPolicySchema:
    def _make(self, **kwargs):
        from app.ai.policy.policy_schema import AIApplyPolicy
        defaults = dict(
            policy_name="conservative",
            allow_safe_mutations=True,
            allow_multivariant_execution=False,
            allow_execution_recommendations=True,
            allow_execution_simulation=True,
            allow_output_ranking=True,
            allow_timing_candidates=False,
            allow_creator_style_adaptation=True,
            allow_visual_rhythm_guidance=True,
            allow_aggressive_behavior=False,
            warnings=[],
            explanation=["test"],
        )
        defaults.update(kwargs)
        return AIApplyPolicy(**defaults)

    def test_to_dict_keys(self):
        p = self._make()
        d = p.to_dict()
        for k in ("policy_name", "allow_safe_mutations", "allow_multivariant_execution",
                  "allow_execution_recommendations", "allow_execution_simulation",
                  "allow_output_ranking", "allow_timing_candidates",
                  "allow_creator_style_adaptation", "allow_visual_rhythm_guidance",
                  "allow_aggressive_behavior", "warnings", "explanation"):
            assert k in d

    def test_warnings_capped_at_10(self):
        p = self._make(warnings=[f"w{i}" for i in range(15)])
        assert len(p.to_dict()["warnings"]) == 10

    def test_explanation_capped_at_10(self):
        p = self._make(explanation=[f"e{i}" for i in range(15)])
        assert len(p.to_dict()["explanation"]) == 10

    def test_bool_coercions(self):
        p = self._make(allow_safe_mutations=1, allow_multivariant_execution=0)
        d = p.to_dict()
        assert d["allow_safe_mutations"] is True
        assert d["allow_multivariant_execution"] is False


class TestAIPolicyDecisionSchema:
    def test_to_dict_keys(self):
        from app.ai.policy.policy_schema import AIPolicyDecision
        d = AIPolicyDecision().to_dict()
        for k in ("available", "selected_policy", "effective_policy",
                  "blocked_capabilities", "warnings"):
            assert k in d

    def test_blocked_capped_at_30(self):
        from app.ai.policy.policy_schema import AIPolicyDecision
        dec = AIPolicyDecision(blocked_capabilities=[f"b{i}" for i in range(40)])
        assert len(dec.to_dict()["blocked_capabilities"]) == 30

    def test_available_bool(self):
        from app.ai.policy.policy_schema import AIPolicyDecision
        dec = AIPolicyDecision(available=1)
        assert dec.to_dict()["available"] is True


# ---------------------------------------------------------------------------
# Policy safety tests
# ---------------------------------------------------------------------------

class TestPolicySafety:
    def test_sanitize_valid_conservative(self):
        from app.ai.policy.policy_safety import sanitize_policy
        assert sanitize_policy("conservative") == "conservative"

    def test_sanitize_valid_balanced(self):
        from app.ai.policy.policy_safety import sanitize_policy
        assert sanitize_policy("balanced") == "balanced"

    def test_sanitize_valid_aggressive(self):
        from app.ai.policy.policy_safety import sanitize_policy
        assert sanitize_policy("aggressive") == "aggressive"

    def test_sanitize_valid_experimental(self):
        from app.ai.policy.policy_safety import sanitize_policy
        assert sanitize_policy("experimental") == "experimental"

    def test_sanitize_invalid_falls_back(self):
        from app.ai.policy.policy_safety import sanitize_policy
        assert sanitize_policy("turbo_mode") == "conservative"
        assert sanitize_policy("") == "conservative"
        assert sanitize_policy("  ") == "conservative"
        assert sanitize_policy(None) == "conservative"
        assert sanitize_policy(42) == "conservative"

    def test_sanitize_case_insensitive(self):
        from app.ai.policy.policy_safety import sanitize_policy
        assert sanitize_policy("BALANCED") == "balanced"
        assert sanitize_policy("Conservative") == "conservative"

    def test_build_policy_conservative(self):
        from app.ai.policy.policy_safety import build_policy
        p = build_policy("conservative")
        assert p.policy_name == "conservative"
        assert p.allow_multivariant_execution is False
        assert p.allow_timing_candidates is False
        assert p.allow_aggressive_behavior is False

    def test_build_policy_balanced(self):
        from app.ai.policy.policy_safety import build_policy
        p = build_policy("balanced")
        assert p.policy_name == "balanced"
        assert p.allow_multivariant_execution is True
        assert p.allow_timing_candidates is False
        assert p.allow_aggressive_behavior is False

    def test_build_policy_aggressive(self):
        from app.ai.policy.policy_safety import build_policy
        p = build_policy("aggressive")
        assert p.policy_name == "aggressive"
        assert p.allow_multivariant_execution is True
        assert p.allow_aggressive_behavior is True
        assert p.allow_timing_candidates is False

    def test_build_policy_experimental(self):
        from app.ai.policy.policy_safety import build_policy
        p = build_policy("experimental")
        assert p.policy_name == "experimental"
        assert p.allow_multivariant_execution is True
        assert p.allow_aggressive_behavior is True
        assert p.allow_timing_candidates is True

    def test_build_policy_invalid_falls_back_to_conservative(self):
        from app.ai.policy.policy_safety import build_policy
        p = build_policy("super_ultra_mode")
        assert p.policy_name == "conservative"

    def test_build_policy_never_raises(self):
        from app.ai.policy.policy_safety import build_policy
        for name in ("conservative", "balanced", "aggressive", "experimental", "", None, 42):
            result = build_policy(name)
            assert result is not None

    def test_get_blocked_conservative(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        p = build_policy("conservative")
        blocked = get_blocked_capabilities(p)
        for hb in _HARD_BLOCKS:
            assert hb in blocked
        assert "multivariant_execution" in blocked
        assert "timing_candidate_apply" in blocked
        assert "aggressive_behavior" in blocked

    def test_get_blocked_balanced_no_multivariant_block(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        p = build_policy("balanced")
        blocked = get_blocked_capabilities(p)
        for hb in _HARD_BLOCKS:
            assert hb in blocked
        assert "multivariant_execution" not in blocked
        assert "timing_candidate_apply" in blocked

    def test_get_blocked_aggressive_no_aggressive_block(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        p = build_policy("aggressive")
        blocked = get_blocked_capabilities(p)
        for hb in _HARD_BLOCKS:
            assert hb in blocked
        assert "multivariant_execution" not in blocked
        assert "aggressive_behavior" not in blocked
        assert "timing_candidate_apply" in blocked

    def test_get_blocked_experimental_allows_timing(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        p = build_policy("experimental")
        blocked = get_blocked_capabilities(p)
        for hb in _HARD_BLOCKS:
            assert hb in blocked
        assert "multivariant_execution" not in blocked
        assert "aggressive_behavior" not in blocked
        assert "timing_candidate_apply" not in blocked

    def test_hard_blocks_always_present_in_all_policies(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            p = build_policy(policy)
            blocked = get_blocked_capabilities(p)
            for hb in _HARD_BLOCKS:
                assert hb in blocked, f"Hard block {hb!r} missing from {policy} policy"

    def test_ffmpeg_always_blocked(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            p = build_policy(policy)
            blocked = get_blocked_capabilities(p)
            assert "ffmpeg_mutation" in blocked

    def test_playback_speed_always_blocked(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            p = build_policy(policy)
            blocked = get_blocked_capabilities(p)
            assert "playback_speed_mutation" in blocked

    def test_subtitle_timing_always_blocked(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            p = build_policy(policy)
            blocked = get_blocked_capabilities(p)
            assert "subtitle_timing_rewrite" in blocked

    def test_segment_reorder_always_blocked(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            p = build_policy(policy)
            blocked = get_blocked_capabilities(p)
            assert "segment_reorder" in blocked

    def test_executor_override_always_blocked(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            p = build_policy(policy)
            blocked = get_blocked_capabilities(p)
            assert "executor_override" in blocked

    def test_validation_bypass_always_blocked(self):
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            p = build_policy(policy)
            blocked = get_blocked_capabilities(p)
            assert "validation_bypass" in blocked

    def test_conservative_is_most_restrictive(self):
        """Conservative should block more capabilities than any other policy."""
        from app.ai.policy.policy_safety import build_policy, get_blocked_capabilities
        conservative_blocked = set(get_blocked_capabilities(build_policy("conservative")))
        for policy in ("balanced", "aggressive", "experimental"):
            other_blocked = set(get_blocked_capabilities(build_policy(policy)))
            assert conservative_blocked >= other_blocked, (
                f"Conservative should block >= {policy}: "
                f"missing {other_blocked - conservative_blocked}"
            )


# ---------------------------------------------------------------------------
# Policy engine tests
# ---------------------------------------------------------------------------

class TestPolicyEngine:
    def test_never_raises_on_none(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, None)
        assert result is not None

    def test_never_raises_on_empty(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(_FakeEditPlan(), None, {})
        assert result is not None

    def test_default_is_conservative(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(_FakeEditPlan(), None, {})
        assert result.selected_policy == "conservative"

    def test_conservative_from_context(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "conservative"})
        assert result.selected_policy == "conservative"

    def test_balanced_from_context(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "balanced"})
        assert result.selected_policy == "balanced"

    def test_aggressive_from_context(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "aggressive"})
        assert result.selected_policy == "aggressive"

    def test_experimental_from_context(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "experimental"})
        assert result.selected_policy == "experimental"

    def test_invalid_falls_back_to_conservative(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "turbo_infinite"})
        assert result.selected_policy == "conservative"

    def test_context_priority_over_payload(self):
        from app.ai.policy.policy_engine import build_policy_decision
        req = _FakeRequest(ai_apply_policy="aggressive")
        result = build_policy_decision(None, req, {"ai_apply_policy": "balanced"})
        assert result.selected_policy == "balanced"

    def test_payload_attribute_used_when_no_context(self):
        from app.ai.policy.policy_engine import build_policy_decision
        req = _FakeRequest(ai_apply_policy="aggressive")
        result = build_policy_decision(None, req, {})
        assert result.selected_policy == "aggressive"

    def test_hard_blocks_in_blocked_capabilities(self):
        from app.ai.policy.policy_engine import build_policy_decision
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            result = build_policy_decision(None, None, {"ai_apply_policy": policy})
            blocked = set(result.blocked_capabilities)
            for hb in _HARD_BLOCKS:
                assert hb in blocked, f"{hb} not blocked in {policy} policy"

    def test_effective_policy_dict_present(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "balanced"})
        assert isinstance(result.effective_policy, dict)
        assert "allow_multivariant_execution" in result.effective_policy

    def test_available_true_on_success(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {})
        assert result.available is True

    def test_deterministic_same_input_same_output(self):
        from app.ai.policy.policy_engine import build_policy_decision
        ctx = {"ai_apply_policy": "balanced"}
        r1 = build_policy_decision(None, None, ctx)
        r2 = build_policy_decision(None, None, ctx)
        assert r1.selected_policy == r2.selected_policy
        assert r1.blocked_capabilities == r2.blocked_capabilities

    def test_no_payload_mutation(self):
        from app.ai.policy.policy_engine import build_policy_decision
        payload = {"some_key": "original_value"}
        original = dict(payload)
        build_policy_decision(None, payload, {})
        assert payload == original

    def test_to_dict_round_trip(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "balanced"})
        d = result.to_dict()
        assert d["selected_policy"] == "balanced"
        assert isinstance(d["blocked_capabilities"], list)
        assert isinstance(d["effective_policy"], dict)

    def test_no_api_key_no_gpu_no_internet(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {})
        assert result is not None


# ---------------------------------------------------------------------------
# edit_plan_schema backward-compat tests
# ---------------------------------------------------------------------------

class TestEditPlanSchemaPhase31:
    def test_ai_apply_policy_field_exists(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        assert hasattr(plan, "ai_apply_policy")
        assert plan.ai_apply_policy == {}

    def test_to_dict_includes_ai_apply_policy(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        assert "ai_apply_policy" in d
        assert d["ai_apply_policy"] == {}

    def test_all_prior_fields_still_present(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        d = plan.to_dict()
        for key in (
            "execution_recommendations", "execution_simulation",
            "safe_render_mutations", "multivariant_render_plans",
            "multivariant_execution", "output_ranking", "ai_apply_policy",
        ):
            assert key in d

    def test_populated_policy_in_to_dict(self):
        from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
        plan = AIEditPlan(
            enabled=True, mode="viral_tiktok", selected_segments=[],
            subtitle=AISubtitlePlan(), camera=AICameraPlan(),
        )
        plan.ai_apply_policy = {
            "available": True,
            "selected_policy": "balanced",
            "effective_policy": {},
            "blocked_capabilities": [],
            "warnings": [],
        }
        d = plan.to_dict()
        assert d["ai_apply_policy"]["selected_policy"] == "balanced"


# ---------------------------------------------------------------------------
# render_influence integration tests
# ---------------------------------------------------------------------------

class TestRenderInfluencePhase31:
    def _make_report(self):
        return {"applied": [], "skipped": [], "warnings": []}

    def _call_report(self, policy_dict: dict):
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        plan = _FakeEditPlan()
        plan.ai_apply_policy = policy_dict
        report = self._make_report()
        ri._report_ai_apply_policy(MagicMock(), plan, report)
        return report

    def test_policy_appears_in_skipped(self):
        report = self._call_report({
            "available": True,
            "selected_policy": "balanced",
            "blocked_capabilities": ["ffmpeg_mutation"],
            "warnings": [],
        })
        assert any("phase31" in s for s in report["skipped"])

    def test_policy_name_in_skipped_message(self):
        report = self._call_report({
            "available": True,
            "selected_policy": "aggressive",
            "blocked_capabilities": [],
        })
        assert any("aggressive" in s for s in report["skipped"])

    def test_policy_not_in_applied(self):
        report = self._call_report({
            "available": True,
            "selected_policy": "experimental",
            "blocked_capabilities": [],
        })
        assert not any("phase31" in a for a in report["applied"])

    def test_empty_dict_skipped(self):
        report = self._call_report({})
        assert any("no_result" in s for s in report["skipped"])

    def test_never_raises_on_none_plan(self):
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        report = self._make_report()
        ri._report_ai_apply_policy(MagicMock(), None, report)

    def test_blocked_count_in_message(self):
        report = self._call_report({
            "available": True,
            "selected_policy": "conservative",
            "blocked_capabilities": ["a", "b", "c", "d"],
        })
        assert any("blocked_count=4" in s for s in report["skipped"])


# ---------------------------------------------------------------------------
# End-to-end integration tests
# ---------------------------------------------------------------------------

class TestPhase31EndToEnd:
    def test_full_conservative_policy(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "conservative"})
        d = result.to_dict()
        assert d["selected_policy"] == "conservative"
        assert d["effective_policy"]["allow_multivariant_execution"] is False
        assert d["effective_policy"]["allow_timing_candidates"] is False
        assert "ffmpeg_mutation" in d["blocked_capabilities"]

    def test_full_balanced_policy(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "balanced"})
        d = result.to_dict()
        assert d["selected_policy"] == "balanced"
        assert d["effective_policy"]["allow_multivariant_execution"] is True
        assert d["effective_policy"]["allow_timing_candidates"] is False
        assert "ffmpeg_mutation" in d["blocked_capabilities"]
        assert "multivariant_execution" not in d["blocked_capabilities"]

    def test_full_aggressive_policy(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "aggressive"})
        d = result.to_dict()
        assert d["selected_policy"] == "aggressive"
        assert d["effective_policy"]["allow_aggressive_behavior"] is True
        assert d["effective_policy"]["allow_timing_candidates"] is False
        assert "ffmpeg_mutation" in d["blocked_capabilities"]
        assert "subtitle_timing_rewrite" in d["blocked_capabilities"]
        assert "segment_reorder" in d["blocked_capabilities"]

    def test_full_experimental_policy(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "experimental"})
        d = result.to_dict()
        assert d["selected_policy"] == "experimental"
        assert d["effective_policy"]["allow_timing_candidates"] is True
        # Hard blocks still present
        assert "ffmpeg_mutation" in d["blocked_capabilities"]
        assert "playback_speed_mutation" in d["blocked_capabilities"]
        assert "executor_override" in d["blocked_capabilities"]
        assert "validation_bypass" in d["blocked_capabilities"]

    def test_policy_attached_to_edit_plan(self):
        from app.ai.policy.policy_engine import build_policy_decision
        ep = _FakeEditPlan()
        result = build_policy_decision(ep, None, {"ai_apply_policy": "balanced"})
        ep.ai_apply_policy = result.to_dict()
        assert ep.ai_apply_policy["selected_policy"] == "balanced"

    def test_influence_pipeline_full(self):
        from app.ai.policy.policy_engine import build_policy_decision
        import importlib
        ri = importlib.import_module("app.ai.director.render_influence")
        ep = _FakeEditPlan()
        result = build_policy_decision(None, None, {"ai_apply_policy": "balanced"})
        ep.ai_apply_policy = result.to_dict()
        report = {"applied": [], "skipped": [], "warnings": []}
        ri._report_ai_apply_policy(MagicMock(), ep, report)
        assert any("balanced" in s for s in report["skipped"])
        assert not report["applied"]

    def test_invalid_policy_in_context_falls_back(self):
        from app.ai.policy.policy_engine import build_policy_decision
        result = build_policy_decision(None, None, {"ai_apply_policy": "super_dangerous"})
        assert result.selected_policy == "conservative"
        assert "ffmpeg_mutation" in result.blocked_capabilities

    def test_all_hard_blocks_in_all_policy_decisions(self):
        from app.ai.policy.policy_engine import build_policy_decision
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            result = build_policy_decision(None, None, {"ai_apply_policy": policy})
            blocked = set(result.blocked_capabilities)
            for hb in _HARD_BLOCKS:
                assert hb in blocked, f"{hb} missing from {policy} decision"

    def test_no_executor_override_in_any_policy(self):
        from app.ai.policy.policy_engine import build_policy_decision
        for policy in ("conservative", "balanced", "aggressive", "experimental"):
            result = build_policy_decision(None, None, {"ai_apply_policy": policy})
            assert "executor_override" in result.blocked_capabilities

    def test_policy_decision_never_raises(self):
        from app.ai.policy.policy_engine import build_policy_decision
        for val in (None, "", "garbage", "aggressive", "experimental", 42, [], {}):
            try:
                ctx = {"ai_apply_policy": val} if val is not None else {}
                result = build_policy_decision(None, None, ctx)
                assert result is not None
            except Exception as e:
                pytest.fail(f"build_policy_decision raised for val={val!r}: {e}")
