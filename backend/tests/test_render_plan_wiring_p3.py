"""Unit tests for P3 resolver functions.

Tests _resolve_motion_aware_crop_from_plan and _resolve_voice_enabled_from_plan
in isolation — no FFmpeg, no subprocess, no DB.

Each resolver must:
  - Return fallback when ctx.render_plan is None (legacy path)
  - Return fallback when plan field is None (AI didn't mention it)
  - Return True/False overriding the fallback when plan field is set
"""
import json
from types import SimpleNamespace
from typing import Optional

import pytest

from app.features.render.engine.stages.part_render_setup import (
    _resolve_motion_aware_crop_from_plan,
)
from app.features.render.engine.stages.part_voice_mix import (
    _resolve_voice_enabled_from_plan,
)
from app.domain.render_plan import RenderPlan


def _ctx_no_plan():
    """Minimal ctx with render_plan=None."""
    return SimpleNamespace(render_plan=None)


def _ctx_with_plan(json_str: str):
    """Minimal ctx with a render_plan parsed from json_str."""
    return SimpleNamespace(render_plan=RenderPlan.from_json(json_str))


# ── _resolve_motion_aware_crop_from_plan ──────────────────────────────────────

def test_motion_crop_no_plan_returns_false_fallback():
    ctx = _ctx_no_plan()
    result, source = _resolve_motion_aware_crop_from_plan(ctx, False)
    assert result is False
    assert source == "fallback"


def test_motion_crop_no_plan_returns_true_fallback():
    ctx = _ctx_no_plan()
    result, source = _resolve_motion_aware_crop_from_plan(ctx, True)
    assert result is True
    assert source == "fallback"


def test_motion_crop_plan_none_field_returns_fallback():
    ctx = _ctx_with_plan('{"clips": []}')
    assert ctx.render_plan.camera_strategy.motion_aware_crop is None
    result, source = _resolve_motion_aware_crop_from_plan(ctx, False)
    assert result is False
    assert source == "fallback"


def test_motion_crop_plan_true_overrides_false_fallback():
    ctx = _ctx_with_plan('{"camera_strategy": {"motion_aware_crop": true}}')
    result, source = _resolve_motion_aware_crop_from_plan(ctx, False)
    assert result is True
    assert source == "render_plan"


def test_motion_crop_plan_false_overrides_true_fallback():
    ctx = _ctx_with_plan('{"camera_strategy": {"motion_aware_crop": false}}')
    result, source = _resolve_motion_aware_crop_from_plan(ctx, True)
    assert result is False
    assert source == "render_plan"


def test_motion_crop_plan_true_and_true_fallback_returns_render_plan():
    ctx = _ctx_with_plan('{"camera_strategy": {"motion_aware_crop": true}}')
    result, source = _resolve_motion_aware_crop_from_plan(ctx, True)
    assert result is True
    assert source == "render_plan"


# ── _resolve_voice_enabled_from_plan ─────────────────────────────────────────

def test_voice_enabled_no_plan_returns_false_fallback():
    ctx = _ctx_no_plan()
    assert _resolve_voice_enabled_from_plan(ctx, False) is False


def test_voice_enabled_no_plan_returns_true_fallback():
    ctx = _ctx_no_plan()
    assert _resolve_voice_enabled_from_plan(ctx, True) is True


def test_voice_enabled_plan_none_field_returns_fallback():
    ctx = _ctx_with_plan('{"clips": []}')
    assert ctx.render_plan.audio_plan.voice_enabled is None
    assert _resolve_voice_enabled_from_plan(ctx, False) is False


def test_voice_enabled_plan_true_overrides_false_fallback():
    ctx = _ctx_with_plan('{"audio_plan": {"voice_enabled": true}}')
    assert _resolve_voice_enabled_from_plan(ctx, False) is True


def test_voice_enabled_plan_false_overrides_true_fallback():
    ctx = _ctx_with_plan('{"audio_plan": {"voice_enabled": false}}')
    assert _resolve_voice_enabled_from_plan(ctx, True) is False


def test_voice_enabled_plan_true_and_true_fallback():
    ctx = _ctx_with_plan('{"audio_plan": {"voice_enabled": true}}')
    assert _resolve_voice_enabled_from_plan(ctx, True) is True
