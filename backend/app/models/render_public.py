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
    "output_dir", "render_output_subdir", "keep_source_copy",
    "cleanup_temp_files",
    # Profile / quality
    "render_profile", "output_fps", "whisper_model",
    # F2 (2026-06-27): the built-in/saved preset the FE selected. The server
    # merges this preset's params for fields the user didn't explicitly send
    # (see routers/lifecycle._apply_render_preset).
    "render_preset_id",
    # Segmentation
    "auto_detect_scene", "min_part_sec", "max_part_sec",
    # T1.4 follow-up — Audit 2026-06-08: `max_export_parts` and
    # `part_order` removed from the Public surface. Both were declared
    # in the TS interface and sent by RenderWorkflow.buildPayload
    # (max_export_parts: cfg.outputCount, part_order: cfg.partOrder)
    # but the render engine reads NEITHER — `max_export_parts` has no
    # grep hit outside models/ and `part_order` is validated then
    # ignored (FINDING-C01 closure noted in the validator at
    # render.py:451-463). The fields stay in RenderRequest for
    # Sacred Contract #2 replay safety. Caught by
    # test_render_request_public_no_dead_fields.py's
    # test_every_public_field_has_downstream_consumer guard.
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
    # AI rewrite (voice_source=="ai_rewrite") — creator-supplied tone hint.
    "rewrite_tone",
    # Narration persona ("" | "reaction") for the ai_rewrite voice path.
    "narration_mode",
    # Reaction density ("" | low | medium | high).
    "reaction_intensity",
    # Hook
    "hook_apply_enabled", "hook_overlay_enabled",
    # T1.4 — Audit 2026-06-08 closure (Batch A V8-B5 + UP26 + UP27 + v2).
    # Removed 19 fields from the FE-facing wire surface because the
    # render pipeline never reads them. They remain in RenderRequest
    # itself (Sacred Contract #2 — historical payload_json blobs still
    # deserialize cleanly under RenderRequest's extra="ignore"). What
    # was removed and why:
    #   Phase-G zombies (11) — `ai_director_enabled`, `ai_auto_cut`,
    #     `ai_use_semantic_hooks`, `ai_render_influence_enabled`,
    #     `ai_beat_pulse_enabled`, `ai_cloud_enabled`,
    #     `ai_cloud_provider`, `ai_cloud_api_key`, `ai_cloud_model`,
    #     `ai_analysis_mode`, `ai_content_driven_selection`. Gated by
    #     `ctx.ai_edit_plan` which is hardcoded None at
    #     render_pipeline.py:931. UI surfacing them as toggles was
    #     deceit.
    #   UP26 Pro Timeline Steering (4) — `clip_lock`, `clip_exclude`,
    #     `structure_bias`, `subtitle_emphasis`. Never reach the LLM
    #     prompt nor a local-side filter; `_scored_from_render_plan`
    #     passes AI clips through without lock/exclude awareness.
    #   UP27 Creator Asset Intelligence (1) — `asset_music_profile`.
    #     Zero grep hits in features/render/engine. (logo/intro/outro
    #     paths kept — they ARE consumed by asset_pipeline.)
    #   v2 vision dead (3) — `energy_style`, `output_language`,
    #     `narration_style`. Validated then never read.
    # `target_duration` is intentionally KEPT in the Public surface —
    # it is targeted for wiring into the LLM prompt by T2.4 (Sprint 2).
    # Asset Library — Phase C. FE can link a render to a registered asset.
    "asset_id",
    # Platform / market
    "target_platform", "ai_target_market",
    # Multi-variant + CTA
    "multi_variant", "cta_enabled", "cta_type",
    # LLM selection (canonical)
    "llm_enabled", "llm_model", "llm_language", "llm_min_quality", "llm_mode",
    "ai_provider",
    # Strategic-1 + Strategic-1c — Audit 2026-06-08 closure. UP26 Pro
    # Timeline Steering — fully wired post-Strategic-1c:
    #   clip_lock / clip_exclude → LLM prompt sections + BE local
    #     filter (Strategic-1 + Strategic-1b).
    #   structure_bias → ranking-formula re-weight, persisted in
    #     result_json.ranking_metadata.applied_structure_bias
    #     (Strategic-1c).
    #   subtitle_emphasis → subtitle font-size multiplier applied at
    #     ASS generation (Strategic-1c).
    "clip_lock", "clip_exclude",
    "structure_bias", "subtitle_emphasis",
    # Creator Asset Intelligence (UP27) — surviving wired fields
    "asset_logo_path", "asset_intro_path", "asset_outro_path",
    # New vision (v2)
    "target_duration", "output_count", "video_type",
    "hook_strength",
    # Recap/Review mode ("clips" | "recap")
    "render_format",
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
    "FE-facing slice of RenderRequest (72 of 152 fields after the T1.4 "
    "audit-2026-06-08 cleanup + follow-up + Strategic-1/1c full UP26 "
    "restoration + F2 render_preset_id, down from the pre-audit 88). "
    "Strictly forbids unknown "
    "fields (``extra='forbid'``). The wire endpoint /api/render/process "
    "accepts this surface and expands to the full RenderRequest "
    "server-side. See module docstring for the migration history."
)


__all__ = [
    "FE_FACING_FIELDS",
    "BE_ONLY_FIELDS",
    "RenderRequestPublic",
]
