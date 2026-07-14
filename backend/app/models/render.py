"""Render + source-prep API schemas.

Split out of ``app.models.schemas`` in the MT-2 schemas decomposition
(audit-2026-06-06 MT-2, 2026-06-06). Existing callers continue to work
via the re-export shim in ``app.models.schemas`` — every public class
defined here is re-exported from there.

Why the split: ``schemas.py`` had grown to ~570 LOC and was the audit's
top "split candidate" for the schemas layer. The render-tier classes
(RenderRequest, RenderRequestStrict, TextLayer*, PrepareSourceRequest,
QuickProcessRequest) dominated the file. Job-status response moved to
``app.models.jobs``. Sacred Contract 2 is preserved: every field,
default, validator, and ConfigDict survives the move byte-for-byte.
"""
from __future__ import annotations

import logging

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

_security_logger = logging.getLogger("app.api.security")

# Render format — the top-level pipeline mode select. Sacred Contract #2:
# default "clips" so every stored historical payload deserialises into the
# legacy clips path bit-identically. The runtime normaliser
# (_validate_render_format below) tolerates legacy casing/whitespace.
# "content" (2026-07-03) = Content Mode: Script → AI narration → Video (no
# source footage). Additive third value — clips/recap paths untouched.
# "story" (2026-07-09) = Story-to-Video: Chapter → AI storyboard (scenes→shots) →
# consistent AI images + narration → Video. Additive fourth value — all prior
# paths untouched (routes to run_story via a fully separate orchestrator).
RenderFormat = Literal["clips", "recap", "content", "story"]


class PrepareSourceRequest(BaseModel):
    # extra="ignore" preserves backward compat with stored payloads that still
    # carry deprecated fields (e.g. legacy youtube_url) from the pre-Sprint-1.2
    # YouTube render path. Unknown fields are silently dropped instead of raising.
    model_config = ConfigDict(extra="ignore")
    source_mode: Optional[str] = "local"
    source_video_path: Optional[str] = ""
    session_id: Optional[str] = None  # client-provided UUID; server generates one if absent


class QuickProcessRequest(BaseModel):
    # extra="ignore" preserves backward compat with legacy payloads that may
    # still carry deprecated YouTube fields (url, etc.) from the pre-Sprint-1.2 path.
    model_config = ConfigDict(extra="ignore")
    source: str = "local"
    url: str = ""  # deprecated, unused after Sprint 1.2 (kept for stored payload compat)
    path: str = ""
    output: str = ""
    resize_width: Optional[int] = None
    resize_height: Optional[int] = None
    video_filter: Optional[str] = None
    trim_black_intro: bool = False
    black_min_duration: float = 0.5
    black_threshold: float = 0.10
    overwrite: bool = True


class TextLayerOutline(BaseModel):
    enabled: bool = False
    thickness: int = 2


class TextLayerShadow(BaseModel):
    enabled: bool = False
    offset_x: int = 2
    offset_y: int = 2


class TextLayerBackground(BaseModel):
    enabled: bool = False
    color: str = "#00000099"
    padding: int = 10


class TextLayerConfig(BaseModel):
    id: str
    text: str
    font_family: str = "Bungee"
    font_size: int = 42
    color: str = "#FFFFFF"
    position: str = "bottom-center"
    x_percent: Optional[float] = None
    y_percent: Optional[float] = None
    alignment: str = "center"
    bold: bool = False
    outline: TextLayerOutline = Field(default_factory=TextLayerOutline)
    shadow: TextLayerShadow = Field(default_factory=TextLayerShadow)
    background: TextLayerBackground = Field(default_factory=TextLayerBackground)
    start_time: float = 0.0
    end_time: float = 0.0
    order: int = 0


class RenderRequest(BaseModel):
    # Sprint 5.3: pin extra="ignore" explicitly. Stored job records in
    # data/app.db may carry deprecated/renamed keys (e.g. groq_* aliases
    # pending DB migration in Sprint 5.4). Silent-drop is the contract
    # the replay path relies on. Pydantic v2 already defaults to ignore,
    # but pinning makes Sacred Contract #2 readable at the class header.
    model_config = ConfigDict(extra="ignore")

    # Source
    source_mode: Optional[str] = "local"
    source_quality_mode: str = "standard_1080"
    youtube_url: Optional[str] = ""
    youtube_urls: Optional[list[str]] = Field(default_factory=list)
    source_video_path: Optional[str] = ""

    # Output
    channel_code: Optional[str] = ""
    output_dir: Optional[str] = ""
    render_output_subdir: Optional[str] = ""
    keep_source_copy: bool = False
    cleanup_temp_files: bool = True

    # Resume
    resume_job_id: Optional[str] = None
    resume_from_last: bool = False

    # Profile / quality
    render_profile: Optional[str] = "quality"
    render_preset: Optional[str] = "custom"
    render_preset_id: Optional[str] = None
    render_preset_label: Optional[str] = None
    video_preset: Optional[str] = None
    video_crf: Optional[int] = None
    video_codec: Optional[str] = "h264"
    audio_bitrate: str = "192k"
    encoder_mode: Optional[str] = "auto"
    output_fps: int = 60
    transition_sec: Optional[float] = None
    whisper_model: Optional[str] = "auto"

    # Segmentation
    auto_detect_scene: bool = True
    min_part_sec: int = 15
    max_part_sec: int = 60
    max_export_parts: Optional[int] = None
    part_order: Optional[str] = "viral"

    # Subtitle
    add_subtitle: bool = True
    subtitle_style: Optional[str] = "tiktok_bounce_v1"
    subtitle_viral_min_score: int = 0
    subtitle_viral_top_ratio: float = 1.0
    subtitle_only_viral_high: bool = False
    subtitle_transcription_engine: Literal["default", "faster_whisper", "whisperx"] = "default"
    highlight_per_word: bool = False
    sub_font_size: int = 72
    sub_font: str = "Bungee"
    sub_margin_v: int = 170
    sub_color: str = "#FFFFFF"
    sub_highlight: str = "#00FF00"
    sub_outline: int = 3
    sub_x_percent: float = 50.0

    # Frame / crop
    aspect_ratio: str = "3:4"
    frame_scale_x: int = 100
    frame_scale_y: int = 106
    motion_aware_crop: bool = True
    reframe_mode: str = "subject"

    # Overlay / effect
    add_title_overlay: bool = False
    title_overlay_text: Optional[str] = ""
    effect_preset: str = "slay_soft_01"
    loudnorm_enabled: bool = True
    audio_cleanup_engine: Literal["none", "deepfilternet"] = "none"
    tts_engine: Literal["edge", "xtts", "gemini"] = "edge"
    remotion_hook_intro: bool = False

    # Reup mode
    reup_mode: bool = False
    reup_overlay_enable: bool = True
    reup_overlay_opacity: float = 0.08
    reup_bgm_enable: bool = False
    reup_bgm_path: Optional[str] = None
    reup_bgm_gain: float = 0.18
    # V8-A7 (audit 2026-06-08) — default changed from 1.07 → 1.0.
    # Pre-fix every render silently ran at 7% speed-up because the FE
    # never set this field and 1.07 was the model default. The new
    # default is honest: 1.0 = no acceleration. Operators who want the
    # legacy viral acceleration set the field explicitly to 1.07.
    playback_speed: float = 1.0

    # Parallel / retry
    # 0 = adaptive (backend selects safe workers from cpu_count + pipeline flags)
    # >=1 = user ceiling — backend will not exceed this value but may use fewer
    max_parallel_parts: int = 0
    retry_count: int = 2

    # Asset Library — Phase C. Links this render job to a registered asset.
    # None = no asset association (backward-compat default).
    asset_id: Optional[str] = None

    # Editor session
    edit_session_id: Optional[str] = None
    edit_trim_in: float = 0
    edit_trim_out: float = 0
    edit_volume: float = 1.0
    text_layers: list[TextLayerConfig] = Field(default_factory=list)
    voice_enabled: bool = False
    voice_language: str = "vi-VN"
    voice_gender: str = "female"
    voice_rate: str = "+0%"
    voice_mix_mode: str = "replace_original"
    voice_text: Optional[str] = None
    voice_source: str = "manual"
    voice_id: Optional[str] = None
    # AI rewrite tone hint (voice_source="ai_rewrite"). Free-text creator
    # nudge rendered into the rewrite prompt's TONE line. Empty string
    # defaults to "natural / informative" inside build_rewrite_prompt.
    # Sacred Contract #2: default "" so stored historical payloads that
    # never set this field replay with no behavioural change.
    rewrite_tone: str = ""
    # Narration persona for the ai_rewrite voice path. "" (default) = faithful
    # rewrite of the transcript for TTS. "reaction" = faceless reaction /
    # storyteller persona: the AI writes first-person reaction commentary that
    # dramatises and leads the story over the clip, adaptively blending added
    # commentary with the source content. Sacred Contract #2: default "" so
    # stored historical payloads replay with no behavioural change.
    narration_mode: str = ""
    # Reaction density (narration_mode="reaction"): "" (default = balanced) |
    # "low" (sparse — few interjections, let the original carry more) | "medium"
    # | "high" (chatty — more reactions + freezes). Sacred Contract #2: default
    # "" so stored payloads replay unchanged.
    reaction_intensity: str = ""
    subtitle_translate_enabled: bool = False
    subtitle_target_language: str = "en"
    market_viral: Optional[dict] = None
    viral_market: Optional[str] = None
    ai_target_market: Optional[str] = None
    hook_applied_text: Optional[str] = None
    # Sprint 3 3E Subset B (audit 2026-06-02): flipped True → False to honor
    # Sacred Contract 2. Also fixes a latent UI bug: the OLD pattern
    # `cfg.hookApplyEnabled || undefined` in buildPayload would send
    # undefined when the user toggled the UI checkbox OFF, and the
    # default-True backend would still apply the hook. After this flip, the
    # OFF case correctly inherits False.
    hook_apply_enabled: bool = False
    hook_overlay_enabled: bool = False
    hook_score: Optional[float] = None
    subtitle_edits: Optional[list] = None
    combined_scoring_enabled: bool = False
    adaptive_scoring_enabled: bool = False
    auto_best_export_enabled: bool = False
    auto_best_export_count: int = 3

    # AI Director (Phase 1) — flag retained for backward compatibility with stored
    # job payloads. Sprint 3 3E Subset A (audit 2026-06-02) flipped this from True
    # to False because the AI Director module was removed in Phase G
    # (see app/main.py:238 "RAG/AI Director removed"). Effectively a no-op now;
    # default-False honors Sacred Contract 2 for replayed historical jobs.
    ai_director_enabled: bool = False
    ai_mode: str = "viral_tiktok"
    # Sprint 3 3E Subset B: flipped True → False to honor Contract 2.
    # New UI jobs explicitly set this True via RenderWorkflow.buildPayload so
    # the user-facing default is unchanged; stored historical job payloads
    # that omit the field no longer silently activate the feature on replay.
    ai_auto_cut: bool = False
    ai_target_duration: Optional[int] = None
    # Sprint 3 3E Subset B: flipped True → False (same Contract 2 rationale).
    ai_use_semantic_hooks: bool = False
    # RAG memory was removed in Phase G alongside the AI Director module. Kept
    # as a no-op flag; default-False per Contract 2 (audit 2026-06-02 Subset A).
    ai_use_rag_memory: bool = False
    # AI Render Influence (Phase 10) — Sprint 3 3E Subset B: was True by
    # default. Flipped to False; UI sets True explicitly for new jobs.
    ai_render_influence_enabled: bool = False
    # AI Beat Execution (Phase 11) — opt-in beat-aware planning; defaults preserve old behavior.
    ai_beat_execution_enabled: bool = False
    # Sprint 3 3E Subset B: flipped True → False (Contract 2).
    ai_beat_pulse_enabled: bool = False
    ai_beat_transition_enabled: bool = False
    # AI Timing Mutation (Phase 19) — opt-in; false = advisory-only, no segment timing changes.
    ai_timing_mutation_enabled: bool = False
    # Multi-variant intelligence (UP13) — 3 purposeful variants from shared source compute.
    # Produces {stem}_aggressive.mp4, {stem}_balanced.mp4, {stem}_story_first.mp4.
    multi_variant: bool = False
    # Platform-aware editing (UP14) — small editorial biases per distribution platform.
    # Options: "tiktok" | "youtube_shorts" | "instagram_reels". Default: tiktok
    # (aligned with FE default in RenderWorkflow.tsx — fixes audit FINDING-C05).
    # Creator explicit settings always win; this is fallback guidance only.
    target_platform: str = "tiktok"
    # CTA / Series Intelligence (UP16) — optional subtitle end card. Default OFF.
    # cta_type: "auto" | "comment" | "part_2" | "follow". Auto picks by content type.
    cta_enabled: bool = False
    cta_type: str = "auto"
    # Creator Style DNA (UP20) — inferred editorial identity context from frontend. Default empty.
    # Computed by creator-dna.js from UP12+UP18 signals. Never overrides explicit creator choices.
    creator_dna: dict = Field(default_factory=dict)
    # AI Variant Planning (Phase 21) — opt-in; plans advisory variants, never auto-renders.
    ai_variant_planning_enabled: bool = False
    ai_variant_count: int = 3
    # AI Clip Candidate Discovery (Phase 35) — opt-in; discovery-only, never executes cuts.
    ai_clip_discovery_enabled: bool = False
    ai_clip_min_duration_sec: int = 15
    ai_clip_max_duration_sec: int = 60
    ai_clip_candidate_limit: int = 5
    # AI Clip Segment Selection (Phase 36) — opt-in; selection-only, never executes renders.
    ai_clip_segment_selection_enabled: bool = False
    ai_clip_target_count: int = 3
    # AI Multi-Clip Batch Planning (Phase 37) — opt-in; planning-only, never executes batch renders.
    ai_clip_batch_planning_enabled: bool = False
    ai_clip_batch_limit: int = 5
    # AI Content-Driven Selection (Phase 44) — opt-in; requires ai_director_enabled=True.
    # When True: AI Director's segment selections from transcript override heuristic scored[].
    # When False (default): existing heuristic sort+select behavior unchanged.
    ai_content_driven_selection: bool = False
    # AI Early Transcription (Phase 45) — opt-in; run Whisper before segment selection.
    # When True: transcription runs immediately after scene detection, before scored[] is built.
    # Enables S4.1/S4.2/S4.5 refinements to operate on the full candidate pool.
    # Combines with ai_content_driven_selection for full content-first pipeline.
    # When False (default): transcription runs at subtitle stage as before.
    ai_early_transcription: bool = False
    # AI Cloud Analyzer — optional one-call-per-job cloud enrichment for clip selection,
    # subtitle hints, and camera hints. Falls back to local analyzers if disabled or on error.
    # ai_cloud_provider: "openai" | "groq"
    # ai_cloud_model: None = use provider default (gpt-4o-mini / llama-3.1-8b-instant)
    ai_cloud_enabled: bool = False
    ai_cloud_provider: Optional[str] = None
    ai_cloud_api_key: Optional[str] = None
    ai_cloud_model: Optional[str] = None
    # AI Analyzer mode — controls which analysis tier runs.
    # "local": offline only, no API cost; "cloud": cloud result 100%;
    # "hybrid" (default/None): 70% cloud + 30% local merge.
    ai_analysis_mode: Optional[Literal["local", "cloud", "hybrid"]] = None

    # UP26: Pro Timeline Steering — creator guidance signals (above DNA, below explicit lock)
    # clip_lock: [{start_sec, end_sec}] — candidate ranges creator wants included
    # clip_exclude: [{start_sec, end_sec}] — timestamp ranges to skip entirely
    # structure_bias: 'hook' | 'balanced' | 'story' — gentle ranking re-weight
    # subtitle_emphasis: 'subtle' | 'balanced' | 'aggressive' — font-size multiplier
    clip_lock: Optional[list[dict]] = None
    clip_exclude: Optional[list[dict]] = None
    structure_bias: Optional[str] = None
    subtitle_emphasis: Optional[str] = None

    # UP27: Creator Asset Intelligence — local brand assets, all optional, all safe-skip
    # asset_logo_path: absolute path to PNG/JPEG logo for watermark overlay
    # asset_intro_path: absolute path to short intro sting clip (prepended)
    # asset_outro_path: absolute path to outro/bumper clip (appended)
    # asset_music_profile: 'clean' | 'energetic' | 'soft' — BGM gain hint
    # asset_brand_subtitle: preferred subtitle style (stronger default when add_subtitle=True)
    asset_logo_path: Optional[str] = None
    asset_intro_path: Optional[str] = None
    asset_outro_path: Optional[str] = None
    asset_music_profile: Optional[str] = None
    asset_brand_subtitle: Optional[str] = None

    # ── New vision fields (v2) ────────────────────────────────────────────────
    # Output Goals
    # Render format: "clips" (default — N short clips, current behaviour) |
    # "recap" (one long, act-structured recap/review video — see
    # docs/RECAP_REVIEW_SPEC.md). Sacred Contract #2: default "clips" so stored
    # historical payloads replay unchanged. Typed as ``RenderFormat`` (Literal)
    # so the OpenAPI schema lists the closed set explicitly; the validator
    # below still normalises legacy casing/whitespace ("RECAP" → "recap").
    render_format: RenderFormat = "clips"

    # ── Content Mode (render_format="content") ────────────────────────────────
    # Script → AI narration → Video. Sacred Contract #2: every field below
    # defaults to an INERT/disabled state, so a stored clips/recap payload (which
    # never set them) replays with NO content behaviour. ``content_script`` is
    # the true off-switch — Content Mode only activates when
    # render_format=="content" AND a non-empty script is supplied. These are
    # BE-only for now (NOT in render_public.FE_FACING_FIELDS); the FE surface +
    # api.ts land together in the Content-tab UI phase (coordinated migration).
    content_script: str = ""                    # the raw user text; "" = not a content job
    content_background_kind: str = "color"      # color|image|video (visual provider 'local')
    content_background_value: str = "#000000"   # color hex / asset path
    content_bgm_path: str = ""                  # "" = no background music
    content_visual_provider: str = "local"      # engine.visual seam selector
    # Imagen tier for the ai_image provider: ""|fast|standard|ultra. "" (default,
    # Sacred #2 inert) = fall back to the CONTENT_IMAGEN_TIER env, then "standard"
    # — so existing jobs behave exactly as before. Only consulted when
    # content_visual_provider="ai_image".
    content_imagen_tier: str = ""
    # P4.1: per-render paid-visual budget cap (relative cost units — see
    # engine.visual.decision). 0.0 (default, Sacred #2 inert) = unlimited → the
    # env CONTENT_AI_BUDGET is used instead. Only meaningful for PAID providers
    # (ai_image/ai_video); free sources (local/stock/ai_image_free) cost 0.
    content_ai_budget: float = 0.0
    # CS-A: an APPROVED/edited ContentPlan JSON from the Review step. When set
    # (Content Studio's mandatory Review → Approve flow), run_content renders
    # FROM this plan and SKIPS the AI planning call. "" = generate the plan via
    # the AI Director as before (Sacred Contract #2: default inert → unchanged).
    content_plan_override: str = ""

    # ── Story Mode (render_format="story") ────────────────────────────────────
    # Chapter → AI storyboard → consistent images + narration → Video. Sacred
    # Contract #2: every field below defaults INERT, so a stored clips/recap/
    # content payload replays with NO story behaviour. Story reuses the CHAPTER
    # text via ``content_script`` (the shared text-input field) — Story Mode only
    # activates when render_format=="story" AND a non-empty content_script is
    # supplied. BE-only for now (NOT in render_public.FE_FACING_FIELDS); the wire
    # surface lands in P6.
    story_series_id: str = ""       # "" = one-off chapter (no cross-chapter Character DB)
    story_chapter_no: int = 0
    story_art_style: str = ""       # anime|wuxia|romance|realistic|inkwash|... ("" = infer)
    story_reading_pace: str = "normal"  # slow|normal|fast (global reading-speed lever)
    # An APPROVED/edited StoryPlan JSON from the Storyboard review (Duyệt #2). When
    # set, run_story renders FROM this plan and SKIPS the AI planning call. "" =
    # generate via the Story Director (Sacred Contract #2: default inert).
    story_plan_override: str = ""
    # ── Story v2 input source (B0) ────────────────────────────────────────────
    # Two ways to feed Story Mode, both → the SAME super-prompt StoryPlan v2:
    #   ""|"paste" = adapt the story text in ``content_script`` (default, inert).
    #   "idea"     = the AI CREATES the story from ``story_idea`` (+ duration/genre),
    #                then storyboards it — one super call. Sacred Contract #2: ""
    #                defaults to the paste path, so stored payloads are unaffected.
    story_source: str = ""          # ""|paste|idea
    story_idea: str = ""            # premise for story_source="idea" ("" = not an idea job)
    story_duration_sec: int = 0     # target length for the idea path (0 = model decides)
    story_genre: str = ""           # wuxia|romance|horror|fantasy|... (idea path hint)
    # Image provider — Story Mode is SVG-ONLY (procedural chibi, offline, $0). The field
    # is RETAINED (not dropped) so a stored payload that still carries an old
    # "gpt_image"/"pollinations" value deserialises cleanly; the validator coerces every
    # value to "svg", so a replayed historical job renders via the SVG engine (the paid
    # gpt-image / free Pollinations story paths were removed).
    story_image_provider: str = "svg"  # svg only — validator coerces any legacy value → "svg"
    # Optional LOCAL base video the story is composited over (A1). "" = image-based
    # story (the default — AI key-visuals + Ken Burns, byte-identical replay). When a
    # valid local path is given, later phases use it as the base layer for the cue
    # render + character overlay. Sacred Contract #2: default inert; an invalid/missing
    # path degrades to the image-based path (Sacred #3 spirit), never aborts.
    story_base_video_path: str = ""
    # P2 — how narration voices are cast for a beat's dialogue lines. "dialogue" (default)
    # = each character's line uses its OWN cast voice — this is the legacy per-beat
    # behaviour, so a replayed job stays bit-identical (Sacred #2). "narrator" = one
    # narrator voice reads every line (pure storytelling / kể chuyện).
    story_voice_mode: str = "dialogue"   # dialogue|narrator

    target_duration: int = 90
    output_count: int = 1
    video_type: str = "auto"          # auto|viral|storytelling|educational|emotional|high_retention

    # Architecture-review C.1 Phase 1 (2026-06-30): when True AND
    # render_format == "clips", the Comprehension stage runs on the Whisper
    # transcript to produce a StoryModel that grounds clip selection in
    # whole-film semantic understanding (theme, conflict, characters,
    # emotional curve). Default False — Sacred Contract #2: stored
    # historical payloads replay bit-identically with the legacy no-
    # StoryModel path. Phase 1 ships this surface only; the Phase 2
    # render_pipeline.py wire-in and Phase 3 provider+prompt consumption
    # land in separate commits. Effective only on the Clip path — Recap
    # always runs Comprehension (gated by STORY_INTELLIGENCE_HOIST_ENABLED
    # env var since Batch C). See docs/audit-c-1-2026-06-30.md.
    use_story_intelligence: bool = False

    # AI Style
    energy_style: str = "auto"        # auto|fast|balanced|slow
    hook_strength: str = "balanced"   # aggressive|balanced|soft

    # Market & Language
    output_language: str = "auto"     # auto|vi|en|ja|ko

    # Narration (AI-directed)
    narration_style: str = "auto"     # auto|energetic|calm|emotional

    # ── LLM Segment Selection (canonical names) ──────────────────────────────
    # llm_enabled=True  → LLM reads SRT, picks segments, is sole authority.
    # llm_enabled=False → fallback to local heuristic scorer.
    #
    # Sprint 7.5 (2026-06-05): the 5 legacy `groq_*` alias fields
    # (groq_analysis_enabled / groq_model / groq_content_language /
    # groq_min_quality_score / groq_selection_strategy) and their
    # _coerce_groq_to_llm validator were deleted. Migration 0002
    # rewrote every stored job's payload_json to use llm_* keys; with
    # model_config = ConfigDict(extra="ignore") (pinned in Sprint 5.3),
    # any payload still carrying legacy groq_* keys is silently dropped
    # and the llm_* fields default to None (which the pipeline treats
    # as "use server defaults"). See
    # docs/review/SPRINT_7_5_GROQ_DELETION_2026-06-05.md.
    llm_enabled: Optional[bool] = None            # None = use server default
    llm_model: Optional[str] = None               # None = server default for selected provider
    llm_language: Optional[str] = None            # None = auto-detect from transcript
    llm_min_quality: Optional[float] = None       # None = use server default (≈ 0.6)
    llm_mode: Optional[str] = None                # None = use server default (≈ "top_n")

    # ── Preserved groq_* keys (no llm_* equivalent — Migration 0002 design) ──
    # groq_only_mode + groq_api_key remain valid input keys; the migration
    # 0002 deliberately preserved them because they have no llm_* counterpart.
    groq_only_mode: bool = False

    # Multi-provider LLM (Phase I) — which LLM provider drives segment selection.
    # Supported: "groq" | "gemini" | "openai" | "claude". Default None means
    # "use server default" (AI_PROVIDER_DEFAULT env, falls back to "gemini").
    # Per-provider API keys; ai_cloud_api_key remains the legacy generic field.
    ai_provider: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    claude_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None

    # ── Cloud LLM credential policy (audit FINDING-F07 / C02 closure) ────────
    # Cloud API keys MUST come from the server's .env (GEMINI_API_KEY,
    # OPENAI_API_KEY, CLAUDE_API_KEY) — never from the client payload.
    # Previously the FE shipped keys via RenderRequest, where they:
    #   - persisted forever in jobs.payload_json
    #   - leaked into per-job log files
    #   - travelled in any DB dump / support bundle
    # The validator below strips any client-supplied *_api_key field to
    # None at parse time and emits a WARN log. The fields are kept in the
    # model (rather than removed) for Sacred Contract #2 backwards-compat:
    # stored payloads with legacy keys deserialize cleanly, just get
    # stripped on re-validation. The LLM stage then falls through to the
    # server env via _resolve_api_key.
    #
    # The /api/render/test-cloud-ai endpoint is unaffected — it accepts a
    # raw dict and uses the key only in-process (no persistence).
    @field_validator(
        "ai_cloud_api_key",
        "gemini_api_key",
        "openai_api_key",
        "claude_api_key",
        "groq_api_key",
    )
    @classmethod
    def _strip_client_api_key(cls, v: Optional[str]) -> Optional[str]:
        if v and isinstance(v, str) and v.strip():
            _security_logger.warning(
                "RenderRequest received a non-empty *_api_key field — stripping to None. "
                "Cloud LLM credentials MUST come from server .env (GEMINI_API_KEY / "
                "OPENAI_API_KEY / CLAUDE_API_KEY). Plaintext keys in payload_json + "
                "per-job logs are a security risk (audit FINDING-F07 / C02)."
            )
        return None

    @field_validator("target_duration")
    @classmethod
    def _validate_target_duration(cls, v: int) -> int:
        return max(60, min(350, int(v)))

    @field_validator("output_count")
    @classmethod
    def _validate_output_count(cls, v: int) -> int:
        return max(1, min(20, int(v)))

    @field_validator("render_format", mode="before")
    @classmethod
    def _validate_render_format(cls, v) -> str:
        # mode="before" runs PRIOR to Pydantic's Literal coercion so legacy
        # casing/whitespace ("RECAP", " Recap ") + None + non-string payloads
        # are normalised first. The Literal check (RenderFormat) then enforces
        # the closed set — any value outside {clips, recap, content} falls back
        # to "clips" here so historical payloads with unknown values keep loading.
        v = str(v or "clips").strip().lower()
        return v if v in {"clips", "recap", "content", "story"} else "clips"

    @field_validator("story_source", mode="before")
    @classmethod
    def _validate_story_source(cls, v) -> str:
        # Coerce (never raise) — Sacred Contract #2: "" (default) = the paste path,
        # so a stored payload without it behaves exactly as before. Unknown/None →
        # "" (paste). "idea" activates the AI-authored path; "paste_json" renders a
        # HAND-PASTED StoryPlan verbatim (no AI — story_plan_override required).
        v = str(v or "").strip().lower()
        return v if v in {"paste", "idea", "paste_json"} else ""

    @field_validator("story_voice_mode", mode="before")
    @classmethod
    def _validate_story_voice_mode(cls, v) -> str:
        # Coerce (never raise) — Sacred #2: "dialogue" (default) reproduces the legacy
        # per-beat per-speaker voice, so a stored payload without it is bit-identical.
        v = str(v or "dialogue").strip().lower()
        return v if v in {"dialogue", "narrator"} else "dialogue"

    @field_validator("story_image_provider", mode="before")
    @classmethod
    def _validate_story_image_provider(cls, v) -> str:
        # Story Mode is SVG-ONLY. Coerce EVERY value → "svg" (never raise) so a stored
        # payload carrying a legacy "gpt_image"/"pollinations" value replays through the
        # SVG engine (the gpt-image / Pollinations story paths were removed).
        return "svg"

    @field_validator("content_background_kind", mode="before")
    @classmethod
    def _validate_content_background_kind(cls, v) -> str:
        # Coerce (never raise) — Sacred Contract #2: a stored payload with a
        # stale/unknown value must replay cleanly. Unknown → "color" (the safe
        # default that needs no external asset).
        v = str(v or "color").strip().lower()
        return v if v in {"color", "image", "video"} else "color"

    @field_validator("content_visual_provider", mode="before")
    @classmethod
    def _validate_content_visual_provider(cls, v) -> str:
        # engine.visual providers: "local" (offline default) | "stock" |
        # "ai_image" | "ai_video" | "ai_image_free" (Pollinations — free, no key)
        # (CS-G, online + opt-in). Unknown/future values coerce to "local" so a
        # payload for a not-yet-shipped provider still renders offline instead of
        # failing (Sacred Contract #2). Online providers always fall back to local
        # at render time when their API key / network is unavailable.
        v = str(v or "local").strip().lower()
        return v if v in {"local", "stock", "ai_image", "ai_video", "ai_image_free"} else "local"

    @field_validator("content_ai_budget", mode="before")
    @classmethod
    def _validate_content_ai_budget(cls, v) -> float:
        # Clamp to >= 0 (never raise) — a stale/negative stored value replays as
        # "unlimited" (0.0), matching the pre-P4.1 default (Sacred Contract #2).
        try:
            return max(0.0, float(v or 0.0))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("ai_clip_min_duration_sec")
    @classmethod
    def _validate_clip_min_duration(cls, v: int) -> int:
        return max(5, min(180, int(v)))

    @field_validator("ai_clip_max_duration_sec")
    @classmethod
    def _validate_clip_max_duration(cls, v: int) -> int:
        return max(10, min(300, int(v)))

    @field_validator("ai_clip_candidate_limit")
    @classmethod
    def _validate_clip_candidate_limit(cls, v: int) -> int:
        return max(1, min(20, int(v)))

    @field_validator("ai_clip_target_count")
    @classmethod
    def _validate_clip_target_count(cls, v: int) -> int:
        return max(1, min(20, int(v)))

    @field_validator("ai_clip_batch_limit")
    @classmethod
    def _validate_clip_batch_limit(cls, v: int) -> int:
        return max(1, min(20, int(v)))

    @field_validator("render_profile")
    @classmethod
    def _validate_render_profile(cls, v: Optional[str]) -> str:
        if v is None:
            return "quality"
        allowed = {"fast", "balanced", "quality", "best"}
        if v not in allowed:
            raise ValueError(f"render_profile must be one of {sorted(allowed)!r}, got {v!r}")
        return v

    @field_validator("whisper_model", mode="before")
    @classmethod
    def _validate_whisper_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None or str(v).strip() == "":
            return v
        m = str(v).strip()
        allowed = {
            "auto",
            "tiny", "tiny.en",
            "base", "base.en",
            "small", "small.en",
            "medium", "medium.en",
            "large", "large-v1", "large-v2", "large-v3", "large-v3-turbo",
            "turbo",
        }
        if m not in allowed:
            raise ValueError(
                f"Unknown whisper_model '{m}'. Allowed: {sorted(allowed)}"
            )
        return m

    @field_validator("part_order")
    @classmethod
    def _validate_part_order(cls, v: Optional[str]) -> str:
        # Closes audit FINDING-C01: FE constrains to {'viral','sequential'}.
        # Coerces (not raises) to preserve Sacred Contract #2 — stored
        # payloads with stale values must replay cleanly. Unknown values
        # fall back to 'viral' (current pipeline behavior). When the pipeline
        # implements true 'sequential' ordering, this validator can stay
        # the same — semantic gating happens at the ranking stage.
        if v is None:
            return "viral"
        allowed = {"viral", "sequential"}
        return v if v in allowed else "viral"

    @field_validator("source_quality_mode")
    @classmethod
    def _validate_source_quality_mode(cls, v: str) -> str:
        allowed = {"standard_1080", "high_1440", "best_available"}
        if v not in allowed:
            raise ValueError(f"source_quality_mode must be one of {sorted(allowed)!r}, got {v!r}")
        return v

    @model_validator(mode="after")
    def validate_clip_discovery_settings(self):
        if self.ai_clip_max_duration_sec < self.ai_clip_min_duration_sec:
            self.ai_clip_max_duration_sec = self.ai_clip_min_duration_sec
        return self

    @model_validator(mode="after")
    def validate_voice_settings(self):
        if not self.voice_enabled:
            return self
        if self.voice_source not in {"manual", "subtitle", "translated_subtitle", "ai_rewrite"}:
            raise ValueError("voice_source must be 'manual', 'subtitle', 'translated_subtitle', or 'ai_rewrite'")
        if self.voice_source == "manual" and not (self.voice_text or "").strip():
            raise ValueError("voice_text is required when voice_enabled=true and voice_source=manual")
        if self.subtitle_target_language not in {"vi", "en", "ja", "ko"}:
            raise ValueError("subtitle_target_language must be one of vi, en, ja, ko")
        if self.voice_language not in {"vi-VN", "ja-JP", "ko-KR", "en-US", "en-GB"}:
            raise ValueError("voice_language must be one of vi-VN, ja-JP, ko-KR, en-US, en-GB")
        if self.voice_gender not in {"female", "male"}:
            raise ValueError("voice_gender must be 'female' or 'male'")
        if self.voice_mix_mode not in {"replace_original", "keep_original_low"}:
            raise ValueError("voice_mix_mode must be 'replace_original' or 'keep_original_low'")
        if self.narration_mode not in {"", "reaction"}:
            raise ValueError("narration_mode must be '' or 'reaction'")
        if self.reaction_intensity not in {"", "low", "medium", "high"}:
            raise ValueError("reaction_intensity must be '', 'low', 'medium', or 'high'")
        if self.narration_mode == "reaction" and self.voice_source != "ai_rewrite":
            raise ValueError("narration_mode='reaction' requires voice_source='ai_rewrite'")
        return self

    # Sprint 7.5 (2026-06-05): _coerce_groq_to_llm validator deleted.
    # Migration 0002 already rewrote every stored job's payload_json to use
    # llm_* keys. Any payload still carrying legacy groq_* keys is silently
    # dropped by extra="ignore" (Sprint 5.3 pin). See
    # docs/review/SPRINT_7_5_GROQ_DELETION_2026-06-05.md.


# ── RenderRequestStrict (audit FINDING-C04 closure, 2026-06-06) ──────────────
# Closes the silent-drop hazard for phased FE rollouts. The parent
# `RenderRequest` carries extra="ignore" because stored payloads with
# deprecated keys (groq_*, ai_director_enabled, ...) must replay cleanly —
# Sacred Contract #2. But at the API boundary, "silently drop unknowns" is
# a footgun: an FE field renamed on the wire is invisible until rendering
# behaviour diverges, which can take days to notice.
#
# Use:
# - POST /api/render/process → RenderRequestStrict (extra="forbid": unknown
#   field → 422 Unprocessable Entity, FE learns immediately).
# - resume/retry from a stored job → RenderRequest (Lenient): replays cleanly.
# - background pipeline replay → RenderRequest (Lenient): same.
#
# Audit verification (2026-06-06): the FE sends 56 fields, all of which
# are defined on RenderRequest. There are 0 FE-only fields — switching the
# POST handler to Strict will not break any current FE submission.
class RenderRequestStrict(RenderRequest):
    """RenderRequest variant that rejects unknown fields with 422.

    Inherits every field, validator, and model_validator from
    ``RenderRequest`` and only overrides ``model_config`` to flip the
    extra-fields policy from "ignore" to "forbid".
    """

    model_config = ConfigDict(extra="forbid")
