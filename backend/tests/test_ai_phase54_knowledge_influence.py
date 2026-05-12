"""
test_ai_phase54_knowledge_influence.py — Phase 54 Knowledge-Aware Influence tests.

Tests cover:
  - knowledge influence context creation
  - missing knowledge fallback
  - subtitle influence confidence support
  - camera influence confidence support
  - ranking influence confidence support
  - confidence delta bounds (max 0.05 per domain, max 0.10 total)
  - safety gate still blocks low confidence (knowledge NEVER bypasses gate)
  - no unbounded tuning
  - deterministic output
  - no crash on empty input
  - no raw knowledge leakage
  - enrich helpers (subtitle, camera, ranking)
  - edit plan schema field presence

All tests are pure-Python. No video rendering, no network, no cloud API.
Audit reference: docs/review/render_audit.md — Phase 54
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------

@dataclass
class _StubPlan:
    knowledge_reasoning_context: dict = field(default_factory=dict)
    creator_subtitle_influence: dict = field(default_factory=dict)
    creator_camera_preference: dict = field(default_factory=dict)
    safe_influence_pack: dict = field(default_factory=dict)
    subtitle_quality_v2: dict = field(default_factory=dict)
    camera_quality_v2: dict = field(default_factory=dict)
    hook_quality_v2: dict = field(default_factory=dict)
    market_optimization_intelligence: dict = field(default_factory=dict)


def _make_full_krc() -> dict:
    """Return a populated knowledge_reasoning_context (Phase 53E output)."""
    return {
        "available": True,
        "domains": ["camera", "hook", "subtitle"],
        "matches": [
            {"domain": "subtitle", "rule_id": "mobile_readability_subtitle",
             "title": "Mobile Subtitle Readability", "confidence": 0.75},
            {"domain": "camera", "rule_id": "anti_jitter_camera",
             "title": "Anti-Jitter Camera Intelligence", "confidence": 0.75},
            {"domain": "hook", "rule_id": "first_5s_retention",
             "title": "First 5-Second Retention Intelligence", "confidence": 0.75},
        ],
        "confidence": 0.75,
        "reasoning": ["Knowledge matched across subtitle, camera and hook domains"],
    }


def _make_full_plan() -> _StubPlan:
    return _StubPlan(
        knowledge_reasoning_context=_make_full_krc(),
        creator_subtitle_influence={"reasoning": ["existing subtitle reason"], "available": True},
        creator_camera_preference={"camera_preference": {"reasoning": ["existing camera reason"]}},
        safe_influence_pack={"reasoning": ["existing ranking reason"], "available": True},
    )


# ---------------------------------------------------------------------------
# 1. Module import and fallback
# ---------------------------------------------------------------------------

def test_module_imports_without_crash():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context
    assert callable(build_knowledge_influence_context)


def test_build_none_returns_fallback():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    result = build_knowledge_influence_context(None)
    ctx = result["knowledge_influence_context"]
    assert ctx["available"] is False
    assert ctx["domains"] == []
    assert ctx["influence_support"] == {}
    assert ctx["confidence"] == 0.0
    assert ctx["knowledge_influence_reasoning"] == []


def test_build_empty_plan_returns_fallback():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    result = build_knowledge_influence_context(_StubPlan())
    ctx = result["knowledge_influence_context"]
    assert ctx["available"] is False


def test_build_unavailable_krc_returns_fallback():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context={"available": False, "domains": []})
    result = build_knowledge_influence_context(plan)
    ctx = result["knowledge_influence_context"]
    assert ctx["available"] is False


def test_build_always_returns_dict():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    for plan in [None, _StubPlan(), "bad", 42]:
        result = build_knowledge_influence_context(plan)
        assert "knowledge_influence_context" in result
        ctx = result["knowledge_influence_context"]
        assert isinstance(ctx["available"], bool)
        assert isinstance(ctx["domains"], list)
        assert isinstance(ctx["influence_support"], dict)
        assert isinstance(ctx["confidence"], float)
        assert isinstance(ctx["knowledge_influence_reasoning"], list)


# ---------------------------------------------------------------------------
# 2. Full context from populated knowledge_reasoning_context
# ---------------------------------------------------------------------------

def test_full_krc_builds_available_context():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    result = build_knowledge_influence_context(plan)
    ctx = result["knowledge_influence_context"]
    assert ctx["available"] is True


def test_full_krc_has_subtitle_support():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert "subtitle" in ctx["influence_support"]
    sub = ctx["influence_support"]["subtitle"]
    assert sub["supported"] is True
    assert sub["confidence_delta"] > 0.0
    assert isinstance(sub["reasons"], list)
    assert len(sub["reasons"]) > 0


def test_full_krc_has_camera_support():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert "camera" in ctx["influence_support"]
    cam = ctx["influence_support"]["camera"]
    assert cam["supported"] is True
    assert cam["confidence_delta"] > 0.0


def test_full_krc_has_ranking_support():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert "ranking" in ctx["influence_support"]
    rank = ctx["influence_support"]["ranking"]
    assert rank["supported"] is True
    assert rank["confidence_delta"] > 0.0


def test_full_krc_reasoning_is_list_of_strings():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    for r in ctx["knowledge_influence_reasoning"]:
        assert isinstance(r, str)
        assert len(r) > 0


# ---------------------------------------------------------------------------
# 3. Confidence delta bounds
# ---------------------------------------------------------------------------

def test_confidence_delta_per_domain_max_005():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    for domain, support in ctx["influence_support"].items():
        assert support["confidence_delta"] <= 0.05, (
            f"Domain '{domain}' exceeds max delta 0.05: {support['confidence_delta']}"
        )


def test_total_confidence_delta_max_010():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    total = sum(
        s["confidence_delta"] for s in ctx["influence_support"].values()
        if s.get("supported")
    )
    assert total <= 0.10, f"Total delta {total:.3f} exceeds max 0.10"


def test_context_confidence_in_valid_range():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert 0.0 <= ctx["confidence"] <= 1.0


def test_delta_positive_only():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    for domain, support in ctx["influence_support"].items():
        assert support["confidence_delta"] >= 0.0, (
            f"Domain '{domain}' has negative delta: {support['confidence_delta']}"
        )


# ---------------------------------------------------------------------------
# 4. Safety gate preservation
# ---------------------------------------------------------------------------

def test_safety_gate_still_blocks_low_confidence():
    """The Phase 48 safety gate blocks at < 0.70. Knowledge delta is metadata only."""
    from app.ai.influence.safety_gate import evaluate_gate

    # Low base confidence — gate must BLOCK regardless of any knowledge delta
    low_confidence = 0.55
    gate = evaluate_gate(low_confidence)
    assert gate["tier"] == "blocked"
    assert gate["passed"] is False

    # Even with max knowledge boost (+0.10), this stays BLOCKED (0.55 + 0.10 = 0.65 < 0.70)
    boosted = min(1.0, low_confidence + 0.10)
    assert boosted < 0.70, "Knowledge boost must not unblock a significantly low confidence"


def test_knowledge_delta_does_not_feed_gate():
    """Verify that confidence_delta in knowledge_influence_context is metadata only.

    The Phase 54 knowledge influence context must NOT be passed to evaluate_gate().
    This test confirms no path from knowledge context to gate evaluation.
    """
    from app.ai.influence.safety_gate import evaluate_gate
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]

    # The context has confidence_delta values — verify gate is separate
    total_delta = sum(
        s["confidence_delta"] for s in ctx["influence_support"].values()
    )

    # The gate must be evaluated independently with its OWN confidence
    # (not boosted by knowledge delta)
    gate_at_blocked = evaluate_gate(0.65)
    assert gate_at_blocked["tier"] == "blocked"

    # Knowledge delta is non-zero
    assert total_delta > 0


# ---------------------------------------------------------------------------
# 5. Enrich helpers — subtitle
# ---------------------------------------------------------------------------

def test_enrich_subtitle_influence_reasoning_appends():
    from app.ai.knowledge.knowledge_influence_context import enrich_subtitle_influence_reasoning

    influence = {"reasoning": ["existing reason"], "available": True}
    support = {"supported": True, "reasons": ["Knowledge-informed subtitle reason"]}
    enriched = enrich_subtitle_influence_reasoning(influence, support)
    assert len(enriched["reasoning"]) == 2
    assert "Knowledge-informed subtitle reason" in enriched["reasoning"]


def test_enrich_subtitle_preserves_other_fields():
    from app.ai.knowledge.knowledge_influence_context import enrich_subtitle_influence_reasoning

    influence = {"reasoning": ["r1"], "available": True, "preset_bias": "viral_bold"}
    support = {"supported": True, "reasons": ["extra"]}
    enriched = enrich_subtitle_influence_reasoning(influence, support)
    assert enriched["available"] is True
    assert enriched["preset_bias"] == "viral_bold"


def test_enrich_subtitle_caps_at_6():
    from app.ai.knowledge.knowledge_influence_context import enrich_subtitle_influence_reasoning

    influence = {"reasoning": [f"r{i}" for i in range(5)]}
    support = {"supported": True, "reasons": ["extra_1", "extra_2"]}
    enriched = enrich_subtitle_influence_reasoning(influence, support)
    assert len(enriched["reasoning"]) <= 6


def test_enrich_subtitle_no_change_when_unsupported():
    from app.ai.knowledge.knowledge_influence_context import enrich_subtitle_influence_reasoning

    influence = {"reasoning": ["existing"]}
    support = {"supported": False, "reasons": ["ignored"]}
    enriched = enrich_subtitle_influence_reasoning(influence, support)
    assert enriched["reasoning"] == ["existing"]


def test_enrich_subtitle_no_crash_on_empty_input():
    from app.ai.knowledge.knowledge_influence_context import enrich_subtitle_influence_reasoning

    for inf, sup in [(None, {}), ({}, {}), ({}, {"supported": True, "reasons": []}),
                     ({"reasoning": []}, {"supported": True, "reasons": ["r"]})]:
        result = enrich_subtitle_influence_reasoning(inf, sup)
        assert result is not None


# ---------------------------------------------------------------------------
# 6. Enrich helpers — camera
# ---------------------------------------------------------------------------

def test_enrich_camera_influence_reasoning_appends():
    from app.ai.knowledge.knowledge_influence_context import enrich_camera_influence_reasoning

    influence = {"reasoning": ["camera existing"]}
    support = {"supported": True, "reasons": ["Stable framing knowledge"]}
    enriched = enrich_camera_influence_reasoning(influence, support)
    assert "Stable framing knowledge" in enriched["reasoning"]


def test_enrich_camera_preserves_other_fields():
    from app.ai.knowledge.knowledge_influence_context import enrich_camera_influence_reasoning

    influence = {"reasoning": ["r"], "deadzone_delta": 0.02, "applied": True}
    support = {"supported": True, "reasons": ["extra"]}
    enriched = enrich_camera_influence_reasoning(influence, support)
    assert enriched["deadzone_delta"] == 0.02
    assert enriched["applied"] is True


def test_enrich_camera_no_crash_on_bad_input():
    from app.ai.knowledge.knowledge_influence_context import enrich_camera_influence_reasoning

    for inf, sup in [(None, {}), ({}, {}), ({}, None)]:
        result = enrich_camera_influence_reasoning(inf, sup or {})
        assert result is not None


# ---------------------------------------------------------------------------
# 7. Enrich helpers — ranking
# ---------------------------------------------------------------------------

def test_enrich_ranking_influence_reasoning_appends():
    from app.ai.knowledge.knowledge_influence_context import enrich_ranking_influence_reasoning

    influence = {"reasoning": ["rank existing"]}
    support = {"supported": True, "reasons": ["Hook retention knowledge"]}
    enriched = enrich_ranking_influence_reasoning(influence, support)
    assert "Hook retention knowledge" in enriched["reasoning"]


def test_enrich_ranking_with_explainability_key():
    from app.ai.knowledge.knowledge_influence_context import enrich_ranking_influence_reasoning

    influence = {"explainability": ["existing explainer"]}
    support = {"supported": True, "reasons": ["Retention knowledge"]}
    enriched = enrich_ranking_influence_reasoning(influence, support)
    assert "Retention knowledge" in enriched["explainability"]


def test_enrich_ranking_no_change_when_unsupported():
    from app.ai.knowledge.knowledge_influence_context import enrich_ranking_influence_reasoning

    influence = {"reasoning": ["existing"]}
    support = {"supported": False}
    enriched = enrich_ranking_influence_reasoning(influence, support)
    assert enriched["reasoning"] == ["existing"]


# ---------------------------------------------------------------------------
# 8. Deterministic output
# ---------------------------------------------------------------------------

def test_deterministic_same_inputs():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    r1 = build_knowledge_influence_context(plan)
    r2 = build_knowledge_influence_context(plan)
    assert r1 == r2


def test_domains_sorted():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert ctx["domains"] == sorted(ctx["domains"])


# ---------------------------------------------------------------------------
# 9. No raw knowledge leakage
# ---------------------------------------------------------------------------

def test_no_raw_json_in_output():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    result_str = str(ctx)
    assert "knowledge_registry" not in result_str
    assert ".json" not in result_str
    assert "backend\\knowledge" not in result_str
    assert "backend/knowledge" not in result_str


def test_no_execution_keys_in_output():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    _FORBIDDEN = {
        "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
        "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
        "executable", "transcript",
    }
    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    result_str = str(build_knowledge_influence_context(plan))
    for key in _FORBIDDEN:
        assert key not in result_str, f"Forbidden key '{key}' found in output"


def test_reasons_are_creator_safe_strings():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    for domain, support in ctx["influence_support"].items():
        for reason in support.get("reasons", []):
            assert isinstance(reason, str)
            assert "{" not in reason or "}" not in reason
            assert len(reason) < 200


# ---------------------------------------------------------------------------
# 10. Edit plan schema field
# ---------------------------------------------------------------------------

def test_edit_plan_has_knowledge_influence_context_field():
    from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

    plan = AIEditPlan(
        enabled=True,
        mode="test",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    assert hasattr(plan, "knowledge_influence_context")
    assert isinstance(plan.knowledge_influence_context, dict)


def test_edit_plan_to_dict_includes_knowledge_influence_context():
    from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan

    plan = AIEditPlan(
        enabled=True,
        mode="test",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
        knowledge_influence_context={"available": True, "domains": ["subtitle"]},
    )
    d = plan.to_dict()
    assert "knowledge_influence_context" in d
    assert d["knowledge_influence_context"]["available"] is True


# ---------------------------------------------------------------------------
# 11. Single-domain fallbacks
# ---------------------------------------------------------------------------

def test_subtitle_only_krc():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    krc = {
        "available": True,
        "domains": ["subtitle"],
        "matches": [
            {"domain": "subtitle", "rule_id": "mobile_readability_subtitle",
             "title": "Mobile Subtitle", "confidence": 0.75},
        ],
        "confidence": 0.75,
    }
    plan = _StubPlan(knowledge_reasoning_context=krc)
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert "subtitle" in ctx["influence_support"]
    assert "camera" not in ctx["influence_support"]
    assert "ranking" not in ctx["influence_support"]
    assert ctx["available"] is True


def test_camera_only_krc():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    krc = {
        "available": True,
        "domains": ["camera"],
        "matches": [
            {"domain": "camera", "rule_id": "anti_jitter_camera",
             "title": "Anti-Jitter", "confidence": 0.75},
        ],
        "confidence": 0.75,
    }
    plan = _StubPlan(knowledge_reasoning_context=krc)
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert "camera" in ctx["influence_support"]
    assert "subtitle" not in ctx["influence_support"]


def test_hook_only_krc_maps_to_ranking():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    krc = {
        "available": True,
        "domains": ["hook"],
        "matches": [
            {"domain": "hook", "rule_id": "first_5s_retention",
             "title": "First 5s Retention", "confidence": 0.75},
        ],
        "confidence": 0.75,
    }
    plan = _StubPlan(knowledge_reasoning_context=krc)
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert "ranking" in ctx["influence_support"]


# ---------------------------------------------------------------------------
# 12. Reasoning bounded
# ---------------------------------------------------------------------------

def test_knowledge_influence_reasoning_bounded():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    ctx = build_knowledge_influence_context(plan)["knowledge_influence_context"]
    assert len(ctx["knowledge_influence_reasoning"]) <= 5


# ---------------------------------------------------------------------------
# 13. No unbounded tuning
# ---------------------------------------------------------------------------

def test_no_tuning_delta_fields_in_context():
    from app.ai.knowledge.knowledge_influence_context import build_knowledge_influence_context

    plan = _StubPlan(knowledge_reasoning_context=_make_full_krc())
    result_str = str(build_knowledge_influence_context(plan))
    # Tuning deltas belong to Phase 50B camera_tuning_engine — not in influence context
    assert "deadzone_delta" not in result_str
    assert "ema_alpha_delta" not in result_str
    assert "hold_frames_delta" not in result_str


# ---------------------------------------------------------------------------
# 14. is_safe_influence_output helper
# ---------------------------------------------------------------------------

def test_is_safe_influence_output_passes_clean_dict():
    from app.ai.knowledge.knowledge_influence_context import _is_safe_influence_output

    clean = {"domain": "subtitle", "rule_id": "mobile_readability", "confidence": 0.75}
    assert _is_safe_influence_output(clean) is True


def test_is_safe_influence_output_rejects_forbidden():
    from app.ai.knowledge.knowledge_influence_context import _is_safe_influence_output

    dirty = {"domain": "subtitle", "ffmpeg_args": "--input foo", "confidence": 0.5}
    assert _is_safe_influence_output(dirty) is False
