
import json
import os
import subprocess
import threading
import time
import logging
from functools import lru_cache
from pathlib import Path
from app.domain.timeline import TimelineMap
from app.services.motion_crop import render_motion_aware_crop, MotionCropConfig
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin, _summarize_ffmpeg_stderr
from app.services.text_overlay import append_text_layer_filters
from app.services.encoder_helpers import (
    ffmpeg_encoders_text as _ffmpeg_encoders_text,
    has_encoder as _has_encoder,
    nvenc_runtime_ready as _nvenc_runtime_ready,
    codec_extra_flags as _codec_extra_flags,
    map_preset_for_encoder as _map_preset_for_encoder,
    reup_video_filters as _reup_video_filters,
    reup_audio_filter as _reup_audio_filter,
    safe_filter_path as _safe_filter_path,
    detect_windows_fontfile as _detect_windows_fontfile,
    detect_windows_fonts_dir as _detect_windows_fonts_dir,
    get_custom_fonts_dir as _get_custom_fonts_dir,
)
from app.services.render.ffmpeg_helpers import (
    NVENC_SEMAPHORE, _FFMPEG_TIMEOUT_SEC, _FPS_CAP, _tls,
    set_thread_cancel_event,
    _PROBE_CACHE, _PROBE_CACHE_LOCK, _file_probe_key,
    probe_video_metadata, extract_thumbnail_frame,
    _run_ffmpeg_with_retry,
    nvenc_available, _resolve_codec,
    _effect_filter, _cinematic_color_filter, _cinematic_sharpen_filter,
    _smart_denoise_filter, content_type_crf_delta,
    _build_audio_mix_filter, _build_audio_filter,
    _parse_fps_ratio, _probe_fps, _resolve_fps,
    _sanitize_speed, _has_audio_stream, _probe_duration,
    resolve_ffmpeg_threads, resolve_target_dimensions,
)
from app.services.render.clip_ops import (
    cut_video,
    detect_silence_trim_offset,
    detect_bad_first_frame,
    _detect_silence_segments,
    apply_micro_pacing,
)
from app.services.render.base_clip_renderer import render_base_clip
from app.services.render.overlay_compositor import composite_overlays_on_base_clip
from app.services.render.legacy_renderer import render_part, render_part_smart


logger = logging.getLogger(__name__)
