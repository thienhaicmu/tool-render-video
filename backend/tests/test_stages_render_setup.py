"""Tests for app.features.render.engine.stages.part_render_setup."""
import pytest
from unittest.mock import MagicMock

from app.features.render.engine.stages.part_render_setup import (
    _RENDER_PLAN_ALLOWED_REFRAME_MODES,
    _resolve_reframe_mode_from_plan,
)


# ---------------------------------------------------------------------------
# _RENDER_PLAN_ALLOWED_REFRAME_MODES
# ---------------------------------------------------------------------------

def test_allowed_reframe_modes_is_frozenset():
    assert isinstance(_RENDER_PLAN_ALLOWED_REFRAME_MODES, frozenset)


def test_allowed_reframe_modes_non_empty():
    assert len(_RENDER_PLAN_ALLOWED_REFRAME_MODES) > 0


def test_allowed_reframe_modes_contains_center():
    assert "center" in _RENDER_PLAN_ALLOWED_REFRAME_MODES


def test_allowed_reframe_modes_contains_track():
    assert "track" in _RENDER_PLAN_ALLOWED_REFRAME_MODES


def test_allowed_reframe_modes_contains_fixed():
    assert "fixed" in _RENDER_PLAN_ALLOWED_REFRAME_MODES


def test_allowed_reframe_modes_does_not_contain_subject():
    # "subject" belongs to payload schema, not plan schema (per docstring)
    assert "subject" not in _RENDER_PLAN_ALLOWED_REFRAME_MODES


# ---------------------------------------------------------------------------
# _resolve_reframe_mode_from_plan
# ---------------------------------------------------------------------------

def _make_ctx(plan_reframe: str | None = None) -> MagicMock:
    """Build a minimal fake PartRenderContext."""
    ctx = MagicMock()
    if plan_reframe is None:
        ctx.render_plan = None
    else:
        rp = MagicMock()
        rp.camera_strategy.reframe_mode = plan_reframe
        ctx.render_plan = rp
    return ctx


def test_resolve_reframe_no_plan_returns_fallback():
    ctx = _make_ctx(plan_reframe=None)
    mode, source = _resolve_reframe_mode_from_plan(ctx, "subject")
    assert mode == "subject"
    assert source == "fallback"


def test_resolve_reframe_plan_overrides_fallback():
    ctx = _make_ctx(plan_reframe="center")
    mode, source = _resolve_reframe_mode_from_plan(ctx, "subject")
    assert mode == "center"
    assert source == "render_plan"


def test_resolve_reframe_invalid_mode_returns_fallback_invalid():
    ctx = _make_ctx(plan_reframe="invalid_reframe_xyz")
    mode, source = _resolve_reframe_mode_from_plan(ctx, "subject")
    assert mode == "subject"
    assert source == "fallback_invalid_reframe"


def test_resolve_reframe_empty_plan_returns_fallback():
    ctx = _make_ctx(plan_reframe="")
    mode, source = _resolve_reframe_mode_from_plan(ctx, "track")
    assert mode == "track"
    assert source == "fallback"


def test_resolve_reframe_all_allowed_modes_accepted():
    """Every mode in the allowed set should produce source='render_plan'."""
    for allowed in _RENDER_PLAN_ALLOWED_REFRAME_MODES:
        ctx = _make_ctx(plan_reframe=allowed)
        mode, source = _resolve_reframe_mode_from_plan(ctx, "subject")
        assert mode == allowed
        assert source == "render_plan"


def test_resolve_reframe_whitespace_returns_fallback():
    ctx = _make_ctx(plan_reframe="   ")
    mode, source = _resolve_reframe_mode_from_plan(ctx, "center")
    assert mode == "center"
    assert source == "fallback"


def test_resolve_reframe_track_mode():
    ctx = _make_ctx(plan_reframe="track")
    mode, source = _resolve_reframe_mode_from_plan(ctx, "subject")
    assert mode == "track"
    assert source == "render_plan"


def test_resolve_reframe_fixed_mode():
    ctx = _make_ctx(plan_reframe="fixed")
    mode, source = _resolve_reframe_mode_from_plan(ctx, "subject")
    assert mode == "fixed"
    assert source == "render_plan"
