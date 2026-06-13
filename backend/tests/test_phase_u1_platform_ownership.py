"""tests/test_phase_u1_platform_ownership.py — Phase U1: Platform Ownership Resolution.

Tests for _resolve_pacing_speed_delta() in part_render_plan_resolvers.py
and its downstream effect on PartExecutionPlan.playback_speed.

Behavior table:
  pacing=""     + TikTok speed_delta=+0.08 → (0.0, +0.08) → 1.08x (unchanged pre-U1)
  pacing="slow" + TikTok speed_delta=+0.08 → (-0.06, +0.02) → 0.96x (AI wins, soft nudge)
  pacing="fast" + TikTok speed_delta=+0.08 → (+0.08, +0.02) → 1.10x (AI + nudge)
  pacing="medium" → (+0.00, soft) → speed unchanged
  No render_plan on ctx → (0.0, full_platform_delta) — pre-U1 passthrough
  idx out of clips range → (0.0, full_platform_delta) — graceful fallback
  Unknown pacing value → (0.0, full_platform_delta) — unknown = inherit
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch


# ── helpers ──────────────────────────────────────────────────────────────────

def _make_ctx(pacing: str = "", has_plan: bool = True, clips_count: int = 3):
    """Build a minimal PartRenderContext-like namespace for testing."""
    clips = [SimpleNamespace(pacing=pacing)] * clips_count if has_plan else []
    render_plan = SimpleNamespace(clips=clips) if has_plan else None
    return SimpleNamespace(render_plan=render_plan)


_TIKTOK_PROFILES = {"tiktok": {"speed_delta": 0.08}, "youtube": {"speed_delta": -0.05}}


def _call(ctx, idx: int, platform: str = "tiktok") -> tuple[float, float]:
    from app.features.render.engine.stages.part_render_plan_resolvers import _resolve_pacing_speed_delta
    with patch(
        "app.features.render.engine.stages.part_render_plan_resolvers._PLATFORM_PROFILES",
        _TIKTOK_PROFILES,
        create=True,
    ):
        # Patch the lazy import inside the function
        import app.features.render.engine.pipeline.pipeline_segment_selection as pss
        original = pss._PLATFORM_PROFILES
        pss._PLATFORM_PROFILES = _TIKTOK_PROFILES
        try:
            return _resolve_pacing_speed_delta(ctx, idx, platform)
        finally:
            pss._PLATFORM_PROFILES = original


# ── core behaviour tests ──────────────────────────────────────────────────────

def test_no_pacing_returns_full_platform_delta():
    """pacing="" → AI silent → returns (0.0, full_platform_delta)."""
    ctx = _make_ctx(pacing="")
    pacing_delta, platform_delta = _call(ctx, idx=1)
    assert pacing_delta == 0.0
    assert abs(platform_delta - 0.08) < 1e-9


def test_slow_pacing_demotes_platform():
    """pacing="slow" → AI wins → platform clamped to ±0.02."""
    ctx = _make_ctx(pacing="slow")
    pacing_delta, platform_delta = _call(ctx, idx=1)
    assert abs(pacing_delta - (-0.06)) < 1e-9
    # TikTok +0.08 clamped to +0.02 soft cap
    assert abs(platform_delta - 0.02) < 1e-9


def test_fast_pacing_adds_ai_delta():
    """pacing="fast" → +0.08 AI delta, platform soft-capped."""
    ctx = _make_ctx(pacing="fast")
    pacing_delta, platform_delta = _call(ctx, idx=1)
    assert abs(pacing_delta - 0.08) < 1e-9
    assert abs(platform_delta - 0.02) < 1e-9


def test_medium_pacing_zero_ai_delta():
    """pacing="medium" → 0.0 AI delta."""
    ctx = _make_ctx(pacing="medium")
    pacing_delta, platform_delta = _call(ctx, idx=1)
    assert abs(pacing_delta - 0.00) < 1e-9
    assert abs(platform_delta - 0.02) < 1e-9


def test_no_render_plan_returns_full_platform():
    """ctx.render_plan=None → pre-U1 passthrough → (0.0, full_delta)."""
    ctx = _make_ctx(has_plan=False)
    pacing_delta, platform_delta = _call(ctx, idx=1)
    assert pacing_delta == 0.0
    assert abs(platform_delta - 0.08) < 1e-9


def test_idx_out_of_clips_range_returns_passthrough():
    """idx beyond clips list → graceful fallback → (0.0, full_delta)."""
    ctx = _make_ctx(pacing="slow", clips_count=1)
    pacing_delta, platform_delta = _call(ctx, idx=5)  # only 1 clip
    assert pacing_delta == 0.0
    assert abs(platform_delta - 0.08) < 1e-9


def test_unknown_pacing_value_is_ignored():
    """Unknown pacing string → treated as inherit → (0.0, full_delta)."""
    ctx = _make_ctx(pacing="turbo")
    pacing_delta, platform_delta = _call(ctx, idx=1)
    assert pacing_delta == 0.0
    assert abs(platform_delta - 0.08) < 1e-9


def test_negative_platform_delta_clamped_correctly():
    """Negative platform_delta (youtube=-0.05) is soft-capped to -0.02."""
    ctx = _make_ctx(pacing="fast")
    pacing_delta, platform_delta = _call(ctx, idx=1, platform="youtube")
    # youtube speed_delta=-0.05 clamped to -0.02
    assert abs(pacing_delta - 0.08) < 1e-9
    assert abs(platform_delta - (-0.02)) < 1e-9


def test_combined_speed_tiktok_slow():
    """Full integration: base=1.0 + slow AI (-0.06) + tiktok soft (+0.02) = 0.96x."""
    ctx = _make_ctx(pacing="slow")
    pd, plat = _call(ctx, idx=1)
    result = max(0.5, min(1.5, 1.0 + pd + plat))
    assert abs(result - 0.96) < 1e-9


def test_combined_speed_tiktok_fast():
    """Full integration: base=1.0 + fast AI (+0.08) + tiktok soft (+0.02) = 1.10x."""
    ctx = _make_ctx(pacing="fast")
    pd, plat = _call(ctx, idx=1)
    result = max(0.5, min(1.5, 1.0 + pd + plat))
    assert abs(result - 1.10) < 1e-9


def test_pacing_to_speed_delta_dict_has_required_keys():
    from app.features.render.engine.stages.part_render_plan_resolvers import _PACING_TO_SPEED_DELTA
    assert "fast" in _PACING_TO_SPEED_DELTA
    assert "medium" in _PACING_TO_SPEED_DELTA
    assert "slow" in _PACING_TO_SPEED_DELTA


def test_platform_soft_cap_constant():
    from app.features.render.engine.stages.part_render_plan_resolvers import _PLATFORM_SOFT_CAP
    assert _PLATFORM_SOFT_CAP == 0.02


def test_no_platform_returns_zero_delta():
    """Unknown platform returns 0.0 for both deltas when no pacing."""
    ctx = _make_ctx(pacing="")
    pacing_delta, platform_delta = _call(ctx, idx=1, platform="unknown_platform")
    assert pacing_delta == 0.0
    assert platform_delta == 0.0
