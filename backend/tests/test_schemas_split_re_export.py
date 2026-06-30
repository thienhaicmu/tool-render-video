"""Audit MT-2 closure (Batch 10I, 2026-06-06).

``app.models.schemas`` was split by domain:

- ``app.models.render`` — RenderRequest, RenderRequestStrict, TextLayer*,
  PrepareSourceRequest, QuickProcessRequest.
- ``app.models.jobs``   — JobStatusResponse.

``schemas.py`` is now a re-export shim so the 17 existing
``from app.models.schemas import …`` callers continue to work without
edits.

This file is the regression guard: every public class MUST be reachable
via BOTH the new path AND the legacy shim path, and the classes must be
the same object (no accidental duplicate definition).

The schema-defining files (render.py, jobs.py) own the fields,
validators, defaults, and ConfigDict. The shim only re-exports — never
redefines.
"""
from __future__ import annotations

import importlib

import pytest


_PUBLIC_CLASSES = (
    "PrepareSourceRequest",
    "QuickProcessRequest",
    "TextLayerOutline",
    "TextLayerShadow",
    "TextLayerBackground",
    "TextLayerConfig",
    "RenderRequest",
    "RenderRequestStrict",
)

_JOB_CLASSES = ("JobStatusResponse",)


def test_shim_path_re_exports_render_classes():
    from app.models import schemas, render
    for name in _PUBLIC_CLASSES:
        assert hasattr(schemas, name), (
            f"app.models.schemas.{name} disappeared. The shim must re-export "
            "every render-tier class so the 17 legacy import sites keep working."
        )
        shim_cls = getattr(schemas, name)
        new_cls = getattr(render, name)
        assert shim_cls is new_cls, (
            f"app.models.schemas.{name} is NOT the same object as "
            f"app.models.render.{name}. Someone re-defined the class instead "
            "of re-exporting — schema drift hazard. Sacred Contract #2."
        )


def test_shim_path_re_exports_job_classes():
    from app.models import schemas, jobs
    for name in _JOB_CLASSES:
        assert hasattr(schemas, name)
        shim_cls = getattr(schemas, name)
        new_cls = getattr(jobs, name)
        assert shim_cls is new_cls, (
            f"app.models.schemas.{name} is NOT the same object as "
            f"app.models.jobs.{name}. The shim must re-export only."
        )


def test_render_module_does_not_depend_on_shim():
    """The new modules must not re-import from the shim (would create a
    bootstrap cycle if anyone ever moves a class back into schemas.py)."""
    src = (
        importlib.import_module("app.models.render")
        .__file__
    )
    with open(src, "r", encoding="utf-8") as f:
        text = f.read()
    assert "from app.models.schemas" not in text
    assert "import app.models.schemas" not in text


def test_jobs_module_does_not_depend_on_shim():
    src = (
        importlib.import_module("app.models.jobs")
        .__file__
    )
    with open(src, "r", encoding="utf-8") as f:
        text = f.read()
    assert "from app.models.schemas" not in text
    assert "import app.models.schemas" not in text


def test_render_request_field_count_unchanged():
    """RenderRequest is a Sacred Contract surface. The split must not
    have added or dropped a field — only relocated the class."""
    from app.models.render import RenderRequest

    field_count = len(RenderRequest.model_fields)
    # 151 fields after output_mode removal (2026-06-09 — field was unused,
    # always "manual", all callers cleaned up). Previously 152 at MT-2 close.
    # 2026-06-27 ai_rewrite feature: +1 (rewrite_tone, default "") → 153.
    # Sacred Contract #2 verified: rewrite_tone defaults to "" (non-active).
    # 2026-06-29 reaction feature: +1 (narration_mode, default "") → 154.
    # Sacred Contract #2 verified: narration_mode defaults to "" (non-active).
    # 2026-06-29 recap R1: +1 (render_format, default "clips") → 155.
    # Sacred Contract #2 verified: render_format defaults to "clips" (current behaviour).
    # 2026-07 N4: +1 (reaction_intensity, default "") → 156.
    # 2026-06-30 C.1 Phase 1: +1 (use_story_intelligence, default False) → 157.
    # Sacred Contract #2 verified: use_story_intelligence defaults to False
    # (Clip path runs without Comprehension stage — bit-identical to pre-C.1).
    assert field_count == 157, (
        f"RenderRequest now has {field_count} fields (expected 157 post-C.1-Phase-1). "
        "If a legitimate new field landed, update this test AND verify "
        "Sacred Contract #2 (new field defaults to disabled state)."
    )


def test_render_request_strict_inherits_from_render_request():
    """RenderRequestStrict is a subclass — every RenderRequest field MUST
    exist on Strict, with the only difference being extra='forbid'."""
    from app.models.render import RenderRequest, RenderRequestStrict

    assert issubclass(RenderRequestStrict, RenderRequest)
    assert RenderRequestStrict.model_config.get("extra") == "forbid"
    assert RenderRequest.model_config.get("extra") == "ignore"


def test_render_request_validators_preserved():
    """The duration / range / profile validators must all still be wired
    on the moved class. Tested by behaviour, not introspection — a
    missing validator would let an out-of-range value through."""
    from app.models.render import RenderRequest

    rr = RenderRequest(target_duration=999)
    assert rr.target_duration <= 350, "target_duration validator missing — accepted 999"

    rr2 = RenderRequest(output_count=999)
    assert rr2.output_count <= 20, "output_count validator missing — accepted 999"

    # Render profile validator should reject unknowns.
    with pytest.raises(Exception):
        RenderRequest(render_profile="not_a_real_profile")

    # Source quality mode validator should reject unknowns.
    with pytest.raises(Exception):
        RenderRequest(source_quality_mode="not_a_real_mode")


def test_api_key_strip_validator_still_fires(caplog):
    """The Cloud LLM credential policy guard must survive the move —
    a non-empty api_key field must be silently stripped to None."""
    import logging
    from app.models.render import RenderRequest

    caplog.set_level(logging.WARNING, logger="app.api.security")
    rr = RenderRequest(gemini_api_key="ya29.fake")
    assert rr.gemini_api_key is None
    assert any("RenderRequest received a non-empty *_api_key" in r.message
               for r in caplog.records)
