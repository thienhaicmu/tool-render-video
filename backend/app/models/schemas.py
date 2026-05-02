from __future__ import annotations

from pydantic import BaseModel, Field, field_validator, model_validator
from typing import Optional


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
    source_mode: Optional[str] = "youtube"
    youtube_url: Optional[str] = ""
    source_video_path: Optional[str] = ""


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
    source_mode: Optional[str] = "youtube"
    source_quality_mode: str = "standard_1080"
    youtube_url: Optional[str] = ""
    youtube_urls: Optional[list[str]] = Field(default_factory=list)
    source_video_path: Optional[str] = ""

    # Output
    output_mode: Optional[str] = "channel"
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
    subtitle_style: Optional[str] = "pro_karaoke"
    subtitle_viral_min_score: int = 0
    subtitle_viral_top_ratio: float = 1.0
    subtitle_only_viral_high: bool = False
    highlight_per_word: bool = False
    sub_font_size: int = 46
    sub_font: str = "Bungee"
    sub_margin_v: int = 170
    sub_color: str = "#FFFFFF"
    sub_highlight: str = "#FFFF00"
    sub_outline: int = 3
    sub_x_percent: float = 50.0

    # Frame / crop
    aspect_ratio: str = "3:4"
    frame_scale_x: int = 100
    frame_scale_y: int = 106
    motion_aware_crop: bool = False
    reframe_mode: str = "center"

    # Overlay / effect
    add_title_overlay: bool = False
    title_overlay_text: Optional[str] = ""
    effect_preset: str = "slay_soft_01"
    loudnorm_enabled: bool = False

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
    hook_applied_text: Optional[str] = None
    hook_apply_enabled: bool = False
    hook_score: Optional[float] = None
    subtitle_edits: Optional[list] = None
    combined_scoring_enabled: bool = False
    adaptive_scoring_enabled: bool = False
    auto_best_export_enabled: bool = False
    auto_best_export_count: int = 3

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
