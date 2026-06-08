"""``RenderRequestPublic`` — the explicit FE-facing slice of ``RenderRequest``.

Audit MT-3 closure phase 1 (Batch 10N, 2026-06-06).

Background
----------
``app.models.render.RenderRequest`` carries 152 fields, evolved over many
sprints. The FE TypeScript interface at
``frontend/src/types/api.ts:RenderRequest`` declares only 88 of those —
the remaining 64 are server-derived, replay-only, or legacy hold-overs
kept around so historical ``payload_json`` blobs deserialize cleanly
(Sacred Contract #2).

The audit's MT-3 recommendation: split the 152 into ``RenderRequestPublic``
(FE-facing) and an internal/server-derived surface. The clarity win:
a reviewer can see at a glance which fields are user-facing API and
which are server-internal plumbing.

Scope of this file
------------------
**Phase 1 — additive only.** This module DEFINES the Public surface and
provides the regression guard. It does NOT switch the wire contract.
``/api/render/process`` still accepts ``RenderRequestStrict`` (which is
the full 152-field schema with ``extra="forbid"``). A future phase can
flip the wire endpoint to validate against Public first, then expand
to the full RenderRequest server-side.

Why this is safe today: Public is built via Pydantic's ``create_model``
from RenderRequest's own ``model_fields`` — types and defaults are
pulled live at import time, so a default change on RenderRequest is
reflected here automatically. Field validators are NOT copied (Pydantic
v2 limitation); if Public ever lands on the wire, the validators that
matter for FE-facing fields (api-key strip, voice settings,
range-bound integers) need to be re-attached at that point.

The complementary set — RenderRequest fields NOT in Public — is
exposed as ``BE_ONLY_FIELDS`` so a future "RenderRequestInternal" model
can be derived just as mechanically.
"""
from __future__ import annotations

from pydantic import ConfigDict, create_model

from app.models.render import RenderRequest


# ── The FE contract ────────────────────────────────────────────────────────
# Frozen field set mirroring the FE TS interface at
# frontend/src/types/api.ts:RenderRequest. Adding a field to the FE
# interface AND to this set is the migration that promotes a BE-only
# field into the Public surface. Tests pin parity in both directions.
FE_FACING_FIELDS: frozenset[str] = frozenset({
    # Source
    "source_mode", "source_quality_mode", "youtube_url", "source_video_path",
    # Output
    "output_mode", "output_dir", "render_output_subdir", "keep_source_copy",
    "cleanup_temp_files",
    # Profile / quality
    "render_profile", "output_fps", "whisper_model",
    # Segmentation
    "auto_detect_scene", "min_part_sec", "max_part_sec", "max_export_parts",
    "part_order",
    # Subtitle (the parts the FE exposes)
    "add_subtitle", "subtitle_style", "highlight_per_word", "sub_font_size",
    "subtitle_translate_enabled", "subtitle_target_language",
    # Frame / crop
    "aspect_ratio", "motion_aware_crop", "reframe_mode",
    "frame_scale_x", "frame_scale_y",
    # Overlay / effect
    "add_title_overlay", "title_overlay_text", "effect_preset",
    "remotion_hook_intro",
    # Reup mode
    "reup_mode", "reup_overlay_enable", "reup_bgm_enable", "reup_bgm_path",
    "playback_speed",
    # Editor session
    "edit_session_id", "edit_trim_in", "edit_trim_out", "edit_volume",
    "text_layers",
    # Voice
    "voice_enabled", "voice_language", "voice_gender", "voice_source",
    "voice_text", "tts_engine", "voice_mix_mode",
    # Hook
    "hook_apply_enabled", "hook_overlay_enabled",
    # AI Director (legacy flags the FE still toggles)
    "ai_director_enabled", "ai_auto_cut", "ai_use_semantic_hooks",
    "ai_render_influence_enabled", "ai_beat_pulse_enabled",
    # Platform / market
    "target_platform", "ai_target_market",
    # Multi-variant + CTA
    "multi_variant", "cta_enabled", "cta_type",
    # Cloud LLM (provider + key + model + mode)
    "ai_cloud_enabled", "ai_cloud_provider", "ai_cloud_api_key",
    "ai_cloud_model", "ai_analysis_mode", "ai_content_driven_selection",
    # LLM selection (canonical)
    "llm_enabled", "llm_model", "llm_language", "llm_min_quality", "llm_mode",
    "ai_provider",
    # Pro Timeline Steering (UP26)
    "clip_lock", "clip_exclude", "structure_bias", "subtitle_emphasis",
    # Creator Asset Intelligence (UP27)
    "asset_logo_path", "asset_intro_path", "asset_outro_path",
    "asset_music_profile",
    # New vision (v2)
    "target_duration", "output_count", "video_type",
    "energy_style", "hook_strength",
    "output_language", "narration_style",
})


# ── The internal complement ────────────────────────────────────────────────
# Derived at module load — every RenderRequest field not in the Public
# set is by definition BE-only (server-derived / replay-compat / legacy).
# Frozen for use by future RenderRequestInternal work.
BE_ONLY_FIELDS: frozenset[str] = frozenset(
    set(RenderRequest.model_fields.keys()) - FE_FACING_FIELDS
)


# ── RenderRequestPublic ────────────────────────────────────────────────────
# Pulled live from RenderRequest's field definitions so a default change
# on RenderRequest is reflected here automatically. ``extra="forbid"``
# means a future wire switch instantly enforces "only Public fields"
# at the boundary.
#
# ``create_model`` accepts (annotation, default) tuples per field. We
# read both straight off ``model_fields[name]`` so the live RenderRequest
# defaults stay authoritative.

_public_field_specs: dict = {
    name: (
        RenderRequest.model_fields[name].annotation,
        RenderRequest.model_fields[name],
    )
    for name in sorted(FE_FACING_FIELDS)
}

RenderRequestPublic = create_model(  # type: ignore[call-overload]
    "RenderRequestPublic",
    __config__=ConfigDict(extra="forbid"),
    **_public_field_specs,
)

RenderRequestPublic.__doc__ = (
    "FE-facing slice of RenderRequest (88 of 152 fields). Strictly forbids "
    "unknown fields (``extra='forbid'``). NOT yet wired to /api/render/"
    "process — current wire still accepts RenderRequestStrict (full schema). "
    "See module docstring for the migration plan."
)


__all__ = [
    "FE_FACING_FIELDS",
    "BE_ONLY_FIELDS",
    "RenderRequestPublic",
]
