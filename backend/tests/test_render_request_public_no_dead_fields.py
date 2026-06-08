"""T1.4 closure regression guard — Audit 2026-06-08 (Batch A V8-B5 + UP26 + UP27 + v2).

T1.4 (commit 0a20349) stripped 19 dead intent fields from the
``RenderRequestPublic`` allow-list — Phase-G zombies, UP26 Pro Timeline
Steering, UP27 ``asset_music_profile``, v2 ``energy_style`` /
``output_language`` / ``narration_style``. The wire used to accept (and
the FE used to send) ~12 of these fields; the backend pipeline read
none of them. Users tweaked knobs that had zero behavioural effect.

This file pins the post-T1.4 surface by asserting that EVERY field
remaining in ``FE_FACING_FIELDS`` has at least one downstream consumer
inside ``backend/app/`` outside of:

- ``models/`` (where the field is defined + validated)
- ``tests/`` (we don't count test references as "real" consumers)
- ``render_public.py`` itself (the allow-list bookkeeping)

If a future change adds a new field to the Public surface without
wiring it to a real consumer, this test fires before that surface
becomes the next batch of dead intent fields.

Whitelist — fields that are LEGITIMATELY allowed to have no engine-side
consumer beyond model validation:

- ``target_duration`` — wired to LLM prompt by T2.4 (commit 7f57475);
  the consumer lives in ``ai/llm/prompts.py``, which IS under app/. So
  no whitelist needed here in practice.

- ``youtube_url`` — kept on the Public surface for legacy stored-job
  inference at ``routes/jobs.py:103-108``; treated as a consumer.

The check is intentionally lax: it tolerates a single keyword grep hit
anywhere under ``backend/app/`` excluding the listed exemption paths.
A pedantic per-field consumer audit lives in the audit report; this
test catches REGRESSIONS, not architectural ideal.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_BACKEND_APP = (
    Path(__file__).resolve().parent.parent / "app"
)


# Paths whose hits do NOT count as "real consumers" — they are
# definition / validation / allow-list bookkeeping or test/audit
# adjacent.
_EXEMPT_PATH_PARTS: tuple[str, ...] = (
    # The model definitions themselves.
    "models" + "/" + "render.py",
    "models" + "/" + "render_public.py",
    "models" + "/" + "render.py".replace("/", ""),  # belt-and-suspenders
    # The schema re-export shim — re-exports the model surface.
    "models" + "/" + "schemas.py",
    # The Pydantic openapi-generated TS interface (not relevant —
    # backend/app/ doesn't contain TS, but tighten the filter).
    "openapi",
)


# Fields that don't need a per-field consumer beyond model validation.
# Justification per field is documented in the docstring above.
_WHITELIST: frozenset[str] = frozenset({
    # No entries currently — every Public field SHOULD have an engine
    # consumer. Add justifications above before adding entries.
})


def _is_exempt_path(path: Path) -> bool:
    s = str(path).replace("\\", "/")
    return any(part in s for part in _EXEMPT_PATH_PARTS)


def _grep_for_field(field: str) -> list[Path]:
    """Return paths under backend/app/ that mention ``field`` (whole-word)
    AND are NOT in the exempt list.

    Whole-word matching is via re.escape + \b boundaries to avoid false
    hits on substrings (e.g. ``llm_model`` matching ``llm_model_xyz``).
    """
    pattern = re.compile(rf"\b{re.escape(field)}\b")
    hits: list[Path] = []
    for path in _BACKEND_APP.rglob("*.py"):
        if _is_exempt_path(path):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if pattern.search(text):
            hits.append(path)
    return hits


def test_every_public_field_has_downstream_consumer():
    """Iterate FE_FACING_FIELDS and assert each name appears in at
    least one .py file under backend/app/ outside of the
    models/render*.py / models/schemas.py definitions.

    A failure here typically means either:
      (a) A new field was added to the Public surface and the FE TS
          interface but the engine wiring was forgotten — the field
          will be silently discarded at render time (the same UI
          deceit class T1.4 just closed).
      (b) A consumer was removed but the field stayed in the Public
          surface — a separate Public allow-list cleanup commit must
          land alongside the consumer removal.

    The error message lists every dead field; copy that list into a
    follow-up commit removing them from FE_FACING_FIELDS AND from
    the FE TS interface (the latter is enforced by
    test_fe_facing_set_matches_typescript_interface).
    """
    from app.models.render_public import FE_FACING_FIELDS

    dead: list[str] = []
    for field in sorted(FE_FACING_FIELDS):
        if field in _WHITELIST:
            continue
        hits = _grep_for_field(field)
        if not hits:
            dead.append(field)

    assert not dead, (
        f"T1.4 regression — {len(dead)} field(s) in FE_FACING_FIELDS "
        f"have no consumer outside models/. Either wire them into the "
        f"engine or remove them from the Public surface AND the FE TS "
        f"interface. Dead fields: {dead}"
    )


def test_known_phase_g_zombies_NOT_in_public_surface():
    """Defence-in-depth: explicitly assert that the 11 Phase-G zombies
    T1.4 removed cannot creep back. If a future change re-introduces
    ``ai_director_enabled`` (etc.) to the Public surface, this test
    fires loudly — even before the consumer-audit catches the missing
    wiring.
    """
    from app.models.render_public import FE_FACING_FIELDS

    phase_g_zombies = frozenset({
        "ai_director_enabled",
        "ai_auto_cut",
        "ai_use_semantic_hooks",
        "ai_render_influence_enabled",
        "ai_beat_pulse_enabled",
        "ai_cloud_enabled",
        "ai_cloud_provider",
        "ai_cloud_api_key",
        "ai_cloud_model",
        "ai_analysis_mode",
        "ai_content_driven_selection",
    })

    leaked = phase_g_zombies & FE_FACING_FIELDS
    assert not leaked, (
        f"T1.4 regression — Phase-G zombie field(s) reappeared in "
        f"FE_FACING_FIELDS: {sorted(leaked)}. These are gated by "
        f"ctx.ai_edit_plan which is hardcoded None at "
        f"render_pipeline.py:931; surfacing them as toggles is "
        f"UI deceit. Remove from render_public.py:FE_FACING_FIELDS "
        f"AND from frontend/src/types/api.ts."
    )


def test_known_up26_dead_NOT_in_public_surface():
    """The UP26 Pro Timeline Steering fields that REMAIN dead must
    stay out of the Public surface. ``structure_bias`` and
    ``subtitle_emphasis`` have no LLM consumer (no prompt wiring) and
    no local filter — they would re-enter as UI deceit if added back.

    Strategic-1 — Audit 2026-06-08 closure: ``clip_lock`` and
    ``clip_exclude`` were RESTORED to the Public surface by
    Strategic-1 because the LLM prompt now consumes them
    (ai/llm/prompts.py:_format_range_section). The dead set is now
    just the two unwired UP26 fields."""
    from app.models.render_public import FE_FACING_FIELDS

    up26_dead_remaining = frozenset({
        "structure_bias", "subtitle_emphasis",
    })
    leaked = up26_dead_remaining & FE_FACING_FIELDS
    assert not leaked, (
        f"T1.4 regression — UP26 STILL-DEAD field(s) reappeared in "
        f"FE_FACING_FIELDS: {sorted(leaked)}. {sorted(up26_dead_remaining)} "
        f"have no LLM consumer and no local filter. Re-introducing "
        f"them without a consumer reverts to UI deceit."
    )

    # Strategic-1 guard: clip_lock and clip_exclude MUST stay in the
    # Public surface (the LLM prompt template includes them as
    # {clip_lock_section} / {clip_exclude_section}).
    up26_restored = frozenset({"clip_lock", "clip_exclude"})
    missing = up26_restored - FE_FACING_FIELDS
    assert not missing, (
        f"Strategic-1 regression — UP26 wired field(s) disappeared from "
        f"FE_FACING_FIELDS: {sorted(missing)}. The LLM prompt template "
        f"requires these be passed through render_pipeline.py:_llm_select_render_plan; "
        f"removing them from the Public surface breaks the wire even "
        f"though the prompt slots still exist."
    )


def test_v2_vision_dead_NOT_in_public_surface():
    """The 3 v2 vision fields T1.4 removed (energy_style,
    output_language, narration_style) had no engine consumer. The 4th
    v2 field, ``target_duration``, was KEPT for T2.4 wiring — and
    T2.4 (commit 7f57475) wired it into the LLM prompt — so it stays
    in the Public surface."""
    from app.models.render_public import FE_FACING_FIELDS

    v2_dead = frozenset({
        "energy_style", "output_language", "narration_style",
    })
    leaked = v2_dead & FE_FACING_FIELDS
    assert not leaked, (
        f"T1.4 regression — v2 vision dead field(s) reappeared in "
        f"FE_FACING_FIELDS: {sorted(leaked)}. These are not consumed "
        f"by any render-engine module."
    )

    # ``target_duration`` MUST still be in Public — T2.4 wired it.
    assert "target_duration" in FE_FACING_FIELDS, (
        "target_duration was dropped from FE_FACING_FIELDS but T2.4 "
        "(commit 7f57475) wired it into the LLM prompt — removing it "
        "from the Public surface breaks the wire for a field the BE "
        "now consumes."
    )
