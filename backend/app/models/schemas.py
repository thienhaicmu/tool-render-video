from __future__ import annotations

from pydantic import BaseModel, Field
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
    highlight_per_word: bool = False
    sub_font_size: int = 46
    sub_font: str = "Bungee"
    sub_margin_v: int = 170
    sub_color: str = "#FFFFFF"
    sub_highlight: str = "#FFFF00"
    sub_outline: int = 3

    # Frame / crop
    aspect_ratio: str = "3:4"
    frame_scale_x: int = 100
    frame_scale_y: int = 106
    motion_aware_crop: bool = True
    reframe_mode: str = "subject"

    # Overlay / effect
    add_title_overlay: bool = True
    title_overlay_text: Optional[str] = ""
    effect_preset: str = "slay_soft_01"

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
