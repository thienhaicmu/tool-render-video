from __future__ import annotations

import math
import os
import subprocess
import time
import logging
from pathlib import Path
from typing import List, Optional, Tuple

# Sprint 6.D dead-import cleanup: this file is now a thin skeleton
# (build_motion_path dispatcher + render_motion_aware_crop + a few
# small helpers). Almost all imports below are intentional re-exports
# for the Sprint 6.D-3.x extracted modules — external consumers
# (render_engine.py, render/legacy_renderer.py, base_clip_renderer.py,
# tests/test_probe_unification.py, tests/test_motion_crop_guards.py,
# tests/test_render_audit_p0_fixes.py, tests/test_encoder_helpers.py,
# and the build_subject_path family inside motion_crop_path.py) reach
# these symbols through `app.services.motion_crop`. The noqa: F401
# markers acknowledge the re-export contract.

# Sprint 6.D-3.1: motion-path cache helpers.
from app.features.render.engine.motion.cache import (  # noqa: F401 (re-exported)
    _MOTION_CACHE_TTL_SEC,
    _motion_cache_key,
    _motion_path_cache_get,
    _motion_path_cache_put,
)
# Sprint 6.D-3.2: MotionCropConfig + content-type tracking overrides.
from app.features.render.engine.motion.config import (
    _CONTENT_TYPE_TRACKING,  # noqa: F401 (re-exported)
    _apply_content_type_to_cfg,  # noqa: F401 (re-exported)
    MotionCropConfig,
)
# Sprint 6.D-3.3: generic helpers (codec flags, font detection, ffprobe,
# math primitives, OpenCV cascade/IoU). Many symbols here ARE used in
# body — _safe_filter_path / _detect_windows_fontfile / fonts_dir
# helpers are called by render_motion_aware_crop.
from app.features.render.engine.motion.utils import (
    _codec_flags,  # noqa: F401 (re-exported for tests)
    _safe_filter_path,
    _detect_windows_fontfile,
    _detect_windows_fonts_dir,
    _get_custom_fonts_dir,
    ffprobe_video_info,  # noqa: F401 (re-exported for tests/test_probe_unification.py)
    has_audio_stream,  # noqa: F401 (re-exported for tests/test_probe_unification.py)
    clamp,
    ema,  # noqa: F401 (re-exported)
    _smoothstep,  # noqa: F401 (re-exported)
    _gaussian_smooth_1d,  # noqa: F401 (re-exported)
    _load_cascade,  # noqa: F401 (re-exported)
    _iou_xywh,  # noqa: F401 (re-exported)
)
# Sprint 6.D-3.4: _ByteTrackSubject + _create_tracker.
from app.features.render.engine.motion.tracker import (  # noqa: F401 (re-exported)
    _ByteTrackSubject,
    _create_tracker,
)
# Sprint 6.D-3.5a: MediaPipe lazy helpers + detection orchestration.
from app.features.render.engine.motion.detection import (  # noqa: F401 (re-exported)
    _get_mp_detector,
    _detect_mediapipe_faces,
    _has_subject_in_sample,
    _get_mp_pose,
    _get_eye_anchor_rel,
    prepare_detection_frame,
    _detect_subjects_in_frame,
)
# Sprint 6.D-3.5b: scoring helpers + best-subject pick.
from app.features.render.engine.motion.scoring import (  # noqa: F401 (re-exported for tests/test_motion_crop_guards.py + the build_subject_path family)
    _subject_area_ratio,
    _subject_edge_overlap_ratio,
    _is_plausible_subject,
    _filter_subject_candidates,
    _pick_best_subject,
    _subject_center,
    _score_subject_candidate,
    _same_subject,
)
# Sprint 6.D-3.5c: trackerless guard helpers.
from app.features.render.engine.motion.trackerless import (  # noqa: F401 (re-exported)
    _trackerless_offcenter_ratio,
    _trackerless_detection_confidence,
    _trackerless_hold_frames_for_confidence,
    _trackerless_crop_side_fill_ratio,
    _apply_trackerless_center_guard,
)
# Sprint 6.D-3.7: pixel-diff motion-path implementation.
# Sprint 7.1 (2026-06-05): module renamed legacy.py → motion_pixel_diff.py
# to stop misleading auditors. Symbols + behaviour unchanged.
from app.features.render.engine.motion.pixel_diff import (  # noqa: F401 (re-exported)
    detect_motion_center,
    _build_motion_path_legacy,
    _detect_scene_ranges_in_clip,
)
# Sprint 6.D-3.6a + 3.6b + Sprint 5.2 split:
#   build_subject_path lives in path.py (multi-scene dispatcher + single-
#   scene fast path). build_subject_path_scene was split out into
#   path_scene.py (per-scene state machine, ~530 LOC).
# build_motion_path dispatcher (defined below) calls build_subject_path.
# build_subject_path_scene is re-exported even though it is only used by
# build_subject_path's multi-scene dispatch loop — the re-export contract
# is what keeps the deferred-import in path.py resolving cleanly across
# the split.
from app.features.render.engine.motion.path import build_subject_path
from app.features.render.engine.motion.path_scene import (
    build_subject_path_scene,  # noqa: F401 (re-exported)
)

import cv2

from app.services.bin_paths import get_ffmpeg_bin, _summarize_ffmpeg_stderr
from app.features.render.engine.overlay.text_overlay import append_text_layer_filters
from app.features.render.engine.encoder.encoder_helpers import (
    resolve_encoder as _resolve_encoder,
    map_preset_for_encoder as _map_preset_for_encoder,
    reup_video_filters as _reup_video_filters,
    reup_audio_filter as _reup_audio_filter,  # noqa: F401 (re-exported for tests/test_encoder_helpers.py via `mc._reup_audio_filter`)
    safe_filter_path as _safe_filter_path,  # noqa: F811 — intentionally shadows motion_crop_utils re-export (same function)
    detect_windows_fontfile as _detect_windows_fontfile,  # noqa: F811
    detect_windows_fonts_dir as _detect_windows_fonts_dir,  # noqa: F811
    get_custom_fonts_dir as _get_custom_fonts_dir,  # noqa: F811
)

logger = logging.getLogger(__name__)
# `_TRACKER_CAPABILITY_LOGGED` moved to motion_crop_tracker.py with
# _create_tracker (Sprint 6.D-3.4) — it's the function's per-process guard.

# Sprint 6.D-3.5a: MediaPipe face block (_get_mp_detector,
# _detect_mediapipe_faces, _has_subject_in_sample) + MediaPipe pose block
# (_get_mp_pose, _get_eye_anchor_rel) + per-process state flags
# (_mp_face_detector*, _mp_pose_detector*, _POSE_LEFT_EYE/RIGHT_EYE,
# _EYE_CROP_THIRDS) → moved to app.services.motion_crop.detection.
# Re-exported at the top of this file so existing internal call sites
# keep their bare references unchanged.


# `_CONTENT_TYPE_TRACKING`, `_apply_content_type_to_cfg`, and `MotionCropConfig`
# → moved to app.services.motion_crop.config (Sprint 6.D-3.2). Re-exported
# at the top of this file so the rest of motion_crop.py and external consumers
# keep using them via `app.services.motion_crop` import paths.


# Sprint 6.D-3.3: 13 generic helpers (codec flags, fonts, ffprobe, math,
# cascade/IoU) → moved to app.services.motion_crop.utils. Re-exported at
# the top of this file so existing callers in this module + tests keep
# their import paths.


# ---------------------------------------------------------------------------
# CapCut-style Auto Reframe: Subject detection & tracking
# ---------------------------------------------------------------------------

# Sprint 6.D-3.4: `_ByteTrackSubject` + `_create_tracker` → moved to
# app.services.motion_crop.tracker. Re-exported at the top of this file
# so existing internal call sites (build_subject_path,
# build_subject_path_scene) keep using them via bare references.


def _sanitize_speed(playback_speed: float | int | None) -> float:
    try:
        v = float(playback_speed or 1.0)
    except Exception:
        v = 1.0
    return max(0.5, min(1.5, v))


# `_subject_area_ratio` + `_subject_edge_overlap_ratio` → moved to
# app.services.motion_crop.scoring (Sprint 6.D-3.5b).


def _required_lock_confirm_frames(
    cfg: MotionCropConfig,
    tracker_available: bool,
    confidence_score: float | None = None,
    offcenter_ratio: float = 0.0,
) -> int:
    if tracker_available:
        return 1
    base = max(2, int(cfg.subject_switch_confirm_frames or 0))
    if confidence_score is None:
        return base
    if confidence_score < 0.55 or offcenter_ratio > 0.35:
        return max(3, base + 1)
    if confidence_score < 0.72:
        return max(2, base)
    return base


def _untracked_hold_frames(cfg: MotionCropConfig, detect_interval: int) -> int:
    return max(4, min(cfg.lost_subject_hold_frames, max(6, detect_interval // 2)))


# Sprint 6.D-3.5c: 5 trackerless guard helpers → moved to
# app.services.motion_crop.trackerless. Re-exported at top of this file.


# Sprint 6.D-3.5b: _is_plausible_subject, _filter_subject_candidates,
# _pick_best_subject (deferred from 3.5a), _subject_center,
# _score_subject_candidate, _same_subject → moved to
# app.services.motion_crop.scoring. Re-exported at top of this file.
# `prepare_detection_frame` + `_detect_subjects_in_frame` were moved to
# motion_crop_detection in Sprint 6.D-3.5a.


def _subject_to_crop_center(
    subject: Tuple[int, int, int, int],
    crop_w: int,
    crop_h: int,
    frame_w: int,
    frame_h: int,
    padding: float,
    subtitle_safe_ratio: float = 0.0,
    subject_kind: str = "face",
    eye_anchor_rel: Optional[float] = None,
) -> Tuple[float, float]:
    """
    Convert a subject bounding box to the desired crop-window center.
    When eye_anchor_rel is provided (from MediaPipe Pose), places the eye
    midpoint at rule-of-thirds (1/3 from top of crop) for premium framing.
    Falls back to a slight upward bias (y + h * 0.34) when unavailable.
    """
    x, y, w, h = subject
    cx = x + w / 2.0
    if eye_anchor_rel is not None and subject_kind != "body":
        # Premium framing: eyes at rule-of-thirds (1/3 from crop top)
        eye_y = y + h * eye_anchor_rel
        cy = eye_y + crop_h * (0.5 - _EYE_CROP_THIRDS)
    elif subject_kind == "body":
        cy = y + h * 0.50
    else:
        cy = y + h * 0.34

    subject_ratio = (w * h) / max(1.0, float(frame_w * frame_h))
    if subject_ratio > 0.18:
        cx = cx * 0.55 + (frame_w / 2.0) * 0.45
        if eye_anchor_rel is None:
            cy = cy * 0.70 + (frame_h * 0.42) * 0.30
    elif subject_ratio < 0.035:
        if eye_anchor_rel is None:
            cy = min(cy, y + h * 0.42)

    # Apply padding: zoom the crop window out around the subject
    # (padding > 0 means we follow a larger region, feels less claustrophobic)
    # Already handled by subject_padding in the caller's crop_w/crop_h—
    # here we just clamp so the crop stays inside the frame.
    cx = clamp(cx, crop_w / 2.0, frame_w - crop_w / 2.0)
    max_cy = frame_h - crop_h / 2.0
    if subtitle_safe_ratio > 0:
        max_cy -= frame_h * subtitle_safe_ratio * 0.35
    max_cy = max(crop_h / 2.0, max_cy)
    cy = clamp(cy, crop_h / 2.0, max_cy)
    return cx, cy


def _apply_velocity_limiter(
    centers_xy: List[Tuple[float, float]],
    src_w: int,
    src_h: int,
    crop_w: int,
    crop_h: int,
    cfg: MotionCropConfig,
) -> List[Tuple[int, int]]:
    """Convert (cx, cy) float centers → (x, y) integer top-left crop coords.

    Applies velocity + acceleration limits with smoothstep easing for
    cinematic panning: full speed when far from target, graceful deceleration
    when close — no snap, no overshoot.

    Also enforces subtitle_safe_bottom_ratio so the velocity limiter cannot
    push the crop into the subtitle zone even if the input path is at the
    boundary.
    """
    if not centers_xy:
        return []

    max_v = max(1.0, src_w * cfg.max_pan_speed_ratio)
    max_a = max(0.5, src_w * cfg.max_pan_accel_ratio)

    # Subtitle-safe ceiling for crop center Y — same formula as EMA loop.
    max_cy = src_h - crop_h / 2.0
    if cfg.subtitle_safe_bottom_ratio > 0:
        max_cy -= src_h * cfg.subtitle_safe_bottom_ratio * 0.35
    max_cy = max(crop_h / 2.0, max_cy)

    result: List[Tuple[int, int]] = []
    px, py = centers_xy[0]
    pvx, pvy = 0.0, 0.0

    for tx, ty in centers_xy:
        dist = math.hypot(tx - px, ty - py)
        # Smoothstep easing: t=0 near target (decelerate), t=1 far from target (full speed).
        # Minimum 0.12 so the camera always creeps toward target even when very close.
        t = clamp(dist / max(1.0, max_v * 8.0), 0.0, 1.0)
        ease = clamp(_smoothstep(t), 0.12, 1.0)
        dvx = clamp((tx - px) * ease, -max_v, max_v)
        dvy = clamp((ty - py) * ease, -max_v, max_v)
        vx = clamp(dvx, pvx - max_a, pvx + max_a)
        vy = clamp(dvy, pvy - max_a, pvy + max_a)
        nx = clamp(px + vx, crop_w / 2.0, src_w - crop_w / 2.0)
        ny = clamp(py + vy, crop_h / 2.0, max_cy)   # subtitle-safe ceiling

        # Convert center → top-left
        ix = int(clamp(round(nx - crop_w / 2.0), 0, src_w - crop_w))
        iy = int(clamp(round(ny - crop_h / 2.0), 0, src_h - crop_h))
        result.append((ix, iy))

        px, py = nx, ny
        pvx, pvy = vx, vy

    return result


# Sprint 6.D-3.6a + 3.6b: `build_subject_path` + `build_subject_path_scene`
# → moved to app.services.motion_crop.path. Re-exported at top of this file.
# The new module uses deferred imports for _subject_to_crop_center,
# _apply_velocity_limiter, _required_lock_confirm_frames, and
# _untracked_hold_frames — all of which still live in this module.



# Sprint 6.D-3.7: detect_motion_center, _build_motion_path_legacy,
# _detect_scene_ranges_in_clip → moved to app.services.motion_crop.motion_pixel_diff
# (file renamed from legacy.py in Sprint 7.1).
# Re-exported at top of this file. build_motion_path dispatcher stays
# here because it routes to build_subject_path (also here).


# ---------------------------------------------------------------------------
# Public entry point (called by render_engine / render_motion_aware_crop)
# ---------------------------------------------------------------------------

def build_motion_path(
    video_path: str,
    crop_w: int,
    crop_h: int,
    cfg: MotionCropConfig,
    _scene_ranges=None,
    content_type: str = "vlog",
) -> Tuple[List[Tuple[int, int]], float]:
    """
    Route to the appropriate tracking algorithm based on cfg.reframe_mode.

    - "subject" (default): CapCut-style face/body detection + CSRT tracker
    - "motion":            legacy pixel-diff motion tracking
    """
    if cfg.reframe_mode == "subject":
        return build_subject_path(
            video_path, crop_w, crop_h, cfg,
            _scene_ranges=_scene_ranges, content_type=content_type,
        )
    return _build_motion_path_legacy(video_path, crop_w, crop_h, cfg)


# ---------------------------------------------------------------------------
# Main render function (signature unchanged)
# ---------------------------------------------------------------------------

def render_motion_aware_crop(
    input_path: str,
    output_path: str,
    aspect_ratio: str = "3:4",
    scale_x_percent: float = 100.0,
    scale_y_percent: float = 106.0,
    subtitle_file: str | None = None,
    title_text: str | None = None,
    effect_preset: str = "slay_soft_01",
    transition_sec: float = 0.25,
    video_codec: str = "h264",
    video_crf: int = 20,
    video_preset: str = "medium",
    audio_bitrate: str = "192k",
    retry_count: int = 2,
    encoder_mode: str = "auto",
    output_fps: int = 60,
    reup_mode: bool = False,
    reup_overlay_enable: bool = True,
    reup_overlay_opacity: float = 0.08,
    reup_bgm_enable: bool = False,
    reup_bgm_path: str | None = None,
    reup_bgm_gain: float = 0.18,
    playback_speed: float = 1.07,
    text_layers: list[dict] | None = None,
    loudnorm_enabled: bool = False,
    ffmpeg_threads: int | None = None,
    cfg: MotionCropConfig | None = None,
    subtitle_safe_bottom_ratio: float | None = None,
    content_type: str = "vlog",
    _cache_key: str | None = None,
    # Sprint 7.8 (2026-06-05) — fused-source-window mode. When both kwargs
    # are set, input_path is the FULL source file and the encode processes
    # ONLY the [source_start_sec, source_start_sec + duration] window via
    # `cv2.VideoCapture.set(CAP_PROP_POS_FRAMES)` + FFmpeg `-ss/-t`. When
    # None (default), pre-7.8 behaviour byte-identical: whole file processed.
    # See docs/review/SPRINT_7_8_MOTION_AWARE_FUSE_PLAN_2026-06-05.md.
    source_start_sec: float | None = None,
    source_duration_sec: float | None = None,
    source_seek_force_accurate: bool = False,
) -> str:
    layer_count = len(text_layers or [])
    if layer_count:
        logger.info("Applying %d text overlay layer(s) in motion-aware pipeline", layer_count)
    cfg = cfg or MotionCropConfig(scale_x_percent=scale_x_percent, scale_y_percent=scale_y_percent)
    if subtitle_safe_bottom_ratio is not None:
        cfg.subtitle_safe_bottom_ratio = max(0.0, min(0.35, float(subtitle_safe_bottom_ratio)))

    logger.info(
        "motion_smoothing_profile hold_frames=%d dead_zone=%.3f pan_speed=%.4f "
        "ema_fast=%.3f ema_normal=%.3f ema_slow=%.3f gauss_window=%d mode=%s",
        cfg.lost_subject_hold_frames,
        cfg.dead_zone_ratio,
        cfg.max_pan_speed_ratio,
        cfg.ema_alpha_fast,
        cfg.ema_alpha_normal,
        cfg.ema_alpha_slow,
        cfg.temporal_smooth_window,
        cfg.reframe_mode,
    )

    # Sprint 7.8 — fused-source-window mode flag. When True, the OpenCV
    # cap is seeked to the window start and the encode loop is bounded.
    # When False, pre-7.8 whole-file processing path runs unchanged.
    _fuse_window_mode = (
        source_start_sec is not None and source_duration_sec is not None
    )
    if _fuse_window_mode:
        # Sub-functions (build_motion_path / _has_subject_in_sample /
        # _build_motion_path_legacy / _detect_scene_ranges_in_clip) still
        # scan the whole source; the OpenCV main loop here is what limits
        # output to the window. Centers list covers full source — indexed
        # below with start_frame offset. Per-window subject-path optim is
        # deferred to Sprint 7.9 per audit plan.
        logger.info(
            "motion_crop_fuse_window start=%.3fs duration=%.3fs accurate=%s",
            source_start_sec, source_duration_sec, source_seek_force_accurate,
        )

    src_w, src_h, probe_fps = ffprobe_video_info(input_path)

    if aspect_ratio == "1:1":
        out_w, out_h = 1080, 1080
    elif aspect_ratio == "9:16":
        out_w, out_h = 1080, 1920
    elif aspect_ratio == "16:9":
        out_w, out_h = 1920, 1080
    else:
        out_w, out_h = 1080, 1440  # 3:4, 4:5, and any unrecognised value

    scaled_w = int(round(src_w * (cfg.scale_x_percent / 100.0)))
    scaled_h = int(round(src_h * (cfg.scale_y_percent / 100.0)))

    target_ratio = out_w / out_h
    scale_ratio = scaled_w / scaled_h

    if scale_ratio > target_ratio:
        crop_h = scaled_h
        crop_w = int(round(crop_h * target_ratio))
    else:
        crop_w = scaled_w
        crop_h = int(round(crop_w / target_ratio))

    crop_w = min(crop_w, scaled_w)
    crop_h = min(crop_h, scaled_h)

    crop_w_src = int(round(crop_w / (cfg.scale_x_percent / 100.0)))
    crop_h_src = int(round(crop_h / (cfg.scale_y_percent / 100.0)))
    crop_w_src = min(crop_w_src, src_w)
    crop_h_src = min(crop_h_src, src_h)

    # Build crop path (subject-tracking or legacy motion)
    scene_ranges = None
    # Sprint 7.8 — scene-aware tracking forced OFF in fused window mode.
    # Scene boundaries are in source-coords; the windowed encode would
    # mis-map them. Single-scene tracking still runs. Scene-aware-in-fuse
    # is Sprint 7.9+ if measured to matter.
    _scene_aware = cfg.scene_aware_tracking and not _fuse_window_mode
    if _scene_aware:
        scene_ranges = _detect_scene_ranges_in_clip(input_path, cfg)
        if not scene_ranges or len(scene_ranges) <= 1:
            scene_ranges = None
        else:
            logger.info("scene-aware scenes=%d", len(scene_ranges))

    # UP28.1: motion path cache — skip frame scan on rerender of same clip
    _motion_hit = False
    if _cache_key:
        _cached_motion = _motion_path_cache_get(_cache_key)
        if _cached_motion is not None:
            centers, detected_fps = _cached_motion
            _motion_hit = True
            logger.info("motion_cache_hit key=%s centers=%d fps=%.2f", _cache_key[:8], len(centers), detected_fps)
    if not _motion_hit:
        # C3b Early exit: skip expensive per-frame MediaPipe scan on videos
        # with no people. Sample 24 sparse frames first; if no face found,
        # fall back to faster legacy motion tracking instead of subject tracking.
        _skip_subject = (
            cfg.reframe_mode == "subject"
            and not _has_subject_in_sample(input_path)
        )
        if _skip_subject:
            logger.info("motion_crop_early_exit: no face in sample, using motion fallback")
            centers, detected_fps = _build_motion_path_legacy(input_path, crop_w_src, crop_h_src, cfg)
        else:
            centers, detected_fps = build_motion_path(
                input_path,
                crop_w_src,
                crop_h_src,
                cfg,
                _scene_ranges=scene_ranges,
                content_type=content_type,
            )
        if _cache_key:
            _motion_path_cache_put(_cache_key, centers, detected_fps)
            logger.info("motion_cache_miss key=%s centers=%d fps=%.2f", _cache_key[:8], len(centers), detected_fps)

    # Diagnostic: log crop-box sample positions (first, midpoint, last)
    if centers:
        _n = len(centers)
        _sample_mid = centers[_n // 2]
        logger.debug(
            "motion_crop_path input=%s centers=%d crop_src=%dx%d out=%dx%d "
            "first_xy=%s mid_xy=%s last_xy=%s",
            Path(input_path).name, _n, crop_w_src, crop_h_src, out_w, out_h,
            centers[0], _sample_mid, centers[-1],
        )

    # Build ffmpeg video filter chain
    vf_parts = []
    preset_low = (video_preset or "").lower()
    # hqdn3d denoiser only for slower/veryslow (quality mode)
    if preset_low in ("slower", "veryslow"):
        vf_parts.append("hqdn3d=1.5:1.5:6:6")
    if reup_mode:
        # Reup mode: dedicated reup filters (already includes eq+unsharp+hqdn3d)
        vf_parts.extend(_reup_video_filters())
        if reup_overlay_enable:
            opacity = max(0.01, min(0.20, float(reup_overlay_opacity or 0.08)))
            vf_parts.append(f"drawbox=x=0:y=0:w=iw:h=ih:color=black@{opacity}:t=fill")
    else:
        # Normal mode: apply creative effect filter
        if effect_preset == "slay_pop_01":
            vf_parts.append("eq=contrast=1.08:saturation=1.18:brightness=0.01:gamma=1.02,unsharp=5:5:1.2:3:3:0.5")
        elif effect_preset == "story_clean_01":
            vf_parts.append("eq=contrast=1.03:saturation=1.05:brightness=0.0,unsharp=3:3:0.6:3:3:0.15")
        else:
            vf_parts.append("eq=contrast=1.05:saturation=1.10:brightness=0.0:gamma=1.01,unsharp=5:5:0.9:3:3:0.35")

    vf_parts.append("format=yuv420p")
    if transition_sec and transition_sec > 0:
        vf_parts.append(f"fade=t=in:st=0:d={max(0.05, min(0.8, transition_sec))}")

    if subtitle_file and os.path.exists(subtitle_file):
        sub_safe = _safe_filter_path(subtitle_file)
        fonts_dir = _get_custom_fonts_dir() or _detect_windows_fonts_dir()
        if fonts_dir:
            vf_parts.append(f"ass='{sub_safe}':fontsdir='{_safe_filter_path(fonts_dir)}'")
        else:
            vf_parts.append(f"ass='{sub_safe}'")

    if title_text:
        fontfile = _detect_windows_fontfile()
        safe_title = title_text.replace("\\", "\\\\").replace(":", r"\:").replace("'", r"\'")
        drawtext = f"drawtext=text='{safe_title}':fontcolor=white:fontsize=36:x=(w-text_w)/2:y=50:enable='lt(t\\,3)'"
        if fontfile:
            drawtext += f":fontfile='{_safe_filter_path(fontfile)}'"
        vf_parts.append(drawtext)
    append_text_layer_filters(vf_parts, text_layers)

    speed = _sanitize_speed(playback_speed)
    if abs(speed - 1.0) > 1e-4:
        # setpts must come BEFORE fps so the fps filter receives speed-adjusted
        # timestamps and produces a constant-rate output at exactly target_fps.
        vf_parts.append(f"setpts=PTS/{speed:.4f}")

    # Source fps: prefer ffprobe (probe_fps) over OpenCV (detected_fps).
    # OpenCV CAP_PROP_FPS returns 0 for some MKV/TS containers; using it for
    # the ffmpeg -r flag would declare the wrong input rate and cause truncated
    # or jittery output.  ffprobe avg_frame_rate is always authoritative.
    _FPS_CAP = 60
    src_fps = max(1.0, float(probe_fps or detected_fps or cfg.fps_fallback))
    if not output_fps:
        target_fps = max(1, min(int(round(src_fps)), _FPS_CAP))
        fps_policy = f"fps_policy=auto src={src_fps:.3f} target={target_fps}"
    else:
        target_fps = max(1, min(int(round(src_fps)), int(output_fps), _FPS_CAP))
        fps_policy = f"fps_policy=user({output_fps}) src={src_fps:.3f} target={target_fps}"
    logger.info("motion_crop: %s | input=%s", fps_policy, Path(input_path).name)
    # fps filter is always the last video filter — guarantees CFR output.
    vf_parts.append(f"fps={target_fps}")

    resolved_codec = _resolve_encoder(video_codec, encoder_mode=encoder_mode)
    resolved_preset = _map_preset_for_encoder(video_preset, resolved_codec)

    bgm_path = str(reup_bgm_path or "").strip()
    bgm_ok = reup_bgm_enable and bgm_path and Path(bgm_path).is_file()
    input_has_audio = has_audio_stream(input_path)

    # Sprint 7.8 — fused-source-window: the stdin (input 0, rawvideo) is
    # already pre-windowed by the OpenCV loop below (seek + bound). The
    # file input (input 1) must also be windowed so audio aligns: `-ss N
    # -t M` BEFORE `-i input_path` for input-side fast seek (default), or
    # AFTER for output-side accurate seek when `source_seek_force_accurate`.
    _input1_pre: list[str] = []
    _input1_post: list[str] = []
    if _fuse_window_mode:
        if source_seek_force_accurate:
            _input1_post = ["-ss", str(float(source_start_sec)), "-t", str(float(source_duration_sec))]
        else:
            _input1_pre = ["-ss", str(float(source_start_sec)), "-t", str(float(source_duration_sec))]

    ffmpeg_cmd = [
        get_ffmpeg_bin(),
        "-hide_banner", "-loglevel", "error", "-nostats", "-y",
        "-f", "rawvideo", "-pix_fmt", "bgr24",
        "-s", f"{out_w}x{out_h}",
        "-r", str(src_fps),
        "-i", "-",
        *_input1_pre,
        "-i", input_path,
        *_input1_post,
    ]
    if bgm_ok:
        ffmpeg_cmd += ["-stream_loop", "-1", "-i", bgm_path]
    vf_chain = ",".join(vf_parts) if vf_parts else ""
    _threads = ffmpeg_threads if ffmpeg_threads is not None else max(1, min(8, (os.cpu_count() or 4) // 2))
    codec_flags = [
        "-c:v", resolved_codec,
        "-preset", resolved_preset,
        *_codec_flags(resolved_codec, int(video_crf), video_preset),
        "-threads", str(_threads),
        "-pix_fmt", "yuv420p",
        "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
        "-movflags", "+faststart",
    ]
    if bgm_ok:
        gain = max(0.01, min(1.0, float(reup_bgm_gain or 0.18)))
        if input_has_audio:
            # Merge video filters + audio mix into one -filter_complex graph
            fc_parts = []
            if vf_chain:
                fc_parts.append(f"[0:v]{vf_chain}[vout]")
            # Prepend loudnorm to the original audio chain when requested (not in reup mode).
            a0_chain = ("loudnorm=I=-16:LRA=11:TP=-1.5,volume=1.0"
                        if (loudnorm_enabled and not reup_mode) else "volume=1.0")
            a1_chain = f"volume={gain}"
            if abs(speed - 1.0) > 1e-4:
                a0_chain += f",atempo={speed:.4f}"
                a1_chain += f",atempo={speed:.4f}"
            fc_parts.append(f"[1:a]{a0_chain}[a0];[2:a]{a1_chain}[a1];[a0][a1]amix=inputs=2:duration=first:dropout_transition=2[aout]")
            v_label = "[vout]" if vf_chain else "0:v:0"
            ffmpeg_cmd += ["-filter_complex", ";".join(fc_parts),
                           "-map", v_label, "-map", "[aout]"]
        else:
            if vf_chain:
                fc = f"[0:v]{vf_chain}[vout]"
                af = f"volume={gain}"
                if abs(speed - 1.0) > 1e-4:
                    af += f",atempo={speed:.4f}"
                ffmpeg_cmd += ["-filter_complex", fc,
                               "-map", "[vout]", "-map", "2:a:0",
                               "-filter:a", af, "-shortest"]
            else:
                af = f"volume={gain}"
                if abs(speed - 1.0) > 1e-4:
                    af += f",atempo={speed:.4f}"
                ffmpeg_cmd += ["-map", "0:v:0", "-map", "2:a:0",
                               "-filter:a", af, "-shortest"]
    else:
        if vf_chain:
            ffmpeg_cmd += ["-vf", vf_chain]
        ffmpeg_cmd += ["-map", "0:v:0", "-map", "1:a?"]
        if input_has_audio:
            af_parts = []
            if loudnorm_enabled and not reup_mode:
                af_parts.append("loudnorm=I=-16:LRA=11:TP=-1.5")
            if reup_mode:
                af_parts.append(_reup_audio_filter())
            if abs(speed - 1.0) > 1e-4:
                af_parts.append(f"atempo={speed:.4f}")
            if af_parts:
                ffmpeg_cmd += ["-af", ",".join(af_parts)]
    ffmpeg_cmd += [*codec_flags, "-c:a", "aac", "-b:a", audio_bitrate, "-shortest", output_path]

    # Sprint 7.8 — pre-compute window seek frame + budget. centers list
    # (from build_motion_path or _build_motion_path_legacy) covers the
    # FULL source — we index into it with start_frame offset so window
    # frame_idx=0 reads centers[start_frame]. This trades subject-path
    # build speed for correctness; window-only build deferred to 7.9.
    _window_start_frame = 0
    _window_frame_budget: int | None = None
    if _fuse_window_mode:
        _window_start_frame = max(0, int(round(float(source_start_sec) * src_fps)))
        _window_frame_budget = max(1, int(round(float(source_duration_sec) * src_fps)))

    attempt = 0
    while True:
        attempt += 1
        cap = cv2.VideoCapture(input_path)
        if not cap.isOpened():
            raise RuntimeError(f"Cannot open input video: {input_path}")
        # Sprint 7.8 — seek cap to window start. Forward-skim alignment
        # for VBR/keyframe-edge sources is bounded inside the loop below
        # (180 frames â‰ˆ 3s at 60fps). force_accurate_cut on the FFmpeg
        # side is the operator escape if frame-precise alignment matters.
        if _fuse_window_mode and _window_start_frame > 0:
            cap.set(cv2.CAP_PROP_POS_FRAMES, float(_window_start_frame))
        proc = None
        try:
            proc = subprocess.Popen(ffmpeg_cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
            frame_idx = 0
            while True:
                ok, frame = cap.read()
                if not ok or frame is None:
                    break
                # Sprint 7.8 — bound the encode loop to the window budget.
                if _window_frame_budget is not None and frame_idx >= _window_frame_budget:
                    break

                # Sprint 7.8 — centers covers FULL source; offset by start_frame
                # so window frame_idx=0 maps to source frame=start_frame.
                _center_idx = frame_idx + _window_start_frame if _fuse_window_mode else frame_idx
                x, y = centers[_center_idx] if _center_idx < len(centers) else centers[-1]
                crop = frame[y:y + crop_h_src, x:x + crop_w_src]
                if crop.size == 0:
                    crop = frame

                target_w = int(round(crop.shape[1] * cfg.scale_x_percent / 100.0))
                target_h = int(round(crop.shape[0] * cfg.scale_y_percent / 100.0))
                upscale = target_w > crop.shape[1] or target_h > crop.shape[0]
                interp = cv2.INTER_CUBIC if upscale else cv2.INTER_AREA
                scaled = cv2.resize(crop, (target_w, target_h), interpolation=interp)
                sh, sw = scaled.shape[:2]
                start_x = max(0, (sw - out_w) // 2)
                start_y = max(0, (sh - out_h) // 2)
                end_x = min(sw, start_x + out_w)
                end_y = min(sh, start_y + out_h)
                final_frame = scaled[start_y:end_y, start_x:end_x]
                if final_frame.shape[1] != out_w or final_frame.shape[0] != out_h:
                    final_frame = cv2.resize(final_frame, (out_w, out_h), interpolation=cv2.INTER_CUBIC)

                if proc.stdin is None:
                    raise RuntimeError("ffmpeg stdin closed unexpectedly")
                proc.stdin.write(final_frame.tobytes())
                frame_idx += 1

            if proc.stdin:
                proc.stdin.close()
            rc = proc.wait()
            if rc != 0:
                err_tail = ""
                try:
                    if proc.stderr is not None:
                        raw = proc.stderr.read() or b""
                        err_tail = raw.decode(errors="ignore")[-2000:].strip()
                except Exception:
                    err_tail = ""
                diag = _summarize_ffmpeg_stderr(err_tail)
                raise RuntimeError(
                    f"FFmpeg render failed: {diag} (exit={rc})"
                    + (f"\n{err_tail}" if err_tail else "")
                )
            cap.release()
            break
        except BrokenPipeError:
            cap.release()
            err_tail = ""
            try:
                if proc and proc.stderr is not None:
                    raw = proc.stderr.read() or b""
                    err_tail = raw.decode(errors="ignore")[-2000:].strip()
            except Exception:
                err_tail = ""
            try:
                if proc and proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            if attempt > retry_count:
                diag = _summarize_ffmpeg_stderr(err_tail)
                raise RuntimeError(
                    f"FFmpeg render failed (broken pipe): {diag}"
                    + (f"\n{err_tail}" if err_tail else "")
                )
            time.sleep(0.8 * attempt)
            continue
        except Exception:
            cap.release()
            try:
                if proc and proc.stdin:
                    proc.stdin.close()
            except Exception:
                pass
            try:
                if proc and proc.poll() is None:
                    proc.kill()
            except Exception:
                pass
            if attempt > retry_count:
                raise
            time.sleep(0.8 * attempt)

    return output_path

