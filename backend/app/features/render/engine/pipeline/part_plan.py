from dataclasses import dataclass


@dataclass
class PartExecutionPlan:
    part_no: int
    # Timing decisions (resolved before cut_video)
    source_start: float
    source_end: float
    effective_start: float
    trim_offset_sec: float
    visual_trim_sec: float
    force_accurate_cut: bool
    # Subtitle
    subtitle_enabled: bool
    # Crop / reframe
    motion_aware_crop: bool
    reframe_mode: str
    frame_scale_x: int
    frame_scale_y: int
    # Visual finish
    content_type: str
    video_crf: int
    bitrate_profile: str
    # Voice intent (what was requested, not whether it succeeded)
    voice_enabled: bool
    voice_source: str
    playback_speed: float
    # Sprint 1: resolved from ClipPlan.hook_score; visual effect wired in Sprint 2
    zoom_burst: bool = False
