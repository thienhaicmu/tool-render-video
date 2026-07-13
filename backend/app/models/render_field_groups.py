"""Logical grouping of RenderRequest's 152 flat fields — A2 (2026-06-27).

RenderRequest is a flat 152-field god-object (see models/render.py). The
flatness is load-bearing: it is the wire shape, the stored-payload shape
(Sacred Contract #2 — bit-identical replay), and the basis of the
auto-derived RenderRequestPublic. So we do NOT nest the fields into Pydantic
sub-models — that would break deserialisation, the public surface, and ~38
flat `req.X` access sites.

Instead this module is a pure, side-effect-free REGISTRY that maps every
field to exactly one logical group. It changes no behaviour and no contract.
What it buys:

  - the god-object becomes navigable (what does field X belong to?);
  - a guard test (tests/test_render_field_groups.py) asserts the registry
    stays complete and disjoint, so a NEW RenderRequest field MUST be
    classified into a group or CI fails — turning silent field sprawl into
    a deliberate, reviewed decision;
  - it is the foundation a later preset layer (F2) maps onto without
    touching the flat model.

Do NOT add a field to two groups. Do NOT remove a field from here without
removing it from RenderRequest. The test enforces both.
"""
from __future__ import annotations

# Each group → the RenderRequest field names it owns. Union must equal the
# full RenderRequest field set; groups must be pairwise disjoint.
FIELD_GROUPS: dict[str, frozenset[str]] = {
    "source": frozenset({
        "source_mode", "source_quality_mode", "youtube_url", "youtube_urls",
        "source_video_path", "channel_code",
    }),
    "output": frozenset({
        "output_dir", "render_output_subdir", "keep_source_copy",
        "cleanup_temp_files", "output_count", "output_language",
        "render_format",
    }),
    "content": frozenset({
        # Content Mode (render_format="content") — Script → AI narration → Video.
        # BE-only; the Visual Generator provider seam selector + user background.
        "content_script", "content_background_kind", "content_background_value",
        "content_bgm_path", "content_visual_provider", "content_imagen_tier",
        "content_ai_budget",
        "content_plan_override",
    }),
    "story": frozenset({
        # Story Mode (render_format="story") — Chapter → AI storyboard → consistent
        # images + narration → Video. BE-only (wire surface lands in P6). The
        # chapter text reuses content_script (in the "content" group).
        "story_series_id", "story_chapter_no", "story_art_style",
        "story_reading_pace", "story_plan_override",
        # v2 (B0): input source — paste text vs AI-authored from an idea.
        "story_source", "story_idea", "story_duration_sec", "story_genre",
        # Phase 2: final image provider (gpt_image paid | pollinations free).
        "story_image_provider",
        # A1: optional local base video the story is composited over ("" = image-based).
        "story_base_video_path",
        "story_voice_mode",
    }),
    "lifecycle": frozenset({
        "resume_job_id", "resume_from_last", "render_profile", "render_preset",
        "render_preset_id", "render_preset_label", "retry_count",
        "max_parallel_parts",
    }),
    "analysis": frozenset({
        "auto_detect_scene", "min_part_sec", "max_part_sec", "max_export_parts",
        "part_order", "whisper_model",
    }),
    "encoding": frozenset({
        "video_preset", "video_crf", "video_codec", "audio_bitrate",
        "encoder_mode", "output_fps", "transition_sec", "playback_speed",
        "aspect_ratio", "frame_scale_x", "frame_scale_y",
    }),
    "subtitle": frozenset({
        "add_subtitle", "subtitle_style", "subtitle_viral_min_score",
        "subtitle_viral_top_ratio", "subtitle_only_viral_high",
        "subtitle_transcription_engine", "highlight_per_word", "sub_font_size",
        "sub_font", "sub_margin_v", "sub_color", "sub_highlight", "sub_outline",
        "sub_x_percent", "subtitle_translate_enabled", "subtitle_target_language",
        "subtitle_edits", "subtitle_emphasis",
    }),
    "motion": frozenset({
        "motion_aware_crop", "reframe_mode",
    }),
    "overlay": frozenset({
        "add_title_overlay", "title_overlay_text", "effect_preset",
        "text_layers", "remotion_hook_intro",
    }),
    "hook": frozenset({
        "hook_applied_text", "hook_apply_enabled", "hook_overlay_enabled",
        "hook_score",
    }),
    "audio": frozenset({
        "loudnorm_enabled", "audio_cleanup_engine", "tts_engine",
    }),
    "voice": frozenset({
        "voice_enabled", "voice_language", "voice_gender", "voice_rate",
        "voice_mix_mode", "voice_text", "voice_source", "voice_id",
        "narration_style", "rewrite_tone", "narration_mode", "reaction_intensity",
    }),
    "reup": frozenset({
        "reup_mode", "reup_overlay_enable", "reup_overlay_opacity",
        "reup_bgm_enable", "reup_bgm_path", "reup_bgm_gain",
    }),
    "editing": frozenset({
        "asset_id", "edit_session_id", "edit_trim_in", "edit_trim_out",
        "edit_volume",
    }),
    "scoring": frozenset({
        "market_viral", "viral_market", "ai_target_market",
        "combined_scoring_enabled", "adaptive_scoring_enabled",
        "auto_best_export_enabled", "auto_best_export_count",
    }),
    "ai_director": frozenset({
        "ai_director_enabled", "ai_mode", "ai_auto_cut", "ai_target_duration",
        "ai_use_semantic_hooks", "ai_use_rag_memory",
        "ai_render_influence_enabled", "ai_beat_execution_enabled",
        "ai_beat_pulse_enabled", "ai_beat_transition_enabled",
        "ai_timing_mutation_enabled", "ai_analysis_mode", "ai_early_transcription",
        "ai_content_driven_selection",
    }),
    "ai_variant": frozenset({
        "multi_variant", "ai_variant_planning_enabled", "ai_variant_count",
    }),
    "ai_clip": frozenset({
        "ai_clip_discovery_enabled", "ai_clip_min_duration_sec",
        "ai_clip_max_duration_sec", "ai_clip_candidate_limit",
        "ai_clip_segment_selection_enabled", "ai_clip_target_count",
        "ai_clip_batch_planning_enabled", "ai_clip_batch_limit",
    }),
    "ai_cloud": frozenset({
        "ai_cloud_enabled", "ai_cloud_provider", "ai_cloud_api_key",
        "ai_cloud_model",
    }),
    "timeline_steering": frozenset({
        "clip_lock", "clip_exclude", "structure_bias", "creator_dna",
        "target_duration", "target_platform", "video_type", "energy_style",
        "hook_strength",
    }),
    "cta": frozenset({
        "cta_enabled", "cta_type",
    }),
    "assets": frozenset({
        "asset_logo_path", "asset_intro_path", "asset_outro_path",
        "asset_music_profile", "asset_brand_subtitle",
    }),
    "llm": frozenset({
        "llm_enabled", "llm_model", "llm_language", "llm_min_quality",
        "llm_mode", "groq_only_mode", "ai_provider",
        # C.1 Phase 1 (2026-06-30): Clip-path feature flag for the Comprehension
        # stage. Belongs here because it gates an LLM-pipeline behaviour
        # (run_comprehension produces a StoryModel passed to select_render_plan).
        "use_story_intelligence",
    }),
    "credentials": frozenset({
        "gemini_api_key", "openai_api_key", "claude_api_key", "groq_api_key",
    }),
}


def group_of(field_name: str) -> str | None:
    """Return the group a RenderRequest field belongs to, or None."""
    for group, names in FIELD_GROUPS.items():
        if field_name in names:
            return group
    return None


# Flat set of every classified field — convenience for the guard test and
# any future preset-mapping layer.
ALL_GROUPED_FIELDS: frozenset[str] = frozenset(
    name for names in FIELD_GROUPS.values() for name in names
)
