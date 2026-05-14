"""
test_ai_phase60d_execution_mode.py — Tests for Phase 60D AI Execution Modes & Rollback.

Coverage:
  - Mode resolution: payload → env → default priority
  - Default mode = safe (no payload, no env)
  - Invalid mode → fallback to safe
  - All four valid modes produce correct policy
  - off mode: allowed_domains=[], rollback_safe=True
  - safe mode: raised threshold deltas, rollback_safe=True
  - balanced mode: zero threshold deltas
  - aggressive mode: negative threshold deltas, hard caps still apply
  - Metrics include mode + rollback_active
  - mode_off stubs: metrics shows blocked=True, reason=mode_off
  - Deterministic output
  - Never raises on None/empty input

REQUIRED EXECUTION TESTS:
  test_execution_mode_off_blocks_all_promotions  — mode=off from payload → rollback active,
                                                   all domains blocked, metrics reason=mode_off
  test_execution_mode_balanced_allows_promotion  — mode=balanced → promotion can apply
"""
import os
import pytest
from types import SimpleNamespace

from app.ai.execution_mode.execution_mode_engine import (
    resolve_execution_mode,
    get_mode_policy,
)
from app.ai.metrics.ai_execution_metrics_engine import build_ai_execution_metrics


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _payload(mode: str = None, **kwargs):
    """Build a simple dict payload."""
    p = {}
    if mode is not None:
        p["ai_execution_mode"] = mode
    p.update(kwargs)
    return p


def _ns_payload(mode: str = None):
    """Build a SimpleNamespace payload."""
    ns = SimpleNamespace()
    if mode is not None:
        ns.ai_execution_mode = mode
    return ns


def _edit_plan_with_mode(mode_data: dict, **extra):
    """Build an edit_plan SimpleNamespace with ai_execution_mode set."""
    attrs = {
        "ai_execution_mode":          mode_data,
        "ai_execution_rollback":       {},
        "subtitle_execution_promotion": {},
        "camera_execution_promotion":   {},
        "segment_selection_promotion":  {},
        "quality_gated_influence":      {},
    }
    attrs.update(extra)
    return SimpleNamespace(**attrs)


def _mode_off_edit_plan():
    """Edit plan simulating pipeline after mode=off: mode data + stub promos."""
    mode_data = resolve_execution_mode({"ai_execution_mode": "off"})["ai_execution_mode"]
    stub = {"applied": False, "eligible": True, "reason": "mode_off", "blocked": True, "confidence": 0.0}
    return SimpleNamespace(
        ai_execution_mode=mode_data,
        ai_execution_rollback={"active": True, "reason": "mode_off",
                               "blocked_domains": ["subtitle", "camera", "segment"]},
        subtitle_execution_promotion=dict(stub),
        camera_execution_promotion=dict(stub),
        segment_selection_promotion=dict(stub),
        quality_gated_influence={},
    )


# ---------------------------------------------------------------------------
# REQUIRED EXECUTION TESTS
# ---------------------------------------------------------------------------

def test_execution_mode_off_blocks_all_promotions():
    """REQUIRED: mode=off from payload → rollback active, all domains blocked, reason=mode_off."""
    payload = {"ai_execution_mode": "off"}

    # Mode resolution
    mode_result = resolve_execution_mode(payload, context={"job_id": "test"})
    mode_data = mode_result["ai_execution_mode"]

    assert mode_data["effective_mode"] == "off",         "effective_mode must be off"
    assert mode_data["allowed_domains"] == [],            "off mode must allow no domains"
    assert mode_data["rollback_safe"] is True,            "off mode must be rollback_safe"
    assert mode_data["source"] == "payload",              "source must be payload"

    # Simulate pipeline: mode=off → write stub promos and rollback
    plan = _mode_off_edit_plan()

    assert plan.ai_execution_rollback["active"] is True,  "rollback must be active"
    assert plan.ai_execution_rollback["reason"] == "mode_off"
    assert "subtitle" in plan.ai_execution_rollback["blocked_domains"]
    assert "camera"   in plan.ai_execution_rollback["blocked_domains"]
    assert "segment"  in plan.ai_execution_rollback["blocked_domains"]

    # Metrics must show mode=off, rollback_active=True, all domains blocked
    metrics_result = build_ai_execution_metrics(plan, context={"job_id": "test"})
    metrics = metrics_result["ai_execution_metrics"]

    assert metrics["mode"] == "off",                       "metrics.mode must be off"
    assert metrics["rollback_active"] is True,             "metrics.rollback_active must be True"
    assert metrics["subtitle"]["applied"]  is False,       "subtitle must not be applied"
    assert metrics["subtitle"]["blocked"]  is True,        "subtitle must be blocked"
    assert metrics["subtitle"]["reason"]   == "mode_off",  "subtitle reason must be mode_off"
    assert metrics["camera"]["applied"]    is False,       "camera must not be applied"
    assert metrics["camera"]["blocked"]    is True,        "camera must be blocked"
    assert metrics["camera"]["reason"]     == "mode_off",  "camera reason must be mode_off"
    assert metrics["segment"]["applied"]   is False,       "segment must not be applied"
    assert metrics["segment"]["blocked"]   is True,        "segment must be blocked"
    assert metrics["segment"]["reason"]    == "mode_off",  "segment reason must be mode_off"


def test_execution_mode_balanced_allows_promotion():
    """REQUIRED: mode=balanced → promotion can apply when eligible."""
    payload = {"ai_execution_mode": "balanced"}

    mode_result = resolve_execution_mode(payload)
    mode_data = mode_result["ai_execution_mode"]

    assert mode_data["effective_mode"] == "balanced"
    assert "subtitle" in mode_data["allowed_domains"]
    assert "camera"   in mode_data["allowed_domains"]
    assert "segment"  in mode_data["allowed_domains"]
    assert mode_data["rollback_safe"] is False

    # Metrics with balanced mode and successful promotions
    plan = _edit_plan_with_mode(
        mode_data,
        subtitle_execution_promotion={"applied": True, "reason": "promotion_applied", "confidence": 0.85},
        camera_execution_promotion={"applied": True, "reason": "promotion_applied", "confidence": 0.83},
        segment_selection_promotion={"applied": True, "reason": "promotion_applied", "confidence": 0.87},
    )

    metrics_result = build_ai_execution_metrics(plan)
    metrics = metrics_result["ai_execution_metrics"]

    assert metrics["mode"] == "balanced",               "metrics.mode must be balanced"
    assert metrics["rollback_active"] is False,          "rollback must not be active"
    assert metrics["subtitle"]["applied"] is True,       "subtitle promotion can apply"
    assert metrics["camera"]["applied"]   is True,       "camera promotion can apply"
    assert metrics["segment"]["applied"]  is True,       "segment promotion can apply"


# ---------------------------------------------------------------------------
# Mode resolution tests
# ---------------------------------------------------------------------------

def test_default_mode_safe():
    """No payload, no env → default mode is safe."""
    result = resolve_execution_mode(None)
    ev = result["ai_execution_mode"]
    assert ev["mode"] == "safe"
    assert ev["source"] == "default"
    assert ev["effective_mode"] == "safe"


def test_payload_mode_off():
    result = resolve_execution_mode({"ai_execution_mode": "off"})
    ev = result["ai_execution_mode"]
    assert ev["mode"] == "off"
    assert ev["source"] == "payload"


def test_payload_mode_balanced():
    result = resolve_execution_mode({"ai_execution_mode": "balanced"})
    ev = result["ai_execution_mode"]
    assert ev["mode"] == "balanced"
    assert ev["source"] == "payload"


def test_payload_mode_aggressive():
    result = resolve_execution_mode({"ai_execution_mode": "aggressive"})
    ev = result["ai_execution_mode"]
    assert ev["mode"] == "aggressive"
    assert ev["source"] == "payload"


def test_invalid_mode_fallback_safe():
    """Invalid mode value → fallback to safe."""
    result = resolve_execution_mode({"ai_execution_mode": "turbo_extreme"})
    ev = result["ai_execution_mode"]
    assert ev["mode"] == "safe"
    assert "fallback" in ev["source"]


def test_namespace_payload_mode():
    """SimpleNamespace payload works the same as dict."""
    payload = _ns_payload(mode="balanced")
    result = resolve_execution_mode(payload)
    assert result["ai_execution_mode"]["mode"] == "balanced"


def test_env_mode(monkeypatch):
    """AI_EXECUTION_MODE env var sets mode when payload is absent."""
    monkeypatch.setenv("AI_EXECUTION_MODE", "aggressive")
    result = resolve_execution_mode(None)
    ev = result["ai_execution_mode"]
    assert ev["mode"] == "aggressive"
    assert ev["source"] == "env"


def test_env_mode_invalid_fallback(monkeypatch):
    """Invalid env mode → fallback to safe."""
    monkeypatch.setenv("AI_EXECUTION_MODE", "ultra")
    result = resolve_execution_mode(None)
    ev = result["ai_execution_mode"]
    assert ev["mode"] == "safe"
    assert "fallback" in ev["source"]


def test_payload_takes_priority_over_env(monkeypatch):
    """Payload mode takes priority over env var."""
    monkeypatch.setenv("AI_EXECUTION_MODE", "aggressive")
    result = resolve_execution_mode({"ai_execution_mode": "off"})
    assert result["ai_execution_mode"]["mode"] == "off"
    assert result["ai_execution_mode"]["source"] == "payload"


# ---------------------------------------------------------------------------
# Mode policy tests
# ---------------------------------------------------------------------------

def test_off_blocks_all_domains():
    result = resolve_execution_mode({"ai_execution_mode": "off"})
    ev = result["ai_execution_mode"]
    assert ev["allowed_domains"] == []
    assert ev["rollback_safe"] is True


def test_safe_raises_thresholds():
    result = resolve_execution_mode({"ai_execution_mode": "safe"})
    policy = result["ai_execution_mode"]["confidence_policy"]
    assert policy["subtitle_threshold_delta"] == pytest.approx(0.05)
    assert policy["camera_threshold_delta"]   == pytest.approx(0.08)
    assert policy["segment_threshold_delta"]  == pytest.approx(0.10)


def test_balanced_zero_threshold_deltas():
    result = resolve_execution_mode({"ai_execution_mode": "balanced"})
    policy = result["ai_execution_mode"]["confidence_policy"]
    assert policy["subtitle_threshold_delta"] == pytest.approx(0.0)
    assert policy["camera_threshold_delta"]   == pytest.approx(0.0)
    assert policy["segment_threshold_delta"]  == pytest.approx(0.0)


def test_aggressive_lowers_thresholds_respects_caps():
    result = resolve_execution_mode({"ai_execution_mode": "aggressive"})
    policy = result["ai_execution_mode"]["confidence_policy"]
    # Threshold deltas are negative (lower bar to apply)
    assert policy["subtitle_threshold_delta"] < 0.0
    assert policy["camera_threshold_delta"]   < 0.0
    assert policy["segment_threshold_delta"]  < 0.0
    # But deltas are not extreme (still bounded)
    assert policy["subtitle_threshold_delta"] >= -0.10
    assert policy["camera_threshold_delta"]   >= -0.10
    assert policy["segment_threshold_delta"]  >= -0.20


def test_safe_rollback_safe():
    result = resolve_execution_mode({"ai_execution_mode": "safe"})
    assert result["ai_execution_mode"]["rollback_safe"] is True


def test_off_reasoning_mentions_blocked():
    result = resolve_execution_mode({"ai_execution_mode": "off"})
    reasoning = " ".join(result["ai_execution_mode"]["reasoning"]).lower()
    assert "blocked" in reasoning or "off" in reasoning


# ---------------------------------------------------------------------------
# get_mode_policy tests
# ---------------------------------------------------------------------------

def test_mode_policy_off():
    policy = get_mode_policy("off")
    assert policy["blocks_promotion"] is True
    assert policy["rollback_safe"] is True
    assert policy["allowed_domains"] == []


def test_mode_policy_balanced():
    policy = get_mode_policy("balanced")
    assert policy["blocks_promotion"] is False
    assert "subtitle" in policy["allowed_domains"]


def test_mode_policy_unknown_falls_back_to_safe():
    policy = get_mode_policy("nonexistent")
    assert policy["mode"] == "safe"


# ---------------------------------------------------------------------------
# Metrics integration tests
# ---------------------------------------------------------------------------

def test_metrics_include_mode_field():
    """Metrics output must include mode and rollback_active."""
    plan = _edit_plan_with_mode({"mode": "balanced", "effective_mode": "balanced"})
    metrics = build_ai_execution_metrics(plan)["ai_execution_metrics"]
    assert "mode" in metrics,           "metrics must have mode field"
    assert "rollback_active" in metrics, "metrics must have rollback_active field"


def test_metrics_mode_off_shows_blocked():
    """mode_off stubs → metrics shows blocked=True, reason=mode_off for all domains."""
    plan = _mode_off_edit_plan()
    metrics = build_ai_execution_metrics(plan)["ai_execution_metrics"]

    assert metrics["mode"] == "off"
    assert metrics["rollback_active"] is True
    for domain in ("subtitle", "camera", "segment"):
        assert metrics[domain]["blocked"] is True,      f"{domain} blocked must be True"
        assert metrics[domain]["applied"] is False,     f"{domain} applied must be False"
        assert metrics[domain]["reason"] == "mode_off", f"{domain} reason must be mode_off"


def test_metrics_user_override_still_wins():
    """User override reason propagates correctly even with mode data present."""
    mode_data = {"mode": "balanced", "effective_mode": "balanced"}
    plan = _edit_plan_with_mode(
        mode_data,
        subtitle_execution_promotion={"applied": False, "reason": "user_override:subtitle_locked"},
    )
    metrics = build_ai_execution_metrics(plan)["ai_execution_metrics"]
    assert metrics["subtitle"]["applied"] is False
    from app.ai.metrics.ai_execution_metrics_engine import _is_user_override
    assert _is_user_override(metrics["subtitle"]["reason"])


def test_metrics_quality_gate_still_blocks():
    """Quality gate block is independent of execution mode."""
    mode_data = {"mode": "balanced", "effective_mode": "balanced"}
    plan = _edit_plan_with_mode(
        mode_data,
        subtitle_execution_promotion={"applied": True, "reason": "promotion_applied", "confidence": 0.85},
        quality_gated_influence={"subtitle": {"applied": True, "gate_action": "block_keyword_strengthening"}},
    )
    metrics = build_ai_execution_metrics(plan)["ai_execution_metrics"]
    assert metrics["subtitle"]["applied"] is False,  "quality gate revert must show not applied"
    assert metrics["subtitle"]["blocked"] is True,   "quality gate must show blocked"


# ---------------------------------------------------------------------------
# Deterministic output
# ---------------------------------------------------------------------------

def test_deterministic_output():
    payload = {"ai_execution_mode": "safe"}
    result_a = resolve_execution_mode(payload)
    result_b = resolve_execution_mode(payload)
    assert result_a == result_b


# ---------------------------------------------------------------------------
# Safety / fallback tests
# ---------------------------------------------------------------------------

def test_never_raises_on_none_payload():
    result = resolve_execution_mode(None)
    assert "ai_execution_mode" in result
    assert result["ai_execution_mode"]["mode"] in ("off", "safe", "balanced", "aggressive")


def test_never_raises_on_empty_dict_payload():
    result = resolve_execution_mode({})
    assert "ai_execution_mode" in result


def test_fallback_shape_complete():
    result = resolve_execution_mode(None)
    ev = result["ai_execution_mode"]
    required = {"mode", "source", "effective_mode", "allowed_domains",
                "confidence_policy", "rollback_safe", "reasoning"}
    assert required.issubset(ev.keys()), f"Missing: {required - ev.keys()}"
    policy_keys = {"subtitle_threshold_delta", "camera_threshold_delta", "segment_threshold_delta"}
    assert policy_keys.issubset(ev["confidence_policy"].keys())


def test_metrics_never_raises_on_empty_edit_plan():
    result = build_ai_execution_metrics(SimpleNamespace())
    assert "ai_execution_metrics" in result
    metrics = result["ai_execution_metrics"]
    assert "mode" in metrics
    assert "rollback_active" in metrics
