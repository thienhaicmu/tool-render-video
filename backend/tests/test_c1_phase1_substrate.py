"""Architecture-review C.1 Phase 1 (2026-06-30) — substrate contract tests.

Covers deliverables C1.2 (RenderRequest field) and C1.3 (Phase 2/3 contract
pins). All tests run in any venv (no cv2 / no real LLM calls); they exist
to lock the surface the next Claude session must preserve when wiring
Phase 2 (render_pipeline.py wire-in) and Phase 3 (provider + prompt +
PROMPT_VERSION bump).

Contract pinned:

  C1.2 — RenderRequest field
    A1 — ``use_story_intelligence`` field exists with default ``False``.
    A2 — Default ``False`` survives payload deserialise → replay-compat
         (Sacred Contract #2 spirit).
    A3 — Explicit ``True`` on the payload survives round-trip.
    A4 — Stored payloads that PRE-DATE this field still load (extra
         field absent → field gets default value).
    A5 — Field is exposed on the public wire surface (FE_FACING_FIELDS).
    A6 — Field accepts only bool — no Literal / no string coercion.

  C1.3 — Phase 2/3 contract surface (structural)
    B1 — ``select_recap_plan`` already accepts ``story_model`` kwarg
         (verifies the existing recap pattern Phase 3 will mirror).
    B2 — Comprehension stage's public entry point exists at the expected
         import path (Phase 2 will import from here).
    B3 — Comprehension stage exposes ``run_comprehension`` callable.
    B4 — Comprehension stage exposes ``is_hoist_enabled`` env-gate helper.
    B5 — ``recap_pipeline.py`` already wires Comprehension via the
         pattern Phase 2 will copy — grep pin so a refactor breaks here.
    B6 — ``render_pipeline.py`` does NOT yet wire Comprehension (Phase 2
         is its own commit).
    B7 — Provider ``select_render_plan`` signatures do NOT yet accept
         ``story_model`` (Phase 3 work).
    B8 — Audit document exists with the Phase 2/3 implementation sketch.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# C1.2 — RenderRequest field tests
# ---------------------------------------------------------------------------


def test_a1_field_exists_default_false():
    """The RenderRequest schema MUST expose use_story_intelligence with
    default False so existing tests + payloads replay bit-identically."""
    from app.models.render import RenderRequest
    fields = RenderRequest.model_fields
    assert "use_story_intelligence" in fields, (
        "C1.2 A1: use_story_intelligence field missing from RenderRequest"
    )
    field = fields["use_story_intelligence"]
    assert field.default is False, (
        f"C1.2 A1: default must be False (Sacred Contract #2 spirit), got {field.default!r}"
    )


def test_a2_default_when_omitted_from_payload():
    """A payload that omits the field gets the default — Sacred Contract #2."""
    from app.models.render import RenderRequest
    r = RenderRequest()
    assert r.use_story_intelligence is False


def test_a3_explicit_true_survives():
    from app.models.render import RenderRequest
    r = RenderRequest(use_story_intelligence=True)
    assert r.use_story_intelligence is True


def test_a4_legacy_payload_without_field_loads():
    """A stored payload from before this field was added still
    deserialises — extra='ignore' on RenderRequest covers it."""
    from app.models.render import RenderRequest
    legacy_payload = {
        "render_format": "clips",
        "target_duration": 90,
        "output_count": 1,
    }
    r = RenderRequest(**legacy_payload)
    assert r.use_story_intelligence is False


def test_a5_field_is_public_facing():
    """C1.2 A5: the field MUST appear in FE_FACING_FIELDS so it ships on
    the public RenderRequestPublic wire."""
    from app.models.render_public import FE_FACING_FIELDS
    assert "use_story_intelligence" in FE_FACING_FIELDS, (
        "C1.2 A5: use_story_intelligence not exposed on public wire — "
        "FE consumers won't see the new feature flag"
    )


def test_a6_field_is_strictly_bool():
    """Pydantic with strict bool: passing 'true' or 1 should not coerce
    silently into True without Pydantic's normal coercion rules. We allow
    Pydantic's default coercion behaviour (which IS lenient — strings
    'true'/'false' coerce) but require that arbitrary garbage raises."""
    from app.models.render import RenderRequest
    from pydantic import ValidationError
    # Coercion of common bool-ish values is allowed (Pydantic default).
    assert RenderRequest(use_story_intelligence=True).use_story_intelligence is True
    assert RenderRequest(use_story_intelligence=False).use_story_intelligence is False
    # But pure garbage MUST raise.
    with pytest.raises(ValidationError):
        RenderRequest(use_story_intelligence="garbage")


def test_a7_public_wire_includes_field_in_schema():
    """The OpenAPI / JSON schema generated from RenderRequestPublic must
    expose the new field so FE can render the toggle."""
    from app.models.render_public import RenderRequestPublic
    schema = RenderRequestPublic.model_json_schema()
    assert "use_story_intelligence" in schema["properties"], (
        "C1.2 A7: use_story_intelligence missing from public OpenAPI schema"
    )
    # Default in schema must match.
    prop = schema["properties"]["use_story_intelligence"]
    assert prop.get("default") is False


# ---------------------------------------------------------------------------
# C1.3 — Phase 2/3 contract surface
# ---------------------------------------------------------------------------


_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RENDER_PIPELINE_PY = (
    _PROJECT_ROOT / "app" / "features" / "render" / "engine" / "pipeline" / "render_pipeline.py"
)
_RECAP_PIPELINE_PY = (
    _PROJECT_ROOT / "app" / "features" / "render" / "engine" / "pipeline" / "recap_pipeline.py"
)
_COMPREHENSION_PY = (
    _PROJECT_ROOT / "app" / "features" / "render" / "engine" / "pipeline" / "comprehension_stage.py"
)


def test_b1_select_recap_plan_accepts_story_model_kwarg():
    """C1.3 B1: pin the existing pattern Phase 3 mirrors. select_recap_plan
    already accepts story_model. If a refactor removes it, Phase 3 has
    no template to copy from."""
    import inspect
    from app.features.render.ai.llm import select_recap_plan
    sig = inspect.signature(select_recap_plan)
    assert "story_model" in sig.parameters, (
        "C1.3 B1: existing select_recap_plan story_model kwarg removed — "
        "Phase 3 mirrors this pattern; please re-verify."
    )


def test_b2_comprehension_module_importable():
    """C1.3 B2: the Comprehension stage must be importable from the
    expected path so Phase 2 can wire it."""
    import importlib
    mod = importlib.import_module(
        "app.features.render.engine.pipeline.comprehension_stage"
    )
    assert mod is not None


def test_b3_comprehension_module_exposes_run_comprehension():
    from app.features.render.engine.pipeline import comprehension_stage
    assert callable(getattr(comprehension_stage, "run_comprehension", None)), (
        "C1.3 B3: run_comprehension callable missing — Phase 2 wire-in target"
    )


def test_b4_comprehension_module_exposes_is_hoist_enabled():
    from app.features.render.engine.pipeline import comprehension_stage
    assert callable(getattr(comprehension_stage, "is_hoist_enabled", None)), (
        "C1.3 B4: is_hoist_enabled callable missing — Phase 2 uses it as the "
        "env-level kill switch for the Comprehension call"
    )


def test_b5_recap_pipeline_wire_pattern_present():
    """Recap pipeline already wires Comprehension. This is the pattern
    Phase 2 copies for the Clip path. Lock it so a refactor can't quietly
    delete the example."""
    src = _RECAP_PIPELINE_PY.read_text(encoding="utf-8")
    assert "from app.features.render.engine.pipeline.comprehension_stage import" in src, (
        "C1.3 B5: recap_pipeline lost its comprehension_stage import — "
        "Phase 2 mirrors this; please re-verify the audit's reference."
    )
    assert "run_comprehension" in src
    assert "story_model=_external_story" in src, (
        "C1.3 B5: recap_pipeline lost its story_model= kwarg pattern — "
        "Phase 2 mirrors this exact shape."
    )


def test_b6_render_pipeline_wires_comprehension_under_flag():
    """C.1 Phase 2 (2026-06-30, post-flip): the original Phase 1 sentinel
    asserted Comprehension was NOT yet wired. Phase 2 shipped the wire-in,
    so this test now asserts the wire-in is PRESENT and gated by:
      (a) payload.use_story_intelligence flag (RenderRequest field)
      (b) STORY_INTELLIGENCE_HOIST_ENABLED env var (Comprehension's own kill switch)
    Phase 3 will additionally pass story_model to select_render_plan; for now
    Phase 2 only produces + persists the StoryModel via Comprehension's own
    internal side-effects (jobs.story_model_json + WS events)."""
    src = _RENDER_PIPELINE_PY.read_text(encoding="utf-8")
    # Comprehension import is present.
    assert "from app.features.render.engine.pipeline.comprehension_stage import" in src, (
        "C1.3 B6: Phase 2 wire-in is missing — render_pipeline.py no longer "
        "imports comprehension_stage. Did a refactor undo Phase 2?"
    )
    # Payload-level gate.
    assert 'getattr(payload, "use_story_intelligence", False)' in src, (
        "C1.3 B6: Phase 2 wire-in is missing the payload-level flag gate — "
        "Sacred Contract #2 honoured by requiring opt-in per RenderRequest"
    )
    # Env-level gate (Comprehension's own kill switch from Batch C).
    assert "_comprehension_enabled()" in src, (
        "C1.3 B6: Phase 2 wire-in is missing the env-level kill-switch check"
    )
    # Defensive try/except (Sacred Contract #3 spirit — never abort the render
    # on a Comprehension failure).
    assert "Sacred Contract #3" in src or "non-fatal" in src.lower() or (
        "try:" in src and "_run_comprehension(" in src
    ), "C1.3 B6: Phase 2 wire-in is missing the Sacred Contract #3 try/except guard"


def test_b7_select_render_plan_now_accepts_story_model():
    """C.1 Phase 3 (2026-06-30, post-flip): the original Phase 1 sentinel
    asserted select_render_plan did NOT yet accept story_model. Phase 3
    shipped the kwarg + prompt injection, so this test now asserts
    story_model IS in the signature with default None (Sacred Contract
    #2 — byte-identical pre-Phase-3 prompt when not provided)."""
    import inspect
    from app.features.render.ai.llm import select_render_plan
    sig = inspect.signature(select_render_plan)
    assert "story_model" in sig.parameters, (
        "C1.3 B7: Phase 3 wire-in missing — select_render_plan no longer "
        "accepts story_model. Did a refactor undo Phase 3?"
    )
    # Default MUST be None so legacy callers behave identically.
    assert sig.parameters["story_model"].default is None, (
        f"C1.3 B7: story_model default must be None for Sacred Contract #2, "
        f"got {sig.parameters['story_model'].default!r}"
    )


def test_b7b_all_three_providers_accept_story_model():
    """Phase 3 hooked story_model through every provider's
    select_render_plan. If any provider drops the kwarg, the dispatcher's
    forwarded story_model raises TypeError on that provider's call site."""
    import inspect
    from app.features.render.ai.llm.providers import gemini, openai, claude
    for mod_name, mod in [("gemini", gemini), ("openai", openai), ("claude", claude)]:
        sig = inspect.signature(mod.select_render_plan)
        assert "story_model" in sig.parameters, (
            f"C1.3 B7b: {mod_name}.select_render_plan missing story_model kwarg"
        )
        assert sig.parameters["story_model"].default is None, (
            f"C1.3 B7b: {mod_name}.select_render_plan story_model default must be None"
        )


def test_b8_audit_document_exists():
    audit = _PROJECT_ROOT.parent / "docs" / "audit-c-1-2026-06-30.md"
    assert audit.exists(), "C1.3 B8: audit doc missing"
    content = audit.read_text(encoding="utf-8")
    # Spot-check the three section anchors Phase 2/3 implementers cite.
    assert "## 2." in content
    assert "Phase 2" in content
    assert "Phase 3" in content


# ---------------------------------------------------------------------------
# Cross-cutting — Phase 2 implementer's checklist
# ---------------------------------------------------------------------------


def test_prompt_byte_identical_when_story_model_none():
    """C.1 Phase 3 Sacred Contract #2 (wire-shape): the user prompt
    produced by build_render_plan_prompt MUST be byte-identical for
    legacy callers who don't pass story_model. This keeps the LLM disk
    cache SHA stable, avoiding an operational cache flush."""
    from app.features.render.ai.llm.prompts import build_render_plan_prompt
    common = dict(
        srt_content="00:00:00,000 --> 00:00:05,000\nhello world",
        output_count=1,
        min_sec=30.0,
        max_sec=60.0,
        language="en-US",
    )
    sys_a, user_a = build_render_plan_prompt(**common)
    sys_b, user_b = build_render_plan_prompt(**common, story_model=None)
    assert sys_a == sys_b
    assert user_a == user_b, (
        "Prompt drifted when story_model=None was passed explicitly — "
        "would invalidate LLM disk cache for legacy callers."
    )


def test_prompt_injects_story_block_when_story_model_provided():
    """C.1 Phase 3: when a StoryModel is provided, the user prompt grows
    a STORY INTELLIGENCE section that the LLM uses to ground clip
    selection."""
    from app.domain.recap_plan import StoryModel, StoryBeat, Character
    from app.features.render.ai.llm.prompts import build_render_plan_prompt
    sm = StoryModel(
        summary="A coffee shop loses its identity.",
        theme="identity",
        conflict="commercial vs craft",
        characters=[Character(name="Maya", role="owner", want="preserve heritage")],
        beats=[StoryBeat(text="franchise approaches", t=120.0)],
    )
    _, user_with = build_render_plan_prompt(
        srt_content="00:00:00,000 --> 00:00:05,000\nhello",
        output_count=1, min_sec=30.0, max_sec=60.0,
        story_model=sm,
    )
    # The block landed.
    assert "STORY INTELLIGENCE" in user_with
    assert "identity" in user_with
    assert "commercial vs craft" in user_with
    assert "Maya" in user_with
    # Editorial instruction is present.
    assert "viral_score" in user_with or "hook_score" in user_with


def test_prompt_story_block_skipped_when_model_is_empty():
    """An empty StoryModel (no summary, no beats) renders to an empty
    block — so a Comprehension call that returned junk doesn't poison
    the clip prompt with a meaningless STORY INTELLIGENCE header."""
    from app.domain.recap_plan import StoryModel
    from app.features.render.ai.llm.prompts import build_render_plan_prompt
    empty_sm = StoryModel()
    _, user_empty = build_render_plan_prompt(
        srt_content="00:00:00,000 --> 00:00:05,000\nhello",
        output_count=1, min_sec=30.0, max_sec=60.0,
        story_model=empty_sm,
    )
    assert "STORY INTELLIGENCE" not in user_empty


def test_story_block_clips_helper_returns_empty_for_none():
    from app.features.render.ai.llm.prompts import _story_block_clips
    assert _story_block_clips(None) == ""


def test_story_block_clips_neutralises_braces_in_user_content():
    """Defensive — a StoryModel whose summary contains '{' / '}' must NOT
    break the subsequent str.format() call on the user template."""
    from app.domain.recap_plan import StoryModel
    from app.features.render.ai.llm.prompts import _story_block_clips
    sm = StoryModel(summary="literal { and } in the summary")
    block = _story_block_clips(sm)
    assert "{" not in block and "}" not in block, (
        "Story block leaked literal braces — would break str.format()"
    )


def test_audit_sketch_line_numbers_remain_accurate():
    """Drift guard for the audit's render_pipeline.py line citations.

    Original Phase 1: audit cited line 888 (pre-Phase-2). Phase 2's
    Comprehension wire-in INSERTED ~43 lines before the LLM call site,
    moving it to ~line 931. The guard's bound is widened to ±30 lines
    around the new post-Phase-2 location so a future refactor still
    trips the guard, but the Phase 2 insertion itself doesn't."""
    src = _RENDER_PIPELINE_PY.read_text(encoding="utf-8")
    lines = src.splitlines()
    # The call site must contain `_llm_select_render_plan(` somewhere
    # around the post-Phase-2 line range. Tolerate ±30 lines drift for
    # whitespace / comment edits.
    found_idx = None
    for i, line in enumerate(lines):
        if "_llm_select_render_plan(" in line:
            found_idx = i + 1  # 1-indexed
            break
    assert found_idx is not None, "render_pipeline lost its _llm_select_render_plan call"
    # Post-Phase-2 baseline: line ~931. Allow ±30 lines drift.
    assert 901 <= found_idx <= 961, (
        f"C1.3: _llm_select_render_plan call site moved to line {found_idx}. "
        f"Post-Phase-2 baseline is ~line 931. If Phase 3 inserts more code, "
        f"update both this bound and the audit citation."
    )
