"""Tests for S5 (B+C) — _llm_plan_cache_key invalidates on creator pref changes.

Verifies the cache key behaves correctly when the new creator preference
fields differ. Without these fields in the key, changing video_type or
hook_strength would NOT invalidate the cache → user changes a setting
hoping for a different AI plan, but the cached plan is returned. The
test suite below guards against that regression.

The actual cache hit/miss behavior is integration-tested in
test_render_pipeline_*; this file isolates the cache key arithmetic.
"""
from __future__ import annotations

import pytest

from app.features.render.engine.pipeline.pipeline_cache import _llm_plan_cache_key


_BASE_ARGS = dict(
    srt_content="some_srt",
    output_count=3,
    min_sec=30.0,
    max_sec=60.0,
    target_platform="tiktok",
    provider="gemini",
    model="",
    editorial_hint="",
    target_duration=0,
    clip_lock_repr="None",
    clip_exclude_repr="None",
    language="auto",
)


def test_implicit_defaults_equal_explicit_defaults():
    """Callers that don't pass the new kwargs must produce the same key
    as callers that pass them as explicit defaults. This is the
    backward-compat guarantee — without it, every pre-S5 cached entry
    would become unreachable even when no creator pref was set."""
    k_implicit = _llm_plan_cache_key(**_BASE_ARGS)
    k_explicit = _llm_plan_cache_key(
        **_BASE_ARGS,
        video_type="auto",
        hook_strength="balanced",
        ai_target_market="",
        subtitle_emphasis="",
        multi_variant=False,
        structure_bias="",
    )
    assert k_implicit == k_explicit


@pytest.mark.parametrize("field,value", [
    ("video_type", "talking"),
    ("video_type", "cinematic"),
    ("hook_strength", "aggressive"),
    ("hook_strength", "light"),
    ("ai_target_market", "vn"),
    ("ai_target_market", "us"),
    ("subtitle_emphasis", "bold-yellow"),
    ("multi_variant", True),
    ("structure_bias", "hook-first"),
])
def test_non_default_value_invalidates_cache(field, value):
    """Each field must independently produce a different cache key when
    set to a non-default value. Without this, changing one knob in the
    UI would silently reuse the prior plan."""
    base = _llm_plan_cache_key(**_BASE_ARGS)
    changed = _llm_plan_cache_key(**_BASE_ARGS, **{field: value})
    assert base != changed, f"changing {field}={value!r} did not invalidate cache key"


def test_two_different_video_types_differ_from_each_other():
    a = _llm_plan_cache_key(**_BASE_ARGS, video_type="talking")
    b = _llm_plan_cache_key(**_BASE_ARGS, video_type="cinematic")
    assert a != b


def test_market_difference_invalidates():
    a = _llm_plan_cache_key(**_BASE_ARGS, ai_target_market="us")
    b = _llm_plan_cache_key(**_BASE_ARGS, ai_target_market="vn")
    assert a != b


def test_existing_field_changes_still_invalidate():
    """The 3 fields the user emphasised — output_count, min_sec, max_sec —
    must continue to invalidate the cache after the S5 extension."""
    base = _llm_plan_cache_key(**_BASE_ARGS)
    out_changed = _llm_plan_cache_key(**{**_BASE_ARGS, "output_count": 4})
    min_changed = _llm_plan_cache_key(**{**_BASE_ARGS, "min_sec": 31.0})
    max_changed = _llm_plan_cache_key(**{**_BASE_ARGS, "max_sec": 61.0})
    assert base != out_changed
    assert base != min_changed
    assert base != max_changed
    # And they're all distinct from each other.
    assert {base, out_changed, min_changed, max_changed} == {
        base, out_changed, min_changed, max_changed
    }
    assert len({base, out_changed, min_changed, max_changed}) == 4


def test_falsy_str_normalisation():
    """Empty strings, None-passed-as-str-empty, and missing-kwarg should
    all map to the same key — otherwise the cache fragments unnecessarily."""
    k1 = _llm_plan_cache_key(**_BASE_ARGS)
    k2 = _llm_plan_cache_key(**_BASE_ARGS, ai_target_market="", subtitle_emphasis="")
    assert k1 == k2
