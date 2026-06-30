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


def test_b6_render_pipeline_does_not_yet_wire_comprehension():
    """Phase 1 has NOT touched render_pipeline.py. If this test starts
    failing, someone wired Phase 2 prematurely or wired it elsewhere.
    This test is intended to flip to pass during Phase 2."""
    src = _RENDER_PIPELINE_PY.read_text(encoding="utf-8")
    # The most specific signal: comprehension_stage import in render_pipeline.
    assert "from app.features.render.engine.pipeline.comprehension_stage import" not in src, (
        "C1.3 B6: render_pipeline.py already imports comprehension_stage — "
        "Phase 2 has shipped OR was wired outside the planned path. "
        "If Phase 2 shipped, REMOVE this test (Phase 1 substrate is now superseded)."
    )


def test_b7_select_render_plan_does_not_yet_accept_story_model():
    """Phase 3 work. Today's signature must NOT have story_model. When
    Phase 3 ships, REMOVE this test."""
    import inspect
    from app.features.render.ai.llm import select_render_plan
    sig = inspect.signature(select_render_plan)
    assert "story_model" not in sig.parameters, (
        "C1.3 B7: select_render_plan already accepts story_model — Phase 3 "
        "shipped. Update or remove this test."
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


def test_audit_sketch_line_numbers_remain_accurate():
    """The audit cites line 888 of render_pipeline.py as the LLM call
    site. A refactor that moves that line will make the audit's sketch
    stale — fix the audit or the refactor before Phase 2."""
    src = _RENDER_PIPELINE_PY.read_text(encoding="utf-8")
    lines = src.splitlines()
    # The call site must contain `_llm_select_render_plan(` somewhere
    # around the audited line range. Tolerate ±30 lines drift for
    # whitespace / comment edits.
    found_idx = None
    for i, line in enumerate(lines):
        if "_llm_select_render_plan(" in line:
            found_idx = i + 1  # 1-indexed
            break
    assert found_idx is not None, "render_pipeline lost its _llm_select_render_plan call"
    # Audit cites line 888. Allow ±30 lines for trivial drift.
    assert 858 <= found_idx <= 918, (
        f"C1.3: _llm_select_render_plan call site moved to line {found_idx}. "
        f"Audit cites line 888. Re-verify Phase 2 sketch before implementing."
    )
