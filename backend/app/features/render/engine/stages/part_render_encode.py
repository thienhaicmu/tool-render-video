"""Per-part FFmpeg encode core — Layer 8 of the render pipeline.

Sprint 6.D-2.5a — extracted verbatim from stages/part_renderer.py.

Block responsibilities (in order):
  1. render_part_smart() — the sole render path.
  2. `finally:` block — signals the encode-progress monitor thread.
  3. _render_ms metric + manifest rendered_path write.
  4. Motion-crop recovery emit when _fallback_flag is non-empty.
  5. visual_finish_applied emit with encoding params context.

Returns:
  RenderEncodeResult(render_ms: int)
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from app.domain.manifests import BaseClipManifest
from app.domain.timeline import TimelineMap
from app.features.render.engine.pipeline.pipeline_segment_selection import _PLATFORM_PROFILES
from app.features.render.engine.pipeline.render_events import _emit_render_event, _job_log
from app.features.render.engine.stages.part_render_context import PartRenderContext
from app.features.render.engine.stages.part_render_setup import RenderPreflightResult
from app.features.render.engine.stages.manifest_writer import write_manifest
from app.features.render.engine.encoder.clip_renderer import render_part_smart
from app.features.render.engine.motion import MotionCropConfig

# Preserve original logger name (same pattern as 6.D-2.1 / 2.2 / 2.3 / 2.4).
logger = logging.getLogger("app.render")



@dataclass
class RenderEncodeResult:
    """Output bundle from run_render_encode.

    Currently single-field; dataclass form chosen for consistency with
    CutStageResult (2.3) and RenderPreflightResult (2.4) plus future
    extensibility (overlay_composite_succeeded or similar may move
    here if downstream code grows a use for it).
    """
    render_ms: int


def run_render_encode(
    ctx: PartRenderContext,
    idx: int,
    seg: dict,
    raw_part: Path,
    ass_part: Path,
    final_part: Path,
    part_subtitle_enabled: bool,
    overlay_title: str,
    part_manifest: BaseClipManifest,
    part_timeline: TimelineMap,
    part_text_layers: list,
    part_text_layers_overlay: list,
    effective_subtitle_style: str,
    preflight: RenderPreflightResult,
) -> RenderEncodeResult:
    """Execute the FFmpeg encode block. See module docstring for the
    7-step responsibility breakdown.

    The encode-progress monitor thread STARTED by run_render_preflight
    (preflight.encode_timer) is signaled and joined inside this
    function's `finally:` block.
    """
    # Local alias the preflight fields used multiple times — keeps
    # the relocated code byte-for-byte identical to the pre-2.5a
    # variable names (which used the underscore-prefixed locals).
    _part_video_crf = preflight.part_video_crf
    _motion_ck = preflight.motion_ck
    _motion_crop_fallback = preflight.motion_crop_fallback

    _resolved_playback_speed = float(
        seg.get("variant_playback_speed")
        or max(0.5, min(1.5, float(ctx.payload.playback_speed or 1.0)
               + _PLATFORM_PROFILES.get(ctx.target_platform, {}).get("speed_delta", 0.0)))
    )
    # Sprint 1: Use resolved camera strategy values from RenderPlan (preflight)
    # instead of raw ctx.payload.*. Closes the pre-existing gap where the resolver
    # results in part_render_setup were computed but never reached render_part_smart.
    _effective_motion_crop = preflight.camera_strategy.motion_aware_crop
    _effective_reframe = preflight.camera_strategy.reframe_mode
    # Build crop_cfg_override when tracker_hint is set so path.py can honour it.
    _crop_cfg_override: MotionCropConfig | None = None
    if _effective_motion_crop and preflight.camera_strategy.tracker_hint:
        _crop_cfg_override = MotionCropConfig(
            scale_x_percent=float(ctx.payload.frame_scale_x),
            scale_y_percent=float(ctx.payload.frame_scale_y),
            reframe_mode=_effective_reframe,
            tracker_hint=preflight.camera_strategy.tracker_hint,
        )
    try:
        render_part_smart(
            str(raw_part), str(final_part), str(ass_part) if part_subtitle_enabled else None, overlay_title if ctx.payload.add_title_overlay else "",
            ctx.payload.aspect_ratio, ctx.payload.frame_scale_x, ctx.payload.frame_scale_y,
            _effective_motion_crop,
            reframe_mode=_effective_reframe,
            add_subtitle=part_subtitle_enabled,
            add_title_overlay=ctx.payload.add_title_overlay,
            effect_preset=ctx.payload.effect_preset,
            transition_sec=ctx.tuned["transition_sec"],
            video_codec=ctx.payload.video_codec,
            video_crf=_part_video_crf,
            video_preset=ctx.tuned["video_preset"],
            audio_bitrate=ctx.payload.audio_bitrate,
            retry_count=ctx.retry_count,
            encoder_mode=ctx.payload.encoder_mode,
            output_fps=ctx.payload.output_fps,
            reup_mode=ctx.payload.reup_mode,
            reup_overlay_enable=ctx.payload.reup_overlay_enable,
            reup_overlay_opacity=ctx.payload.reup_overlay_opacity,
            reup_bgm_enable=ctx.payload.reup_bgm_enable,
            reup_bgm_path=ctx.payload.reup_bgm_path,
            reup_bgm_gain=ctx.payload.reup_bgm_gain,
            playback_speed=_resolved_playback_speed,
            text_layers=part_text_layers,
            loudnorm_enabled=getattr(ctx.payload, "loudnorm_enabled", False),
            ffmpeg_threads=ctx.ffmpeg_threads,
            content_type=seg.get("content_type_hint", "vlog"),
            crop_cfg_override=_crop_cfg_override,
            _motion_cache_key=_motion_ck,
            _fallback_flag=_motion_crop_fallback,
            visual_intensity_hint="high" if preflight.camera_strategy.zoom_burst else None,
            zoom_burst=preflight.camera_strategy.zoom_burst,
        )
    finally:
        preflight.encode_stop.set()
        preflight.encode_timer.join(timeout=5.0)
    _render_ms = int((time.perf_counter() - preflight.t_render) * 1000)
    logger.info("render_part_ms=%d part=%d codec=%s crop=%s tracker=%s zoom_burst=%s",
                _render_ms, idx, ctx.payload.video_codec, _effective_motion_crop,
                preflight.camera_strategy.tracker_hint or "auto",
                preflight.camera_strategy.zoom_burst)
    part_manifest.rendered_path = str(final_part)
    write_manifest(ctx.work_dir, part_manifest)
    if _motion_ck:
        _job_log(ctx.effective_channel, ctx.job_id, f"rerender_fast_path part={idx} motion_cache_key={_motion_ck[:8]} render_ms={_render_ms}")
    if _motion_crop_fallback:
        ctx.recovery_notes.append("Motion crop unavailable — used standard crop")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="recovery_success",
            level="WARNING",
            message=f"Recovery: motion crop failed for part {idx}, standard crop used",
            step="render.motion_crop",
            context={
                "recovery_strategy": "fallback_standard_crop",
                "part_no": idx,
                "reason": _motion_crop_fallback[0],
            },
        )
    _emit_render_event(
        channel_code=ctx.effective_channel,
        job_id=ctx.job_id,
        event="visual_finish_applied",
        level="INFO",
        message=f"Visual finish: part {idx} content_type={preflight.vf_ct} crf={_part_video_crf}({preflight.vf_crf_delta:+d}) bitrate={preflight.vf_bitrate_profile}",
        step="render.visual_finish",
        context={
            "part_no": idx,
            "content_type": preflight.vf_ct,
            "visual_finish_score": min(100, max(0, 50 + (_part_video_crf - ctx.tuned["video_crf"]) * -5)),
            "clarity_level": "enhanced" if preflight.vf_ct in ("tutorial", "interview") else (
                "reduced" if preflight.vf_ct == "montage" else "standard"
            ),
            "compression_risk": "low" if preflight.vf_ct in ("interview", "tutorial") else (
                "high" if preflight.vf_ct == "montage" else "medium"
            ),
            "subtitle_visibility": "adjusted" if preflight.vf_subtitle_bump else "standard",
            "crf_applied": _part_video_crf,
            "crf_delta": preflight.vf_crf_delta,
            "bitrate_profile": preflight.vf_bitrate_profile,
        },
    )

    return RenderEncodeResult(render_ms=_render_ms)

