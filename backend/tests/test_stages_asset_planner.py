"""Tests for app.features.render.engine.stages.part_asset_planner."""
import pytest
from unittest.mock import MagicMock

from app.features.render.engine.stages.part_asset_planner import (
    _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES,
    _resolve_subtitle_style_from_plan,
)


# ---------------------------------------------------------------------------
# _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES
# ---------------------------------------------------------------------------

def test_allowed_subtitle_styles_is_frozenset():
    assert isinstance(_RENDER_PLAN_ALLOWED_SUBTITLE_STYLES, frozenset)


def test_allowed_subtitle_styles_non_empty():
    assert len(_RENDER_PLAN_ALLOWED_SUBTITLE_STYLES) > 0


def test_allowed_subtitle_styles_contains_viral():
    assert "viral" in _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES


def test_allowed_subtitle_styles_contains_clean():
    assert "clean" in _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES


def test_allowed_subtitle_styles_contains_story():
    assert "story" in _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES


def test_allowed_subtitle_styles_contains_gaming():
    assert "gaming" in _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES


def test_allowed_subtitle_styles_contains_tiktok_bounce_v1():
    assert "tiktok_bounce_v1" in _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES


# ---------------------------------------------------------------------------
# _resolve_subtitle_style_from_plan
# ---------------------------------------------------------------------------

def _make_ctx(plan_style: str | None = None) -> MagicMock:
    """Build a minimal fake PartRenderContext."""
    ctx = MagicMock()
    if plan_style is None:
        ctx.render_plan = None
    else:
        rp = MagicMock()
        rp.subtitle_policy.style = plan_style
        ctx.render_plan = rp
    return ctx


def test_resolve_subtitle_style_no_plan_returns_fallback():
    ctx = _make_ctx(plan_style=None)
    style, source = _resolve_subtitle_style_from_plan(ctx, "tiktok_bounce_v1")
    assert style == "tiktok_bounce_v1"
    assert source == "fallback"


def test_resolve_subtitle_style_plan_overrides_fallback():
    ctx = _make_ctx(plan_style="viral")
    style, source = _resolve_subtitle_style_from_plan(ctx, "tiktok_bounce_v1")
    assert style == "viral"
    assert source == "render_plan"


def test_resolve_subtitle_style_invalid_plan_returns_fallback():
    ctx = _make_ctx(plan_style="completely_invalid_style_xyz")
    style, source = _resolve_subtitle_style_from_plan(ctx, "tiktok_bounce_v1")
    assert style == "tiktok_bounce_v1"
    assert source == "fallback_invalid_style"


def test_resolve_subtitle_style_empty_plan_style_returns_fallback():
    ctx = _make_ctx(plan_style="")
    style, source = _resolve_subtitle_style_from_plan(ctx, "story")
    assert style == "story"
    assert source == "fallback"


def test_resolve_subtitle_style_all_allowed_styles_accepted():
    """Every allowed style should be accepted, not fall back."""
    for allowed in _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES:
        ctx = _make_ctx(plan_style=allowed)
        style, source = _resolve_subtitle_style_from_plan(ctx, "tiktok_bounce_v1")
        assert style == allowed
        assert source == "render_plan"


def test_resolve_subtitle_style_whitespace_plan_returns_fallback():
    ctx = _make_ctx(plan_style="   ")
    style, source = _resolve_subtitle_style_from_plan(ctx, "clean_pro")
    assert style == "clean_pro"
    assert source == "fallback"
