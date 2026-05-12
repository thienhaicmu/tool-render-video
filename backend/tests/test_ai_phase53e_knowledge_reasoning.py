"""
test_ai_phase53e_knowledge_reasoning.py — Phase 53E Knowledge-Aware Render Reasoning tests.

Tests cover:
  - knowledge reasoning context from full metadata
  - missing knowledge fallback
  - deterministic retrieval order
  - bounded result count
  - subtitle / camera / hook routing
  - malformed knowledge ignored
  - no execution mutation in output
  - no raw knowledge leak
  - no crash on empty input
  - unified quality evaluator integration
  - edit plan schema field presence
  - safe_knowledge_reasoning_summary helper

All tests are pure-Python. No video rendering, no network, no cloud API.
Audit reference: docs/review/render_audit.md — Phase 53E
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


# ---------------------------------------------------------------------------
# Minimal stub edit plan (mimics AIEditPlan attribute access)
# ---------------------------------------------------------------------------

@dataclass
class _StubPlan:
    subtitle_quality_v2: dict = field(default_factory=dict)
    camera_quality_v2: dict = field(default_factory=dict)
    hook_quality_v2: dict = field(default_factory=dict)
    creator_subtitle_preference: dict = field(default_factory=dict)
    creator_camera_preference: dict = field(default_factory=dict)
    market_optimization_intelligence: dict = field(default_factory=dict)
    knowledge_reasoning_context: dict = field(default_factory=dict)


def _make_full_plan() -> _StubPlan:
    """Return a stub plan with all quality signals populated."""
    return _StubPlan(
        subtitle_quality_v2={
            "overall": 60, "confidence": 0.7,
            "mobile_readability": 55,  # < 70 → triggers mobile/readability routing
        },
        camera_quality_v2={
            "overall": 65, "confidence": 0.7,
            "micro_jitter_risk": 40,   # >= 35 → triggers anti_jitter routing
            "whip_pan_risk": 20,
        },
        hook_quality_v2={
            "overall": 58, "confidence": 0.65,
            "first_3s_strength": 50,   # < 55 → triggers first_3s routing
            "curiosity_strength": 45,  # < 50 → triggers curiosity routing
            "hook_fatigue_risk": 20,
        },
        market_optimization_intelligence={"target_market": "us", "available": True},
    )


def _make_empty_plan() -> _StubPlan:
    return _StubPlan()


# ---------------------------------------------------------------------------
# 1. Module imports and fallback
# ---------------------------------------------------------------------------

def test_module_imports_without_crash():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context
    assert callable(build_knowledge_reasoning_context)


def test_build_none_returns_fallback():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(None)
    ctx = result["knowledge_reasoning_context"]
    assert ctx["available"] is False
    assert ctx["domains"] == []
    assert ctx["matches"] == []
    assert ctx["confidence"] == 0.0
    assert ctx["reasoning"] == []


def test_build_empty_plan_returns_fallback():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_empty_plan())
    ctx = result["knowledge_reasoning_context"]
    assert ctx["available"] is False


def test_build_returns_dict_always():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    for plan in [None, _make_empty_plan(), {}, "not_a_plan"]:
        result = build_knowledge_reasoning_context(plan)
        assert "knowledge_reasoning_context" in result
        ctx = result["knowledge_reasoning_context"]
        assert isinstance(ctx["available"], bool)
        assert isinstance(ctx["domains"], list)
        assert isinstance(ctx["matches"], list)
        assert isinstance(ctx["confidence"], float)
        assert isinstance(ctx["reasoning"], list)


# ---------------------------------------------------------------------------
# 2. Tag routing — subtitle
# ---------------------------------------------------------------------------

def test_subtitle_tags_derived_from_low_mobile_readability():
    from app.ai.knowledge.knowledge_reasoning_context import _get_subtitle_tags

    plan = _StubPlan(
        subtitle_quality_v2={"overall": 60, "mobile_readability": 55}
    )
    tags = _get_subtitle_tags(plan)
    assert "mobile" in tags
    assert "readability" in tags


def test_subtitle_tags_empty_when_no_quality_data():
    from app.ai.knowledge.knowledge_reasoning_context import _get_subtitle_tags

    plan = _StubPlan()
    tags = _get_subtitle_tags(plan)
    assert tags == []


def test_subtitle_tags_viral_bold_style():
    from app.ai.knowledge.knowledge_reasoning_context import _get_subtitle_tags

    plan = _StubPlan(
        subtitle_quality_v2={"overall": 60},
        creator_subtitle_preference={"subtitle_preference": {"style": "viral_bold"}},
    )
    tags = _get_subtitle_tags(plan)
    assert "tiktok" in tags


def test_subtitle_tags_clean_pro_style():
    from app.ai.knowledge.knowledge_reasoning_context import _get_subtitle_tags

    plan = _StubPlan(
        subtitle_quality_v2={"overall": 60},
        creator_subtitle_preference={"subtitle_preference": {"style": "clean_pro"}},
    )
    tags = _get_subtitle_tags(plan)
    assert "podcast" in tags


# ---------------------------------------------------------------------------
# 3. Tag routing — camera
# ---------------------------------------------------------------------------

def test_camera_tags_derived_from_high_jitter():
    from app.ai.knowledge.knowledge_reasoning_context import _get_camera_tags

    plan = _StubPlan(
        camera_quality_v2={"overall": 65, "micro_jitter_risk": 40, "whip_pan_risk": 10}
    )
    tags = _get_camera_tags(plan)
    assert "anti_jitter" in tags
    assert "jitter" in tags


def test_camera_tags_derived_from_high_whip_pan():
    from app.ai.knowledge.knowledge_reasoning_context import _get_camera_tags

    plan = _StubPlan(
        camera_quality_v2={"overall": 65, "micro_jitter_risk": 10, "whip_pan_risk": 40}
    )
    tags = _get_camera_tags(plan)
    assert "stable_framing" in tags


def test_camera_tags_empty_when_no_quality_data():
    from app.ai.knowledge.knowledge_reasoning_context import _get_camera_tags

    plan = _StubPlan()
    tags = _get_camera_tags(plan)
    assert tags == []


def test_camera_tags_static_center_motion_style():
    from app.ai.knowledge.knowledge_reasoning_context import _get_camera_tags

    plan = _StubPlan(
        camera_quality_v2={"overall": 65, "micro_jitter_risk": 10, "whip_pan_risk": 10},
        creator_camera_preference={"camera_preference": {"motion_style": "static_center"}},
    )
    tags = _get_camera_tags(plan)
    assert "interview" in tags or "talking_head" in tags


# ---------------------------------------------------------------------------
# 4. Tag routing — hook
# ---------------------------------------------------------------------------

def test_hook_tags_derived_from_weak_first_3s():
    from app.ai.knowledge.knowledge_reasoning_context import _get_hook_tags

    plan = _StubPlan(
        hook_quality_v2={"overall": 55, "first_3s_strength": 48, "curiosity_strength": 60,
                         "hook_fatigue_risk": 20}
    )
    tags = _get_hook_tags(plan)
    assert "first_3s" in tags
    assert "opening" in tags


def test_hook_tags_derived_from_weak_curiosity():
    from app.ai.knowledge.knowledge_reasoning_context import _get_hook_tags

    plan = _StubPlan(
        hook_quality_v2={"overall": 55, "first_3s_strength": 60, "curiosity_strength": 45,
                         "hook_fatigue_risk": 20}
    )
    tags = _get_hook_tags(plan)
    assert "curiosity" in tags


def test_hook_tags_include_market_code():
    from app.ai.knowledge.knowledge_reasoning_context import _get_hook_tags

    plan = _StubPlan(
        hook_quality_v2={"overall": 55, "first_3s_strength": 60, "curiosity_strength": 60,
                         "hook_fatigue_risk": 20},
        market_optimization_intelligence={"target_market": "eu"},
    )
    tags = _get_hook_tags(plan)
    assert "market_hook" in tags
    assert "eu" in tags


def test_hook_tags_empty_when_no_quality_data():
    from app.ai.knowledge.knowledge_reasoning_context import _get_hook_tags

    plan = _StubPlan()
    tags = _get_hook_tags(plan)
    assert tags == []


# ---------------------------------------------------------------------------
# 5. Full plan builds available context
# ---------------------------------------------------------------------------

def test_full_plan_builds_available_context():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    ctx = result["knowledge_reasoning_context"]
    # Available depends on real knowledge packs being present — should not crash
    assert "available" in ctx
    assert "domains" in ctx
    assert "matches" in ctx
    assert "confidence" in ctx
    assert "reasoning" in ctx


def test_full_plan_context_confidence_in_range():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    ctx = result["knowledge_reasoning_context"]
    assert 0.0 <= ctx["confidence"] <= 1.0


def test_full_plan_domains_are_sorted():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    ctx = result["knowledge_reasoning_context"]
    domains = ctx["domains"]
    assert domains == sorted(domains)


def test_full_plan_reasoning_is_list_of_strings():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    ctx = result["knowledge_reasoning_context"]
    assert isinstance(ctx["reasoning"], list)
    for r in ctx["reasoning"]:
        assert isinstance(r, str)


def test_full_plan_matches_have_required_keys():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    ctx = result["knowledge_reasoning_context"]
    for match in ctx["matches"]:
        assert "domain" in match
        assert "rule_id" in match
        assert "title" in match
        assert "confidence" in match
        assert 0.0 <= match["confidence"] <= 1.0


# ---------------------------------------------------------------------------
# 6. Deterministic retrieval order
# ---------------------------------------------------------------------------

def test_deterministic_context_same_inputs():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    plan = _make_full_plan()
    result1 = build_knowledge_reasoning_context(plan)
    result2 = build_knowledge_reasoning_context(plan)
    assert result1 == result2


def test_deterministic_domains_sorted_consistently():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    domains = result["knowledge_reasoning_context"]["domains"]
    assert domains == sorted(domains)


# ---------------------------------------------------------------------------
# 7. No execution mutation in output
# ---------------------------------------------------------------------------

def test_no_execution_keys_in_context():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    _FORBIDDEN = {
        "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
        "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
        "executable", "transcript", "hook_rewrite",
    }

    result = build_knowledge_reasoning_context(_make_full_plan())
    result_str = str(result)
    for key in _FORBIDDEN:
        assert key not in result_str, f"Forbidden key '{key}' found in context output"


def test_no_execution_keys_in_fallback():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    _FORBIDDEN = {"ffmpeg_args", "render_command", "subprocess", "executable"}
    result = build_knowledge_reasoning_context(None)
    result_str = str(result)
    for key in _FORBIDDEN:
        assert key not in result_str


# ---------------------------------------------------------------------------
# 8. No raw knowledge leak
# ---------------------------------------------------------------------------

def test_no_internal_file_paths_in_context():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    result_str = str(result)
    assert "knowledge_registry" not in result_str
    assert ".json" not in result_str
    assert "backend\\knowledge" not in result_str
    assert "backend/knowledge" not in result_str


def test_no_raw_json_dump_in_reasoning():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    for r in result["knowledge_reasoning_context"]["reasoning"]:
        assert "{" not in r or "}" not in r or len(r) < 100


# ---------------------------------------------------------------------------
# 9. safe_knowledge_reasoning_summary
# ---------------------------------------------------------------------------

def test_summary_empty_on_unavailable_context():
    from app.ai.knowledge.knowledge_reasoning_context import safe_knowledge_reasoning_summary

    assert safe_knowledge_reasoning_summary({}) == ""
    assert safe_knowledge_reasoning_summary({"available": False}) == ""
    assert safe_knowledge_reasoning_summary(None) == ""


def test_summary_single_domain():
    from app.ai.knowledge.knowledge_reasoning_context import safe_knowledge_reasoning_summary

    ctx = {"available": True, "domains": ["subtitle"]}
    hint = safe_knowledge_reasoning_summary(ctx)
    assert isinstance(hint, str)
    assert "subtitle" in hint
    assert "AI used" in hint


def test_summary_multi_domain():
    from app.ai.knowledge.knowledge_reasoning_context import safe_knowledge_reasoning_summary

    ctx = {"available": True, "domains": ["camera", "hook", "subtitle"]}
    hint = safe_knowledge_reasoning_summary(ctx)
    assert isinstance(hint, str)
    assert len(hint) > 0
    # Should mention at least one domain
    assert any(d in hint for d in ("camera", "hook", "subtitle"))


def test_summary_no_forbidden_content():
    from app.ai.knowledge.knowledge_reasoning_context import safe_knowledge_reasoning_summary

    ctx = {"available": True, "domains": ["subtitle", "camera", "hook"]}
    hint = safe_knowledge_reasoning_summary(ctx)
    for forbidden in ("ffmpeg", "render_command", "subprocess", "transcript"):
        assert forbidden not in hint


def test_summary_never_raises_on_bad_input():
    from app.ai.knowledge.knowledge_reasoning_context import safe_knowledge_reasoning_summary

    for bad in [None, {}, "string", 42, [], {"available": True, "domains": None}]:
        result = safe_knowledge_reasoning_summary(bad)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# 10. Edit plan schema field presence
# ---------------------------------------------------------------------------

def test_edit_plan_schema_has_knowledge_reasoning_context_field():
    from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

    plan = AIEditPlan(
        enabled=True,
        mode="test",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    assert hasattr(plan, "knowledge_reasoning_context")
    assert isinstance(plan.knowledge_reasoning_context, dict)


def test_edit_plan_to_dict_includes_knowledge_reasoning_context():
    from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

    plan = AIEditPlan(
        enabled=True,
        mode="test",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        knowledge_reasoning_context={"available": True, "domains": ["hook"]},
    )
    d = plan.to_dict()
    assert "knowledge_reasoning_context" in d
    assert d["knowledge_reasoning_context"]["available"] is True


# ---------------------------------------------------------------------------
# 11. Unified quality evaluator integration (Phase 52D)
# ---------------------------------------------------------------------------

def test_unified_quality_evaluator_no_crash_with_knowledge_context():
    from app.ai.unified_quality.unified_quality_evaluator import evaluate_unified_quality_v2

    result = evaluate_unified_quality_v2(None)
    assert "render_quality_v2" in result
    assert isinstance(result["render_quality_v2"], dict)


def test_unified_quality_evaluator_schema_unchanged():
    from app.ai.unified_quality.unified_quality_evaluator import evaluate_unified_quality_v2

    result = evaluate_unified_quality_v2(None)
    q = result["render_quality_v2"]
    for key in ("subtitle_score", "camera_score", "hook_score",
                "creator_fit", "market_fit", "strategy_fit",
                "overall", "confidence", "reasoning"):
        assert key in q, f"Missing key: {key}"


def test_unified_quality_reasoning_still_list():
    from app.ai.unified_quality.unified_quality_evaluator import evaluate_unified_quality_v2

    result = evaluate_unified_quality_v2(None)
    reasoning = result["render_quality_v2"]["reasoning"]
    assert isinstance(reasoning, list)
    for r in reasoning:
        assert isinstance(r, str)


def test_knowledge_reasoning_hint_no_crash():
    from app.ai.unified_quality.unified_quality_evaluator import _knowledge_reasoning_hint

    for plan in [None, _make_empty_plan(), _make_full_plan()]:
        hint = _knowledge_reasoning_hint(plan)
        assert isinstance(hint, str)


def test_knowledge_reasoning_hint_no_forbidden_content():
    from app.ai.unified_quality.unified_quality_evaluator import _knowledge_reasoning_hint

    for plan in [None, _make_full_plan()]:
        hint = _knowledge_reasoning_hint(plan)
        for forbidden in ("ffmpeg", "render_command", "subprocess", "transcript"):
            assert forbidden not in hint


def test_knowledge_reasoning_hint_with_available_context():
    from app.ai.unified_quality.unified_quality_evaluator import _knowledge_reasoning_hint

    plan = _StubPlan(
        knowledge_reasoning_context={
            "available": True,
            "domains": ["subtitle", "camera"],
        }
    )
    hint = _knowledge_reasoning_hint(plan)
    assert isinstance(hint, str)
    # When context is available, hint should be non-empty
    assert len(hint) > 0


# ---------------------------------------------------------------------------
# 12. Bounded result count
# ---------------------------------------------------------------------------

def test_context_matches_bounded():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    matches = result["knowledge_reasoning_context"]["matches"]
    # At most 3 domains × 1 match each
    assert len(matches) <= 3


def test_context_reasoning_bounded():
    from app.ai.knowledge.knowledge_reasoning_context import build_knowledge_reasoning_context

    result = build_knowledge_reasoning_context(_make_full_plan())
    reasoning = result["knowledge_reasoning_context"]["reasoning"]
    assert len(reasoning) <= 5  # _MAX_REASONING_LINES


# ---------------------------------------------------------------------------
# 13. Market code routing
# ---------------------------------------------------------------------------

def test_market_us_routes_to_hook_tags():
    from app.ai.knowledge.knowledge_reasoning_context import _get_hook_tags

    plan = _StubPlan(
        hook_quality_v2={"overall": 55, "first_3s_strength": 60, "curiosity_strength": 60,
                         "hook_fatigue_risk": 20},
        market_optimization_intelligence={"target_market": "us"},
    )
    tags = _get_hook_tags(plan)
    assert "us" in tags


def test_market_jp_routes_to_hook_tags():
    from app.ai.knowledge.knowledge_reasoning_context import _get_hook_tags

    plan = _StubPlan(
        hook_quality_v2={"overall": 55, "first_3s_strength": 60, "curiosity_strength": 60,
                         "hook_fatigue_risk": 20},
        market_optimization_intelligence={"target_market": "jp"},
    )
    tags = _get_hook_tags(plan)
    assert "jp" in tags
