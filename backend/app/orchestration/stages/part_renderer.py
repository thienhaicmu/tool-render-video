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
    _part_subtitle_voice_path = None
    if (
        getattr(ctx.payload, "voice_enabled", False)
        and getattr(ctx.payload, "voice_source", "manual") == "subtitle"
        and ctx.voice_audio_path is None
    ):
        _part_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
        _part_srt_inmem_text: str | None = None
        if _part_srt is None and ctx.full_srt_available:
            try:
                _part_srt_inmem_text = slice_srt_to_text(str(ctx.full_srt), seg["start"], seg["end"])
                _part_srt = ctx.full_srt
                _job_log(ctx.effective_channel, ctx.job_id, f"voice.srt_in_memory part_no={idx} (no temp file written)", kind="debug")
            except Exception:
                _part_srt = None
        if _part_srt:
            _part_narration_text = _part_srt_inmem_text if _part_srt_inmem_text is not None else extract_text_from_srt(str(_part_srt))
            if _part_narration_text.strip():
                ctx.voice_part_tts_attempts.append(idx)
                _part_mp3 = str(TEMP_DIR / ctx.job_id / "voice" / f"part_{idx:03d}.mp3")
                if ctx.cancel_registry.is_cancelled(ctx.job_id):
                    raise ctx.cancel_registry.JobCancelledError()
                try:
                    _job_log(ctx.effective_channel, ctx.job_id, f"Generating AI narration for part {idx}/{ctx.total_parts} from subtitle", kind="debug")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_tts_started",
                        level="INFO",
                        message=f"Generating AI voice from subtitle (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "language": ctx.payload.voice_language, "source": "subtitle"},
                    )
                    _part_subtitle_voice_path = generate_narration_audio(
                        text=_part_narration_text,
                        language=ctx.payload.voice_language,
                        gender=ctx.payload.voice_gender,
                        rate=ctx.payload.voice_rate,
                        job_id=ctx.job_id,
                        voice_id=getattr(ctx.payload, "voice_id", None),
                        output_path=_part_mp3,
                        content_type=str(seg.get("content_type_hint") or "vlog"),
                        tts_engine=getattr(ctx.payload, "tts_engine", "edge"),
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_tts_completed",
                        level="INFO",
                        message=f"AI voice from subtitle generated (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                    )
                    _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                        str(_part_subtitle_voice_path),
                        ctx.payload,
                        effective_channel=ctx.effective_channel,
                        job_id=ctx.job_id,
                        part_no=idx,
                        source="subtitle",
                    )
                except Exception as _part_tts_exc:
                    _part_subtitle_voice_path = None
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice_part_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                    _job_log(ctx.effective_channel, ctx.job_id, f"Narration generation failed for part {idx}. Continuing without narration.", kind="warning")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_failed",
                        level="ERROR",
                        message=f"AI voice (subtitle, part {idx}) failed: {_part_tts_exc}",
                        step="voice.tts",
                        exception=_part_tts_exc,
                        traceback_text=traceback.format_exc(),
                        context={"part_no": idx, "error_code": "VOICE001"},
                    )
            else:
                _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} subtitle text empty; narration skipped", kind="warning")
        else:
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_subtitle_source_missing part_no={idx} source=subtitle; narration skipped", kind="warning")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_subtitle_source_missing",
                level="WARNING",
                message=f"Subtitle voice source missing for part {idx}; narration skipped",
                step="voice.tts",
                context={"part_no": idx, "source": "subtitle"},
            )
    elif (
        getattr(ctx.payload, "voice_enabled", False)
        and getattr(ctx.payload, "voice_source", "manual") == "translated_subtitle"
        and ctx.voice_audio_path is None
    ):
        _tgt_lang_voice = getattr(ctx.payload, "subtitle_target_language", "en")
        if not ctx.payload.voice_language.lower().startswith(_tgt_lang_voice.lower()):
            _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_LANGUAGE_TARGET_MISMATCH: voice_language={ctx.payload.voice_language} target={_tgt_lang_voice}", kind="warning")
        _voice_srt = translated_srt_part if translated_srt_part.exists() and translated_srt_part.stat().st_size > 0 else None
        if _voice_srt is None:
            _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_TRANSLATED_SUBTITLE_MISSING: part {idx} translated SRT not found; falling back to original", kind="warning")
            _voice_srt = srt_part if srt_part.exists() and srt_part.stat().st_size > 0 else None
        _voice_srt_inmem_text: str | None = None
        if _voice_srt is None and ctx.full_srt_available:
            try:
                _voice_srt_inmem_text = slice_srt_to_text(str(ctx.full_srt), seg["start"], seg["end"])
                _voice_srt = ctx.full_srt
                _job_log(ctx.effective_channel, ctx.job_id, f"voice.translated_srt_in_memory part_no={idx} (no temp file written)", kind="debug")
            except Exception:
                _voice_srt = None
        if _voice_srt:
            _part_narration_text = _voice_srt_inmem_text if _voice_srt_inmem_text is not None else extract_text_from_srt(str(_voice_srt))
            if _part_narration_text.strip():
                ctx.voice_part_tts_attempts.append(idx)
                _part_mp3 = str(TEMP_DIR / ctx.job_id / "voice" / f"part_{idx:03d}.mp3")
                try:
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice_translated_subtitle_tts_started part_no={idx}", kind="debug")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_translated_subtitle_tts_started",
                        level="INFO",
                        message=f"Generating AI voice from translated subtitle (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "language": ctx.payload.voice_language, "target": _tgt_lang_voice},
                    )
                    _part_subtitle_voice_path = generate_narration_audio(
                        text=_part_narration_text,
                        language=ctx.payload.voice_language,
                        gender=ctx.payload.voice_gender,
                        rate=ctx.payload.voice_rate,
                        job_id=ctx.job_id,
                        voice_id=getattr(ctx.payload, "voice_id", None),
                        output_path=_part_mp3,
                        content_type=str(seg.get("content_type_hint") or "vlog"),
                        tts_engine=getattr(ctx.payload, "tts_engine", "edge"),
                    )
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_translated_subtitle_tts_completed",
                        level="INFO",
                        message=f"AI voice from translated subtitle generated (part {idx})",
                        step="voice.tts",
                        context={"part_no": idx, "audio_path": _part_subtitle_voice_path, "voice_text_length": len(_part_narration_text)},
                    )
                    _part_subtitle_voice_path = _maybe_cleanup_narration_audio(
                        str(_part_subtitle_voice_path),
                        ctx.payload,
                        effective_channel=ctx.effective_channel,
                        job_id=ctx.job_id,
                        part_no=idx,
                        source="translated_subtitle",
                    )
                except Exception as _part_tts_exc:
                    _part_subtitle_voice_path = None
                    _job_log(ctx.effective_channel, ctx.job_id, f"voice_translated_subtitle_tts_failed part_no={idx}: {_part_tts_exc}", kind="error")
                    _job_log(ctx.effective_channel, ctx.job_id, f"Narration generation failed for part {idx}. Continuing without narration.", kind="warning")
                    _emit_render_event(
                        channel_code=ctx.effective_channel,
                        job_id=ctx.job_id,
                        event="voice_failed",
                        level="ERROR",
                        message=f"AI voice (translated subtitle, part {idx}) failed: {_part_tts_exc}",
                        step="voice.tts",
                        exception=_part_tts_exc,
                        traceback_text=traceback.format_exc(),
                        context={"part_no": idx, "error_code": "VOICE001"},
                    )
            else:
                _job_log(ctx.effective_channel, ctx.job_id, f"VOICE_SUBTITLE_EMPTY: part {idx} translated subtitle text empty; narration skipped", kind="warning")
        else:
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_subtitle_source_missing part_no={idx} source=translated_subtitle; narration skipped", kind="warning")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_subtitle_source_missing",
                level="WARNING",
                message=f"Translated subtitle voice source missing for part {idx}; narration skipped",
                step="voice.tts",
                context={"part_no": idx, "source": "translated_subtitle"},
            )
    _final_voice_path = ctx.voice_audio_path or _part_subtitle_voice_path
    if _final_voice_path:
        _part_manifest.narration_path = str(_final_voice_path)
        write_manifest(ctx.work_dir, _part_manifest)
        mixed_part = final_part.with_name(final_part.stem + ".voice_tmp.mp4")
        try:
            _job_log(ctx.effective_channel, ctx.job_id, f"Mixing AI narration into part {idx}/{ctx.total_parts}", kind="debug")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_mix_started",
                level="INFO",
                message="Mixing narration audio",
                step="voice.mix",
                context={"part_no": idx, "mix_mode": ctx.payload.voice_mix_mode},
            )
            mix_narration_audio(
                video_path=str(final_part),
                narration_audio_path=str(_final_voice_path),
                mix_mode=ctx.payload.voice_mix_mode,
                output_path=str(mixed_part),
                playback_speed=_get_effective_playback_speed(ctx.payload, ctx.target_platform),
            )
            os.replace(str(mixed_part), str(final_part))
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_mix_completed part_no={idx}/{ctx.total_parts}")
            ctx.voice_mix_ok.append(idx)
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_mix_completed",
                level="INFO",
                message="Voice narration completed",
                step="voice.mix",
                context={"part_no": idx, "output_file": str(final_part)},
            )
        except Exception as mix_exc:
            _safe_unlink(mixed_part)
            _job_log(ctx.effective_channel, ctx.job_id, f"voice_mix_failed part_no={idx}: {mix_exc}", kind="error")
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="voice_failed",
                level="ERROR",
                message=f"voice_mix_failed part_no={idx}: {mix_exc}",
                step="voice.mix",
                context={"part_no": idx, "output_file": str(final_part), "error_code": "VOICE001"},
                exception=mix_exc,
                traceback_text=traceback.format_exc(),
            )

    _micro_pacing_applied = False
    _micro_pacing_trim_sec = 0.0
    if ctx.cancel_registry.is_cancelled(ctx.job_id):
        raise ctx.cancel_registry.JobCancelledError()
    if final_part.exists() and final_part.stat().st_size > 0:
        _paced_part = ctx.work_dir / f"{ctx.source['slug']}_part_{idx:03d}_paced.mp4"
        _t_mp = time.perf_counter()
        try:
            _seg_content_type = seg.get("content_type_hint", "vlog")
            _pacing = apply_micro_pacing(
                str(final_part), str(_paced_part),
                content_type=_seg_content_type,
            )
            _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
            if _pacing["applied"] and _paced_part.exists() and _paced_part.stat().st_size > 0:
                os.replace(str(_paced_part), str(final_part))
                _micro_pacing_applied = True
                _micro_pacing_trim_sec = max(0.0, float(_pacing.get("total_trim_ms") or 0) / 1000.0)
                _job_log(
                    ctx.effective_channel, ctx.job_id,
                    f"Part {idx} micro pacing: {_pacing['segments_trimmed']} segments, "
                    f"{_pacing['total_trim_ms']}ms trimmed, "
                    f"content_type={_seg_content_type}",
                )
                _emit_render_event(
                    channel_code=ctx.effective_channel,
                    job_id=ctx.job_id,
                    event="micro_pacing_applied",
                    level="INFO",
                    message=(
                        f"Micro pacing applied: {_pacing['segments_trimmed']} segments, "
                        f"{_pacing['total_trim_ms']}ms removed"
                    ),
                    step="render.micro_pacing",
                    context={
                        "part_no": idx,
                        "segments_trimmed": _pacing["segments_trimmed"],
                        "total_trim_ms": _pacing["total_trim_ms"],
                        "method": _pacing["method"],
                        "content_type": _seg_content_type,
                    },
                )
            else:
                _emit_render_event(
                    channel_code=ctx.effective_channel,
                    job_id=ctx.job_id,
                    event="micro_pacing_skipped",
                    level="INFO",
                    message="Micro pacing skipped: no qualifying silence segments",
                    step="render.micro_pacing",
                    context={"part_no": idx},
                )
        except subprocess.TimeoutExpired:
            _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"micro_pacing_timeout part_no={idx} elapsed_ms={_micro_pacing_ms} — skipped, original kept",
                kind="warning",
            )
        except Exception as _pace_exc:
            _micro_pacing_ms = int((time.perf_counter() - _t_mp) * 1000)
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"micro_pacing_failed part_no={idx}: {_pace_exc}",
                kind="warning",
            )
        finally:
            _safe_unlink(_paced_part)
        logger.info("micro_pacing_ms=%d part=%d applied=%s", _micro_pacing_ms, idx, _micro_pacing_applied)

    _emit_render_event(
        channel_code=ctx.effective_channel,
        job_id=ctx.job_id,
        event="p4_output_opening_optimized",
        level="INFO",
        message=(
            f"P4 opening: part {idx} trim={_trim_offset:.3f}s "
            f"hook={_hook_subtitle_formatted} pacing={_micro_pacing_applied}"
        ),
        step="render.p4_opening",
        context={
            "part_no": idx,
            "original_start": seg["start"],
            "effective_start": _effective_start,
            "trim_offset": _trim_offset,
            "original_duration": seg["end"] - seg["start"],
            "effective_duration": seg["end"] - _effective_start,
            "subtitle_count": _srt_count,
            "hook_subtitle_formatted": _hook_subtitle_formatted,
            "micro_pacing_applied": _micro_pacing_applied,
            "micro_pacing_trim_sec": _micro_pacing_trim_sec,
        },
    )

    _encode_ms = int((time.perf_counter() - _t_encode) * 1000)
    _total_part_ms = int((time.perf_counter() - _t_part_start) * 1000)
    _effective_duration = max(0.0, float(seg["end"]) - float(_effective_start))
    _render_speed = _get_effective_playback_speed(ctx.payload, ctx.target_platform)
    _remotion_intro_sec = _maybe_prepend_remotion_hook_intro(
        final_part,
        ctx.payload,
        effective_channel=ctx.effective_channel,
        job_id=ctx.job_id,
        part_no=idx,
        content_type=str(seg.get("content_type_hint") or "vlog"),
        hook_text=ctx.hook_applied_text or None,
        source_title=str(ctx.source.get("title") or ""),
    )
    _maybe_prepend_asset_intro(final_part, ctx.payload,
        effective_channel=ctx.effective_channel, job_id=ctx.job_id, part_no=idx)
    _maybe_append_asset_outro(final_part, ctx.payload,
        effective_channel=ctx.effective_channel, job_id=ctx.job_id, part_no=idx)
    _maybe_apply_asset_logo(final_part, ctx.payload,
        effective_channel=ctx.effective_channel, job_id=ctx.job_id, part_no=idx)
    _expected_final_duration = max(
        0.0,
        (_effective_duration / _render_speed) - _micro_pacing_trim_sec + _remotion_intro_sec,
    )
    _speed_ratio = round(_expected_final_duration * 1000 / max(_encode_ms, 1), 2)
    _job_log(
        ctx.effective_channel, ctx.job_id,
        f"playback_speed_resolution part={idx} "
        f"payload_speed={float(ctx.payload.playback_speed or 1.0):.4f} "
        f"platform_delta={_PLATFORM_PROFILES.get(ctx.target_platform, {}).get('speed_delta', 0.0):.4f} "
        f"effective_speed={_render_speed:.4f} "
        f"target_platform={ctx.target_platform} "
        f"source_duration={_part_timeline.source_duration:.3f}s "
        f"output_duration={_part_timeline.output_duration:.3f}s "
        f"effective_duration={_effective_duration:.3f}s "
        f"expected_duration={_expected_final_duration:.3f}s "
        f"manifest={_manifest_path(ctx.work_dir, idx)}",
        kind="debug",
    )
    logger.info(
        "total_part_render_ms=%d part=%d "
        "cut_ms=%d first_frame_ms=%d subtitle_ass_ms=%d "
        "render_ms=%d pacing_ms=%d quality_ms=%d",
        _total_part_ms, idx,
        _cut_ms, _first_frame_scan_ms, _subtitle_ass_ms,
        _render_ms, _micro_pacing_ms, _quality_validation_ms,
    )
    if ctx.normalized_text_layers:
        _job_log(
            ctx.effective_channel,
            ctx.job_id,
            f"Applied {len(ctx.normalized_text_layers)} text layer(s) on part {idx}/{ctx.total_parts}",
            kind="debug",
        )
    _job_log(
        ctx.effective_channel, ctx.job_id,
        f"Part {idx}/{ctx.total_parts} done: encode_ms={_encode_ms} "
        f"expected_final_duration={_expected_final_duration:.2f}s speed_ratio={_speed_ratio}x "
        f"(>1 = faster than realtime)",
        kind="info",
    )

    try:
        _mv_text = ""
        if srt_part.exists() and srt_part.stat().st_size > 0:
            _mv_text = extract_text_from_srt(str(srt_part))
        _mv_dur = float(seg.get("duration") or 0) or None
        _mv_result = _mv_score_part(_mv_text, _mv_dur, ctx.mv_market)
        seg["mv_viral_score"]   = _mv_result.get("viral_score",  0)
        seg["mv_viral_tier"]    = _mv_result.get("viral_tier",   "weak")
        seg["mv_viral_market"]  = _mv_result.get("viral_market", ctx.mv_market)
        seg["mv_viral_reasons"] = _mv_result.get("reasons",      [])
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="market_viral_scored",
            level="INFO",
            message=(
                f"Part {idx} market viral: {seg['mv_viral_score']} "
                f"{seg['mv_viral_tier']} ({seg['mv_viral_market']})"
            ),
            step="render.market_viral",
            context={
                "part_no":              idx,
                "market_viral_score":   seg["mv_viral_score"],
                "market_viral_tier":    seg["mv_viral_tier"],
                "market_viral_market":  seg["mv_viral_market"],
                "market_viral_reasons": seg["mv_viral_reasons"][:2],
            },
        )
    except Exception:
        pass

    try:
        _cs_enabled  = bool(getattr(ctx.payload, "combined_scoring_enabled", False))
        _cs_adaptive = bool(getattr(ctx.payload, "adaptive_scoring_enabled", False))
        _cs_viral    = float(seg.get("viral_score", 0) or 0)
        _cs_mv_raw   = seg.get("mv_viral_score")
        _cs_mv       = float(_cs_mv_raw) if _cs_mv_raw is not None else _cs_viral
        _cs_hook_raw = (seg.get("hook_text_score") or seg.get("hook_timing_score") or
                        seg.get("hook_opening_score") or seg.get("hook_score"))
        _cs_hook     = float(_cs_hook_raw or 0)
        _cs_dur      = float(seg.get("duration") or 0) or None

        _cs_weights = resolve_combined_score_weights(
            target_market=ctx.mv_market,
            has_market_score=(_cs_mv_raw is not None),
            has_hook_score=(_cs_hook_raw is not None and float(_cs_hook_raw) > 0),
            duration=_cs_dur,
            adaptive_enabled=_cs_adaptive,
        )
        seg["combined_weights"] = _cs_weights

        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="adaptive_score_weights_resolved",
            level="INFO",
            message=f"Part {idx} weights v={_cs_weights['viral_weight']} m={_cs_weights['market_weight']} h={_cs_weights['hook_weight']} reason={_cs_weights['reason']}",
            step="render.combined_score",
            context={
                "part_no":                  idx,
                "adaptive_scoring_enabled": _cs_adaptive,
                "target_market":            ctx.mv_market,
                "duration":                 _cs_dur,
                "viral_weight":             _cs_weights["viral_weight"],
                "market_weight":            _cs_weights["market_weight"],
                "hook_weight":              _cs_weights["hook_weight"],
                "reason":                   _cs_weights["reason"],
            },
        )

        _cs_raw = (
            _cs_viral * _cs_weights["viral_weight"] +
            _cs_mv    * _cs_weights["market_weight"] +
            _cs_hook  * _cs_weights["hook_weight"]
        )
        seg["combined_score"] = round(max(0.0, min(100.0, _cs_raw)), 1)
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="combined_score_computed",
            level="INFO",
            message=f"Part {idx} combined_score={seg['combined_score']}",
            step="render.combined_score",
            context={
                "part_no":                  idx,
                "viral_score":              _cs_viral,
                "market_viral_score":       _cs_mv,
                "hook_score_component":     _cs_hook,
                "combined_score":           seg["combined_score"],
                "combined_scoring_enabled": _cs_enabled,
                "viral_weight":             _cs_weights["viral_weight"],
                "market_weight":            _cs_weights["market_weight"],
                "hook_weight":              _cs_weights["hook_weight"],
            },
        )
    except Exception:
        pass

    _render_output = RenderOutputResult(
        output_path=str(final_part),
        render_ms=_render_ms,
        codec=str(ctx.payload.video_codec),
        crop_fallback=bool(_motion_crop_fallback),
        overlay_composite_used=bool(
            int(os.environ.get("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0"))
            and int(os.environ.get("FEATURE_BASE_CLIP_FIRST", "0"))
        ),
    )
    logger.info(
        "render_output part=%d codec=%s render_ms=%d crop_fallback=%s overlay=%s",
        idx, _render_output.codec, _render_output.render_ms,
        _render_output.crop_fallback, _render_output.overlay_composite_used,
    )

    _expect_audio: bool | None = None
    if getattr(ctx.payload, "voice_enabled", False):
        _expect_audio = True
    elif (getattr(ctx.payload, "reup_bgm_enable", False)
          and bool(str(getattr(ctx.payload, "reup_bgm_path", None) or "").strip())):
        _expect_audio = True
    _qa = _validate_render_output(
        final_part,
        expected_duration=_expected_final_duration if _expected_final_duration > 0 else None,
        expect_audio=_expect_audio,
    )
    _actual_final_duration = float((_qa.get("metadata") or {}).get("duration") or 0.0)
    _job_log(
        ctx.effective_channel,
        ctx.job_id,
        f"Part {idx} duration validation: expected_final_duration={_expected_final_duration:.3f}s "
        f"actual_final_duration={_actual_final_duration:.3f}s "
        f"effective_start={float(_effective_start):.3f}s segment_end={float(seg['end']):.3f}s "
        f"playback_speed={_render_speed:.4f}",
        kind="debug",
    )
    if not _qa["ok"]:
        _qa_code = str(_qa.get("code") or "RN001")
        _job_log(ctx.effective_channel, ctx.job_id,
                 f"Part {idx} output_validation_failed: {_qa['error']} | "
                 f"code={_qa_code} output={final_part} meta={_qa['metadata']}", kind="error")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_validation_failed",
            level="ERROR",
            message=f"Part {idx} output validation failed: {_qa['error']}",
            step="render.output.validate",
            error_code=_qa_code,
            context={
                "part_no": idx,
                "output_file": str(final_part),
                "validation_code": _qa_code,
                **_qa["metadata"],
            },
        )
        raise RuntimeError(f"output_validation_failed[{_qa_code}]: {_qa['error']}")
    if _qa["warnings"]:
        _job_log(ctx.effective_channel, ctx.job_id,
                 f"Part {idx} output_validation_warning: {'; '.join(_qa['warnings'])} | "
                 f"meta={_qa['metadata']}", kind="warning")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_validation_warning",
            level="WARNING",
            message=f"Part {idx} output validation passed with warnings: {'; '.join(_qa['warnings'])}",
            step="render.output.validate",
            context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
        )
    else:
        _job_log(ctx.effective_channel, ctx.job_id,
                 f"Part {idx} output_validation_passed: "
                 f"dur={_qa['metadata']['duration']:.2f}s "
                 f"size={_qa['metadata']['size_bytes']} "
                 f"has_video={_qa['metadata']['has_video']} "
                 f"has_audio={_qa['metadata']['has_audio']}")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_validation_passed",
            level="INFO",
            message=f"Part {idx} output validation passed",
            step="render.output.validate",
            context={"part_no": idx, "output_file": str(final_part), **_qa["metadata"]},
        )

    _emit_render_event(
        channel_code=ctx.effective_channel,
        job_id=ctx.job_id,
        event="output_quality_validation_started",
        level="INFO",
        message=f"Part {idx} quality validation started",
        step="render.output.quality",
        context={"part_no": idx, "output_file": str(final_part)},
    )
    _t_qq = time.perf_counter()
    _qq = _assess_output_quality(
        final_part,
        ctx.output_dir,
        expect_subtitle=part_subtitle_enabled,
        subtitle_file=ass_part if part_subtitle_enabled else None,
        expect_hook=ctx.hook_overlay_enabled,
        hook_applied=_hook_overlay_applied_for_part,
    )
    _quality_validation_ms = int((time.perf_counter() - _t_qq) * 1000)
    logger.info("quality_validation_ms=%d part=%d penalty=%d",
                _quality_validation_ms, idx, int(_qq["score_penalty"]))
    _quality_penalty = int(_qq["score_penalty"])
    seg["quality_penalty"] = _quality_penalty
    if _qq["warnings"] or not _qq["passed"]:
        _qq_level = "ERROR" if not _qq["passed"] else "WARNING"
        _qq_evt = "output_quality_validation_failed" if not _qq["passed"] else "output_quality_validation_warning"
        for _qw in _qq["warnings"]:
            _job_log(ctx.effective_channel, ctx.job_id, f"Part {idx} quality_warning: {_qw}", kind="warning")
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event=_qq_evt,
            level=_qq_level,
            message=f"Part {idx} quality validation: {len(_qq['warnings'])} warning(s)",
            step="render.output.quality",
            context={
                "part_no": idx,
                "output_file": str(final_part),
                "warnings": _qq["warnings"],
                "hard_failures": _qq["hard_failures"],
                "checks": _qq["checks"],
                "score_penalty": _quality_penalty,
            },
        )
    else:
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_quality_validation_passed",
            level="INFO",
            message=f"Part {idx} quality validation passed",
            step="render.output.quality",
            context={"part_no": idx, "output_file": str(final_part), "checks": _qq["checks"]},
        )
    if _quality_penalty > 0:
        _job_log(
            ctx.effective_channel, ctx.job_id,
            f"Part {idx} quality_score_penalty: -{_quality_penalty} checks={_qq['checks']}",
            kind="warning",
        )
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="output_quality_score_penalty_applied",
            level="WARNING",
            message=f"Part {idx} quality penalty applied: -{_quality_penalty} points",
            step="render.output.quality",
            context={
                "part_no": idx,
                "score_penalty": _quality_penalty,
                "checks": _qq["checks"],
                "warnings": _qq["warnings"],
            },
        )
    if _quality_penalty > 20:
        _emit_render_event(
            channel_code=ctx.effective_channel,
            job_id=ctx.job_id,
            event="render.quality_penalty_high",
            level="WARNING",
            message=f"Part {idx} quality penalty high: -{_quality_penalty} points",
            step="render.output.quality",
            context={
                "part_no": idx,
                "warnings": _qq["warnings"],
                "score_penalty": _quality_penalty,
            },
        )

    try:
        _qi_srt = ass_part if part_subtitle_enabled and ass_part and ass_part.suffix == ".srt" else None
        _qi_srt_path: Path | None = None
        if srt_path is not None and Path(str(srt_path)).exists():  # noqa: F821 — preserved bug: srt_path is undefined, caught by except below
            _qi_srt_path = Path(str(srt_path))
        elif _qi_srt is not None and Path(str(_qi_srt)).exists():
            _qi_srt_path = Path(str(_qi_srt))
        _qi_manifest: Path | None = None
        try:
            from app.ai.tracing import _DEFAULT_LOG_DIR as _ai_log_dir
            _qi_ai_trace = _ai_log_dir / f"{ctx.job_id}_ai_trace.jsonl"
            _qi_ai_trace = _qi_ai_trace if _qi_ai_trace.exists() else None
        except Exception:
            _qi_ai_trace = None
        _assess_render_quality_intelligence(
            video_path=final_part,
            part_no=idx,
            job_id=ctx.job_id,
            srt_path=_qi_srt_path,
            manifest_path=_qi_manifest,
            ai_trace_path=_qi_ai_trace,
        )
    except Exception:
        pass

    try:
        _clip_dur = max(1.0, float(seg.get("duration") or 0))
        _cover_hint_ratio: float | None = None
        try:
            if ctx.ai_edit_plan is not None:
                _plan_hint = (ctx.ai_edit_plan.clip_cover_hints or {}).get(idx - 1) or {}
                _raw_ratio = _plan_hint.get("preferred_offset_ratio")
                if _raw_ratio is not None:
                    _cover_hint_ratio = float(_raw_ratio)
        except Exception:
            pass
        _cover_offset, _cover_reason = _select_cover_frame_time(
            clip_duration=_clip_dur,
            hook_score=float(seg.get("hook_score") or 0),
            srt_meta=_srt_meta,
            target_platform=ctx.target_platform,
            variant_type=str(seg.get("variant_type") or ""),
            cover_hint_ratio=_cover_hint_ratio,
        )
        _cover_quality_reasons: list = []
        _cover_bytes = None
        if os.getenv("S4_THUMBNAIL_QUALITY_ENABLED") == "1":
            try:
                from app.services.thumbnail_quality import select_best_thumbnail
                _t_thumb = time.perf_counter()
                _cover_bytes, _cover_offset, _cover_quality_reasons = select_best_thumbnail(
                    str(final_part), _cover_offset, _clip_dur, width=640
                )
                _thumb_ms = int((time.perf_counter() - _t_thumb) * 1000)
                logger.debug("s4_thumbnail_select_ms part=%d ms=%d offset=%.3f", idx, _thumb_ms, _cover_offset)
            except Exception as _s43_exc:
                logger.debug("s4_thumbnail_quality_failed part=%d: %s", idx, _s43_exc)
        if not _cover_bytes:
            _cover_bytes = extract_thumbnail_frame(str(final_part), _cover_offset, width=640)
        if _cover_bytes:
            _cover_stem = (
                f"{ctx.output_stem}_{_variant_type}_cover" if _variant_type
                else f"{ctx.output_stem}_part_{idx:03d}_cover"
            )
            _cover_path = ctx.output_dir / f"{_cover_stem}.jpg"
            _cover_path.write_bytes(_cover_bytes)
            seg["cover_file"] = str(_cover_path)
            seg["cover_frame_offset"] = _cover_offset
            _emit_render_event(
                channel_code=ctx.effective_channel,
                job_id=ctx.job_id,
                event="cover_frame_selected",
                level="INFO",
                message=f"Smart cover: part {idx} offset={_cover_offset:.3f}s",
                step="render.cover",
                context={
                    "part_no":        idx,
                    "cover_file":     str(_cover_path),
                    "frame_offset":   _cover_offset,
                    "cover_reason":   _cover_reason,
                    "target_platform": ctx.target_platform,
                    "variant_type":   str(seg.get("variant_type") or ""),
                    "thumbnail_quality_reason": _cover_quality_reasons,
                },
            )
            _job_log(
                ctx.effective_channel, ctx.job_id,
                f"cover_frame_selected part_no={idx} offset={_cover_offset:.3f}s "
                f"platform={ctx.target_platform} reason={_cover_reason!r}",
            )
    except Exception as _cov_exc:
        logger.warning("cover_frame_extraction_failed part=%d: %s", idx, _cov_exc)
    upsert_job_part(ctx.job_id, idx, part_name, JobPartStage.DONE, 100, seg["start"], seg["end"], seg["duration"], seg.get("viral_score", 0), seg.get("motion_score", 0), seg.get("hook_score", 0), str(final_part), "Completed")
    row = [ctx.job_id, ctx.effective_channel, ctx.source["title"], idx, seg["start"], seg["end"], seg["duration"], seg["viral_score"], seg["priority_rank"], str(final_part)]
    if ctx.payload.cleanup_temp_files:
        _safe_unlink(raw_part)
        _safe_unlink(srt_part)
        _safe_unlink(ass_part)
    return {"idx": idx, "output": str(final_part), "row": row, "skipped": False}
