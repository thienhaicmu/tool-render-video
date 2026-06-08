"""Strategic-2 closure regression guard — Audit 2026-06-08.

Pre-Strategic-2 the LLM's per-clip ``RenderPlan.clips[i].title`` was
DISPLAY ONLY:
- ``_scored_from_render_plan`` at render_pipeline.py:267 copies the
  title into ``seg["ai_title"]``.
- That value flows to ``result_json[segments].ai_title`` and is
  surfaced via the parts HTTP endpoint (`/api/jobs/{id}/parts`) so
  the FE can show it as part metadata.
- BUT the value was never composed into a text overlay on the
  rendered MP4. The Batch A audit (Phase 7 mismatch table) flagged
  this as one of the highest "AI's creative output is wasted" items.

Strategic-2 wires ``seg["ai_title"]`` into the per-clip hook overlay
text resolution. ``resolve_hook_overlay_text`` gains an ``ai_title``
kwarg as a new priority-2 source (between operator-explicit override
and SRT-first-block fallback). ``part_asset_planner.prepare_part_
assets`` reads ``seg.get("ai_title")`` and passes it to the resolver.

The result: when the AI provides a per-clip title and the operator
has NOT set an explicit hook text, the AI's title now appears as the
visual hook overlay (top-center, large font, 0-2.5s into the clip)
on the rendered output.

This file pins the resolver's behaviour across the four priority
slots.
"""
from __future__ import annotations

import pytest

from app.features.render.engine.subtitle.processing.text_transforms import (
    resolve_hook_overlay_text,
)


# ---------------------------------------------------------------------------
# 1. ai_title as the source when nothing else is set.
# ---------------------------------------------------------------------------


def test_ai_title_is_used_when_no_explicit_and_no_srt():
    """The new priority slot: ai_title becomes the hook text when the
    operator has not set an explicit override and no SRT is supplied."""
    text, source = resolve_hook_overlay_text(
        hook_applied_text=None,
        srt_path=None,
        ai_title="The hook everyone missed",
    )
    assert text == "The hook everyone missed"
    assert source == "ai_title"


def test_ai_title_blank_falls_through_to_srt_or_empty():
    """An empty / whitespace-only ai_title doesn't shortcut the
    pipeline — the resolver continues to the SRT fallback (or returns
    empty when no SRT is supplied)."""
    text, source = resolve_hook_overlay_text(
        hook_applied_text=None,
        srt_path=None,
        ai_title="   ",
    )
    assert text == ""
    assert source == "no_suitable_text"


def test_ai_title_none_behaves_as_before():
    """Backward compatibility: callers that don't pass ai_title (the
    default None) get the pre-Strategic-2 behaviour exactly."""
    text, source = resolve_hook_overlay_text(
        hook_applied_text=None,
        srt_path=None,
    )
    assert text == ""
    assert source == "no_suitable_text"


# ---------------------------------------------------------------------------
# 2. Explicit operator override always wins over ai_title.
# ---------------------------------------------------------------------------


def test_explicit_hook_text_wins_over_ai_title():
    """The operator's explicit hook_applied_text is the highest
    priority — Strategic-2 must NOT silently override an operator
    intent. If the operator set a hook string, the AI's title is
    ignored even when both are present."""
    text, source = resolve_hook_overlay_text(
        hook_applied_text="Operator chose this",
        srt_path=None,
        ai_title="AI proposed this",
    )
    assert text == "Operator chose this"
    assert source == "explicit"


def test_explicit_whitespace_falls_through_to_ai_title():
    """A whitespace-only explicit hook is treated as 'unset' — the
    resolver falls through to the next priority. This mirrors the
    pre-Strategic-2 behaviour for the SRT-fallback case."""
    text, source = resolve_hook_overlay_text(
        hook_applied_text="   ",
        srt_path=None,
        ai_title="AI proposed this",
    )
    assert text == "AI proposed this"
    assert source == "ai_title"


# ---------------------------------------------------------------------------
# 3. ai_title takes precedence over the SRT-first-block fallback.
# ---------------------------------------------------------------------------


def test_ai_title_preferred_over_srt_first_block(tmp_path):
    """When ai_title AND srt_path are both supplied, ai_title wins —
    the AI's creative text is preferred over a generic lift from the
    transcript."""
    srt_file = tmp_path / "sample.srt"
    srt_file.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nFirst transcript line here\n\n",
        encoding="utf-8",
    )
    text, source = resolve_hook_overlay_text(
        hook_applied_text=None,
        srt_path=str(srt_file),
        ai_title="AI chose this hook",
    )
    assert text == "AI chose this hook"
    assert source == "ai_title"


def test_srt_fallback_still_runs_when_ai_title_is_unset(tmp_path):
    """When ai_title is unset and srt is provided, the resolver falls
    through to the SRT first block — the pre-Strategic-2 behaviour
    is preserved for legacy paths."""
    srt_file = tmp_path / "fallback.srt"
    srt_file.write_text(
        "1\n00:00:00,000 --> 00:00:02,000\nFallback transcript line\n\n",
        encoding="utf-8",
    )
    text, source = resolve_hook_overlay_text(
        hook_applied_text=None,
        srt_path=str(srt_file),
    )
    assert text == "Fallback transcript line"
    assert source == "subtitle_first_block"


# ---------------------------------------------------------------------------
# 4. Cleaning rules apply to ai_title (whitespace, ASS tags, case).
# ---------------------------------------------------------------------------


def test_ai_title_is_truncated_to_max_words():
    """Long titles must be word-truncated to max_words just like the
    explicit / SRT sources. The default cap is 10."""
    text, source = resolve_hook_overlay_text(
        hook_applied_text=None,
        srt_path=None,
        ai_title="This is a very long hook title that exceeds the default cap easily",
    )
    assert source == "ai_title"
    # Should be exactly 10 words.
    assert len(text.split()) == 10
    assert text.startswith("This is a very long hook title that exceeds the")


def test_ai_title_all_caps_converted_to_title_case():
    """Strident all-caps titles (>3 words) get title-cased — the
    cleaner rule that pre-Strategic-2 also applied to explicit and
    SRT sources. Preserves operator intent without screaming."""
    text, source = resolve_hook_overlay_text(
        hook_applied_text=None,
        srt_path=None,
        ai_title="THIS IS LOUD HOOK TEXT",
    )
    assert source == "ai_title"
    assert text == "This Is Loud Hook Text"


def test_ai_title_ass_override_tags_stripped():
    """ASS override tags like ``{\\b1}`` must be stripped — these are
    artefacts from a re-emitted SRT-derived title and would render as
    literal text in the overlay."""
    text, source = resolve_hook_overlay_text(
        hook_applied_text=None,
        srt_path=None,
        ai_title="{\\b1}Bold{\\b0} ai hook text",
    )
    assert source == "ai_title"
    assert text == "Bold ai hook text"


# ---------------------------------------------------------------------------
# 5. Anti-regression — part_asset_planner threads seg["ai_title"] in.
# ---------------------------------------------------------------------------


def test_part_asset_planner_reads_seg_ai_title():
    """Source-level guard pinning the wiring in part_asset_planner.py:
    the resolver is called with ``ai_title=`` kwarg derived from
    ``seg.get('ai_title')``. A future refactor that drops this kwarg
    reverts ai_title to display-only (Batch A V8-C2 regression
    territory)."""
    from pathlib import Path
    import re

    src_path = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "stages" / "part_asset_planner.py"
    )
    source = src_path.read_text(encoding="utf-8-sig")

    # The literal seg.get("ai_title") read must appear.
    assert re.search(r'seg\.get\(\s*[\'"]ai_title[\'"]\s*\)', source), (
        "Strategic-2 regression — part_asset_planner.py no longer reads "
        "seg.get('ai_title'). The AI's per-clip title once again "
        "becomes display-only and is never composed into the hook "
        "overlay. Restore the seg.get('ai_title') read alongside the "
        "resolve_hook_overlay_text call."
    )

    # The resolve_hook_overlay_text call must pass ai_title=.
    assert re.search(
        r"resolve_hook_overlay_text\([^)]*\bai_title\s*=",
        source,
        flags=re.DOTALL,
    ), (
        "Strategic-2 regression — the resolve_hook_overlay_text "
        "call no longer forwards ai_title=. Restore the kwarg."
    )
