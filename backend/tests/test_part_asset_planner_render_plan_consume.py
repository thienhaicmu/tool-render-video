"""
Sprint 4.E — pin the RenderPlan.subtitle_policy consume contract.

These tests anchor the two resolver helpers (_resolve_subtitle_style_
from_plan and _resolve_market_from_plan) that part_asset_planner uses
to migrate the subtitle-style + market decisions from the legacy
5-tier resolution to a per-field merge with the AI-emitted RenderPlan.

The resolvers are pure: no I/O, no LLM calls, no subtitle-engine
invocation. They take a PartRenderContext and a fallback value (style
only) and return (value, source_tag). Per Planner brief Section D the
deeper behavioural verification — "the planner actually consumes the
plan and emits the right event source tag" — is covered by a separate
source-level pin (test_event_source_enum_expanded) so we never
regress the wire-up.

emphasis_pass and line_break_rule are EXPLICITLY out of scope for
Sprint 4.E. emphasis was deferred because the SubtitlePolicy dataclass
can't disambiguate "default False" from "explicit False" without
flipping baseline behaviour (Sacred Contract #2). line_break_rule was
deferred because consuming it requires extending the signature of
apply_market_line_break_to_srt — a cross-file change.
"""
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.domain.render_plan import (
    AudioPlan,
    CameraStrategy,
    ClipPlan,
    OutputConfig,
    RenderPlan,
    SubtitlePolicy,
)
from app.orchestration.stages.part_asset_planner import (
    _RENDER_PLAN_ALLOWED_SUBTITLE_STYLES,
    _resolve_market_from_plan,
    _resolve_subtitle_style_from_plan,
)


def _ctx(render_plan):
    """Bare-attribute ctx — the resolvers only read `render_plan`."""
    ctx = MagicMock()
    ctx.render_plan = render_plan
    return ctx


# ── _resolve_subtitle_style_from_plan ────────────────────────────────────


class TestResolveSubtitleStyleFromPlan:
    def test_returns_fallback_when_plan_is_none(self):
        result = _resolve_subtitle_style_from_plan(_ctx(None), "tiktok_bounce_v1")
        assert result == ("tiktok_bounce_v1", "fallback")

    def test_returns_plan_style_when_set(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(style="viral"))
        result = _resolve_subtitle_style_from_plan(_ctx(plan), "tiktok_bounce_v1")
        assert result == ("viral", "render_plan")

    def test_returns_fallback_when_plan_style_empty(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(style=""))
        result = _resolve_subtitle_style_from_plan(_ctx(plan), "tiktok_bounce_v1")
        assert result == ("tiktok_bounce_v1", "fallback")

    def test_returns_fallback_when_plan_style_whitespace(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(style="   "))
        result = _resolve_subtitle_style_from_plan(_ctx(plan), "tiktok_bounce_v1")
        assert result == ("tiktok_bounce_v1", "fallback")

    def test_returns_fallback_with_invalid_style_tag(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(style="bogus_xyz"))
        result = _resolve_subtitle_style_from_plan(_ctx(plan), "tiktok_bounce_v1")
        assert result == ("tiktok_bounce_v1", "fallback_invalid_style")

    def test_accepts_every_documented_render_plan_style(self):
        """The SubtitlePolicy docstring lists viral|clean|story|gaming
        as the canonical vocabulary. Pin that every one resolves."""
        for canonical in ("viral", "clean", "story", "gaming"):
            plan = RenderPlan(subtitle_policy=SubtitlePolicy(style=canonical))
            result = _resolve_subtitle_style_from_plan(_ctx(plan), "tiktok_bounce_v1")
            assert result == (canonical, "render_plan"), f"style={canonical!r}"

    def test_accepts_registered_preset_ids(self):
        """Backwards compat: the legacy preset_ids that already exist
        in subtitle_engine continue to resolve through the plan path."""
        for preset in (
            "tiktok_bounce_v1", "viral_bold", "story_clean_01",
            "clean_pro", "boxed_caption", "pro_karaoke",
        ):
            plan = RenderPlan(subtitle_policy=SubtitlePolicy(style=preset))
            result = _resolve_subtitle_style_from_plan(_ctx(plan), "tiktok_bounce_v1")
            assert result == (preset, "render_plan"), f"preset={preset!r}"

    def test_strips_whitespace_from_plan_style(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(style="  viral  "))
        result = _resolve_subtitle_style_from_plan(_ctx(plan), "tiktok_bounce_v1")
        assert result == ("viral", "render_plan")


# ── _resolve_market_from_plan ────────────────────────────────────────────


class TestResolveMarketFromPlan:
    def test_returns_empty_when_plan_is_none(self):
        assert _resolve_market_from_plan(_ctx(None)) == ""

    def test_returns_plan_market_when_set(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(market="us"))
        assert _resolve_market_from_plan(_ctx(plan)) == "us"

    def test_returns_empty_when_plan_market_empty(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(market=""))
        assert _resolve_market_from_plan(_ctx(plan)) == ""

    def test_returns_empty_when_plan_market_whitespace_only(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(market="   "))
        assert _resolve_market_from_plan(_ctx(plan)) == ""

    def test_strips_whitespace(self):
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(market="  vn  "))
        assert _resolve_market_from_plan(_ctx(plan)) == "vn"

    def test_market_resolution_independent_from_style(self):
        """Per-field merge contract: style empty in plan does NOT
        force market to empty. The two fields resolve independently."""
        plan = RenderPlan(subtitle_policy=SubtitlePolicy(style="", market="vn"))
        assert _resolve_market_from_plan(_ctx(plan)) == "vn"


# ── Source-level pin for event source enum expansion ────────────────────


class TestEventSourceEnumWired:
    """The `subtitle_style_applied` event payload's
    `subtitle_style_source` key gains two new vocabulary values in
    Sprint 4.E: `"render_plan"` (plan override accepted) and
    `"fallback_invalid_style"` (plan emitted an unknown value and we
    soft-fell back). These tests grep the planner source to make sure
    the wire-up survives future refactors."""

    @staticmethod
    def _read_source() -> str:
        from app.orchestration.stages import part_asset_planner as pap
        return Path(pap.__file__).read_text(encoding="utf-8")

    def test_source_enum_includes_render_plan(self):
        src = self._read_source()
        assert '"render_plan"' in src or "'render_plan'" in src

    def test_source_enum_includes_fallback_invalid_style(self):
        src = self._read_source()
        assert "fallback_invalid_style" in src

    def test_legacy_source_values_preserved(self):
        """Pre-4.E values `"auto"` and `"explicit"` must remain valid
        — the new tag set is additive."""
        src = self._read_source()
        assert '"auto"' in src
        assert '"explicit"' in src

    def test_market_resolver_call_site_present(self):
        """Sprint 4.E migrates the market argument at the
        subtitle_emphasis_pass call site only (functional override).
        Log fields still use ctx.mv_market — pin the resolver call
        appears exactly where the Planner brief Section C/C4 put it."""
        src = self._read_source()
        assert "_resolve_market_from_plan(ctx) or ctx.mv_market" in src
