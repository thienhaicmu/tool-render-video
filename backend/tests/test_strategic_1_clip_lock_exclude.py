"""Strategic-1 closure regression guard — Audit 2026-06-08 (Batch A V8-A12 / UP26).

Pre-Strategic-1 the operator's clip_lock / clip_exclude ranges were
STRIPPED from the wire by T1.4 (commit 0a20349) because no consumer
existed in the BE — the LLM prompt never saw them, no local filter
checked them, the fields were pure UI deceit.

Strategic-1 restores them WITH a real consumer:

  1. ``models/render_public.py:FE_FACING_FIELDS`` re-includes
     clip_lock and clip_exclude (Public surface 67 → 69).

  2. ``frontend/src/types/api.ts:RenderRequest`` re-declares the two
     fields. FE form widgets / buildPayload remain TODO (operator
     can use the API directly).

  3. ``ai/llm/prompts.py:build_render_plan_prompt`` accepts
     clip_lock + clip_exclude kwargs and renders them as HARD LOCKED
     RANGES / HARD EXCLUDED RANGES sections in the prompt body. The
     helper ``_format_range_section`` is defensive — None / empty /
     malformed entries collapse to no section.

  4. Three providers (gemini/openai/claude) and the dispatcher
     forward the kwargs through to the prompt builder.

  5. ``render_pipeline.py`` reads ``payload.clip_lock`` and
     ``payload.clip_exclude`` and passes them to the dispatcher at
     the LLM call site.

This file pins the new behaviour.
"""
from __future__ import annotations

import inspect

import pytest


# ---------------------------------------------------------------------------
# 1. _format_range_section — defensive rendering helper.
# ---------------------------------------------------------------------------


def test_format_range_section_returns_empty_for_none():
    """None input MUST suppress the prompt section entirely (no
    header, no body). Backward-compat with all callers that don't
    set the new kwargs."""
    from app.features.render.ai.llm.prompts import _format_range_section
    assert _format_range_section(None, header="X", body="Y") == ""


def test_format_range_section_returns_empty_for_empty_list():
    """An empty list is semantically identical to None — no operator
    intent expressed."""
    from app.features.render.ai.llm.prompts import _format_range_section
    assert _format_range_section([], header="X", body="Y") == ""


def test_format_range_section_renders_valid_entries():
    """Each {start_sec, end_sec} dict becomes one bullet in the
    prompt section, with the header + body block above."""
    from app.features.render.ai.llm.prompts import _format_range_section
    output = _format_range_section(
        [{"start_sec": 10.5, "end_sec": 25.0}, {"start_sec": 60.0, "end_sec": 90.0}],
        header="HARD LOCKED RANGES",
        body="Each entry is a range the operator MARKED FOR INCLUSION.",
    )
    assert "HARD LOCKED RANGES:" in output
    assert "Each entry is a range the operator MARKED FOR INCLUSION." in output
    # Each range bullet uses one decimal place to match the existing
    # SRT timestamp convention.
    assert "[10.5s, 25.0s]" in output
    assert "[60.0s, 90.0s]" in output


def test_format_range_section_skips_malformed_entries():
    """Non-dict entries, missing keys, non-numeric values, negative
    starts, zero-length ranges (end <= start) all collapse silently.
    The helper never raises — Sacred Contract #3 spirit applies to
    AI-input assembly."""
    from app.features.render.ai.llm.prompts import _format_range_section
    output = _format_range_section(
        [
            None,                                       # not a dict
            "garbage",                                  # string
            {"start_sec": "x", "end_sec": 5},           # non-numeric
            {"start_sec": 10},                          # missing end_sec
            {"start_sec": -5, "end_sec": 10},           # negative start
            {"start_sec": 10, "end_sec": 10},           # zero length
            {"start_sec": 20, "end_sec": 15},           # end < start
            {"start_sec": 30.0, "end_sec": 45.0},       # valid
        ],
        header="HARD LOCKED RANGES",
        body="Lock body.",
    )
    assert "[30.0s, 45.0s]" in output
    # Only the one valid entry made it through.
    assert output.count("[") == 1


def test_format_range_section_returns_empty_when_all_entries_malformed():
    """A list that contains entries but no VALID range collapses to
    empty — there's no point emitting an empty header in the prompt."""
    from app.features.render.ai.llm.prompts import _format_range_section
    output = _format_range_section(
        [{"start_sec": -1, "end_sec": 0}, None, "junk"],
        header="X",
        body="Y",
    )
    assert output == ""


# ---------------------------------------------------------------------------
# 2. build_render_plan_prompt — kwargs reach the rendered prompt.
# ---------------------------------------------------------------------------


def test_prompt_omits_lock_exclude_sections_by_default():
    """Backward-compat: callers that don't pass clip_lock /
    clip_exclude get the pre-Strategic-1 prompt verbatim (no lock /
    exclude section markers)."""
    from app.features.render.ai.llm.prompts import build_render_plan_prompt

    _system, user = build_render_plan_prompt(
        srt_content="1\n00:00:01,000 --> 00:00:05,000\nhello world\n\n",
        output_count=3,
        min_sec=15,
        max_sec=60,
    )
    assert "HARD LOCKED RANGES" not in user
    assert "HARD EXCLUDED RANGES" not in user


def test_prompt_includes_lock_section_when_clip_lock_set():
    """When clip_lock is non-empty, the rendered prompt MUST include
    the HARD LOCKED RANGES section AND each range bullet."""
    from app.features.render.ai.llm.prompts import build_render_plan_prompt

    _system, user = build_render_plan_prompt(
        srt_content="1\n00:00:01,000 --> 00:00:05,000\nhello\n\n",
        output_count=3,
        min_sec=15,
        max_sec=60,
        clip_lock=[{"start_sec": 12.0, "end_sec": 30.0}],
    )
    assert "HARD LOCKED RANGES:" in user
    assert "MUST OVERLAP" in user, (
        "The lock section must explain the OVERLAP rule (the LLM "
        "needs to know that 'lock' means 'at least one clip overlaps'."
    )
    assert "[12.0s, 30.0s]" in user


def test_prompt_includes_exclude_section_when_clip_exclude_set():
    """Symmetric: clip_exclude renders the HARD EXCLUDED RANGES
    section and explains the no-overlap rule."""
    from app.features.render.ai.llm.prompts import build_render_plan_prompt

    _system, user = build_render_plan_prompt(
        srt_content="1\n00:00:01,000 --> 00:00:05,000\nhi\n\n",
        output_count=3,
        min_sec=15,
        max_sec=60,
        clip_exclude=[{"start_sec": 100.0, "end_sec": 120.0}],
    )
    assert "HARD EXCLUDED RANGES:" in user
    assert "NONE of your emitted clips may overlap" in user
    assert "[100.0s, 120.0s]" in user


def test_prompt_includes_both_sections_simultaneously():
    """Both sections can coexist in the same prompt for the same
    clip. The order is lock → exclude (consistent with the operator
    mental model: 'include these, avoid those')."""
    from app.features.render.ai.llm.prompts import build_render_plan_prompt

    _system, user = build_render_plan_prompt(
        srt_content="1\n00:00:01,000 --> 00:00:05,000\nhi\n\n",
        output_count=3,
        min_sec=15,
        max_sec=60,
        clip_lock=[{"start_sec": 10, "end_sec": 30}],
        clip_exclude=[{"start_sec": 100, "end_sec": 120}],
    )
    lock_pos = user.find("HARD LOCKED RANGES:")
    exclude_pos = user.find("HARD EXCLUDED RANGES:")
    assert lock_pos != -1
    assert exclude_pos != -1
    assert lock_pos < exclude_pos, (
        "Lock section MUST precede exclude section to match the "
        "operator mental model 'include these, avoid those'."
    )


# ---------------------------------------------------------------------------
# 3. Dispatcher + providers — kwargs propagate end-to-end.
# ---------------------------------------------------------------------------


def test_dispatcher_signature_accepts_clip_lock_and_clip_exclude():
    """The ``ai.llm.select_render_plan`` dispatcher MUST accept the
    new kwargs. A refactor that drops them silently disables the
    Strategic-1 wiring — the prompt template would still have the
    {clip_lock_section} slot but the kwargs would never reach the
    builder."""
    from app.features.render.ai.llm import select_render_plan
    sig = inspect.signature(select_render_plan)
    assert "clip_lock" in sig.parameters, (
        "Strategic-1 regression — ai.llm.select_render_plan no longer "
        "accepts clip_lock kwarg."
    )
    assert "clip_exclude" in sig.parameters, (
        "Strategic-1 regression — ai.llm.select_render_plan no longer "
        "accepts clip_exclude kwarg."
    )


@pytest.mark.parametrize("module_name", [
    "app.features.render.ai.llm.providers.gemini",
    "app.features.render.ai.llm.providers.openai",
    "app.features.render.ai.llm.providers.claude",
])
def test_provider_signature_accepts_clip_lock_and_clip_exclude(module_name: str):
    """Each provider's select_render_plan MUST accept the new kwargs.
    Dispatcher would crash with TypeError if any provider lacks them."""
    import importlib
    module = importlib.import_module(module_name)
    sig = inspect.signature(module.select_render_plan)
    assert "clip_lock" in sig.parameters, (
        f"Strategic-1 regression — {module_name}.select_render_plan no "
        f"longer accepts clip_lock kwarg."
    )
    assert "clip_exclude" in sig.parameters, (
        f"Strategic-1 regression — {module_name}.select_render_plan no "
        f"longer accepts clip_exclude kwarg."
    )


# ---------------------------------------------------------------------------
# 4. render_pipeline.py call site — payload fields are read.
# ---------------------------------------------------------------------------


def test_orchestrator_passes_clip_lock_and_clip_exclude_to_dispatcher():
    """Source-level guard pinning the wiring at render_pipeline.py.
    A refactor that drops the kwargs reverts Strategic-1 — the
    dispatcher and prompt builder both accept the kwargs but the
    orchestrator never supplies them, so the prompt sections never
    render even when the operator sets the fields."""
    from pathlib import Path
    import re

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "pipeline" / "render_pipeline.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    # The _llm_select_render_plan call must include both kwargs.
    # OPT-02 pre-extracts the values into local variables before the call,
    # so we check (a) kwarg is in the call and (b) payload.clip_lock is read.
    assert re.search(
        r"_llm_select_render_plan\([\s\S]*?clip_lock\s*=",
        source,
    ), (
        "Strategic-1 regression — render_pipeline.py no longer passes "
        "clip_lock= into _llm_select_render_plan. The kwarg cascade is "
        "broken; the prompt section never renders."
    )
    assert re.search(
        r"getattr\(payload,\s*['\"]clip_lock['\"]",
        source,
    ), (
        "Strategic-1 regression — render_pipeline.py no longer reads "
        "payload.clip_lock before passing to _llm_select_render_plan."
    )
    assert re.search(
        r"_llm_select_render_plan\([\s\S]*?clip_exclude\s*=",
        source,
    ), (
        "Strategic-1 regression — render_pipeline.py no longer passes "
        "clip_exclude= into _llm_select_render_plan."
    )
    assert re.search(
        r"getattr\(payload,\s*['\"]clip_exclude['\"]",
        source,
    ), (
        "Strategic-1 regression — render_pipeline.py no longer reads "
        "payload.clip_exclude before passing to _llm_select_render_plan."
    )


# ---------------------------------------------------------------------------
# 5. Public surface — clip_lock / clip_exclude restored.
# ---------------------------------------------------------------------------


def test_clip_lock_and_clip_exclude_are_in_public_surface():
    """The wire endpoint must accept the two fields. T1.4 stripped
    them; Strategic-1 puts them back so operator-supplied lock /
    exclude lists reach the BE."""
    from app.models.render_public import FE_FACING_FIELDS

    assert "clip_lock" in FE_FACING_FIELDS, (
        "Strategic-1 regression — clip_lock removed from "
        "FE_FACING_FIELDS. The prompt builder still has the section "
        "but the wire rejects the field with HTTP 422 (extra='forbid')."
    )
    assert "clip_exclude" in FE_FACING_FIELDS, (
        "Strategic-1 regression — clip_exclude removed from "
        "FE_FACING_FIELDS. Same problem as clip_lock."
    )
