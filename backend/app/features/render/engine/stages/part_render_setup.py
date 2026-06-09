"""Per-part RENDER pre-flight stage — encoding params + thread + plan.

Sprint 6.D-2.4 — extracted verbatim from stages/part_renderer.py
(lines 219-319 of the post-2.3 file). No logic changes; pure relocation.

run_render_preflight() runs once per part during process_one_part,
immediately after the JobPartStage.RENDERING upsert (which stays in
the caller — Sacred Contract #5 visibility) and before the
base-clip/motion-crop/render_part_smart FFmpeg core (Sprint 6.D-2.5
target).

Scope re-cast note:
  Plan Â§3.2 originally listed phase 2.4 as "TRANSCRIBE stage block".
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

"""
from __future__ import annotations

import logging
import os
import threading
import time
from dataclasses import dataclass
from typing import Optional

from app.features.render.engine.pipeline.camera_strategy import CameraStrategy
from app.features.render.engine.pipeline.part_plan import PartExecutionPlan
from app.features.render.engine.pipeline.pipeline_cache import _render_cache_key
from app.features.render.engine.pipeline.pipeline_segment_selection import _PLATFORM_PROFILES
from app.features.render.engine.pipeline.render_events import _emit_render_event, _render_progress_timer
from app.features.render.engine.stages.part_render_context import PartRenderContext
from app.features.render.engine.encoder.ffmpeg_helpers import (
    content_type_crf_delta as _crf_delta_for_content_type,
)

# Preserve original logger name (same pattern as 6.D-2.1 / 2.2 / 2.3).
logger = logging.getLogger("app.render")



# ────────────────────────────────────────────────────────────────────
# Sprint 4.F — RenderPlan.camera_strategy consume helper.
#
# When ctx.render_plan is None (LLM_EMIT_RENDER_PLAN OFF, no AI
# emission), the resolver falls through to the caller's fallback —
# Sacred Contract #2 (default behaviour identical baseline). When
# ctx.render_plan is set, per-field merge applies: empty fields stay
# at fallback ("empty == inherit" per render_plan.py CameraStrategy);
# set fields override. Invalid reframe_mode values soft-fall back per
# Sacred Contract #3.
#
# Scope of Sprint 4.F: reframe_mode only. Extended in P3:
#   - motion_aware_crop: wired in P3 — render_plan.camera_strategy.motion_aware_crop
#     (Optional[bool]) overrides ctx.payload.motion_aware_crop when not None.
# Sprint 1 extensions:
#   - tracker_hint: wired — "trackerless" forces detection-only in path.py.
#     Other values ("bytetrack", "legacy") reserved; treated as auto for now.
#   - zoom_burst: resolved from ClipPlan.hook_score. Visual effect deferred to
#     Sprint 2 (requires crop.py FFmpeg filter change). Field captured in
#     PartExecutionPlan + CameraStrategy for observability now.
# ────────────────────────────────────────────────────────────────────

# Vocabulary of reframe_mode values the planner will accept from a
# RenderPlan. Matches the CameraStrategy dataclass docstring at
# render_plan.py. Legacy fallback value "subject" stays valid via
# the caller's fallback path — it is not in this set because that
# token belongs to the payload schema, not the plan schema.
_RENDER_PLAN_ALLOWED_REFRAME_MODES: frozenset[str] = frozenset({
    "center", "track", "fixed",
})

# Vocabulary the plan may set for tracker selection. "trackerless" disables
# the OpenCV tracker entirely (detection-only mode). "bytetrack"/"legacy"
# are reserved for future dispatch; currently treated as auto ("").
_RENDER_PLAN_ALLOWED_TRACKER_HINTS: frozenset[str] = frozenset({
    "bytetrack", "trackerless", "legacy",
})


def _resolve_reframe_mode_from_plan(
    ctx: PartRenderContext, fallback_value: str
) -> tuple[str, str]:
    """Return ``(effective_reframe_mode, source_tag)``.

    Source tag is one of ``"render_plan"``, ``"fallback"``, or
    ``"fallback_invalid_reframe"`` — the planner surfaces it in the
    Sprint 4.F ``camera_strategy_applied`` event so operators can
    attribute the choice without re-reading the dataclass.
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return fallback_value, "fallback"
    plan_reframe = (rp.camera_strategy.reframe_mode or "").strip()
    if not plan_reframe:
        return fallback_value, "fallback"
    if plan_reframe not in _RENDER_PLAN_ALLOWED_REFRAME_MODES:
        return fallback_value, "fallback_invalid_reframe"
    return plan_reframe, "render_plan"


def _resolve_tracker_from_plan(
    ctx: PartRenderContext, fallback_value: str
) -> tuple[str, str]:
    """Return ``(effective_tracker_hint, source_tag)``.

    Returns render_plan.camera_strategy.tracker when set and valid,
    otherwise the caller's fallback. Source tag is ``"render_plan"``,
    ``"fallback"``, or ``"fallback_invalid_tracker"``.
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return fallback_value, "fallback"
    plan_tracker = (rp.camera_strategy.tracker or "").strip()
    if not plan_tracker:
        return fallback_value, "fallback"
    if plan_tracker not in _RENDER_PLAN_ALLOWED_TRACKER_HINTS:
        return fallback_value, "fallback_invalid_tracker"
    return plan_tracker, "render_plan"


def _resolve_zoom_burst_from_seg(
    seg: dict,
    ctx: PartRenderContext = None,
    part_no: int = 0,
    threshold: float = 0.75,
) -> bool:
    """Return True when the clip warrants an intro zoom-burst visual effect.

    Sprint 2.2 — priority chain:
      1. ClipPlan.hook_intensity (0.0–1.0, explicit AI signal) when > 0.
         Threshold applied directly. "0.0" means AI left it unset → fall through.
      2. hook_score from seg dict (0–100 scale). Threshold * 100 applied.
    """
    if ctx is not None and part_no > 0:
        rp = getattr(ctx, "render_plan", None)
        if rp is not None and rp.clips and (part_no - 1) < len(rp.clips):
            hi = float(getattr(rp.clips[part_no - 1], "hook_intensity", 0.0) or 0.0)
            if hi > 0.0:
                return hi >= threshold
    hook_score = float(seg.get("hook_score", 0.0) or 0.0)
    return hook_score >= (threshold * 100.0)


def _resolve_motion_aware_crop_from_plan(
    ctx: PartRenderContext, fallback_value: bool
) -> tuple[bool, str]:
    """Return ``(effective_motion_aware_crop, source_tag)``.

    Source tag is ``"render_plan"`` when the plan explicitly set the
    field, ``"fallback"`` otherwise. Follows the same pattern as
    _resolve_reframe_mode_from_plan (Sprint 4.F).
    """
    rp = getattr(ctx, "render_plan", None)
    if rp is None:
        return fallback_value, "fallback"
    plan_crop = rp.camera_strategy.motion_aware_crop
    if plan_crop is None:
        return fallback_value, "fallback"
    return bool(plan_crop), "render_plan"


def _score_crf_micro_delta(seg: dict) -> int:
    """Return a ±1 CRF micro-adjustment from viral_score + retention_score.

    Both ≥ 85 → -1 (raise quality for strong clips).
    Both < 35 → +1 (save bitrate on weak clips).
    Otherwise → 0 (no adjustment).
    """
    try:
        viral = float(seg.get("viral_score", 0.0) or 0.0)
        retention = float(seg.get("retention_score", 0.0) or 0.0)
        if viral >= 85.0 and retention >= 85.0:
            return -1
        if viral < 35.0 and retention < 35.0:
            return 1
    except Exception:
        pass
    return 0


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
    _effective_motion_crop, _motion_crop_source = _resolve_motion_aware_crop_from_plan(
        ctx, bool(ctx.payload.motion_aware_crop)
    )
    _effective_tracker, _tracker_source = _resolve_tracker_from_plan(ctx, "")
    _zoom_burst = _resolve_zoom_burst_from_seg(seg, ctx=ctx, part_no=idx)
    _vf_ct = seg.get("content_type_hint", "vlog")
    _vf_crf_delta = _crf_delta_for_content_type(_vf_ct)
    _vf_crf_delta += _score_crf_micro_delta(seg)
    _part_video_crf = max(11, min(28, ctx.tuned["video_crf"] + _vf_crf_delta))
    _vf_bitrate_profile = (
        "high" if _vf_ct == "montage" else
        "low" if _vf_ct in ("interview", "tutorial") else "standard"
    )
    _vf_subtitle_bump = not _effective_motion_crop and _vf_ct in ("interview", "commentary")
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
    # Sprint 4.F — resolve effective reframe_mode ONCE so the cache
    # key (below), PartExecutionPlan, and CameraStrategy ctor all see
    # the same value. Falls back to ctx.payload value when
    # ctx.render_plan is None or its camera_strategy.reframe_mode is
    # empty/invalid.
    _legacy_reframe = str(getattr(ctx.payload, "reframe_mode", "subject"))
    _effective_reframe, _reframe_source = _resolve_reframe_mode_from_plan(
        ctx, _legacy_reframe
    )
    _motion_ck = None
    _motion_crop_fallback: list = []
    if _effective_motion_crop and ctx.src_stat_for_motion is not None:
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
                _effective_reframe,
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
        motion_aware_crop=_effective_motion_crop,
        reframe_mode=_effective_reframe,
        frame_scale_x=int(ctx.payload.frame_scale_x),
        frame_scale_y=int(ctx.payload.frame_scale_y),
        content_type=_vf_ct,
        video_crf=_part_video_crf,
        bitrate_profile=_vf_bitrate_profile,
        voice_enabled=bool(getattr(ctx.payload, "voice_enabled", False)),
        voice_source=str(getattr(ctx.payload, "voice_source", "none")),
        playback_speed=float(
            max(0.5, min(1.5, float(ctx.payload.playback_speed or 1.0)
                   + _PLATFORM_PROFILES.get(ctx.target_platform, {}).get("speed_delta", 0.0)))
        ),
        zoom_burst=_zoom_burst,
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
        motion_aware_crop=_effective_motion_crop,
        reframe_mode=_effective_reframe,
        content_type=_vf_ct,
        tracker_hint=_effective_tracker,
        zoom_burst=_zoom_burst,
    )
    logger.info(
        "camera_strategy part=%d mode=%s crop=%s reframe=%s aspect=%s scale=%dx%d",
        idx, _camera_strategy.camera_mode, _camera_strategy.motion_aware_crop,
        _camera_strategy.reframe_mode, _camera_strategy.aspect_ratio,
        _camera_strategy.frame_scale_x, _camera_strategy.frame_scale_y,
    )
    # Sprint 4.F — additive event mirroring the Sprint 4.E
    # `subtitle_style_applied` pattern. Lets operators attribute the
    # reframe choice ("render_plan" override vs legacy "fallback")
    # without grepping the logger output. The previous module-docstring
    # assertion at L50-51 ("this block has NO _emit_render_event
    # calls") was Sprint 6.D-era — Sprint 4.F adds one event per part.
    _emit_render_event(
        channel_code=ctx.effective_channel,
        job_id=ctx.job_id,
        event="camera_strategy_applied",
        level="INFO",
        message=f"Camera strategy applied for part {idx}: reframe={_effective_reframe}",
        step="render.preflight",
        context={
            "part_no": idx,
            "reframe_mode": _effective_reframe,
            "reframe_mode_source": _reframe_source,
            "motion_aware_crop": _camera_strategy.motion_aware_crop,
            "motion_crop_source": _motion_crop_source,
            "camera_mode": _camera_strategy.camera_mode,
            "aspect_ratio": _camera_strategy.aspect_ratio,
            "tracker_hint": _effective_tracker,
            "tracker_hint_source": _tracker_source,
            "zoom_burst": _zoom_burst,
        },
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

