"""Tests for app.features.render.engine.stages.part_asset_planner."""
import pytest
from unittest.mock import MagicMock

from app.features.render.engine.stages.part_asset_planner import (
    _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES,
    _resolve_subtitle_style_from_plan,
)
from app.features.render.engine.stages.part_render_plan_resolvers import (
    _resolve_market_from_plan,
    _resolve_cta_audio_from_plan,
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


# ---------------------------------------------------------------------------
# _resolve_subtitle_style_from_plan — per-clip path (part_no > 0) — P6
# ---------------------------------------------------------------------------

def _make_ctx_with_clips(clip_styles: list, global_style: str = "") -> MagicMock:
    """ctx with render_plan having clips with per-clip subtitle_style set."""
    ctx = MagicMock()
    rp = MagicMock()
    rp.subtitle_policy.style = global_style
    rp.clips = [MagicMock(subtitle_style=s) for s in clip_styles]
    ctx.render_plan = rp
    return ctx


def test_resolve_subtitle_style_per_clip_overrides_global():
    ctx = _make_ctx_with_clips(["story"], global_style="viral")
    style, source = _resolve_subtitle_style_from_plan(ctx, "clean", part_no=1)
    assert style == "story"
    assert source == "render_plan_clip"


def test_resolve_subtitle_style_per_clip_invalid_falls_to_global():
    ctx = _make_ctx_with_clips(["invalid_xyz"], global_style="viral")
    style, source = _resolve_subtitle_style_from_plan(ctx, "clean", part_no=1)
    assert style == "viral"
    assert source == "render_plan"


def test_resolve_subtitle_style_per_clip_empty_falls_to_global():
    ctx = _make_ctx_with_clips([""], global_style="gaming")
    style, source = _resolve_subtitle_style_from_plan(ctx, "clean", part_no=1)
    assert style == "gaming"
    assert source == "render_plan"


def test_resolve_subtitle_style_per_clip_out_of_bounds_falls_to_global():
    ctx = _make_ctx_with_clips(["story"], global_style="viral")
    style, source = _resolve_subtitle_style_from_plan(ctx, "clean", part_no=5)
    assert style == "viral"
    assert source == "render_plan"


def test_resolve_subtitle_style_per_clip_overrides_when_global_empty():
    ctx = _make_ctx_with_clips(["gaming"], global_style="")
    style, source = _resolve_subtitle_style_from_plan(ctx, "clean", part_no=1)
    assert style == "gaming"
    assert source == "render_plan_clip"


def test_resolve_subtitle_style_part_no_zero_uses_global_only():
    ctx = _make_ctx_with_clips(["story"], global_style="viral")
    style, source = _resolve_subtitle_style_from_plan(ctx, "clean", part_no=0)
    assert style == "viral"
    assert source == "render_plan"


# ---------------------------------------------------------------------------
# _resolve_market_from_plan — P7
# ---------------------------------------------------------------------------

def test_resolve_market_no_plan_returns_empty():
    ctx = _make_ctx(plan_style=None)
    assert _resolve_market_from_plan(ctx) == ""


def test_resolve_market_plan_with_market_returns_it():
    ctx = MagicMock()
    ctx.render_plan = MagicMock()
    ctx.render_plan.subtitle_policy.market = "vn"
    assert _resolve_market_from_plan(ctx) == "vn"


def test_resolve_market_plan_empty_returns_empty():
    ctx = MagicMock()
    ctx.render_plan = MagicMock()
    ctx.render_plan.subtitle_policy.market = ""
    assert _resolve_market_from_plan(ctx) == ""


def test_resolve_market_plan_whitespace_returns_empty():
    ctx = MagicMock()
    ctx.render_plan = MagicMock()
    ctx.render_plan.subtitle_policy.market = "   "
    assert _resolve_market_from_plan(ctx) == ""


# ---------------------------------------------------------------------------
# _resolve_cta_audio_from_plan — P7
# ---------------------------------------------------------------------------

def test_resolve_cta_audio_no_plan_returns_empty():
    ctx = _make_ctx(plan_style=None)
    assert _resolve_cta_audio_from_plan(ctx) == ""


def test_resolve_cta_audio_plan_with_text_returns_it():
    ctx = MagicMock()
    ctx.render_plan = MagicMock()
    ctx.render_plan.audio_plan.cta_audio = "Subscribe now"
    assert _resolve_cta_audio_from_plan(ctx) == "Subscribe now"


def test_resolve_cta_audio_plan_strips_whitespace():
    ctx = MagicMock()
    ctx.render_plan = MagicMock()
    ctx.render_plan.audio_plan.cta_audio = "  Follow me  "
    assert _resolve_cta_audio_from_plan(ctx) == "Follow me"


def test_resolve_cta_audio_plan_empty_returns_empty():
    ctx = MagicMock()
    ctx.render_plan = MagicMock()
    ctx.render_plan.audio_plan.cta_audio = ""
    assert _resolve_cta_audio_from_plan(ctx) == ""
