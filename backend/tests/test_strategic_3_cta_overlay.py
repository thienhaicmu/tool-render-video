"""Strategic-3 closure regression guard — Audit 2026-06-08.

Pre-Strategic-3 the AI's ``RenderPlan.overlays[kind=cta]`` entry was
silently dropped at render_pipeline.py:679-684 — the consumer loop
there only matched ``kind=="hook"`` (Batch A Phase 6.2 finding). The
prompt at ai/llm/prompts.py:153-160 explicitly asks the AI to emit
``kind=cta`` with a ``type`` field (one of ``comment | part_2 |
follow | auto``); the audit confirmed it was wasted intent.

Strategic-3 wires the AI's ``overlays[kind=cta].type`` as a
priority-2 bias on the CTA-type resolution in
``part_asset_planner.py`` (the existing per-clip CTA text
composition). Pre-Strategic-3 the resolution order was:
1. ``payload.cta_type`` (operator-explicit).
2. ``seg["hook_type"]`` (hook-type bias on auto).
3. Library default.

Post-Strategic-3:
1. ``payload.cta_type`` (operator-explicit) — UNCHANGED priority 1.
2. ``RenderPlan.overlays[kind=cta].type`` (AI's intent) — NEW slot.
3. ``seg["hook_type"]`` bias — UNCHANGED.
4. Library default — UNCHANGED.

The actual CTA TEXT remains a library lookup
(``_select_cta_text(content_type, target_platform, cta_type,
variant)``). The AI's ``audio_plan.cta_audio`` string (already wired
pre-Strategic-3) still overrides the library lookup when set.

This file pins the new resolver helper and the integration site.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# 1. Resolver unit tests.
# ---------------------------------------------------------------------------


class _FakeRenderPlan:
    """Minimal RenderPlan shape — only fields the resolver reads."""

    def __init__(self, overlays):
        self.overlays = overlays


class _FakeCtx:
    """Minimal PartRenderContext stub for the resolver."""

    def __init__(self, render_plan=None):
        self.render_plan = render_plan


def _resolver():
    """Import the resolver fresh each test (avoids stale imports)."""
    from app.features.render.engine.stages.part_asset_planner import (
        _resolve_cta_type_from_plan,
    )
    return _resolve_cta_type_from_plan


@pytest.mark.parametrize(
    "cta_type",
    ["comment", "part_2", "follow", "auto"],
)
def test_resolver_returns_allowed_cta_types(cta_type):
    """The four documented CTA types from prompts.py:158 all pass."""
    resolver = _resolver()
    ctx = _FakeCtx(_FakeRenderPlan([
        {"kind": "cta", "type": cta_type},
    ]))
    assert resolver(ctx) == cta_type


def test_resolver_rejects_unknown_type():
    """Defence: a future prompt drift that emits an arbitrary type
    string MUST not smuggle invalid values into the library lookup.
    Returns empty string, caller falls through to the hook-type bias."""
    resolver = _resolver()
    ctx = _FakeCtx(_FakeRenderPlan([
        {"kind": "cta", "type": "subscribe_aggressively_now"},
    ]))
    assert resolver(ctx) == ""


def test_resolver_returns_empty_when_no_render_plan():
    """Legacy renders without a RenderPlan must continue with the
    pre-Strategic-3 CTA resolution (operator + hook_type bias)."""
    resolver = _resolver()
    assert resolver(_FakeCtx(render_plan=None)) == ""


def test_resolver_returns_empty_when_overlays_empty():
    """An empty overlays list (the prompt's canonical 'no overlay
    fits' signal at prompts.py:160) means no AI hint."""
    resolver = _resolver()
    ctx = _FakeCtx(_FakeRenderPlan([]))
    assert resolver(ctx) == ""


def test_resolver_returns_empty_when_only_hook_overlay():
    """A kind=hook entry alone (no kind=cta) returns empty — the
    AI did not emit a CTA hint for this clip."""
    resolver = _resolver()
    ctx = _FakeCtx(_FakeRenderPlan([
        {"kind": "hook", "text": "watch this"},
    ]))
    assert resolver(ctx) == ""


def test_resolver_picks_first_cta_entry():
    """If multiple kind=cta entries appear (shouldn't per the prompt's
    'at most one per kind' rule but the AI could drift), the FIRST
    one wins. The second is ignored — matches the prompt's
    one-per-kind contract."""
    resolver = _resolver()
    ctx = _FakeCtx(_FakeRenderPlan([
        {"kind": "cta", "type": "comment"},
        {"kind": "cta", "type": "follow"},
    ]))
    assert resolver(ctx) == "comment"


def test_resolver_returns_empty_on_first_cta_invalid_does_not_fall_through():
    """When the FIRST cta entry has an invalid type, the resolver
    bails out — does NOT continue scanning for a second cta entry.
    The prompt allows only one kind=cta entry; a stray second one is
    not the canonical signal."""
    resolver = _resolver()
    ctx = _FakeCtx(_FakeRenderPlan([
        {"kind": "cta", "type": "nonsense"},
        {"kind": "cta", "type": "follow"},
    ]))
    assert resolver(ctx) == ""


def test_resolver_does_not_raise_on_malformed_overlay():
    """An overlay entry without ``get`` (e.g. None or string) must not
    blow up the resolver — Sacred Contract #3 spirit. The resolver
    catches and returns empty."""
    resolver = _resolver()
    ctx = _FakeCtx(_FakeRenderPlan([None, "garbage", {"kind": "cta", "type": "comment"}]))
    # The malformed entries surface as AttributeError on .get(); the
    # try/except catches and returns "".
    assert resolver(ctx) == ""


# ---------------------------------------------------------------------------
# 2. Integration with the per-clip CTA composition path.
# ---------------------------------------------------------------------------


def test_resolver_is_called_inside_part_asset_planner_cta_block():
    """Source-level guard: the new resolver is invoked from inside the
    ``if _cta_enabled:`` block in part_asset_planner.py. A refactor
    that drops the call reverts Strategic-3 (overlays[kind=cta]
    silently dropped again)."""
    from pathlib import Path
    import re

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "stages" / "part_asset_planner.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    assert re.search(r"_resolve_cta_type_from_plan\s*\(\s*ctx\s*\)", source), (
        "Strategic-3 regression — part_asset_planner.py no longer "
        "calls _resolve_cta_type_from_plan(ctx). The AI's "
        "overlays[kind=cta].type once again becomes wasted intent. "
        "Restore the call inside the `if _cta_enabled:` CTA block "
        "BEFORE the hook-type bias."
    )


def test_operator_cta_type_wins_over_ai_overlays_type():
    """Source-level guard: the new wiring must gate on
    ``_cta_type == 'auto'`` so an operator-explicit cta_type
    (e.g. ``cta_type='comment'``) ALWAYS wins. Strategic-2 set the
    same operator-priority precedent for ai_title; Strategic-3
    follows."""
    from pathlib import Path
    import re

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "stages" / "part_asset_planner.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    # The gate is `if _cta_type == "auto" and _plan_cta_type and
    # _plan_cta_type != "auto":` — verify it appears in source.
    assert re.search(
        r"_cta_type\s*==\s*\"auto\"\s*and\s*_plan_cta_type\b",
        source,
    ), (
        "Strategic-3 regression — the operator-priority gate "
        "`if _cta_type == 'auto' and _plan_cta_type:` is missing. "
        "Without it, the AI's overlays[kind=cta].type can override "
        "an operator-explicit cta_type — breaks the "
        "operator-intent-preservation pattern Strategic-2 set."
    )


def test_ai_overlays_type_runs_before_hook_type_bias():
    """The Strategic-3 wiring must sit ABOVE the existing hook-type
    bias dict (``{question: comment, humor: comment, reveal: follow,
    ...}``). A reorder that flips them changes priority and breaks
    the documented resolution order in this test file's docstring."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "stages" / "part_asset_planner.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    plan_idx = source.find("_plan_cta_type")
    hook_bias_idx = source.find('"question": "comment"')
    assert plan_idx != -1, "Strategic-3 wiring (_plan_cta_type) is gone"
    assert hook_bias_idx != -1, "Hook-type bias dict is gone (pre-existing logic)"
    assert plan_idx < hook_bias_idx, (
        "Strategic-3 regression — the AI's overlays[kind=cta].type "
        "wiring (_plan_cta_type) must sit ABOVE the hook-type bias "
        "dict. Reordering flips the priority and breaks the documented "
        "resolution order."
    )


def test_render_pipeline_comment_does_not_claim_cta_is_dropped():
    """The Batch A audit noted the stale comment at
    render_pipeline.py:679 claiming `kind=cta is intentionally
    skipped` — that comment is no longer correct after Strategic-3
    (kind=cta IS consumed downstream, just not as a text overlay).
    Pin that the misleading wording is gone."""
    from pathlib import Path

    src = (
        Path(__file__).resolve().parent.parent
        / "app" / "features" / "render" / "engine"
        / "pipeline" / "render_pipeline.py"
    )
    source = src.read_text(encoding="utf-8-sig")

    # The exact pre-Strategic-3 wording was:
    # "kind=cta is intentionally skipped — handled separately by audio_plan.cta_audio"
    # Strategic-3 updates this. Pin that the misleading version is gone.
    assert "kind=cta is intentionally skipped" not in source, (
        "Strategic-3 documentation regression — the stale comment "
        "'kind=cta is intentionally skipped' came back. Post-"
        "Strategic-3 kind=cta IS consumed (in part_asset_planner.py's "
        "CTA-type resolution). Update the comment to reflect actual "
        "behaviour, not the pre-Strategic-3 audit finding."
    )
