"""
Per-part render logic extracted from run_render_pipeline() inner closures (Phase A-3).
PartRenderContext carries all closure-captured state.
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.config import TEMP_DIR
from app.core.stage import JobPartStage
from app.domain.manifests import BaseClipManifest
from app.domain.timeline import TimelineMap
from app.orchestration.asset_pipeline import (
    _maybe_append_asset_outro,
    _maybe_apply_asset_logo,
    _maybe_prepend_asset_intro,
    _maybe_prepend_remotion_hook_intro,
)
from app.orchestration.audio_pipeline import _maybe_cleanup_narration_audio
from app.orchestration.camera_strategy import CameraStrategy
from app.orchestration.part_assets import PartAssets
from app.orchestration.part_plan import PartExecutionPlan
from app.orchestration.pipeline_cache import _render_cache_key
from app.orchestration.pipeline_config import extract_text_from_srt
from app.orchestration.pipeline_subtitle_utils import (
    _append_cta_block_to_srt,
    _apply_subtitle_edits_to_srt,
    _aspect_play_res_y,
    _read_srt_meta,
)
from app.orchestration.pipeline_segment_selection import (
    _PLATFORM_PROFILES,
    _get_effective_playback_speed,
    _select_cover_frame_time,
    _select_cta_text,
)
from app.orchestration.pipeline_ranking import resolve_combined_score_weights
from app.orchestration.qa_pipeline import (
    _assess_output_quality,
    _assess_render_quality_intelligence,
    _resume_output_valid,
    _validate_render_output,
)
from app.orchestration.render_events import (
    _emit_render_event,
    _job_log,
    _render_progress_timer,
    _safe_unlink,
)
from app.orchestration.render_output import RenderOutputResult
from app.services.audio_mix_service import mix_narration_audio
from app.services.db import upsert_job_part
from app.services.manifest_writer import manifest_path as _manifest_path
from app.services.manifest_writer import write_manifest
from app.services.render_engine import (
    apply_micro_pacing,
    composite_overlays_on_base_clip,
    content_type_crf_delta as _crf_delta_for_content_type,
    cut_video,
    detect_bad_first_frame,
    detect_silence_trim_offset,
    extract_thumbnail_frame,
    render_base_clip,
    render_part_smart,
    set_thread_cancel_event,
)
from app.services.subtitle_engine import (
    apply_hook_subtitle_format,
    apply_market_hook_text_to_srt,
    apply_market_line_break_to_srt,
    parse_srt_blocks,
    resegment_srt_for_readability,
    resolve_hook_overlay_text,
    slice_srt_to_output_timeline,
    slice_srt_to_text,
    srt_to_ass_bounce,
    srt_to_ass_karaoke,
    subtitle_emphasis_pass,
    write_srt_blocks,
)
from app.services.subtitle_transcription_adapters import transcribe_with_adapter
from app.services.text_overlay import MAX_TEXT_LAYERS
from app.services.translation_service import translate_srt_file
from app.services.tts_service import generate_narration_audio

logger = logging.getLogger("app.render")

_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"


# Sprint 6.D-2.1: PartRenderContext dataclass extracted to a dedicated
# module. Re-exported here so existing external consumers
# (pipeline_render_loop.py, render_pipeline.py) keep their existing
# import paths working unchanged.
from app.orchestration.stages.part_render_context import PartRenderContext
# Sprint 6.D-2.2: prepare_part_assets extracted to a dedicated module.
# Re-exported here so the internal caller (process_one_part below)
# keeps using `prepare_part_assets(...)` via the bare reference.
from app.orchestration.stages.part_asset_planner import prepare_part_assets
# Sprint 6.D-2.3: CUT stage (post-WAITING / pre-RENDERING block) extracted
# to a dedicated module. Re-exported so the internal caller below keeps
# the bare reference; CutStageResult is consumed only inside process_one_part.
from app.orchestration.stages.part_cut import CutStageResult, run_cut_stage
# Sprint 6.D-2.4: RENDER pre-flight (encoding params + progress-timer
# thread + cache key + PartExecutionPlan + CameraStrategy + feature-flag
# warning) extracted to a dedicated module. The encode-progress thread
# is STARTED inside run_render_preflight and the caller is responsible
# for encode_stop.set() + encode_timer.join() after the FFmpeg render
# completes. Plan §3.2 phase 2.4 was re-scoped here because the original
# TRANSCRIBE scope was already absorbed into prepare_part_assets (2.2).
from app.orchestration.stages.part_render_setup import (
    RenderPreflightResult,
    run_render_preflight,
)
# Sprint 6.D-2.5a: FFmpeg encode core (base_clip + overlay composite +
# render_part_smart fallback + encode-thread lifecycle close + motion-crop
# recovery emit + visual_finish_applied emit) extracted to a dedicated
# module. The encode_stop.set() + encode_timer.join() pair that closes
# the encode-progress thread (started in run_render_preflight) lives
# inside run_render_encode's finally block.
from app.orchestration.stages.part_render_encode import (
    RenderEncodeResult,
    run_render_encode,
)
# Sprint 6.D-2.5d: Per-part DONE block (quality intelligence + cover
# frame + JobPartStage.DONE terminal upsert + cleanup + return dict)
# extracted to a dedicated module. The terminal stage transition
# (Sacred Contract #5) moves WITH this helper since it is the natural
# return point of process_one_part.
from app.orchestration.stages.part_done import run_part_done
# Sprint 6.D-2.5b: Per-part voice TTS + audio mix block (subtitle and
# translated_subtitle voice paths + mix_narration_audio with atomic
# file swap) extracted to a dedicated module. Side-effect-only —
# mutates ctx.voice_part_tts_attempts / voice_mix_ok lists,
# part_manifest.narration_path, and overwrites final_part with the
# mixed video.
from app.orchestration.stages.part_voice_mix import run_part_voice_mix
# Sprint 6.D-2.5c (CRITICAL): Per-part finalize block (micro-pacing +
# intro/outro/logo + duration math + scoring + Sacred Contract #8
# qa_pipeline validation surface). Raises RuntimeError on validation
# failure — the per-part worker in pipeline_render_loop catches it
# and records the failure in result_json[failed_parts].
from app.orchestration.stages.part_render_finalize import run_part_finalize


def process_one_part(ctx: PartRenderContext, idx: int, seg: dict):
    raw_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}_raw.mp4"
    srt_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}.srt"
    ass_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}.ass"
    _variant_type = str(seg.get("variant_type") or "")
    if _variant_type:
        final_part = ctx.output_dir / f"{ctx.output_stem}_{_variant_type}.mp4"
        part_name  = f"{ctx.output_stem}_{_variant_type}.mp4"
    else:
        _clip_name = str(seg.get("clip_name") or "").strip()
        if _clip_name:
            # Groq-provided natural filename — already FS-safe (sanitized by groq/parser.py).
            # Append part index if a file with the same name already exists (collision guard).
            _cn_path = ctx.output_dir / f"{_clip_name}.mp4"
            if _cn_path.exists():
                _clip_name = f"{_clip_name}_{idx:03d}"
            final_part = ctx.output_dir / f"{_clip_name}.mp4"
            part_name  = f"{_clip_name}.mp4"
        else:
            final_part = ctx.output_dir / f"{ctx.output_stem}_part_{idx:03d}.mp4"
            part_name  = f"{ctx.output_stem}_part_{idx:03d}.mp4"
    _sub_target_lang = getattr(ctx.payload, "subtitle_target_language", "en")
    translated_srt_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}.{_sub_target_lang}.srt"
    _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx}/{ctx.total_parts} start", kind="debug")
    import os as _os2
    if _os2.getenv("RENDER_DEBUG_LOG", "0") == "1":
        try:
            import json as _json2
            _meta_path = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}_meta.json"
            _meta_data = {
                "part": idx,
                "start": float(seg.get("start", 0)),
                "end": float(seg.get("end", 0)),
                "duration": float(seg.get("duration", 0)),
                "viral_score": float(seg.get("viral_score", 0)),
                "motion_score": float(seg.get("motion_score", 0)),
                "hook_score": float(seg.get("hook_score", 0)),
                "content_type": seg.get("content_type_hint", ""),
                "variant": seg.get("variant_type", ""),
                "files": {
                    "raw": str(raw_part),
                    "srt": str(srt_part),
                    "ass": str(ass_part),
                    "output": str(final_part),
                },
            }
            _meta_path.write_text(_json2.dumps(_meta_data, indent=2), encoding="utf-8")
            logger.debug("debug_artifact segment_meta=%s", _meta_path)
        except Exception as _meta_exc:
            logger.debug("debug_artifact segment_meta_failed part=%d: %s", idx, _meta_exc)

    if ctx.cancel_registry.is_cancelled(ctx.job_id):
        raise ctx.cancel_registry.JobCancelledError()
    _cancel_ev = ctx.cancel_registry.get_event(ctx.job_id)
    if _cancel_ev is not None:
        set_thread_cancel_event(_cancel_ev)

    _existing_part_info = ctx.existing_parts.get(idx, {})
    if (
        ctx.payload.resume_from_last
        and ((_existing_part_info.get("status") or "").lower() == "done")
        and final_part.exists()
        and final_part.stat().st_size > 0
        and _resume_output_valid(final_part)
    ):
        upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Skipped (already rendered)")
        _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} skipped: final output already exists", kind="debug")
        return {"idx": idx, "output": str(final_part), "row": None, "skipped": True}

    upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.WAITING, 5, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), "", "Waiting for worker")

    _t_part_start = time.perf_counter()
    _subtitle_ass_ms = 0
    _render_ms = _micro_pacing_ms = _quality_validation_ms = 0

    # Sprint 6.D-2.3: CUT stage (post-WAITING / pre-RENDERING) moved to
    # app.orchestration.stages.part_cut.run_cut_stage. All 9 returned
    # fields are aliased back to their original local names so the
    # downstream RENDER block stays byte-for-byte unchanged.
    _cut = run_cut_stage(ctx, idx, seg, raw_part, part_name, final_part)
    _trim_offset         = _cut.trim_offset
    _effective_start     = _cut.effective_start
    _effective_end       = _cut.effective_end
    _force_accurate_cut  = _cut.force_accurate_cut
    _visual_trim         = _cut.visual_trim
    _part_timeline       = _cut.part_timeline
    _part_manifest       = _cut.part_manifest
    _cut_ms              = _cut.cut_ms
    _first_frame_scan_ms = _cut.first_frame_scan_ms

    (_part_assets, _srt_count, _srt_meta,
     _hook_subtitle_formatted, _subtitle_ass_ms) = prepare_part_assets(
        ctx, idx, seg, srt_part, ass_part, translated_srt_part,
        _effective_start, _part_manifest, part_name, final_part,
        raw_part,
    )
    part_subtitle_enabled = _part_assets.subtitle_enabled
    _part_text_layers = list(_part_assets.text_layers)
    _part_text_layers_overlay = list(_part_assets.text_layers_overlay)
    _effective_subtitle_style = _part_assets.subtitle_style
    _hook_overlay_applied_for_part = _part_assets.hook_overlay_applied
    overlay_title = (ctx.payload.title_overlay_text or "").strip() or ctx.source["title"]
    upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.RENDERING, 70, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Rendering final video")

    # Sprint 6.D-2.4: RENDER pre-flight (encoding params + progress-timer
    # thread + cache key + PartExecutionPlan + CameraStrategy +
    # feature-flag warning) moved to part_render_setup.run_render_preflight.
    # 13 returned fields aliased back to original local names so the
    # downstream FFmpeg core block stays byte-for-byte unchanged.
    _preflight = run_render_preflight(
        ctx, idx, seg, part_name, str(final_part),
        _effective_start, _trim_offset, _visual_trim,
        _force_accurate_cut, part_subtitle_enabled,
    )
    _vf_ct                = _preflight.vf_ct
    _vf_crf_delta         = _preflight.vf_crf_delta
    _part_video_crf       = _preflight.part_video_crf
    _vf_bitrate_profile   = _preflight.vf_bitrate_profile
    _vf_subtitle_bump     = _preflight.vf_subtitle_bump
    _encode_stop          = _preflight.encode_stop
    _encode_timer         = _preflight.encode_timer
    _t_encode             = _preflight.t_encode
    _t_render             = _preflight.t_render
    _motion_ck            = _preflight.motion_ck
    _motion_crop_fallback = _preflight.motion_crop_fallback
    _part_plan            = _preflight.part_plan
    _camera_strategy      = _preflight.camera_strategy

    # Sprint 6.D-2.5a: FFmpeg encode core (base_clip + overlay composite +
    # render_part_smart fallback + encode-thread lifecycle close + motion-crop
    # recovery + visual_finish_applied) moved to part_render_encode.run_render_encode.
    # The single returned field is aliased back to its original local name
    # so the downstream voice/mix/finalize blocks stay byte-for-byte unchanged.
    _encode = run_render_encode(
        ctx, idx, seg, raw_part, ass_part, final_part,
        part_subtitle_enabled, overlay_title,
        _part_manifest, _part_timeline,
        _part_text_layers, _part_text_layers_overlay,
        _effective_subtitle_style, _preflight,
    )
    _render_ms = _encode.render_ms
    # Sprint 6.D-2.5b: Voice TTS + audio mix block (subtitle and
    # translated_subtitle paths + mix_narration_audio with atomic file
    # swap) moved to part_voice_mix.run_part_voice_mix. Side-effect-only:
    # mutates ctx.voice_part_tts_attempts / voice_mix_ok, manifest.narration_path,
    # and overwrites final_part in-place when narration was generated.
    run_part_voice_mix(
        ctx, idx, seg, srt_part, translated_srt_part, final_part, _part_manifest,
    )
    # Sprint 6.D-2.5c: Finalize block (micro-pacing + intro/outro/logo +
    # duration math + scoring + Sacred Contract #8 qa_pipeline validation)
    # moved to part_render_finalize.run_part_finalize. The helper raises
    # RuntimeError on validation failure — propagates up to the per-part
    # worker in pipeline_render_loop which records the failure.
    run_part_finalize(
        ctx, idx, seg, srt_part, ass_part, final_part,
        part_subtitle_enabled, _hook_overlay_applied_for_part,
        _hook_subtitle_formatted, _srt_count,
        _trim_offset, _effective_start, _part_timeline,
        _t_part_start, _cut_ms, _first_frame_scan_ms, _subtitle_ass_ms,
        _preflight, _encode,
    )
    # Sprint 6.D-2.5d: Per-part DONE block (quality intelligence +
    # cover frame + JobPartStage.DONE terminal upsert + cleanup +
    # return dict) moved to part_done.run_part_done. The function
    # returns the dict shape that process_one_part has always handed
    # back to its caller (pipeline_render_loop.run_render_loop).
    return run_part_done(
        ctx, idx, seg, raw_part, srt_part, ass_part, final_part,
        part_name, _srt_meta, _variant_type, part_subtitle_enabled,
    )
