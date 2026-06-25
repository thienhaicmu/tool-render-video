"""Tests for S5 (B+C) — creator preferences in the RenderPlan prompt.

Verifies:
1. Defaults produce zero "creator preferences" section (byte-for-byte
   identical to the pre-S5 baseline prompt).
2. Each individual hint surfaces exactly once when non-default.
3. The full set of hints produces a section with all expected lines.
4. The hard-constraints text in the prompt still wins — the section
   is explicitly labelled as hints, not rules.
"""
from __future__ import annotations

import pytest

from app.features.render.ai.llm.prompts import (
    _build_creator_preferences_section,
    build_render_plan_prompt,
)


# ---------------------------------------------------------------------------
# Builder: empty when every hint is at default
# ---------------------------------------------------------------------------


def test_builder_empty_when_all_defaults():
    assert _build_creator_preferences_section() == ""


def test_builder_empty_when_explicit_defaults():
    """video_type=auto / hook_strength=balanced / empty market should
    produce no section. This is what 95% of FE renders submit."""
    s = _build_creator_preferences_section(
        video_type="auto",
        hook_strength="balanced",
        ai_target_market="",
        subtitle_emphasis=None,
        multi_variant=False,
        structure_bias=None,
    )
    assert s == ""


# ---------------------------------------------------------------------------
# Each hint surfaces independently
# ---------------------------------------------------------------------------


def test_video_type_surfaces():
    s = _build_creator_preferences_section(video_type="talking")
    assert "content_type_hint: talking" in s
    assert "CREATOR PREFERENCES" in s


def test_hook_strength_aggressive_surfaces_with_explanation():
    s = _build_creator_preferences_section(hook_strength="aggressive")
    assert "hook_intensity_target: aggressive" in s
    assert "punchier" in s.lower()


def test_hook_strength_light_surfaces_with_explanation():
    s = _build_creator_preferences_section(hook_strength="light")
    assert "hook_intensity_target: light" in s
    assert "softer" in s.lower()


def test_ai_target_market_surfaces():
    s = _build_creator_preferences_section(ai_target_market="vn")
    assert "target_market: vn" in s


def test_subtitle_emphasis_surfaces():
    s = _build_creator_preferences_section(subtitle_emphasis="bold-yellow")
    assert "subtitle_emphasis_preference: bold-yellow" in s


def test_multi_variant_surfaces():
    s = _build_creator_preferences_section(multi_variant=True)
    assert "variant_emission: ON" in s


def test_structure_bias_surfaces():
    s = _build_creator_preferences_section(structure_bias="hook-first")
    assert "ranking_priority: hook-first" in s


# ---------------------------------------------------------------------------
# Combined hints + hard-constraints label
# ---------------------------------------------------------------------------


def test_all_hints_combined_in_one_section():
    s = _build_creator_preferences_section(
        video_type="talking",
        hook_strength="aggressive",
        ai_target_market="vn",
        subtitle_emphasis="bold",
        multi_variant=True,
        structure_bias="narrative",
    )
    assert "content_type_hint: talking" in s
    assert "hook_intensity_target: aggressive" in s
    assert "target_market: vn" in s
    assert "subtitle_emphasis_preference: bold" in s
    assert "variant_emission: ON" in s
    assert "ranking_priority: narrative" in s
    # Section appears exactly once.
    assert s.count("CREATOR PREFERENCES") == 1


def test_section_explicitly_labels_as_hints_not_rules():
    """A user reading the prompt should know these are hints, not
    overrides for min/max/output_count. Prevents an LLM from being
    confused into ignoring the hard constraints."""
    s = _build_creator_preferences_section(video_type="cinematic")
    lower = s.lower()
    assert "hints" in lower
    assert "hard constraint" in lower or "hard rules" in lower or "hard rule" in lower


# ---------------------------------------------------------------------------
# build_render_plan_prompt — defaults match baseline byte-for-byte
# ---------------------------------------------------------------------------


@pytest.fixture
def _srt():
    return (
        "1\n00:00:01,000 --> 00:00:04,000\nHello world.\n\n"
        "2\n00:00:05,000 --> 00:00:08,000\nThis is a test.\n"
    )


def test_default_kwargs_match_unmentioned_kwargs(_srt):
    """Calling build_render_plan_prompt with explicit "no hint" defaults
    must produce a prompt byte-for-byte identical to omitting them.
    This is the backward-compat guarantee for every pre-S5 caller."""
    _, u1 = build_render_plan_prompt(
        srt_content=_srt, output_count=3, min_sec=30, max_sec=60,
    )
    _, u2 = build_render_plan_prompt(
        srt_content=_srt, output_count=3, min_sec=30, max_sec=60,
        video_type="auto", hook_strength="balanced",
        ai_target_market="", subtitle_emphasis=None,
        multi_variant=False, structure_bias=None,
    )
    assert u1 == u2


def test_non_default_hints_change_prompt(_srt):
    _, base = build_render_plan_prompt(
        srt_content=_srt, output_count=3, min_sec=30, max_sec=60,
    )
    _, mod = build_render_plan_prompt(
        srt_content=_srt, output_count=3, min_sec=30, max_sec=60,
        video_type="talking", hook_strength="aggressive",
    )
    assert base != mod
    assert "content_type_hint: talking" in mod
    assert "hook_intensity_target: aggressive" in mod


def test_hard_constraints_section_still_present_with_hints(_srt):
    """The hard-constraints block must NOT be removed by the new section
    — it's the regression guard for the only-clip-on-min/max rule."""
    _, u = build_render_plan_prompt(
        srt_content=_srt, output_count=3, min_sec=30, max_sec=60,
        video_type="cinematic",
    )
    assert "HARD CONSTRAINTS" in u
    assert "({end} - {start}) MUST be in [30, 60]" in u
