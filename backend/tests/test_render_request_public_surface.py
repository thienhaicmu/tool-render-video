"""Audit MT-3 phase 1 closure (Batch 10N 2026-06-06).

``RenderRequestPublic`` is the explicit FE-facing slice of
``RenderRequest`` (71 of 152 fields after the T1.4 audit-2026-06-08
cleanup + follow-up + Strategic-1/1c full UP26 restoration; 21 dead
fields removed by T1.4 then 4 restored — 2 by Strategic-1 (clip_lock
/ clip_exclude) and 2 by Strategic-1c (structure_bias /
subtitle_emphasis)). This file pins the contract so
the Public surface can't accidentally drift:

1. ``FE_FACING_FIELDS`` matches the FE TS interface field set.
2. ``RenderRequestPublic.model_fields`` is exactly that set.
3. ``BE_ONLY_FIELDS`` is the complement and the two sets partition
   ``RenderRequest.model_fields`` (no overlap, no gaps).
4. For every Public field, the annotation + default match
   ``RenderRequest`` byte-for-byte — Public stays in lockstep.
5. ``extra="forbid"`` is wired so a future wire switch immediately
   enforces "only Public fields" at the boundary.
6. The model accepts a real FE-shape payload and produces a working
   instance (round-trip via model_dump).

Phase 1 deliberately does NOT switch ``/api/render/process`` to use
Public — that's a wire-contract change that requires a deliberate
follow-up. This file's job is to lock the definition so the wire
switch is mechanical when someone picks it up.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. FE_FACING_FIELDS parity with the TS interface
# ---------------------------------------------------------------------------


_FRONTEND_API_TS = (
    Path(__file__).resolve().parents[2]
    / "frontend" / "src" / "types" / "api.ts"
)


def _fe_field_names_from_ts() -> set[str]:
    """Parse the FE TS file for the field list inside
    ``export interface RenderRequest { ... }``. Cheap regex — the file is
    machine-generated style enough that this is stable. If the FE moves
    to a different declaration form the test will fail loudly."""
    text = _FRONTEND_API_TS.read_text(encoding="utf-8")
    match = re.search(
        r"export interface RenderRequest \{(?P<body>.*?)\}",
        text,
        flags=re.DOTALL,
    )
    if not match:
        pytest.fail("Could not find 'export interface RenderRequest { ... }' in api.ts")
    body = match.group("body")
    names: set[str] = set()
    for line in body.splitlines():
        m = re.match(r"\s+([a-z_]\w*)\??:", line)
        if m:
            names.add(m.group(1))
    return names


def test_fe_facing_set_matches_typescript_interface():
    from app.models.render_public import FE_FACING_FIELDS

    ts_names = _fe_field_names_from_ts()
    assert ts_names, "TS field extraction returned empty — fix the regex"

    only_in_constant = FE_FACING_FIELDS - ts_names
    only_in_ts       = ts_names - FE_FACING_FIELDS

    assert not only_in_constant and not only_in_ts, (
        "FE_FACING_FIELDS drifted from the TS interface in api.ts. "
        f"Only in constant: {sorted(only_in_constant)}. "
        f"Only in TS: {sorted(only_in_ts)}. "
        "Update both sides AND a backwards-compat plan for stored payloads."
    )


# ---------------------------------------------------------------------------
# 2-3. Public model field set + complement partition RenderRequest
# ---------------------------------------------------------------------------


def test_public_model_fields_exactly_match_fe_set():
    from app.models.render_public import FE_FACING_FIELDS, RenderRequestPublic

    public_fields = set(RenderRequestPublic.model_fields.keys())
    assert public_fields == FE_FACING_FIELDS, (
        "RenderRequestPublic field set drifted from FE_FACING_FIELDS. "
        f"Missing: {FE_FACING_FIELDS - public_fields}. "
        f"Extra: {public_fields - FE_FACING_FIELDS}."
    )


def test_public_and_be_only_partition_render_request():
    from app.models.render import RenderRequest
    from app.models.render_public import BE_ONLY_FIELDS, FE_FACING_FIELDS

    all_fields = set(RenderRequest.model_fields.keys())
    assert FE_FACING_FIELDS | BE_ONLY_FIELDS == all_fields, (
        "Public ∪ BE_only must cover every RenderRequest field. "
        f"Uncovered: {all_fields - (FE_FACING_FIELDS | BE_ONLY_FIELDS)}"
    )
    assert FE_FACING_FIELDS & BE_ONLY_FIELDS == set(), (
        "Public ∩ BE_only must be empty (a field can only belong to one). "
        f"Overlap: {FE_FACING_FIELDS & BE_ONLY_FIELDS}"
    )


def test_public_field_count_pinned():
    """T1.4 — Audit 2026-06-08 closure: 69 Public + 83 BE-only = 152
    total (was 88 + 64 = 152 pre-cleanup). The 19-field drop is the
    Batch A V8-B5 + UP26 + UP27 + v2 dead-field removal — see
    backend/app/models/render_public.py:FE_FACING_FIELDS for the full
    per-field rationale. Pinned so adding a field on either side
    without updating the FE TS interface is loud."""
    from app.models.render import RenderRequest
    from app.models.render_public import BE_ONLY_FIELDS, FE_FACING_FIELDS

    assert len(FE_FACING_FIELDS) == 71, f"FE_FACING_FIELDS = {len(FE_FACING_FIELDS)}"
    assert len(BE_ONLY_FIELDS)   == 81, f"BE_ONLY_FIELDS = {len(BE_ONLY_FIELDS)}"
    assert len(RenderRequest.model_fields) == 152, (
        f"RenderRequest has {len(RenderRequest.model_fields)} fields — "
        "MT-3 pin must move together with MT-2's pin."
    )


# ---------------------------------------------------------------------------
# 4. Defaults + annotations stay in lockstep
# ---------------------------------------------------------------------------


def test_public_field_annotations_match_render_request():
    from app.models.render import RenderRequest
    from app.models.render_public import FE_FACING_FIELDS, RenderRequestPublic

    mismatches: list[str] = []
    for name in FE_FACING_FIELDS:
        rr_anno = RenderRequest.model_fields[name].annotation
        pp_anno = RenderRequestPublic.model_fields[name].annotation
        if rr_anno != pp_anno:
            mismatches.append(f"  {name}: RenderRequest={rr_anno!r} Public={pp_anno!r}")
    assert not mismatches, (
        "RenderRequestPublic annotations drifted from RenderRequest. "
        "Public is built via create_model and SHOULD inherit live. "
        "If this fires, the create_model wiring broke:\n"
        + "\n".join(mismatches)
    )


def test_public_field_defaults_match_render_request():
    from app.models.render import RenderRequest
    from app.models.render_public import FE_FACING_FIELDS, RenderRequestPublic

    # Construct a default instance and compare per-field defaults.
    # Some defaults are factory-built (e.g. Field(default_factory=list))
    # so we compare the resolved default values on a fresh model instance
    # rather than the FieldInfo metadata directly.
    rr_defaults = RenderRequest().model_dump()
    pp_defaults = RenderRequestPublic().model_dump()

    mismatches: list[str] = []
    for name in FE_FACING_FIELDS:
        if rr_defaults.get(name) != pp_defaults.get(name):
            mismatches.append(
                f"  {name}: RenderRequest={rr_defaults.get(name)!r} "
                f"Public={pp_defaults.get(name)!r}"
            )
    assert not mismatches, (
        "Resolved field defaults drifted between Public and RenderRequest:\n"
        + "\n".join(mismatches)
    )


# ---------------------------------------------------------------------------
# 5. extra="forbid" wiring
# ---------------------------------------------------------------------------


def test_public_rejects_be_only_fields_at_construction():
    """Sending a BE-only field through Public must raise — that's the
    whole point of the explicit surface."""
    from pydantic import ValidationError

    from app.models.render_public import RenderRequestPublic

    # channel_code is one of the 64 BE-only fields.
    with pytest.raises(ValidationError, match="channel_code"):
        RenderRequestPublic(channel_code="k1")


def test_public_rejects_typo_fields():
    """``extra='forbid'`` is the design — a typo at the wire surfaces as
    a 4xx instantly instead of being silently dropped."""
    from pydantic import ValidationError

    from app.models.render_public import RenderRequestPublic

    with pytest.raises(ValidationError, match="not_a_real_field"):
        RenderRequestPublic(not_a_real_field=True)


# ---------------------------------------------------------------------------
# 6. Smoke: a FE-shape payload round-trips
# ---------------------------------------------------------------------------


def test_public_accepts_realistic_fe_payload():
    """The payload below uses only Public fields and is close to what the
    actual FE buildPayload produces (minus the verbose defaults)."""
    from app.models.render_public import RenderRequestPublic

    payload = {
        "source_mode": "local",
        "source_video_path": "C:/test/video.mp4",
        "output_dir": "C:/out",
        "render_profile": "fast",
        "output_count": 1,
        "add_subtitle": False,
        "voice_enabled": False,
        "motion_aware_crop": False,
        "llm_enabled": True,
        "ai_provider": "gemini",
        "llm_model": "gemini-2.5-flash",
    }
    obj = RenderRequestPublic(**payload)
    dumped = obj.model_dump()
    # All sent fields land verbatim in the dump.
    for k, v in payload.items():
        assert dumped[k] == v, f"{k}: sent={v!r}, dumped={dumped[k]!r}"


def test_public_dump_is_subset_of_render_request_dump():
    """A Public instance's dump should be a strict subset of what the
    equivalent RenderRequest constructed from the same input would dump.
    Pins that Public is a true projection — not a divergent schema."""
    from app.models.render import RenderRequest
    from app.models.render_public import RenderRequestPublic

    payload = {
        "source_video_path": "x.mp4",
        "render_profile": "fast",
        "output_count": 3,
        "voice_enabled": False,
        "add_subtitle": True,
    }
    pp = RenderRequestPublic(**payload).model_dump()
    rr = RenderRequest(**payload).model_dump()
    for k, v in pp.items():
        assert k in rr, f"Public field {k} disappeared from RenderRequest"
        assert rr[k] == v, (
            f"Public dump diverged from RenderRequest dump for {k}: "
            f"Public={v!r}, RenderRequest={rr[k]!r}"
        )
