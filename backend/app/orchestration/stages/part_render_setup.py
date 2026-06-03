"""Per-part RENDER pre-flight stage — encoding params + thread + plan.

Sprint 6.D-2.4 — extracted verbatim from stages/part_renderer.py
(lines 219-319 of the post-2.3 file). No logic changes; pure relocation.

run_render_preflight() runs once per part during process_one_part,
immediately after the JobPartStage.RENDERING upsert (which stays in
the caller — Sacred Contract #5 visibility) and before the
base-clip/motion-crop/render_part_smart FFmpeg core (Sprint 6.D-2.5
target).

Scope re-cast note:
  Plan §3.2 originally listed phase 2.4 as "TRANSCRIBE stage block".
  By the time phase 2.4 ran, all TRANSCRIBE logic had already been
  absorbed into prepare_part_assets (Sprint 6.D-2.2) — no separate
  TRANSCRIBE block remained in process_one_part. Phase 2.4 was
  re-scoped to "RENDER pre-flight" (this module) so that phase 2.5's
  FFmpeg/qa_pipeline core block could be tackled at a safer LOC
  budget.

Block responsibilities (in order):
  1. Visual-finish params from content type:
       _vf_ct, _vf_crf_delta, _part_video_crf, _vf_bitrate_profile,
       _vf_subtitle_bump, + visual_finish_applied INFO log.
  2. Encode-progress monitor thread (_render_progress_timer running
     on a daemon thread). Returns _encode_stop (Event) and
     _encode_timer (Thread) for the caller's render-completion
     `_encode_stop.set()` + `_encode_timer.join(timeout=5.0)`.
  3. Render-start timers: _t_encode + _t_render.
  4. Motion-crop cache key resolution (_render_cache_key) + the empty
     _motion_crop_fallback list (mutated by-ref by downstream
     composite_overlays_on_base_clip call).
  5. PartExecutionPlan construction + part_execution_plan INFO log.
  6. CameraStrategy construction + camera_strategy INFO log.
  7. Feature-flag warning when FEATURE_OVERLAY_AFTER_BASE_CLIP=1 but
     FEATURE_BASE_CLIP_FIRST=0 — read at the module-load level of
     this module via os.getenv (identical to part_renderer.py's
     module-level reads; same behavior, same env-var lookup).

Returns RenderPreflightResult dataclass with all 13 outputs the
downstream RENDER block consumes. The caller aliases each field
back to its original local-variable name in process_one_part so
the rest of the RENDER block is byte-for-byte unchanged.

Sacred Contracts honored:
  - #5 Frozen part-stage names: JobPartStage.RENDERING transition
       stays in the CALLER (process_one_part line 217) — not moved
       into this module. This keeps the frozen state-machine
       transition visible at the call site where reviewers expect it.
  - #6 _emit_render_event signature: this block has NO _emit_render_event
       calls (visual_finish_applied is a logger.info, not a WS event).
  - #7 Sole DB writer: this block has NO upsert_job_part calls.

Logger note (same pattern as 6.D-2.1 / 2.2 / 2.3):
  `logger = logging.getLogger("app.render")` preserved verbatim so
  existing log routing resolves identically.

Feature-flag env-var read note:
  `_FEATURE_BASE_CLIP_FIRST` and `_FEATURE_OVERLAY_AFTER_BASE_CLIP`
  are read at module-load time via os.getenv (identical to
  part_renderer.py's module-level reads). The flags are read ONCE
  per process startup in BOTH modules — behavior is identical
  because both reads happen at import time and read the same
  deterministic env var. No drift risk.
"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

from app.orchestration.camera_strategy import CameraStrategy
from app.orchestration.part_plan import PartExecutionPlan
from app.orchestration.pipeline_cache import _render_cache_key
from app.orchestration.pipeline_segment_selection import _PLATFORM_PROFILES
from app.orchestration.render_events import _render_progress_timer
from app.orchestration.stages.part_render_context import PartRenderContext
from app.services.render_engine import (
    content_type_crf_delta as _crf_delta_for_content_type,
)

# Preserve original logger name (same pattern as 6.D-2.1 / 2.2 / 2.3).
logger = logging.getLogger("app.render")

# Re-read feature flags at this module's load time — identical to
# part_renderer.py module-level reads. Both modules read the same env
# vars deterministically at import; no drift possible.
_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"


@dataclass
class RenderPreflightResult:
    """Bundle of values produced by run_render_preflight — caller aliases
    each field back to its original local-variable name so the rest of
    process_one_part is byte-for-byte unchanged.

    `motion_crop_fallback` is a mutable list passed by reference and
    appended to by downstream composite_overlays_on_base_clip via the
    `_fallback_flag=` kwarg. Do not replace with a tuple.
    """
    # Encoding params
    vf_ct: str
    vf_crf_delta: int
    part_video_crf: int
    vf_bitrate_profile: str
    vf_subtitle_bump: bool
    # Threading (lifecycle continues in caller: encode_stop.set() + encode_timer.join())
    encode_stop: threading.Event
    encode_timer: threading.Thread
    # Timers
    t_encode: float
    t_render: float
    # Motion-crop state
    motion_ck: Optional[str]
    motion_crop_fallback: list
    # Plan + camera
    part_plan: PartExecutionPlan
    camera_strategy: CameraStrategy


def run_render_preflight(
    ctx: PartRenderContext,
    idx: int,
    seg: dict,
    part_name: str,
    final_part_path: str,
    _effective_start: float,
    _trim_offset: float,
    _visual_trim: float,
    _force_accurate_cut: bool,
    part_subtitle_enabled: bool,
) -> RenderPreflightResult:
    """Run the RENDER pre-flight block. See module docstring for the
    7-step responsibility breakdown.

    The encode-progress monitor thread is STARTED here. The caller
    is responsible for `result.encode_stop.set()` + `result.encode_timer.join(timeout=5.0)`
    after the FFmpeg render completes (or in a finally block).
    """
    _vf_ct = seg.get("content_type_hint", "vlog")
    _vf_crf_delta = _crf_delta_for_content_type(_vf_ct)
    _part_video_crf = max(11, min(28, ctx.tuned["video_crf"] + _vf_crf_delta))
    _vf_bitrate_profile = (
        "high" if _vf_ct == "montage" else
        "low" if _vf_ct in ("interview", "tutorial") else "standard"
    )
    _vf_subtitle_bump = not ctx.payload.motion_aware_crop and _vf_ct in ("interview", "commentary")
    logger.info(
        "visual_finish_applied part=%d content_type=%s crf=%d(delta=%+d) "
        "bitrate_profile=%s subtitle_safety_bump=%s",
        idx, _vf_ct, _part_video_crf, _vf_crf_delta,
        _vf_bitrate_profile, _vf_subtitle_bump,
    )

    _encode_stop = threading.Event()
    _encode_timer = threading.Thread(
        target=_render_progress_timer,
        args=(
            _encode_stop, ctx.job_id, idx, part_name, seg,
            final_part_path,
            time.monotonic(),
            max(float(seg.get("duration") or 0), 1.0),
            ctx.effective_channel,
        ),
        daemon=True,
        name=f"progress-timer-{ctx.job_id[:8]}-p{idx}",
    )
    _encode_timer.start()
    _t_encode = time.perf_counter()
    _t_render = time.perf_counter()
    _motion_ck = None
    _motion_crop_fallback: list = []
    if ctx.payload.motion_aware_crop and ctx.src_stat_for_motion is not None:
        try:
            _motion_ck = _render_cache_key(
                str(ctx.source_path),
                ctx.src_stat_for_motion.st_mtime,
                ctx.src_stat_for_motion.st_size,
                round(_effective_start, 3),
                round(float(seg["end"]), 3),
                str(ctx.payload.aspect_ratio),
                float(ctx.payload.frame_scale_x),
                float(ctx.payload.frame_scale_y),
                str(getattr(ctx.payload, "reframe_mode", "subject")),
                str(seg.get("content_type_hint", "vlog")),
            )
        except Exception:
            _motion_ck = None
    _part_plan = PartExecutionPlan(
        part_no=idx,
        source_start=float(seg["start"]),
        source_end=float(seg["end"]),
        effective_start=_effective_start,
        trim_offset_sec=_trim_offset,
        visual_trim_sec=_visual_trim,
        force_accurate_cut=_force_accurate_cut,
        subtitle_enabled=part_subtitle_enabled,
        motion_aware_crop=bool(ctx.payload.motion_aware_crop),
        reframe_mode=str(getattr(ctx.payload, "reframe_mode", "subject")),
        frame_scale_x=int(ctx.payload.frame_scale_x),
        frame_scale_y=int(ctx.payload.frame_scale_y),
        content_type=_vf_ct,
        video_crf=_part_video_crf,
        bitrate_profile=_vf_bitrate_profile,
        voice_enabled=bool(getattr(ctx.payload, "voice_enabled", False)),
        voice_source=str(getattr(ctx.payload, "voice_source", "none")),
        playback_speed=float(
            max(0.5, min(1.5, float(ctx.payload.playback_speed or 1.07)
                   + _PLATFORM_PROFILES.get(ctx.target_platform, {}).get("speed_delta", 0.0)))
        ),
    )
    logger.info(
        "part_execution_plan part=%d trim=%.3f+%.3f accurate_cut=%s "
        "subtitle=%s crop=%s reframe=%s voice=%s speed=%.3f crf=%d",
        _part_plan.part_no, _part_plan.trim_offset_sec, _part_plan.visual_trim_sec,
        _part_plan.force_accurate_cut, _part_plan.subtitle_enabled,
        _part_plan.motion_aware_crop, _part_plan.reframe_mode,
        _part_plan.voice_enabled, _part_plan.playback_speed, _part_plan.video_crf,
    )
    _camera_strategy = CameraStrategy(
        aspect_ratio=ctx.payload.aspect_ratio,
        frame_scale_x=int(ctx.payload.frame_scale_x),
        frame_scale_y=int(ctx.payload.frame_scale_y),
        motion_aware_crop=bool(ctx.payload.motion_aware_crop),
        reframe_mode=str(getattr(ctx.payload, "reframe_mode", "subject")),
        content_type=_vf_ct,
    )
    logger.info(
        "camera_strategy part=%d mode=%s crop=%s reframe=%s aspect=%s scale=%dx%d",
        idx, _camera_strategy.camera_mode, _camera_strategy.motion_aware_crop,
        _camera_strategy.reframe_mode, _camera_strategy.aspect_ratio,
        _camera_strategy.frame_scale_x, _camera_strategy.frame_scale_y,
    )
    if _FEATURE_OVERLAY_AFTER_BASE_CLIP and not _FEATURE_BASE_CLIP_FIRST:
        logger.warning(
            "overlay_flag_ignored job_id=%s part=%d: "
            "FEATURE_OVERLAY_AFTER_BASE_CLIP=1 requires FEATURE_BASE_CLIP_FIRST=1 "
            "— using render_part_smart() for final output",
            ctx.job_id, idx,
        )

    return RenderPreflightResult(
        vf_ct=_vf_ct,
        vf_crf_delta=_vf_crf_delta,
        part_video_crf=_part_video_crf,
        vf_bitrate_profile=_vf_bitrate_profile,
        vf_subtitle_bump=_vf_subtitle_bump,
        encode_stop=_encode_stop,
        encode_timer=_encode_timer,
        t_encode=_t_encode,
        t_render=_t_render,
        motion_ck=_motion_ck,
        motion_crop_fallback=_motion_crop_fallback,
        part_plan=_part_plan,
        camera_strategy=_camera_strategy,
    )
