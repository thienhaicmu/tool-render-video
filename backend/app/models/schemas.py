from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Optional


# ── Channel ──────────────────────────────────────────────────────────────

class ChannelCreate(BaseModel):
    channel_code: str
    channel_path: Optional[str] = None
    account_key: Optional[str] = None
    schedule_slots: Optional[list[str]] = None
    browser_preference: Optional[str] = "chromeportable"
    network_mode: Optional[str] = "direct"
    video_output_subdir: Optional[str] = "video_out"
    proxy_server: Optional[str] = ""
    proxy_username: Optional[str] = ""
    proxy_password: Optional[str] = ""
    tiktok_username: Optional[str] = ""
    tiktok_password: Optional[str] = ""
    mail_username: Optional[str] = ""
    mail_password: Optional[str] = ""
    credential_line: Optional[str] = ""
    default_hashtags: Optional[str] = ""


class ChannelInfo(BaseModel):
    channel_code: str
    hashtags_file: str
    input_dir: str
    uploaded_dir: str
    failed_dir: str
    browser_profile_dir: str


# ── Render ───────────────────────────────────────────────────────────────

class PrepareSourceRequest(BaseModel):
    source_mode: Optional[str] = "local"
    youtube_url: Optional[str] = ""
    source_video_path: Optional[str] = ""
    session_id: Optional[str] = None  # client-provided UUID; server generates one if absent


class DownloadHealthRequest(BaseModel):
    youtube_url: Optional[str] = ""


class DownloadBatchRequest(BaseModel):
    urls: list[str] = Field(default_factory=list)
    output_dir: str = ""


class DownloadRetryRequest(BaseModel):
    part_numbers: list[int] = Field(default_factory=list)


class QuickProcessRequest(BaseModel):
    source: str = "youtube"
    url: str = ""
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
    # Source
    source_mode: Optional[str] = "local"
    source_quality_mode: str = "standard_1080"
    youtube_url: Optional[str] = ""
    youtube_urls: Optional[list[str]] = Field(default_factory=list)
    source_video_path: Optional[str] = ""

    # Output
    output_mode: Optional[str] = "manual"
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
    tts_engine: Literal["edge", "xtts"] = "edge"
    remotion_hook_intro: bool = False

    # Reup mode
    reup_mode: bool = False
    reup_overlay_enable: bool = True
    reup_overlay_opacity: float = 0.08
    reup_bgm_enable: bool = False
    reup_bgm_path: Optional[str] = None
    reup_bgm_gain: float = 0.18
    playback_speed: float = 1.07

    # Parallel / retry
    # 0 = adaptive (backend selects safe workers from cpu_count + pipeline flags)
    # >=1 = user ceiling — backend will not exceed this value but may use fewer
    max_parallel_parts: int = 0
    retry_count: int = 2

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
    # Options: "tiktok" | "youtube_shorts" | "instagram_reels". Default: youtube_shorts.
    # Creator explicit settings always win; this is fallback guidance only.
    target_platform: str = "youtube_shorts"
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
    target_duration: int = 90
    output_count: int = 1
    video_type: str = "auto"          # auto|viral|storytelling|educational|emotional|high_retention

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
    llm_enabled: Optional[bool] = None            # None = inherit from groq_analysis_enabled (backward compat)
    llm_model: Optional[str] = None               # None = server default for selected provider
    llm_language: Optional[str] = None            # None = auto-detect from transcript
    llm_min_quality: Optional[float] = None       # None = inherit from groq_min_quality_score (default 0.6)
    llm_mode: Optional[str] = None                # None = inherit from groq_selection_strategy (default "top_n")

    # ── Legacy groq_* fields — kept for backward compat with stored jobs ─────
    # New code should use llm_* above. groq_* values are copied to llm_* at
    # deserialization time (see model_validator below) so the pipeline only
    # reads llm_* fields.
    groq_analysis_enabled: bool = False
    groq_model: Optional[str] = None
    groq_content_language: Optional[str] = None
    groq_min_quality_score: float = 0.6
    groq_selection_strategy: str = "top_n"
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

    @field_validator("target_duration")
    @classmethod
    def _validate_target_duration(cls, v: int) -> int:
        return max(60, min(350, int(v)))

    @field_validator("output_count")
    @classmethod
    def _validate_output_count(cls, v: int) -> int:
        return max(1, min(20, int(v)))

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
        if self.voice_source not in {"manual", "subtitle", "translated_subtitle"}:
            raise ValueError("voice_source must be 'manual', 'subtitle', or 'translated_subtitle'")
        if self.voice_source == "manual" and not (self.voice_text or "").strip():
            raise ValueError("voice_text is required when voice_enabled=true and voice_source=manual")
        if self.subtitle_target_language not in {"vi", "en", "ja"}:
            raise ValueError("subtitle_target_language must be one of vi, en, ja")
        if self.voice_language not in {"vi-VN", "ja-JP", "en-US", "en-GB"}:
            raise ValueError("voice_language must be one of vi-VN, ja-JP, en-US, en-GB")
        if self.voice_gender not in {"female", "male"}:
            raise ValueError("voice_gender must be 'female' or 'male'")
        if self.voice_mix_mode not in {"replace_original", "keep_original_low"}:
            raise ValueError("voice_mix_mode must be 'replace_original' or 'keep_original_low'")
        return self

    @model_validator(mode="after")
    def _coerce_groq_to_llm(self):
        """Copy groq_* legacy fields into llm_* canonical fields when llm_* is not set.

        Runs at deserialization time so stored jobs that predate llm_* fields
        work transparently — the pipeline only reads llm_* fields.
        """
        if self.llm_enabled is None:
            self.llm_enabled = self.groq_analysis_enabled
        if self.llm_model is None:
            self.llm_model = self.groq_model
        if self.llm_language is None:
            self.llm_language = self.groq_content_language
        if self.llm_min_quality is None:
            self.llm_min_quality = self.groq_min_quality_score
        if self.llm_mode is None:
            self.llm_mode = self.groq_selection_strategy
        return self


# ── Upload ───────────────────────────────────────────────────────────────

class UploadRequest(BaseModel):
    channel_code: str
    account_key: str = "default"
    config_mode: Optional[str] = "ui"

    # Schedule
    dry_run: bool = False
    max_items: int = 0
    include_hashtags: bool = True
    caption_prefix: Optional[str] = ""
    use_schedule: bool = False
    schedule_slot_1: Optional[str] = None
    schedule_slot_2: Optional[str] = None
    schedule_slots: Optional[list[str]] = None
    schedule_use_local_tz: bool = True
    selected_files: Optional[list[str]] = None

    # Network / proxy
    network_mode: Optional[str] = "direct"
    proxy_server: Optional[str] = ""
    proxy_username: Optional[str] = ""
    proxy_password: Optional[str] = ""
    proxy_bypass: Optional[str] = ""

    # GPM
    use_gpm: bool = False
    gpm_profile_id: Optional[str] = ""
    gpm_browser_ws: Optional[str] = ""

    # Browser
    browser_preference: Optional[str] = "chromeportable"
    browser_executable: Optional[str] = ""
    headless: bool = False

    # Credentials
    login_username: Optional[str] = ""
    login_password: Optional[str] = ""
    tiktok_username: Optional[str] = ""
    tiktok_password: Optional[str] = ""
    mail_username: Optional[str] = ""
    mail_password: Optional[str] = ""

    # Paths
    root_path: Optional[str] = ""
    user_data_dir: Optional[str] = ""
    video_input_dir: Optional[str] = ""
    retry_count: int = 2


class UploadQueueAddRequest(BaseModel):
    video_id: Optional[str] = ""
    video_path: Optional[str] = ""
    render_job_id: Optional[str] = ""
    part_no: int = 0
    channel_code: Optional[str] = ""
    account_id: Optional[str] = ""
    platform: Optional[str] = "tiktok"
    caption: Optional[str] = ""
    hashtags: Optional[list[str]] = None
    scheduled_at: Optional[str] = ""
    priority: int = 0


UPLOAD_ACCOUNT_STATUSES = {"active", "warming", "limited", "banned", "disabled", "login_required"}
UPLOAD_LOGIN_STATES = {"unknown", "logged_in", "logged_out", "challenge", "expired"}
UPLOAD_PROFILE_LOCK_STATES = {"idle", "locked", "stale_recovered", "conflict"}
UPLOAD_VIDEO_SOURCE_TYPES = {"manual_file", "import_folder", "render_export_later"}
UPLOAD_VIDEO_STATUSES = {"ready", "queued", "uploaded", "failed", "disabled"}
UPLOAD_QUEUE_STATUSES = {"pending", "scheduled", "uploading", "success", "failed", "held", "cancelled"}
UPLOAD_QUEUE_SAFE_UPDATE_STATUSES = {"pending", "scheduled", "held"}
UPLOAD_SCHEDULER_STATUSES = {"stopped", "running"}


class UploadAccountBase(BaseModel):
    platform: Optional[str] = "tiktok"
    channel_code: Optional[str] = ""
    account_key: Optional[str] = ""
    display_name: Optional[str] = ""
    status: Optional[str] = "active"
    profile_path: Optional[str] = ""
    proxy_id: Optional[str] = ""
    proxy_config: Optional[dict] = Field(default_factory=dict)
    daily_limit: Optional[int] = 0
    cooldown_minutes: Optional[int] = 0
    today_count: Optional[int] = 0
    last_upload_at: Optional[str] = None
    last_login_check_at: Optional[str] = None
    login_state: Optional[str] = "unknown"
    profile_lock_state: Optional[str] = "idle"
    health_json: Optional[dict] = Field(default_factory=dict)
    metadata_json: Optional[dict] = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: Optional[str]) -> str:
        value = (v or "active").strip().lower()
        if value not in UPLOAD_ACCOUNT_STATUSES:
            raise ValueError(f"status must be one of {sorted(UPLOAD_ACCOUNT_STATUSES)!r}")
        return value

    @field_validator("login_state")
    @classmethod
    def _validate_login_state(cls, v: Optional[str]) -> str:
        value = (v or "unknown").strip().lower()
        if value not in UPLOAD_LOGIN_STATES:
            raise ValueError(f"login_state must be one of {sorted(UPLOAD_LOGIN_STATES)!r}")
        return value

    @field_validator("profile_lock_state")
    @classmethod
    def _validate_profile_lock_state(cls, v: Optional[str]) -> str:
        value = (v or "idle").strip().lower()
        if value not in UPLOAD_PROFILE_LOCK_STATES:
            raise ValueError(f"profile_lock_state must be one of {sorted(UPLOAD_PROFILE_LOCK_STATES)!r}")
        return value

    @field_validator("daily_limit", "cooldown_minutes", "today_count")
    @classmethod
    def _validate_non_negative(cls, v: Optional[int]) -> int:
        return max(0, int(v or 0))


class UploadAccountCreate(UploadAccountBase):
    account_id: Optional[str] = None
    account_key: Optional[str] = "default"


class UploadAccountUpdate(BaseModel):
    platform: Optional[str] = None
    channel_code: Optional[str] = None
    account_key: Optional[str] = None
    display_name: Optional[str] = None
    status: Optional[str] = None
    profile_path: Optional[str] = None
    proxy_id: Optional[str] = None
    proxy_config: Optional[dict] = None
    daily_limit: Optional[int] = None
    cooldown_minutes: Optional[int] = None
    today_count: Optional[int] = None
    last_upload_at: Optional[str] = None
    last_login_check_at: Optional[str] = None
    login_state: Optional[str] = None
    profile_lock_state: Optional[str] = None
    health_json: Optional[dict] = None
    metadata_json: Optional[dict] = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip().lower()
        if value not in UPLOAD_ACCOUNT_STATUSES:
            raise ValueError(f"status must be one of {sorted(UPLOAD_ACCOUNT_STATUSES)!r}")
        return value

    @field_validator("login_state")
    @classmethod
    def _validate_login_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip().lower()
        if value not in UPLOAD_LOGIN_STATES:
            raise ValueError(f"login_state must be one of {sorted(UPLOAD_LOGIN_STATES)!r}")
        return value

    @field_validator("profile_lock_state")
    @classmethod
    def _validate_profile_lock_state(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip().lower()
        if value not in UPLOAD_PROFILE_LOCK_STATES:
            raise ValueError(f"profile_lock_state must be one of {sorted(UPLOAD_PROFILE_LOCK_STATES)!r}")
        return value

    @field_validator("daily_limit", "cooldown_minutes", "today_count")
    @classmethod
    def _validate_non_negative(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        return max(0, int(v or 0))


class ProxyTestRequest(BaseModel):
    type: Optional[str] = "http"
    host: str = ""
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None


class AddUploadVideoRequest(BaseModel):
    video_path: str
    platform: Optional[str] = "tiktok"
    source_type: Optional[str] = "manual_file"
    caption: Optional[str] = ""
    hashtags: list[str] = Field(default_factory=list)
    cover_path: Optional[str] = ""
    note: Optional[str] = ""
    metadata: Optional[dict] = Field(default_factory=dict)

    @field_validator("video_path")
    @classmethod
    def _validate_video_path(cls, v: str) -> str:
        value = str(v or "").strip()
        if not value:
            raise ValueError("video_path is required")
        return value

    @field_validator("source_type")
    @classmethod
    def _validate_source_type(cls, v: Optional[str]) -> str:
        value = (v or "manual_file").strip().lower()
        if value not in UPLOAD_VIDEO_SOURCE_TYPES:
            raise ValueError(f"source_type must be one of {sorted(UPLOAD_VIDEO_SOURCE_TYPES)!r}")
        return value


class UpdateUploadVideoRequest(BaseModel):
    caption: Optional[str] = None
    hashtags: Optional[list[str]] = None
    cover_path: Optional[str] = None
    note: Optional[str] = None
    status: Optional[str] = None
    metadata: Optional[dict] = None

    @field_validator("status")
    @classmethod
    def _validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip().lower()
        if value not in UPLOAD_VIDEO_STATUSES:
            raise ValueError(f"status must be one of {sorted(UPLOAD_VIDEO_STATUSES)!r}")
        return value


class UploadVideoResponse(BaseModel):
    video_id: str
    video_path: str
    file_name: str = ""
    platform: str = "tiktok"
    source_type: str = "manual_file"
    status: str = "ready"
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    cover_path: str = ""
    note: str = ""
    duration_sec: float = 0
    file_size: int = 0
    metadata: dict = Field(default_factory=dict)
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UploadQueueUpdateRequest(BaseModel):
    account_id: Optional[str] = None
    caption: Optional[str] = None
    hashtags: Optional[list[str]] = None
    priority: Optional[int] = None
    scheduled_at: Optional[str] = None
    status: Optional[str] = None

    @field_validator("status")
    @classmethod
    def _validate_queue_status(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        value = v.strip().lower()
        if value not in UPLOAD_QUEUE_SAFE_UPDATE_STATUSES:
            raise ValueError(f"status can only be one of {sorted(UPLOAD_QUEUE_SAFE_UPDATE_STATUSES)!r}")
        return value


class UploadQueueResponse(BaseModel):
    queue_id: str
    video_id: Optional[str] = ""
    video_path: str
    account_id: Optional[str] = ""
    platform: str = "tiktok"
    caption: str = ""
    hashtags: list[str] = Field(default_factory=list)
    status: str = "pending"
    priority: int = 0
    scheduled_at: str = ""
    attempt_count: int = 0
    max_attempts: int = 3
    last_error: str = ""
    metadata: dict = Field(default_factory=dict)
    video_file_name: str = ""
    account_display_name: str = ""
    account_key: str = ""
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UploadSchedulerStatusResponse(BaseModel):
    scheduler_enabled: bool = False
    max_concurrent_uploads: int = 1
    tick_interval_seconds: int = 30
    last_tick_at: str = ""
    running_count: int = 0
    status: str = "stopped"
    next_eligible_count: int = 0
    blocked_counts: dict = Field(default_factory=dict)

    @field_validator("status")
    @classmethod
    def _validate_scheduler_status(cls, v: Optional[str]) -> str:
        value = (v or "stopped").strip().lower()
        if value not in UPLOAD_SCHEDULER_STATUSES:
            raise ValueError(f"status must be one of {sorted(UPLOAD_SCHEDULER_STATUSES)!r}")
        return value


PROXY_POOL_TYPES = {"http", "https", "socks4", "socks5"}
PROXY_POOL_MARKETS = {"", "us", "jp", "eu", "custom"}


class ProxyPoolCreate(BaseModel):
    name: Optional[str] = ""
    type: Optional[str] = "http"
    host: str
    port: Optional[int] = None
    username: Optional[str] = ""
    password: Optional[str] = ""
    market: Optional[str] = ""
    notes: Optional[str] = ""

    @field_validator("host")
    @classmethod
    def _validate_host(cls, v: str) -> str:
        value = str(v or "").strip()
        if not value:
            raise ValueError("host is required")
        return value

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: Optional[str]) -> str:
        return str(v or "http").strip().lower() or "http"

    @field_validator("market")
    @classmethod
    def _validate_market(cls, v: Optional[str]) -> str:
        return str(v or "").strip().lower()

    @field_validator("port")
    @classmethod
    def _validate_port(cls, v: Optional[int]) -> int:
        return max(0, int(v or 0))


class ProxyPoolUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    market: Optional[str] = None
    notes: Optional[str] = None
    status: Optional[str] = None
    last_tested_at: Optional[str] = None
    last_ok_at: Optional[str] = None
    latency_ms: Optional[int] = None
    last_ip: Optional[str] = None
    last_error: Optional[str] = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return str(v).strip().lower() or "http"

    @field_validator("market")
    @classmethod
    def _validate_market(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return str(v).strip().lower()

    @field_validator("port")
    @classmethod
    def _validate_port(cls, v: Optional[int]) -> Optional[int]:
        if v is None:
            return None
        return max(0, int(v or 0))


# ── Job status response (GET /api/jobs/{job_id}) ─────────────────────────────
# Mirrors frontend/src/types/api.ts:JobStatus and the day-1 columns of the
# `jobs` table in app.db. Wired as response_model on routes/jobs.py:359 so the
# field set is documented and enforced by Pydantic. extra="allow" preserves
# additive forward-compatibility: future columns reach the wire without
# breaking the contract, but the documented fields are guaranteed present.
class JobStatusResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    job_id: str
    kind: str
    status: str
    stage: str = ""
    progress_percent: int = 0
    message: str = ""
    payload_json: Optional[str] = None
    result_json: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    # error_kind is populated by the handler when status == "failed" — Optional
    # so non-failed responses (where the field may be NULL in DB) still validate.
    error_kind: Optional[str] = None
