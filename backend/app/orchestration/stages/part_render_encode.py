"""Per-part FFmpeg encode core — Layer 8 of the render pipeline.

Sprint 6.D-2.5a — extracted verbatim from stages/part_renderer.py
(lines 254-469 of the post-2.4 file). No logic changes; pure relocation.

run_render_encode() runs once per part during process_one_part,
immediately after run_render_preflight (Sprint 6.D-2.4) and before
the voice/audio-mix phase (Sprint 6.D-2.5b target).

Block responsibilities (in order):
  1. Optional base-clip rendering via render_base_clip() when
     FEATURE_BASE_CLIP_FIRST=1 AND a consumer is active (either
     FEATURE_OVERLAY_AFTER_BASE_CLIP=1 OR
     FEATURE_BASE_CLIP_VALIDATION_ARTIFACT=1 — Sprint 6 P0 HIGH).
     Writes base_clip manifest fields (base_clip_path, duration, fps,
     width, height, has_audio, created_at, bgm_applied). Failure is
     caught locally — falls through to render_part_smart.
  2. Optional overlay composite via composite_overlays_on_base_clip()
     when FEATURE_BASE_CLIP_FIRST=1 AND FEATURE_OVERLAY_AFTER_BASE_CLIP=1
     AND base_clip_path was produced. Slices output-timeline SRT and
     generates a per-output-timeline ASS file before compositing.
     Failure is caught locally — falls through to render_part_smart.
  3. render_part_smart() fallback (the default render path) — runs
     when overlay composite did not succeed.
  4. `finally:` block — signals the encode-progress monitor thread
     (preflight.encode_stop.set()) and joins it (timeout=5.0). This
     pairs with the .start() in run_render_preflight (Sprint 2.4).
  5. _render_ms metric + render_part_ms log + manifest rendered_path
     write + rerender_fast_path log (when motion cache hit).
  6. Motion-crop recovery emit when preflight.motion_crop_fallback
     became non-empty (mutated by-ref by render_part_smart's
     `_fallback_flag=` kwarg).
  7. visual_finish_applied emit with full encoding params context.

Returns:
  RenderEncodeResult(render_ms: int) — used downstream by 2.5c
  (total_part_render_ms log + RenderOutputResult construction).

Other outputs (mutated in place, not returned):
  - preflight.motion_crop_fallback: list — mutated by render_part_smart
    and composite_overlays_on_base_clip via `_fallback_flag=` kwarg.
    Same list reference the caller already holds.
  - part_manifest: BaseClipManifest — mutated for base_clip_*, overlay_*,
    rendered_path, overlay_text_layers_applied fields. Same reference
    the caller already holds.
  - final_part on disk — the FFmpeg encode writes the final mp4.
  - preflight.encode_stop / encode_timer — signaled and joined inside
    this helper's finally block. After return, the thread is dead.

Sacred Contracts honored:
  - #5 Frozen part-stage names: none touched. The RENDERING transition
       upserted by the caller BEFORE calling this helper; the DONE
       transition will be upserted by 2.5d AFTER 2.5c validation.
  - #6 _emit_render_event signature: 2 call sites preserved verbatim
       (recovery_success, visual_finish_applied).
  - #7 Sole DB writer: 0 upsert_job_part calls in this block.
  - #8 qa_pipeline not bypassed: no validation here. Validation happens
       in 2.5c (run_part_finalize) which is downstream.

NVENC semaphore (Sprint 4.2 contract): acquired INSIDE the
render_engine helpers (render_base_clip / render_part_smart /
composite_overlays_on_base_clip — each one acquires
NVENC_SEMAPHORE before invoking ffmpeg with NVENC encoder).
This block does NOT acquire the semaphore directly. No change
to the semaphore surface from this extraction.

Logger note (same pattern as 6.D-2.1 / 2.2 / 2.3 / 2.4):
  `logger = logging.getLogger("app.render")` preserved verbatim so
  existing log routing resolves identically.

Feature-flag env-var triple-read note:
  _FEATURE_BASE_CLIP_FIRST + _FEATURE_OVERLAY_AFTER_BASE_CLIP are now
  read at module-load time in THREE modules: part_renderer.py,
  part_render_setup.py (Sprint 2.4), and this module. All three reads
  happen at import time on the same deterministic env vars — behavior
  is identical. No drift possible.
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path

from app.domain.manifests import BaseClipManifest
from app.domain.timeline import TimelineMap
from app.orchestration.pipeline_segment_selection import _PLATFORM_PROFILES
from app.orchestration.pipeline_subtitle_utils import _aspect_play_res_y
from app.orchestration.render_events import _emit_render_event, _job_log
from app.orchestration.stages.part_render_context import PartRenderContext
from app.orchestration.stages.part_render_setup import RenderPreflightResult
from app.services.manifest_writer import write_manifest
from app.services.render_engine import (
    composite_overlays_on_base_clip,
    render_base_clip,
    render_part_smart,
)
# Sprint 7.4 — direct import (not via render_engine shim) since this is
# a new helper that does not need the historical re-export.
from app.services.render.base_clip_renderer import render_part_from_source
from app.services.subtitle_engine import (
    slice_srt_to_output_timeline,
    srt_to_ass_bounce,
)

# Preserve original logger name (same pattern as 6.D-2.1 / 2.2 / 2.3 / 2.4).
logger = logging.getLogger("app.render")

# Feature-flag env reads (third read in the chain — identical to
# part_renderer.py and part_render_setup.py reads; no drift possible).
_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"
# Sprint 7.2 (2026-06-05): FEATURE_BASE_CLIP_VALIDATION_ARTIFACT removed —
# see render_pipeline.py for the closure rationale.
# Sprint 7.4 (2026-06-05): raw_part skip flag — see render_pipeline.py.
_FEATURE_RAW_PART_SKIP: bool = os.getenv("FEATURE_RAW_PART_SKIP", "0") == "1"
# Sprint 7.8 (2026-06-05): motion-aware extension flag — see render_pipeline.py.
_FEATURE_RAW_PART_SKIP_MOTION_AWARE: bool = os.getenv("FEATURE_RAW_PART_SKIP_MOTION_AWARE", "0") == "1"


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

    # Sprint 6 P0 HIGH gate (post Sprint 7.2 simplification): the
    # base_clip render only fires when its single downstream consumer is
    # active — the overlay composite block below. Sprint 7.2 removed the
    # FEATURE_BASE_CLIP_VALIDATION_ARTIFACT opt-in (zero usage observed
    # during 30-day settling). The gate is now a plain AND.
    # When FEATURE_BASE_CLIP_FIRST is OFF the whole block is skipped as
    # before — Sacred Contract #2 default-behaviour preservation.
    if _FEATURE_BASE_CLIP_FIRST and _FEATURE_OVERLAY_AFTER_BASE_CLIP:
        _base_clip_out = ctx.work_dir / f"part_{idx}" / "base_clip.mp4"
        try:
            _base_clip_out.parent.mkdir(parents=True, exist_ok=True)
            _bc_bgm_path = str(getattr(ctx.payload, "reup_bgm_path", None) or "").strip()
            _bc_bgm_ok = (
                getattr(ctx.payload, "reup_bgm_enable", False)
                and _bc_bgm_path
                and Path(_bc_bgm_path).is_file()
            )
            _bc_meta = render_base_clip(
                input_path=str(raw_part),
                output_path=str(_base_clip_out),
                timeline=part_timeline,
                aspect_ratio=ctx.payload.aspect_ratio,
                scale_x=ctx.payload.frame_scale_x,
                scale_y=ctx.payload.frame_scale_y,
                motion_aware_crop=ctx.payload.motion_aware_crop,
                reframe_mode=getattr(ctx.payload, "reframe_mode", "subject"),
                effect_preset=ctx.payload.effect_preset,
                transition_sec=ctx.tuned["transition_sec"],
                video_codec=ctx.payload.video_codec,
                video_crf=_part_video_crf,
                video_preset=ctx.tuned["video_preset"],
                audio_bitrate=ctx.payload.audio_bitrate,
                retry_count=ctx.retry_count,
                encoder_mode=ctx.payload.encoder_mode,
                output_fps=ctx.payload.output_fps,
                loudnorm_enabled=getattr(ctx.payload, "loudnorm_enabled", False),
                ffmpeg_threads=ctx.ffmpeg_threads,
                content_type=seg.get("content_type_hint", "vlog"),
                _motion_cache_key=_motion_ck,
                reup_bgm_enable=getattr(ctx.payload, "reup_bgm_enable", False),
                reup_bgm_path=getattr(ctx.payload, "reup_bgm_path", None),
                reup_bgm_gain=getattr(ctx.payload, "reup_bgm_gain", 0.18),
                visual_intensity_hint=ctx.vis_intensity_hint,
            )
            part_manifest.base_clip_path = str(_base_clip_out)
            part_manifest.base_clip_duration = _bc_meta.get("duration")
            part_manifest.base_clip_fps = _bc_meta.get("fps")
            part_manifest.base_clip_width = _bc_meta.get("width")
            part_manifest.base_clip_height = _bc_meta.get("height")
            part_manifest.base_clip_has_audio = _bc_meta.get("has_audio")
            part_manifest.base_clip_created_at = _bc_meta.get("created_at")
            part_manifest.base_clip_bgm_applied = bool(_bc_bgm_ok)
            write_manifest(ctx.work_dir, part_manifest)
            logger.info(
                "base_clip_rendered part=%d path=%s duration=%.3fs",
                idx, _base_clip_out, _bc_meta.get("duration", 0.0),
            )
        except Exception as _bc_err:
            logger.warning(
                "base_clip_render_failed part=%d err=%s — render_part_smart continues",
                idx, _bc_err,
            )

    _overlay_composite_succeeded = False
    if (
        _FEATURE_BASE_CLIP_FIRST
        and _FEATURE_OVERLAY_AFTER_BASE_CLIP
        and part_manifest.base_clip_path is not None
    ):
        _overlay_dir = Path(part_manifest.base_clip_path).parent
        _overlay_srt = _overlay_dir / "subtitle_output_timeline.srt"
        _overlay_ass = _overlay_dir / "subtitle_output_timeline.ass"
        try:
            _overlay_ass_path: "str | None" = None
            if part_subtitle_enabled and ctx.full_srt_available and ctx.full_srt.exists():
                _ot_meta = slice_srt_to_output_timeline(
                    source_srt_path=str(ctx.full_srt),
                    output_srt_path=str(_overlay_srt),
                    source_start=part_timeline.source_start,
                    source_end=part_timeline.source_end,
                    timeline=part_timeline,
                )
                if _ot_meta.get("subtitle_count", 0) > 0:
                    _overlay_play_res_y = _aspect_play_res_y(ctx.payload.aspect_ratio)
                    _overlay_margin_v = getattr(ctx.payload, "sub_margin_v", 180)
                    if (
                        not ctx.payload.motion_aware_crop
                        and seg.get("content_type_hint") in ("interview", "commentary")
                    ):
                        _overlay_margin_v += 40
                    srt_to_ass_bounce(
                        str(_overlay_srt),
                        str(_overlay_ass),
                        subtitle_style=effective_subtitle_style,
                        scale_y=ctx.payload.frame_scale_y,
                        font_name=getattr(ctx.payload, "sub_font", "Bungee"),
                        font_size=getattr(ctx.payload, "sub_font_size", 0),
                        margin_v=_overlay_margin_v,
                        play_res_y=_overlay_play_res_y,
                        play_res_x=1080,
                        x_percent=getattr(ctx.payload, "sub_x_percent", 50.0),
                        highlight_per_word=getattr(ctx.payload, "highlight_per_word", True),
                    )
                    _overlay_ass_path = str(_overlay_ass)
                    part_manifest.overlay_srt_path = str(_overlay_srt)
                    part_manifest.overlay_ass_path = str(_overlay_ass)

            _oc_meta = composite_overlays_on_base_clip(
                base_clip_path=part_manifest.base_clip_path,
                output_path=str(final_part),
                timeline=part_timeline,
                subtitle_ass=_overlay_ass_path,
                text_layers=part_text_layers_overlay if part_text_layers_overlay else None,
                title_text=overlay_title if ctx.payload.add_title_overlay else None,
                video_codec=ctx.payload.video_codec,
                video_crf=_part_video_crf,
                video_preset=ctx.tuned["video_preset"],
                audio_bitrate=ctx.payload.audio_bitrate,
                retry_count=ctx.retry_count,
                encoder_mode=ctx.payload.encoder_mode,
                ffmpeg_threads=ctx.ffmpeg_threads,
            )
            part_manifest.overlay_rendered_path = str(final_part)
            part_manifest.rendered_path = str(final_part)
            part_manifest.overlay_text_layers_applied = len(part_text_layers_overlay or [])
            write_manifest(ctx.work_dir, part_manifest)
            logger.info(
                "overlay_composite_succeeded part=%d path=%s subtitle=%s",
                idx, final_part, _overlay_ass_path is not None,
            )
            _overlay_composite_succeeded = True
        except Exception as _oc_err:
            logger.warning(
                "overlay_composite_failed job_id=%s part=%d base_clip=%s err=%s "
                "— falling back to render_part_smart",
                ctx.job_id, idx, part_manifest.base_clip_path, _oc_err,
            )

    # Sprint 7.4 — fused-cut+render path detection. When run_cut_stage
    # skipped cut_video (predicate fired + FEATURE_RAW_PART_SKIP=1 +
    # motion_aware_crop=False), raw_part stays absent on disk. Route to
    # render_part_from_source instead of render_part_smart so the input-
    # side -ss/-t seek runs in the same FFmpeg invocation as the encode.
    _raw_part_absent = not raw_part.exists()
    _resolved_playback_speed = float(
        seg.get("variant_playback_speed")
        or max(0.5, min(1.5, float(ctx.payload.playback_speed or 1.07)
               + _PLATFORM_PROFILES.get(ctx.target_platform, {}).get("speed_delta", 0.0)))
    )
    try:
        if not _overlay_composite_succeeded:
            if _raw_part_absent:
                # Sprint 7.4 — fused cut+render: read source with input-side
                # -ss/-t instead of from a pre-cut raw_part.mp4.
                # Sprint 7.8 — extended to motion-aware case. Motion-aware
                # branch is selected by motion_aware_crop kwarg INSIDE
                # render_part_from_source. Windowed motion cache key
                # prevents stale hits across different windows of the
                # same source.
                _source_duration = float(part_timeline.source_end - part_timeline.source_start)
                _windowed_motion_ck = (
                    f"{_motion_ck}-w{part_timeline.source_start:.3f}-{_source_duration:.3f}"
                    if (_motion_ck and ctx.payload.motion_aware_crop)
                    else _motion_ck
                )
                logger.info(
                    "render_part_from_source_invoked part=%d source_start=%.3f duration=%.3f motion_aware=%s",
                    idx, part_timeline.source_start, _source_duration,
                    ctx.payload.motion_aware_crop,
                )
                render_part_from_source(
                    str(ctx.source_path),
                    str(final_part),
                    part_timeline.source_start,
                    _source_duration,
                    str(ass_part) if part_subtitle_enabled else None,
                    overlay_title if ctx.payload.add_title_overlay else "",
                    aspect_ratio=ctx.payload.aspect_ratio,
                    scale_x=ctx.payload.frame_scale_x,
                    scale_y=ctx.payload.frame_scale_y,
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
                    visual_intensity_hint=ctx.vis_intensity_hint,
                    motion_aware_crop=ctx.payload.motion_aware_crop,
                    reframe_mode=getattr(ctx.payload, "reframe_mode", "subject"),
                    _motion_cache_key=_windowed_motion_ck,
                    _fallback_flag=_motion_crop_fallback,
                )
            else:
                render_part_smart(
                    str(raw_part), str(final_part), str(ass_part) if part_subtitle_enabled else None, overlay_title if ctx.payload.add_title_overlay else "",
                    ctx.payload.aspect_ratio, ctx.payload.frame_scale_x, ctx.payload.frame_scale_y,
                    ctx.payload.motion_aware_crop,
                    reframe_mode=ctx.payload.reframe_mode,
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
                    _motion_cache_key=_motion_ck,
                    _fallback_flag=_motion_crop_fallback,
                    visual_intensity_hint=ctx.vis_intensity_hint,
                )
    finally:
        preflight.encode_stop.set()
        preflight.encode_timer.join(timeout=5.0)
    _render_ms = int((time.perf_counter() - preflight.t_render) * 1000)
    logger.info("render_part_ms=%d part=%d codec=%s crop=%s",
                _render_ms, idx, ctx.payload.video_codec, ctx.payload.motion_aware_crop)
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
