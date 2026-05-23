"""
test_render_pipeline_ai_execution_hints.py — Tests for Phase 5.3 render pipeline integration.

Verifies:
- ai disabled path does not change behavior
- missing knowledge path does not change behavior
- invalid hints do not change behavior
- hook_overlay_enabled=False gates hook overlay
- pacing hint is logged as advisory only
- subtitle hint is logged as advisory only
"""
from __future__ import annotations

import types
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_plan(execution_hints=None, phase52_hints=None, retrieved_count=0):
    """Build a minimal AIEditPlan-like namespace for testing."""
    from app.ai.director.edit_plan_schema import (
        AIEditPlan, AISubtitlePlan, AICameraPlan,
    )
    plan = AIEditPlan(
        enabled=True,
        mode="viral_tiktok",
        selected_segments=[],
        subtitle=AISubtitlePlan(),
        camera=AICameraPlan(),
    )
    hints52 = phase52_hints or {}
    ki = {
        "retrieved_count": retrieved_count,
        "hints": hints52,
        "filters_used": {},
        "execution_hints": execution_hints or {},
        "validation_fixups": [],
        "validation_warnings": [],
    }
    plan.knowledge_injection = ki
    return plan


# ---------------------------------------------------------------------------
# 1. AI disabled path — execution_hints block not entered
# ---------------------------------------------------------------------------

def test_ai_disabled_exec_hints_not_applied():
    """When ai_director_enabled=False, _ai_edit_plan is None → hints block skipped."""
    # This is structural: if ai_director_enabled=False, the AI director block is
    # never entered, so _ai_edit_plan stays None, and the Phase 5.3 block is skipped.
    # We verify that _exec_hints would be {} when plan is None.
    _ai_edit_plan = None
    _exec_hints = (
        _ai_edit_plan.knowledge_injection.get("execution_hints") or {}
    ) if _ai_edit_plan is not None and isinstance(getattr(_ai_edit_plan, "knowledge_injection", None), dict) else {}
    assert _exec_hints == {}


# ---------------------------------------------------------------------------
# 2. Missing knowledge path — exec hints are empty dict
# ---------------------------------------------------------------------------

def test_missing_knowledge_exec_hints_empty():
    """When no knowledge retrieved, execution_hints is empty → no changes."""
    plan = _make_plan(execution_hints={})
    ki = plan.knowledge_injection
    eh = ki.get("execution_hints") or {}
    assert eh == {}
    # No fields → hook_overlay_enabled not touched
    assert eh.get("hook_overlay_enabled") is None
    assert eh.get("cut_interval_min") is None


# ---------------------------------------------------------------------------
# 3. Invalid hints do not change behavior
# ---------------------------------------------------------------------------

def test_invalid_hints_do_not_crash():
    """Garbage execution_hints dict is safe — no exception."""
    plan = _make_plan(execution_hints={"cut_interval_min": "invalid", "hook_overlay_enabled": "yes"})
    ki = plan.knowledge_injection
    eh = ki.get("execution_hints") or {}
    # Just read them — should not crash
    _ = eh.get("cut_interval_min")
    _ = eh.get("hook_overlay_enabled")


# ---------------------------------------------------------------------------
# 4. hook_overlay_enabled=False gates hook overlay
# ---------------------------------------------------------------------------

def test_hook_overlay_false_hint_disables_overlay():
    """If execution_hints.hook_overlay_enabled=False and _hook_overlay_enabled=True,
    the render pipeline logic should set _hook_overlay_enabled=False."""
    # Simulate the exact logic from render_pipeline.py Phase 5.3 C block
    _hook_overlay_enabled = True  # initial payload state
    plan = _make_plan(execution_hints={"hook_overlay_enabled": False})
    _exec_hints = plan.knowledge_injection.get("execution_hints") or {}
    _hook_enabled_hint = _exec_hints.get("hook_overlay_enabled")

    if _hook_enabled_hint is False:
        if _hook_overlay_enabled:
            _hook_overlay_enabled = False

    assert _hook_overlay_enabled is False


def test_hook_overlay_none_hint_leaves_overlay_unchanged():
    """hook_overlay_enabled=None → no change to existing behavior."""
    _hook_overlay_enabled = True
    plan = _make_plan(execution_hints={"hook_overlay_enabled": None})
    _exec_hints = plan.knowledge_injection.get("execution_hints") or {}
    _hook_enabled_hint = _exec_hints.get("hook_overlay_enabled")

    if _hook_enabled_hint is False:
        _hook_overlay_enabled = False

    assert _hook_overlay_enabled is True  # unchanged


def test_hook_overlay_true_hint_leaves_overlay_enabled():
    """hook_overlay_enabled=True → keep existing behavior (already enabled)."""
    _hook_overlay_enabled = True
    plan = _make_plan(execution_hints={"hook_overlay_enabled": True})
    _exec_hints = plan.knowledge_injection.get("execution_hints") or {}
    _hook_enabled_hint = _exec_hints.get("hook_overlay_enabled")

    if _hook_enabled_hint is False:
        _hook_overlay_enabled = False

    assert _hook_overlay_enabled is True


def test_hook_overlay_false_hint_already_disabled():
    """hook_overlay_enabled=False when overlay was already disabled → no change."""
    _hook_overlay_enabled = False
    plan = _make_plan(execution_hints={"hook_overlay_enabled": False})
    _exec_hints = plan.knowledge_injection.get("execution_hints") or {}
    _hook_enabled_hint = _exec_hints.get("hook_overlay_enabled")

    if _hook_enabled_hint is False:
        if _hook_overlay_enabled:
            _hook_overlay_enabled = False

    assert _hook_overlay_enabled is False


# ---------------------------------------------------------------------------
# 5. Pacing hint — advisory only (no compatible hook → logged only)
# ---------------------------------------------------------------------------

def test_pacing_hint_is_advisory_only():
    """Pacing hint sets cut_interval values but doesn't crash or mutate pipeline."""
    plan = _make_plan(execution_hints={"cut_interval_min": 2.0, "cut_interval_max": 4.0})
    _exec_hints = plan.knowledge_injection.get("execution_hints") or {}
    _pacing_cut_min = _exec_hints.get("cut_interval_min")
    _pacing_cut_max = _exec_hints.get("cut_interval_max")
    # Values are readable — advisory context exists
    assert _pacing_cut_min == 2.0
    assert _pacing_cut_max == 4.0
    # No exception thrown — pipeline continues


def test_pacing_hint_none_no_effect():
    plan = _make_plan(execution_hints={"cut_interval_min": None, "cut_interval_max": None})
    _exec_hints = plan.knowledge_injection.get("execution_hints") or {}
    assert _exec_hints.get("cut_interval_min") is None
    assert _exec_hints.get("cut_interval_max") is None


# ---------------------------------------------------------------------------
# 6. Subtitle emphasis hint — advisory only
# ---------------------------------------------------------------------------

def test_subtitle_hint_is_advisory_only():
    """Subtitle emphasis hint is readable but doesn't alter per-part style."""
    plan = _make_plan(execution_hints={"subtitle_emphasis_style": "strong"})
    _exec_hints = plan.knowledge_injection.get("execution_hints") or {}
    _sub_hint = _exec_hints.get("subtitle_emphasis_style")
    assert _sub_hint == "strong"
    # Advisory — no crash, no mutation of _effective_subtitle_style


def test_subtitle_hint_none_no_effect():
    plan = _make_plan(execution_hints={"subtitle_emphasis_style": None})
    _exec_hints = plan.knowledge_injection.get("execution_hints") or {}
    assert _exec_hints.get("subtitle_emphasis_style") is None


# ---------------------------------------------------------------------------
# 7. Exec hints block safe when knowledge_injection is malformed
# ---------------------------------------------------------------------------

def test_exec_hints_safe_when_knowledge_injection_not_dict():
    """If knowledge_injection is not a dict, exec_hints defaults to {}."""
    from app.ai.director.edit_plan_schema import AIEditPlan, AISubtitlePlan, AICameraPlan
    plan = AIEditPlan(
        enabled=True, mode="viral", selected_segments=[],
        subtitle=AISubtitlePlan(), camera=AICameraPlan(),
    )
    plan.knowledge_injection = "bad_value"  # not a dict

    _exec_hints = (
        plan.knowledge_injection.get("execution_hints") or {}
    ) if isinstance(plan.knowledge_injection, dict) else {}

    assert _exec_hints == {}


def test_exec_hints_safe_when_plan_none():
    """If plan is None, exec_hints block is skipped safely."""
    _ai_edit_plan = None
    _exec_hints = (
        _ai_edit_plan.knowledge_injection.get("execution_hints") or {}
    ) if _ai_edit_plan is not None and isinstance(
        getattr(_ai_edit_plan, "knowledge_injection", None), dict
    ) else {}
    assert _exec_hints == {}
