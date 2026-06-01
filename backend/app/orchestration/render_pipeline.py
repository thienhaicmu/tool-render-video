
import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
import time
import traceback
import logging
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Callable
from fastapi import HTTPException
from app.models.schemas import RenderRequest
from app.services.db import upsert_job, update_job_progress, upsert_job_part, list_job_parts, close_thread_conn
from app.services.channel_service import ensure_channel
from app.services.downloader import slugify
from app.services.segment_builder import refine_segment_boundaries, refine_cuts_for_naturalness
from app.services.subtitle_engine import (
    srt_to_ass_bounce, srt_to_ass_karaoke, slice_srt_by_time,
    slice_srt_to_text, slice_srt_to_output_timeline,
    has_audio_stream, apply_market_line_break_to_srt,
    apply_market_hook_text_to_srt, apply_hook_subtitle_format, resolve_hook_overlay_text,
    subtitle_emphasis_pass, parse_srt_blocks, write_srt_blocks,
    resegment_srt_for_readability,
)
from app.services.subtitle_transcription_adapters import transcribe_with_adapter
from app.services.render_engine import cut_video, render_part_smart, render_base_clip, composite_overlays_on_base_clip, nvenc_available, resolve_ffmpeg_threads, detect_silence_trim_offset, apply_micro_pacing, detect_bad_first_frame, set_thread_cancel_event, content_type_crf_delta as _crf_delta_for_content_type, extract_thumbnail_frame
from app.services import cancel_registry
from app.services.job_manager import MAX_CONCURRENT_JOBS as _MAX_CONCURRENT_JOBS
from app.services.viral_scorer import apply_retention_proxy
from app.services.viral_scoring import score_part_for_market as _mv_score_part
from app.services.report_service import append_rows
from app.core.config import TEMP_DIR, CHANNELS_DIR, LOGS_DIR, APP_DATA_DIR
from app.core.stage import JobStage, JobPartStage, STAGE_TO_EVENT
from app.services.bin_paths import get_ffprobe_bin, get_ffmpeg_bin, _summarize_ffmpeg_stderr
from app.services.text_overlay import normalize_text_layers, MAX_TEXT_LAYERS
from app.services.tts_service import generate_narration_mp3, generate_narration_audio
from app.services.audio_mix_service import mix_narration_audio
from app.services.audio_cleanup_adapters import cleanup_audio_with_adapter
from app.services.translation_service import translate_srt_file
from app.services.remotion_adapter import (
    generate_hook_intro, prepend_intro_clip, resolve_intro_preset,
    append_outro_clip, apply_logo_watermark,  # UP27
)
from app.ai.visibility.ai_visibility_summary import attach_ai_visibility_summaries
from app.domain.timeline import TimelineMap
from app.domain.manifests import BaseClipManifest
from app.services.manifest_writer import write_manifest, manifest_path as _manifest_path
from app.orchestration.render_events import (
    _JOB_LOG_DIRS,
    _append_json_line,
    _emit_render_event,
    _event_from_stage,
    _job_log,
    _render_error_code,
    _render_progress_timer,
    _resolve_job_log_dir,
    _safe_unlink,
)
from app.orchestration.asset_pipeline import (
    _maybe_append_asset_outro,
    _maybe_apply_asset_logo,
    _maybe_prepend_asset_intro,
    _maybe_prepend_remotion_hook_intro,
)
from app.orchestration.audio_pipeline import (
    _maybe_cleanup_narration_audio,
)
from app.orchestration.qa_pipeline import (
    _assess_output_quality,
    _assess_render_quality_intelligence,
    _duration_tolerance,
    _failed_part_progress,
    _render_part_failure_detail,
    _resume_output_valid,
    _stall_deadline,
    _validate_render_output,
)
from app.orchestration.part_plan import PartExecutionPlan
from app.orchestration.stages.part_renderer import PartRenderContext
from app.orchestration.pipeline_render_loop import RenderLoopResult as _RenderLoopResult, run_render_loop
from app.orchestration.pipeline_pre_render import run_pre_render_scenes
from app.orchestration.part_assets import PartAssets
from app.orchestration.camera_strategy import CameraStrategy
from app.orchestration.render_output import RenderOutputResult
from app.orchestration.pipeline_cache import (
    _RENDER_CACHE_TTL_SEC,
    _render_cache_key,
    _scene_cache_get, _scene_cache_put,
    _transcription_cache_get, _transcription_cache_put,
    _score_cache_get, _score_cache_put,
)
from app.orchestration.pipeline_ranking import (
    resolve_combined_score_weights,
    _score_component, _first_score,
    _output_ranking_detail, _output_ranking_reason,
    _compute_output_ranking_entry,
)
from app.orchestration.pipeline_config import (
    _resolve_profile, _probe_video_duration,
    extract_text_from_srt,
    _reserve_source_path_in_dir, _reserve_source_path,
    _sanitize_channel_subdir, _resolve_output_dir,
)
from app.orchestration.pipeline_subtitle_utils import (
    _aspect_play_res_y, _apply_subtitle_edits_to_srt,
    _append_cta_block_to_srt, _read_srt_meta,
)
from app.orchestration.pipeline_segment_selection import (
    _safe_output_name, _smart_output_stem, _map_ai_segments_to_scored,
    _select_cover_frame_time, _select_cta_text, _get_effective_playback_speed,
    _build_variant_segments, _PLATFORM_PROFILES,
)
from app.orchestration.pipeline_ai_phases import (
    run_phase_43_feedback_learning,
    run_phase_44_content_selection,
    run_phase_60d_execution_mode,
    run_phase_60d_mode_off_rollback,
    run_phase_11_beat_execution,
    run_phase_60a_execution_metrics,
    run_phase_60b_ab_evaluation,
    run_phase_60c_creator_benchmark,
    run_phase_61a_archetype_strategy,
    run_phase_61d_creator_render_strategy,
    run_phase_62a_outcome_tracking,
    run_phase_62b_preference_reinforcement,
    run_phase_62c_success_patterns,
    run_phase_62d_learning_calibration,
)

# Feature flag: generate a no-overlay base clip as a parallel artifact before the
# final render.  OFF by default.  Set FEATURE_BASE_CLIP_FIRST=1 to enable.
# The base clip is never fed into the final output — render_part_smart() always
# produces the final video unless FEATURE_OVERLAY_AFTER_BASE_CLIP is also enabled.
_FEATURE_BASE_CLIP_FIRST: bool = os.getenv("FEATURE_BASE_CLIP_FIRST", "0") == "1"

# Feature flag: composite subtitle overlays onto base_clip.mp4 as the final output.
# Requires FEATURE_BASE_CLIP_FIRST=1.  OFF by default.
# When both flags are ON: overlay composite path → fallback render_part_smart() on failure.
_FEATURE_OVERLAY_AFTER_BASE_CLIP: bool = os.getenv("FEATURE_OVERLAY_AFTER_BASE_CLIP", "0") == "1"

logger = logging.getLogger("app.render")


# _safe_output_name, _smart_output_stem, _map_ai_segments_to_scored,
# _select_cover_frame_time, _select_cta_text, _append_cta_block_to_srt,
# _get_effective_playback_speed, _read_srt_meta, _build_variant_segments,
# _aspect_play_res_y, _apply_subtitle_edits_to_srt, _PLATFORM_PROFILES,
# _PLAY_RES_Y_MAP, _VARIANT_AGGRESSIVE_SUB, _VARIANT_STORY_SUB,
# _CTA_TEXTS, _CTA_AUTO_TYPE
# → moved to app.orchestration.pipeline_helpers (Phase A-1)

# _map_ai_segments_to_scored already imported from pipeline_helpers above

# _RENDER_CACHE_TTL_SEC, _render_cache_key, _scene_cache_get/put,
# _transcription_cache_get/put, _score_cache_get/put
# → moved to app.orchestration.pipeline_cache (C-1)

# resolve_combined_score_weights, _score_component, _first_score,
# _RANKING_WEIGHTS, _output_ranking_detail, _output_ranking_reason,
# _compute_output_ranking_entry
# → moved to app.orchestration.pipeline_ranking (C-1)

# _maybe_prepend_remotion_hook_intro, _maybe_prepend_asset_intro,
# _maybe_append_asset_outro, _maybe_apply_asset_logo
# → moved to app.orchestration.asset_pipeline (Phase 4B)

# _maybe_cleanup_narration_audio → moved to app.orchestration.audio_pipeline (Phase 4D)


# _PROGRESS_TICK_SEC, _render_progress_timer → moved to app.orchestration.render_events (Phase 4D)

# _resume_output_valid → moved to app.orchestration.qa_pipeline (Phase 4C)


# ---------------------------------------------------------------------------
# Resource throttling
# ---------------------------------------------------------------------------
# JOB_SEMAPHORE caps how many render pipelines can be in the FFmpeg-encode
# section simultaneously.  This prevents CPU saturation when multiple jobs
# are dispatched by the scheduler at the same time.
# Default derives from MAX_CONCURRENT_JOBS so the semaphore never silently
# under-utilises slots that the scheduler has already granted.
# Override with MAX_RENDER_JOBS env var to set an explicit ceiling.
_JOB_SEM_VALUE: int = max(1, int(os.getenv("MAX_RENDER_JOBS", str(_MAX_CONCURRENT_JOBS))))
JOB_SEMAPHORE = threading.Semaphore(_JOB_SEM_VALUE)
_render_active_lock = threading.Lock()
_render_active_count: list[int] = [0]   # mutable int; guarded by _render_active_lock


# _apply_subtitle_edits_to_srt → moved to app.orchestration.pipeline_helpers (Phase A-1)

# _duration_tolerance, _stall_deadline → moved to app.orchestration.qa_pipeline (Phase 4C)


# _render_progress_timer → moved to app.orchestration.render_events (Phase 4D)


# HIGH_MOTION_MIN_SCORE, HIGH_MOTION_MIN_KEEP â†' moved to pipeline_pre_render (Phase A-6)
# _JOB_LOG_DIRS, _job_log, _append_json_line, _render_error_code, _emit_render_event
# → moved to app.orchestration.render_events (Phase 4B)


# _event_from_stage, _resolve_job_log_dir → moved to app.orchestration.render_events (Phase 4D)


def _validate_text_layers_or_400(payload: RenderRequest) -> list[dict]:
    try:
        raw_layers = [x.model_dump() if hasattr(x, "model_dump") else dict(x) for x in (payload.text_layers or [])]
        if len(raw_layers) > MAX_TEXT_LAYERS:
            raise ValueError(f"text_layers exceeds maximum {MAX_TEXT_LAYERS}")
        return normalize_text_layers(raw_layers)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid text_layers: {exc}") from exc


# _resolve_profile, _probe_video_duration, extract_text_from_srt,
# _reserve_source_path_in_dir, _reserve_source_path,
# _sanitize_channel_subdir, _resolve_output_dir
# → moved to app.orchestration.pipeline_config (C-1)

# _safe_unlink → moved to app.orchestration.render_events (Phase 4B)

# _failed_part_progress → moved to app.orchestration.qa_pipeline (Phase 4C)

# _validate_render_output → moved to app.orchestration.qa_pipeline (Phase 4C)

# _assess_output_quality → moved to app.orchestration.qa_pipeline (Phase 4C)

# _render_part_failure_detail → moved to app.orchestration.qa_pipeline (Phase 4C)


def run_render_pipeline(
    job_id: str,
    payload: RenderRequest,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
):
    output_mode = (payload.output_mode or "channel").strip().lower()
    effective_channel = (payload.channel_code or "").strip() or "manual"
    started_at = datetime.utcnow()

    # Market Viral — resolve target market once; used by all part workers via closure
    _mv_cfg = getattr(payload, "market_viral", None) or {}
    _mv_cfg_enabled = isinstance(_mv_cfg, dict) and bool(_mv_cfg)
    _mv_payload_market = getattr(payload, "ai_target_market", None) or getattr(payload, "viral_market", None)
    _mv_market = str(
        _mv_payload_market
        or ((_mv_cfg.get("target_market") or "US") if isinstance(_mv_cfg, dict) else "US")
    ).upper()
    if _mv_market not in {"US", "EU", "JP"}:
        _mv_market = "US"
    if _mv_cfg_enabled:
        _mv_cfg = {**_mv_cfg, "target_market": _mv_market}
    else:
        _mv_cfg = {}
    _hook_apply_enabled = bool(getattr(payload, "hook_apply_enabled", False))
    _hook_applied_text = str(getattr(payload, "hook_applied_text", None) or "").strip()
    _hook_score = getattr(payload, "hook_score", None)
    _hook_overlay_enabled = bool(getattr(payload, "hook_overlay_enabled", False))
    if not _hook_applied_text:
        _hook_apply_enabled = False
    if output_mode == "channel":
        ensure_channel(effective_channel)
        if not (payload.render_output_subdir or "").strip():
            raise RuntimeError("render_output_subdir is required")
        output_dir = _resolve_output_dir(effective_channel, payload.output_dir, payload.render_output_subdir)
    else:
        output_dir = Path(payload.output_dir).expanduser()
        if not output_dir.is_absolute():
            output_dir = (Path.cwd() / output_dir).resolve()
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.output.prepare.start",
        level="INFO",
        message="Preparing output directory",
        step="render.output.prepare",
        context={"output_dir": str(output_dir)},
    )
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.output.prepare.success",
            level="INFO",
            message="Output directory ready",
            step="render.output.prepare",
            context={"output_dir": str(output_dir)},
        )
    except Exception as output_exc:
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.output.prepare.error",
            level="ERROR",
            message=f"Failed to prepare output directory: {output_exc}",
            step="render.output.prepare",
            context={"output_dir": str(output_dir)},
            exception=output_exc,
            traceback_text=traceback.format_exc(),
        )
        raise
    _JOB_LOG_DIRS[job_id] = _resolve_job_log_dir(output_dir, output_mode, effective_channel)
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    tuned = _resolve_profile(payload)
    retry_count = max(0, min(5, int(payload.retry_count)))
    current_stage = JobStage.STARTING
    current_progress = 1

    def _set_stage(stage: str, progress: int, message: str):
        nonlocal current_stage, current_progress
        current_stage = stage
        current_progress = max(0, min(99, int(progress)))
        update_job_progress(job_id, stage, progress, message)
        _job_log(effective_channel, job_id, f"[STAGE] {stage} | {message}")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event=_event_from_stage(stage),
            level="INFO",
            message=message,
            step=stage,
            context={"progress_percent": progress},
        )

    _job_log(
        effective_channel,
        job_id,
        f"Render started | resume={resume_mode} | profile={payload.render_profile} | codec={payload.video_codec} | reup_mode={payload.reup_mode} | source_mode={payload.source_mode} | output_mode={output_mode}",
    )
    _job_log(
        effective_channel,
        job_id,
        f"Market Viral hook | market={_mv_market} | hook_apply_enabled={_hook_apply_enabled} | hook_score={_hook_score}",
    )
    _preset_name = str(getattr(payload, "render_preset", None) or "").strip() or "custom"
    _preset_id = str(getattr(payload, "render_preset_id", None) or _preset_name or "").strip() or "custom"
    _preset_label = str(getattr(payload, "render_preset_label", None) or "").strip()
    if not _preset_label:
        _preset_label = "Custom" if _preset_id.lower() == "custom" else _preset_id
    if _preset_id and _preset_id.lower() != "custom":
        _job_log(
            effective_channel,
            job_id,
            f"Render preset applied | id={_preset_id} | label={_preset_label}",
        )
    _job_log(
        effective_channel, job_id,
        f"profile_resolved | render_profile={payload.render_profile} | preset={tuned['video_preset']} crf={tuned['video_crf']} whisper={tuned['whisper_model']} trans={tuned['transition_sec']:.2f}",
    )
    if payload.video_preset:
        _job_log(effective_channel, job_id, f"profile_override_used video_preset={payload.video_preset}", kind="warning")
    if payload.video_crf is not None:
        _job_log(effective_channel, job_id, f"profile_override_used video_crf={payload.video_crf}", kind="warning")
    try:
        normalized_text_layers = _validate_text_layers_or_400(payload)
    except Exception as layer_exc:
        normalized_text_layers = []
        _job_log(effective_channel, job_id, f"Text layer parse warning: {layer_exc}", kind="warning")
        update_job_progress(
            job_id, "starting", 0,
            f"âš ï¸ Text overlays skipped (parse error): {layer_exc}",
        )
    _job_log(
        effective_channel,
        job_id,
        f"Text overlay layers accepted: {len(normalized_text_layers)}",
    )
    for layer_idx, layer in enumerate(normalized_text_layers, start=1):
        _job_log(
            effective_channel,
            job_id,
            f"Text layer {layer_idx}: order={layer.get('order', layer_idx-1)} "
            f"pos={layer.get('position', 'bottom-center')} "
            f"xy={float(layer.get('x_percent', 50) or 50):.1f}%,{float(layer.get('y_percent', 90) or 90):.1f}% "
            f"time={float(layer.get('start_time', 0) or 0):.2f}->{float(layer.get('end_time', 0) or 0):.2f}",
            kind="debug",
        )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.text_layers.accepted",
        level="INFO",
        message=f"Accepted {len(normalized_text_layers)} text layer(s)",
        step="render.text_layers",
        context={"layer_count": len(normalized_text_layers)},
    )
    _emit_render_event(
        channel_code=effective_channel,
        job_id=job_id,
        event="render.start",
        level="INFO",
        message="Render started",
        step="render.start",
        context={
            "resume_mode": bool(resume_mode),
            "profile": payload.render_profile,
            "codec": payload.video_codec,
            "source_mode": payload.source_mode,
            "output_mode": output_mode,
        },
    )
    upsert_job(
        job_id,
        "render",
        effective_channel,
        "running",
        payload.model_dump(),
        {},
        stage=JobStage.STARTING,
        progress_percent=1,
        message="Resuming render job" if resume_mode else "Initializing render job",
    )
    _final_status = ""  # set to terminal status string on success path; empty means failure/cancelled
    edit_session_id = ""  # assigned inside try; pre-init so finally block can reference it safely
    try:
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.start",
            level="INFO",
            message="Preparing source",
            step="render.prepare_source",
            context={"source_mode": payload.source_mode},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.input.validate.start",
            level="INFO",
            message="Validating render input",
            step="render.input.validate",
        )
        _set_stage(JobStage.DOWNLOADING, 5, "Preparing source video")
        edit_session_id = (getattr(payload, "edit_session_id", None) or "").strip()
        sess = load_session_fn(edit_session_id) if edit_session_id else None
        if edit_session_id and not sess:
            raise RuntimeError(
                f"Editor session '{edit_session_id}' not found — "
                "the session may have expired or the server was restarted. "
                "Please re-open the editor to re-prepare the source."
            )
        detected_source_mode = "session" if sess else "local"
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.detect_input",
            level="INFO",
            message=f"Detecting source type: {detected_source_mode}",
            step="render.prepare_source.detect_input",
            context={"source_mode": detected_source_mode},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.validate_input",
            level="INFO",
            message="Validating source input",
            step="render.prepare_source.validate_input",
        )
        if sess:
            source_path = Path(sess["video_path"])
            if not source_path.exists():
                raise RuntimeError(f"Editor session video not found: {source_path}")
            source = {
                "title": sess.get("title", source_path.stem),
                "slug": slugify(sess.get("title", source_path.stem)),
                "duration": sess.get("duration") or _probe_video_duration(source_path),
                "filepath": str(source_path),
            }
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"source_path": str(source_path), "work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting editor-session source strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "editor_session"},
            )
            _job_log(effective_channel, job_id, f"Reusing editor session video: {source_path}")
        else:
            if payload.source_mode and payload.source_mode.lower() not in ("local",):
                raise RuntimeError(
                    f"Unsupported source_mode '{payload.source_mode}'. "
                    "Only local video files are supported."
                )
            source_path = Path(payload.source_video_path or "").expanduser().resolve()
            if not source_path.exists() or not source_path.is_file():
                raise RuntimeError(
                    f"Render stopped: the source video file was not found.\n"
                    f"Path: {source_path}\n"
                    f"Please reopen the editor and verify the file is still accessible."
                )
            source = {
                "title": source_path.stem.replace("_", " ").replace("-", " "),
                "slug": slugify(source_path.stem),
                "duration": _probe_video_duration(source_path),
                "filepath": str(source_path),
            }
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.prepare_paths",
                level="INFO",
                message="Preparing source paths",
                step="render.prepare_source.prepare_paths",
                context={"source_path": str(source_path), "work_dir": str(work_dir)},
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.select_strategy",
                level="INFO",
                message="Selecting local source strategy",
                step="render.prepare_source.select_strategy",
                context={"strategy": "local_source"},
            )
            _job_log(effective_channel, job_id, f"Local source selected: {source_path}")
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.input.validate.success",
            level="INFO",
            message="Render input validated",
            step="render.input.validate",
            context={"source_path": str(source_path)},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.prepare_source.success",
            level="INFO",
            message="Source prepared successfully",
            step="render.prepare_source.success",
            context={"source_mode": detected_source_mode, "source_path": str(source_path)},
        )

        # Compute once; captured by _process_one_part closure and auto_best_export
        _output_stem = _smart_output_stem(_hook_applied_text, source.get("title", ""), job_id)

        # Apply editor edits: trim and/or volume adjustment
        trim_in = float(getattr(payload, "edit_trim_in", 0) or 0)
        trim_out = float(getattr(payload, "edit_trim_out", 0) or 0)
        edit_volume = float(getattr(payload, "edit_volume", 1.0) or 1.0)
        needs_trim = trim_in > 0.5 or (trim_out > 0.5 and trim_out < source["duration"] - 0.5)
        needs_volume = abs(edit_volume - 1.0) > 0.005
        if needs_trim or needs_volume:
            edited_path = work_dir / f"edited_{source_path.stem}.mp4"
            cmd = [get_ffmpeg_bin(), "-y"]
            if trim_in > 0.5:
                cmd += ["-ss", f"{trim_in:.3f}"]
            cmd += ["-i", str(source_path)]
            if needs_trim and trim_out > 0.5 and trim_out < source["duration"] - 0.5:
                duration_t = trim_out - (trim_in if trim_in > 0.5 else 0)
                cmd += ["-t", f"{max(1.0, duration_t):.3f}"]
            if needs_volume:
                cmd += ["-af", f"volume={edit_volume:.3f}", "-c:v", "copy", "-c:a", "aac", "-b:a", "256k"]
            else:
                cmd += ["-c:v", "copy", "-c:a", "copy"]
            cmd += ["-avoid_negative_ts", "make_zero", str(edited_path)]
            _job_log(effective_channel, job_id, f"Applying edits: trim_in={trim_in:.1f}s trim_out={trim_out:.1f}s volume={edit_volume:.2f}")
            try:
                subprocess.run(cmd, check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as _preprocess_exc:
                _pp_stderr = _preprocess_exc.stderr or ""
                _pp_diag = _summarize_ffmpeg_stderr(_pp_stderr)
                _pp_tail = _pp_stderr[-2000:].strip()
                _job_log(
                    effective_channel, job_id,
                    f"FFmpeg preprocess failed exit={_preprocess_exc.returncode} diag={_pp_diag!r}",
                    kind="warning",
                )
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.ffmpeg.preprocess.error",
                    level="ERROR",
                    message=f"FFmpeg preprocess failed: {_pp_diag}",
                    step="render.preprocess",
                    context={
                        "exit_code": _preprocess_exc.returncode,
                        "diagnostic": _pp_diag,
                        "stderr_tail": _pp_tail,
                        "input_path": str(source_path),
                        "output_path": str(edited_path),
                    },
                )
                raise RuntimeError(f"FFmpeg preprocess failed: {_pp_diag}") from _preprocess_exc
            new_dur = _probe_video_duration(edited_path)
            source["duration"] = new_dur or max(1, source["duration"] - trim_in)
            source_path = edited_path
            source["filepath"] = str(edited_path)
            _job_log(effective_channel, job_id, f"Edits applied → {edited_path} | new_duration={source['duration']}s")

        # Pre-render source preflight: catch local files moved/deleted after initial validation
        if detected_source_mode == "local" and not source_path.exists():
            raise RuntimeError(
                f"Render stopped: the source video file was moved or deleted.\n"
                f"Path: {source_path}\n"
                f"Please reopen the editor and confirm the file is still accessible."
            )

        if payload.keep_source_copy:
            ext = source_path.suffix or ".mp4"
            keep_source_dir = output_dir / "source"
            # If output is a typical "video_output/video_out" folder, keep source as sibling under upload/source.
            if output_dir.name.lower() in ("video_output", "video_out"):
                keep_source_dir = output_dir.parent / "source"
            # Only temp-origin files (YouTube downloads, edited locals) need to be
            # persisted into source/. A user's original local file is already permanent —
            # copying it would waste disk space (10 GB+) and slow render startup.
            is_temp_source = str(source_path).startswith(str(TEMP_DIR))
            if is_temp_source:
                keep_path = _reserve_source_path_in_dir(keep_source_dir, source["slug"], ext=ext)
                if not keep_path.exists():
                    # Move instead of copy when source is in temp dir (instant on same drive, saves I/O + disk)
                    try:
                        shutil.move(str(source_path), str(keep_path))
                        _job_log(effective_channel, job_id, f"Source moved (zero-copy) to: {keep_path}")
                    except Exception:
                        shutil.copy2(source_path, keep_path)
                        _job_log(effective_channel, job_id, f"Source copied to: {keep_path}")
                source_path = keep_path
            else:
                # Local original (not temp): render directly from user's file — no copy, no hardlink.
                _job_log(effective_channel, job_id, f"local_source.passthrough path={source_path} (source copy skipped)")

        voice_audio_path = None
        _voice_tts_failed = False
        _voice_mix_ok = []
        _voice_part_tts_attempts = []
        _sub_translate_attempts = []
        _sub_translate_clean = []
        _sub_translate_partial = []
        _sub_translate_failed_parts = []
        _recovery_notes: list[str] = []   # UP24: accumulate fallback events for observability
        if getattr(payload, "voice_enabled", False) and getattr(payload, "voice_source", "manual") == "manual":
            if cancel_registry.is_cancelled(job_id):
                raise cancel_registry.JobCancelledError()
            try:
                update_job_progress(job_id, current_stage, current_progress, "Generating AI voice...")
                _job_log(effective_channel, job_id, "Generating AI narration audio")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_tts_started",
                    level="INFO",
                    message="Generating AI voice",
                    step="voice.tts",
                    context={"language": payload.voice_language, "gender": payload.voice_gender},
                )
                # Infer content type from subtitle_style since manual voice fires before
                # segment scoring. subtitle_style is the best available creator-intent signal.
                _manual_voice_ct = {
                    "viral":   "commentary",
                    "clean":   "tutorial",
                    "story":   "vlog",
                    "gaming":  "montage",
                }.get((payload.subtitle_style or "").strip().lower(), "vlog")
                voice_audio_path = generate_narration_audio(
                    text=str(payload.voice_text or ""),
                    language=payload.voice_language,
                    gender=payload.voice_gender,
                    rate=payload.voice_rate,
                    job_id=job_id,
                    voice_id=getattr(payload, "voice_id", None),
                    content_type=_manual_voice_ct,
                    tts_engine=getattr(payload, "tts_engine", "edge"),
                )
                update_job_progress(job_id, current_stage, current_progress, "AI voice generated")
                _job_log(effective_channel, job_id, f"AI narration audio ready: {voice_audio_path}")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_tts_completed",
                    level="INFO",
                    message="AI voice generated",
                    step="voice.tts",
                    context={"audio_path": str(voice_audio_path), "voice_text_length": len(str(payload.voice_text or ""))},
                )
                voice_audio_path = _maybe_cleanup_narration_audio(
                    str(voice_audio_path),
                    payload,
                    effective_channel=effective_channel,
                    job_id=job_id,
                    source="manual",
                )
            except Exception as voice_exc:
                voice_audio_path = None
                _voice_tts_failed = True
                update_job_progress(job_id, current_stage, current_progress, "AI voice failed - continuing with original audio")
                _job_log(effective_channel, job_id, f"AI voice generation failed: {voice_exc}", kind="error")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="voice_failed",
                    level="ERROR",
                    message=f"AI voice generation failed: {voice_exc}",
                    step="voice.tts",
                    exception=voice_exc,
                    traceback_text=traceback.format_exc(),
                    context={"error_code": "VOICE001"},
                )
                # UP24: recovery — voice is optional, render continues without it
                _recovery_notes.append("AI narration failed — rendered without voice")
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="recovery_success",
                    level="INFO",
                    message="Recovery: AI narration failed, rendering without voice (original audio preserved)",
                    step="voice.tts",
                    context={"recovery_strategy": "skip_voice"},
                )

        # full_srt hoisted here: Phase 45 early transcription may populate it
        # before segment building. Existing subtitle block reads _early_transcription_done
        # and skips Whisper when already done.
        # Phase A-6: scene detection + segment scoring moved to pipeline_pre_render.run_pre_render_scenes().
        _pre = run_pre_render_scenes(
            source_path=source_path,
            source=source,
            work_dir=work_dir,
            payload=payload,
            tuned=tuned,
            job_id=job_id,
            effective_channel=effective_channel,
            retry_count=retry_count,
            cancel_registry=cancel_registry,
            set_stage_fn=_set_stage,
        )
        full_srt = _pre.full_srt
        full_srt_available = _pre.full_srt_available
        _early_transcription_done = _pre.early_transcription_done
        scored = _pre.scored
        total_parts = _pre.total_parts
        _content_analysis = _pre.content_analysis
        _target_platform = _pre.target_platform
        _dna_clean_visual = _pre.dna_clean_visual
        _early_retrieved_knowledge = _pre.early_retrieved_knowledge
        _seg_min_sec = _pre.seg_min_sec
        _seg_max_sec = _pre.seg_max_sec
        # full_srt and full_srt_available initialized before scene detection (Phase 45 hoist).
        # _early_transcription_done=True means Phase 45 already ran Whisper — subtitle block skips.
        existing_parts = {int(x["part_no"]): x for x in list_job_parts(job_id)}
        _job_log(effective_channel, job_id, f"Segment building done: {total_parts} parts")
        # Diagnostic: per-segment selection summary (always at INFO for QA traceability)
        for _qi, _qs in enumerate(scored, start=1):
            logger.info(
                "selected_segment part=%d start=%.3f end=%.3f duration=%.3f "
                "viral=%.1f motion=%.1f hook=%.1f content_type=%s variant=%s",
                _qi, float(_qs.get("start", 0)), float(_qs.get("end", 0)),
                float(_qs.get("duration", 0)),
                float(_qs.get("viral_score", 0)), float(_qs.get("motion_score", 0)),
                float(_qs.get("hook_score", 0)), _qs.get("content_type_hint", ""),
                _qs.get("variant_type", ""),
            )
        # Debug artifact: timeline JSON saved to work_dir when RENDER_DEBUG_LOG=1
        import os as _os
        if _os.getenv("RENDER_DEBUG_LOG", "0") == "1":
            try:
                import json as _json
                _tl_path = work_dir / f"{source['slug']}_timeline.json"
                _tl_data = [
                    {
                        "part": _qi,
                        "start": float(_qs.get("start", 0)),
                        "end": float(_qs.get("end", 0)),
                        "duration": float(_qs.get("duration", 0)),
                        "viral_score": float(_qs.get("viral_score", 0)),
                        "motion_score": float(_qs.get("motion_score", 0)),
                        "hook_score": float(_qs.get("hook_score", 0)),
                        "content_type": _qs.get("content_type_hint", ""),
                        "variant": _qs.get("variant_type", ""),
                        "transition_score": float(_qs.get("transition_score", 0)),
                    }
                    for _qi, _qs in enumerate(scored, start=1)
                ]
                _tl_path.write_text(_json.dumps(_tl_data, indent=2), encoding="utf-8")
                logger.debug("debug_artifact timeline_json=%s", _tl_path)
            except Exception as _tl_exc:
                logger.debug("debug_artifact timeline_json_failed: %s", _tl_exc)

        subtitle_cutoff = payload.subtitle_viral_min_score
        subtitle_top_count = max(1, int(total_parts * max(0.1, min(1.0, float(payload.subtitle_viral_top_ratio)))))
        if scored:
            ranked_scores = sorted([int(s.get("viral_score", 0)) for s in scored], reverse=True)
            subtitle_cutoff = max(subtitle_cutoff, ranked_scores[min(subtitle_top_count - 1, len(ranked_scores) - 1)])
        _job_log(effective_channel, job_id, f"Subtitle viral cutoff={subtitle_cutoff}, top_count={subtitle_top_count}")

        subtitle_enabled_by_idx = {}
        for idx, seg in enumerate(scored, start=1):
            subtitle_enabled_by_idx[idx] = payload.add_subtitle and (
                (not payload.subtitle_only_viral_high) or int(seg.get("viral_score", 0)) >= int(subtitle_cutoff)
            )
        if payload.add_subtitle and not any(subtitle_enabled_by_idx.values()):
            # Safety fallback: avoid "no subtitle at all" when viral gates are too strict.
            for idx in range(1, total_parts + 1):
                subtitle_enabled_by_idx[idx] = True
            _job_log(
                effective_channel,
                job_id,
                "No parts passed subtitle viral filters; fallback enabled subtitles for all parts",
                kind="warning",
            )

        if payload.add_subtitle and any(subtitle_enabled_by_idx.values()):
            _set_stage(JobStage.TRANSCRIBING_FULL, 28, "Transcribing full video once")
            if (
                (payload.resume_from_last and full_srt.exists() and full_srt.stat().st_size > 0)
                or _early_transcription_done
            ):
                if not full_srt_available:
                    full_srt_available = full_srt.exists() and full_srt.stat().st_size > 0
                _srt_source = "early_transcription" if _early_transcription_done else "resume"
                _job_log(effective_channel, job_id,
                         f"subtitle_transcription_skipped source={_srt_source}: reusing existing SRT",
                         kind="debug")
            else:
                source_has_audio = has_audio_stream(str(source_path))
                if not source_has_audio:
                    _job_log(effective_channel, job_id, f"subtitle.audio_missing source={source_path}; subtitles skipped", kind="warning")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="subtitle.audio_missing",
                        level="WARNING",
                        message="Source video has no usable audio stream; subtitles skipped",
                        step="subtitle.transcribe",
                        context={"source_path": str(source_path)},
                    )
                else:
                    _whisper_model = tuned["whisper_model"]
                    _src_name = Path(source_path).name
                    # UP28: check transcription cache before running Whisper
                    _transcribe_engine = getattr(payload, "subtitle_transcription_engine", "default")
                    _transcribe_cache_key = f"{_transcribe_engine}_{int(bool(payload.highlight_per_word))}"
                    _cached_srt = _transcription_cache_get(str(source_path), _whisper_model, _transcribe_cache_key)
                    if _cached_srt is not None:
                        shutil.copy2(str(_cached_srt), str(full_srt))
                        full_srt_available = bool(full_srt.exists() and full_srt.stat().st_size > 0)
                        _job_log(effective_channel, job_id, f"cache_hit type=transcription model={_whisper_model} srt_exists={full_srt_available}")
                        _emit_render_event(
                            channel_code=effective_channel, job_id=job_id,
                            event="cache_hit", level="INFO",
                            message=f"Transcription cache hit: model={_whisper_model}",
                            step="subtitle.transcribe",
                            context={"type": "transcription", "whisper_model": _whisper_model, "srt_exists": full_srt_available},
                        )
                    else:
                        _t_transcribe = time.perf_counter()
                        _hb_stop = threading.Event()

                        def _hb_thread_fn(_stop=_hb_stop, _m=_whisper_model, _s=_src_name):
                            _pct = 29
                            while not _stop.wait(12):
                                _elapsed = round(time.perf_counter() - _t_transcribe)
                                update_job_progress(job_id, JobStage.TRANSCRIBING_FULL, _pct, f"Still transcribing… ({_elapsed}s)")
                                _job_log(effective_channel, job_id, f"subtitle_transcription_progress elapsed_sec={_elapsed} model={_m} source={_s}")
                                _emit_render_event(
                                    channel_code=effective_channel, job_id=job_id,
                                    event="subtitle_transcription_progress",
                                    level="INFO",
                                    message=f"Still transcribing… elapsed={_elapsed}s",
                                    step="subtitle.transcribe",
                                    context={"elapsed_sec": _elapsed, "whisper_model": _m, "source": _s},
                                )
                                _pct = _pct + 1 if _pct < 34 else (33 if _pct == 34 else 34)

                        _job_log(effective_channel, job_id, f"subtitle_transcription_started model={_whisper_model} source={_src_name}")
                        _emit_render_event(
                            channel_code=effective_channel, job_id=job_id,
                            event="subtitle_transcription_started",
                            level="INFO",
                            message=f"Transcription started: model={_whisper_model}",
                            step="subtitle.transcribe",
                            context={"whisper_model": _whisper_model, "source": _src_name},
                        )
                        _hb = threading.Thread(target=_hb_thread_fn, daemon=True, name=f"transcribe_hb_{job_id[:8]}")
                        _hb.start()
                        if cancel_registry.is_cancelled(job_id):
                            raise cancel_registry.JobCancelledError()
                        try:
                            _transcription_result = transcribe_with_adapter(
                                str(source_path),
                                str(full_srt),
                                engine=_transcribe_engine,
                                model_name=_whisper_model,
                                retry_count=retry_count,
                                highlight_per_word=payload.highlight_per_word,
                                logger=logger,
                            )
                            if _transcription_result.warnings:
                                _job_log(
                                    effective_channel,
                                    job_id,
                                    "subtitle_transcription_adapter_warning "
                                    f"requested={_transcribe_engine} "
                                    f"used={_transcription_result.engine} "
                                    f"warnings={','.join(_transcription_result.warnings)}",
                                    kind="warning",
                                )
                            full_srt_available = bool(full_srt.exists() and full_srt.stat().st_size > 0)
                            _transcribe_ms = int((time.perf_counter() - _t_transcribe) * 1000)
                            _srt_size = full_srt.stat().st_size if full_srt_available else 0
                            _job_log(effective_channel, job_id, f"subtitle_transcription_completed model={_whisper_model} elapsed_ms={_transcribe_ms} srt_exists={full_srt_available} size_bytes={_srt_size}")
                            _emit_render_event(
                                channel_code=effective_channel, job_id=job_id,
                                event="subtitle_transcription_completed",
                                level="INFO",
                                message=f"Transcription complete: model={_whisper_model} elapsed={_transcribe_ms}ms",
                                step="subtitle.transcribe",
                                context={"whisper_model": _whisper_model, "elapsed_ms": _transcribe_ms, "srt_path": str(full_srt), "file_exists": full_srt_available, "size_bytes": _srt_size},
                            )
                            _transcription_cache_put(str(source_path), _whisper_model, _transcribe_cache_key, full_srt)
                        except Exception as transcribe_exc:
                            full_srt_available = False
                            _safe_unlink(full_srt)
                            _transcribe_ms = int((time.perf_counter() - _t_transcribe) * 1000)
                            _job_log(effective_channel, job_id, f"subtitle_transcription_failed source={source_path} model={_whisper_model} elapsed_ms={_transcribe_ms}: {transcribe_exc}", kind="warning")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="subtitle_transcription_failed",
                                level="WARNING",
                                message=f"Subtitle transcription failed: {transcribe_exc}",
                                step="subtitle.transcribe",
                                context={"source_path": str(source_path), "whisper_model": _whisper_model, "elapsed_ms": _transcribe_ms},
                                exception=transcribe_exc,
                            )
                            # UP24: recovery — subtitles optional, render continues without them
                            _recovery_notes.append("Subtitle transcription failed — rendered without subtitles")
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="recovery_success",
                                level="INFO",
                                message="Recovery: subtitle transcription failed, rendering without subtitles",
                                step="subtitle.transcribe",
                                context={"recovery_strategy": "skip_subtitles"},
                            )
                        finally:
                            _hb_stop.set()
                            _hb.join(timeout=2)

        # ── S4.1: Transcript-aware boundary refinement (S4_CANDIDATE_INTELLIGENCE_ENABLED=1) ──
        # Runs after transcription so it works on the first render (no cold-cache requirement).
        # Nudges already-selected segment start/end to align with sentence boundaries (Â±15% max).
        _s4_before = None  # pre-S4.1 boundaries; forwarded to S4.5 for combined-nudge cap
        if os.getenv("S4_CANDIDATE_INTELLIGENCE_ENABLED") == "1" and full_srt_available and scored:
            try:
                _s4_blocks = parse_srt_blocks(str(full_srt))
                if _s4_blocks:
                    _s4_before = [(s.get("start"), s.get("end")) for s in scored]
                    scored = refine_segment_boundaries(
                        scored, _s4_blocks,
                        float(_seg_min_sec), float(_seg_max_sec),
                    )
                    _s4_adjusted = sum(
                        1 for i, s in enumerate(scored)
                        if s.get("candidate_adjustment_reason") and (s.get("start"), s.get("end")) != _s4_before[i]
                    )
                    _job_log(effective_channel, job_id,
                             f"s4_boundary_refinement segments={len(scored)} adjusted={_s4_adjusted}")
            except Exception as _s4_exc:
                logger.debug("s4_boundary_refinement_failed job_id=%s: %s", job_id, _s4_exc)

        # ── S4.2: Real Retention Proxy (S4_RETENTION_PROXY_ENABLED=1) ──
        # Applies a bounded Â±15 adjustment to viral_score using multi-signal
        # retention estimation. Works on first render (uses freshly-generated
        # SRT when available; tier-1 signals fire even without transcript).
        if os.getenv("S4_RETENTION_PROXY_ENABLED") == "1" and scored:
            try:
                _s42_blocks = parse_srt_blocks(str(full_srt)) if full_srt_available else None
                scored = apply_retention_proxy(scored, _s42_blocks)
                _s42_adj = sum(1 for s in scored if s.get("retention_adjustment_reason"))
                _job_log(effective_channel, job_id,
                         f"s4_retention_proxy segments={len(scored)} adjusted={_s42_adj}")
            except Exception as _s42_exc:
                logger.debug("s4_retention_proxy_failed job_id=%s: %s", job_id, _s42_exc)

        # ── S4.5: Speaker-aware cuts (S4_SPEAKER_AWARE_CUTS_ENABLED=1) ──
        # Snaps boundaries to nearby pause midpoints and utterance endpoints.
        # End boundary gets full nudge window (primary); start gets half
        # (detect_silence_trim_offset already handles opening cleanup).
        if os.getenv("S4_SPEAKER_AWARE_CUTS_ENABLED") == "1" and scored:
            try:
                _s45_blocks = parse_srt_blocks(str(full_srt)) if full_srt_available else None
                if _s45_blocks:
                    scored = refine_cuts_for_naturalness(
                        scored, _s45_blocks,
                        float(_seg_min_sec), float(_seg_max_sec),
                        original_segments=[{"start": s, "end": e} for s, e in _s4_before] if _s4_before else None,
                    )
                    _s45_adj = sum(1 for s in scored if s.get("cut_adjustment_reason"))
                    _job_log(effective_channel, job_id,
                             f"s4_natural_cuts segments={len(scored)} adjusted={_s45_adj}")
            except Exception as _s45_exc:
                logger.debug("s4_natural_cuts_failed job_id=%s: %s", job_id, _s45_exc)

        # ── AI Director Phase 1 — safe edit plan (observation only, no override) ──
        _ai_edit_plan = None
        if getattr(payload, "ai_director_enabled", False):
            try:
                from app.ai.director.ai_director import create_ai_edit_plan as _create_ai_plan
                from app.ai.knowledge.knowledge_store_builder import get_pack_knowledge_store as _get_pack_store

                # ── Phase 5.2: Build knowledge filters from payload ────────────────
                _knowledge_filters: dict = {}
                try:
                    _knowledge_filters = {
                        "platform": getattr(payload, "render_profile", None) or None,
                        "niche": None,
                        "style": None,
                        "duration": source.get("duration", None),
                        "aspect_ratio": getattr(payload, "aspect_ratio", None) or None,
                        "subtitle_style": getattr(payload, "subtitle_style", None) or None,
                        "target_goal": None,
                    }
                    # Remove None-valued keys for clarity (query handles None)
                    _knowledge_filters = {k: v for k, v in _knowledge_filters.items() if v is not None}
                except Exception as _kf_err:
                    logger.debug("knowledge_filter_build_failed job_id=%s: %s", job_id, _kf_err)
                    _knowledge_filters = {}

                # ── Phase 5.2: AI Trace Logger ────────────────────────────────────
                _ai_tracer = None
                try:
                    from app.ai.tracing import AITraceLogger
                    _ai_tracer = AITraceLogger(job_id)
                    _ai_tracer.log_input_filters(_knowledge_filters)
                except Exception as _tracer_err:
                    logger.debug("ai_tracer_init_failed job_id=%s: %s", job_id, _tracer_err)

                # ── Phase 5.2: Retrieve knowledge items ───────────────────────────
                # Phase 5.4: Reuse early retrieval results if available (avoids
                # double FAISS query). _early_retrieved_knowledge is set by the
                # Phase 5.4 early pacing block above before segment building.
                _retrieved_knowledge: list = []
                if _early_retrieved_knowledge:
                    # Reuse results from Phase 5.4 early retrieval — no second query needed
                    _retrieved_knowledge = _early_retrieved_knowledge
                    logger.debug(
                        "phase54_knowledge_reused job_id=%s count=%d (skipping second query)",
                        job_id, len(_retrieved_knowledge),
                    )
                    if _ai_tracer is not None:
                        try:
                            _ai_tracer.log_knowledge_retrieved(_retrieved_knowledge)
                        except Exception:
                            pass
                else:
                    try:
                        from app.ai.rag.knowledge_warmup import get_knowledge_index
                        _kidx = get_knowledge_index()
                        if _kidx.is_ready():
                            _retrieved_knowledge = _kidx.query(_knowledge_filters, top_k=10)
                            logger.info(
                                "knowledge_retrieved job_id=%s filters=%s count=%d",
                                job_id, list(_knowledge_filters.keys()), len(_retrieved_knowledge),
                            )
                            if _ai_tracer is not None:
                                _ai_tracer.log_knowledge_retrieved(_retrieved_knowledge)
                        else:
                            logger.debug("knowledge_index_not_ready job_id=%s", job_id)
                            if _ai_tracer is not None:
                                _ai_tracer.log_fallback("no_index", "knowledge index not ready at render time")
                    except Exception as _kr_err:
                        logger.warning("knowledge_retrieval_failed job_id=%s: %s", job_id, _kr_err)
                        _retrieved_knowledge = []
                        if _ai_tracer is not None:
                            try:
                                _ai_tracer.log_fallback("ai_exception", str(_kr_err))
                            except Exception:
                                pass

                if not _retrieved_knowledge:
                    if _ai_tracer is not None:
                        try:
                            _ai_tracer.log_fallback("no_matching_rules", "no knowledge items matched filters")
                        except Exception:
                            pass

                _ai_context = {
                    "job_id": job_id,
                    "srt_path": str(full_srt) if full_srt_available else None,
                    "scenes": scenes,
                    "duration": source.get("duration", 0.0),
                    "market": getattr(payload, "ai_target_market", None) or getattr(payload, "viral_market", None),
                    # Phase 4: source path for optional beat analysis
                    "source_path": str(source_path) if source_path else None,
                    # Phase 5.2: retrieved knowledge items and filters
                    "retrieved_knowledge": _retrieved_knowledge,
                    "knowledge_filters": _knowledge_filters,
                    # Phase 53A: pack-based semantic knowledge store (LocalKnowledgeStore singleton)
                    "knowledge_store": _get_pack_store(),
                    # Phase 46: pre-computed content analysis (ContentAnalysisResult | None)
                    "content_analysis": _content_analysis,
                }
                _ai_edit_plan = _create_ai_plan(payload, _ai_context)
                if _ai_edit_plan is not None:
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="ai_director_plan_created",
                        level="INFO",
                        message=(
                            f"AI Director plan: mode={_ai_edit_plan.mode} "
                            f"segments={len(_ai_edit_plan.selected_segments)} "
                            f"fallback={_ai_edit_plan.fallback_used}"
                        ),
                        step="ai_director",
                        context=_ai_edit_plan.to_dict(),
                    )
                    # Phase 5.2: trace render plan summary
                    if _ai_tracer is not None:
                        try:
                            _ai_tracer.log_render_plan_summary({
                                "mode": _ai_edit_plan.mode,
                                "segments": len(_ai_edit_plan.selected_segments),
                                "fallback_used": _ai_edit_plan.fallback_used,
                                "knowledge_items_used": len(_retrieved_knowledge),
                                "warnings": list(_ai_edit_plan.warnings),
                            })
                        except Exception:
                            pass
            except Exception as _ai_err:
                _job_log(
                    effective_channel, job_id,
                    f"ai_director_failed_fallback: {_ai_err}",
                    kind="warning",
                )

        # ── Phase 43: Creator feedback learning pack (advisory metadata only) ──
        run_phase_43_feedback_learning(_ai_edit_plan, payload, job_id, effective_channel)

        # ── Phase 44: AI content-driven segment selection ──────────────────────
        scored = run_phase_44_content_selection(
            _ai_edit_plan, scored, payload, effective_channel, job_id
        )

        # ── Phase 5.3: Apply execution hints from AI plan (advisory, safe, bounded) ──
        # Reads execution_hints from plan.knowledge_injection (set by ai_director).
        # If ai_director_enabled=False, _ai_edit_plan is None → this block is skipped.
        # If hints are invalid or absent → behavior unchanged, advisory log only.
        # NEVER crashes render. NEVER modifies FFmpeg commands or filter graphs.
        _exec_hints: dict = {}
        _phase53_tracer = _ai_tracer if getattr(payload, "ai_director_enabled", False) else None
        if _ai_edit_plan is not None:
            try:
                _exec_hints = (
                    _ai_edit_plan.knowledge_injection.get("execution_hints") or {}
                ) if isinstance(_ai_edit_plan.knowledge_injection, dict) else {}
            except Exception:
                _exec_hints = {}

            if _exec_hints and _phase53_tracer is not None:
                try:
                    _phase53_tracer.log_execution_hints(
                        _exec_hints,
                        _exec_hints.get("source_knowledge_ids") or [],
                    )
                except Exception:
                    pass

            # Log validation fixups if any
            if _ai_edit_plan is not None and _phase53_tracer is not None:
                try:
                    _fixups_53 = (
                        _ai_edit_plan.knowledge_injection.get("validation_fixups") or []
                    ) if isinstance(_ai_edit_plan.knowledge_injection, dict) else []
                    if _fixups_53:
                        _phase53_tracer.log_validation_fixup(_fixups_53)
                except Exception:
                    pass

            # A. Pacing hint — Phase 5.4: pacing hints are now APPLIED before
            #    segment building via _seg_min_sec/_seg_max_sec (see early pacing
            #    block above). Here we only log for observability — no further action.
            _pacing_cut_min = _exec_hints.get("cut_interval_min")
            _pacing_cut_max = _exec_hints.get("cut_interval_max")
            if _pacing_cut_min is not None or _pacing_cut_max is not None:
                logger.debug(
                    "phase53_pacing_hint_observed job_id=%s cut_min=%s cut_max=%s "
                    "(Phase 5.4: pacing applied before segment building via _seg_min_sec/_seg_max_sec)",
                    job_id, _pacing_cut_min, _pacing_cut_max,
                )

            # B. Subtitle emphasis hint — if a style is suggested, note it.
            #    The actual emphasis style is resolved per-part from payload.subtitle_style
            #    and DNA/platform bias. The hint is advisory and cannot override the
            #    per-part resolution without rewriting that logic (out of scope).
            _sub_emph_hint = _exec_hints.get("subtitle_emphasis_style")
            if _sub_emph_hint is not None:
                logger.info(
                    "phase53_subtitle_emphasis_hint_advisory job_id=%s style=%r "
                    "(advisory only — per-part subtitle style resolved from payload)",
                    job_id, _sub_emph_hint,
                )
                if _phase53_tracer is not None:
                    try:
                        _phase53_tracer.log_decision_rejected(
                            "subtitle_emphasis_hint_advisory_only",
                            detail={
                                "hint": "subtitle_emphasis_style",
                                "value": _sub_emph_hint,
                                "reason": (
                                    "subtitle style is resolved per-part from payload.subtitle_style "
                                    "and DNA/platform bias; hint is advisory"
                                ),
                            },
                        )
                    except Exception:
                        pass

            # C. Hook overlay hint — if explicitly disabled, gate the hook overlay.
            #    This is the one hint that IS applied: hook_overlay_enabled=False → skip overlay.
            #    hook_overlay_enabled=True or None → keep existing behavior (unchanged).
            _hook_enabled_hint = _exec_hints.get("hook_overlay_enabled")
            if _hook_enabled_hint is False:
                # AI says: skip hook overlay for this render job
                if _hook_overlay_enabled:
                    _hook_overlay_enabled = False
                    logger.info(
                        "phase53_hook_overlay_disabled_by_ai job_id=%s "
                        "(knowledge hint hook_overlay_enabled=False overrides payload=True)",
                        job_id,
                    )
                    if _phase53_tracer is not None:
                        try:
                            _phase53_tracer.log_execution_hints(
                                {"hook_overlay_enabled": False, "applied": True},
                                _exec_hints.get("source_knowledge_ids") or [],
                            )
                        except Exception:
                            pass

        # ── Phase 5.5: Build AI subtitle emphasis config ─────────────────────────
        # Runs only when ai_director_enabled=True and _ai_edit_plan is not None.
        # Config is built once per job; applied per-part in the subtitle loop below.
        # NEVER mutates payload. NEVER changes _effective_subtitle_style (preset ID).
        # NEVER alters SRT timestamps. NEVER touches FFmpeg commands.
        # If AI disabled or no hints → _ai_subtitle_emphasis_config.applied=False → no change.
        _ai_subtitle_emphasis_config = None
        if getattr(payload, "ai_director_enabled", False) and _ai_edit_plan is not None:
            try:
                from app.ai.subtitle_hints import build_ai_subtitle_emphasis_config as _build_sub_emph
                _ai_subtitle_emphasis_config = _build_sub_emph(_exec_hints, payload)
                if _phase53_tracer is not None:
                    try:
                        _emph_reason = (
                            "valid_ai_subtitle_hint" if _ai_subtitle_emphasis_config.applied
                            else str(_ai_subtitle_emphasis_config.rejected_reason or "no_subtitle_emphasis_hint")
                        )
                        _phase53_tracer.log_subtitle_emphasis_applied(
                            {**_ai_subtitle_emphasis_config.to_dict(), "reason": _emph_reason}
                        )
                    except Exception:
                        pass
                if not _ai_subtitle_emphasis_config.applied and _phase53_tracer is not None:
                    try:
                        _phase53_tracer.log_decision_rejected(
                            str(_ai_subtitle_emphasis_config.rejected_reason or "no_subtitle_emphasis_hint"),
                            detail={
                                "hint": "subtitle_emphasis_style",
                                "value": _ai_subtitle_emphasis_config.emphasis_style,
                                "phase": "5.5",
                            },
                        )
                    except Exception:
                        pass
                logger.debug(
                    "phase55_subtitle_emphasis_config job_id=%s applied=%s style=%s reason=%s",
                    job_id,
                    _ai_subtitle_emphasis_config.applied,
                    _ai_subtitle_emphasis_config.emphasis_style,
                    _ai_subtitle_emphasis_config.rejected_reason,
                )
            except Exception as _sub55_err:
                logger.warning(
                    "phase55_subtitle_emphasis_config_failed job_id=%s: %s", job_id, _sub55_err
                )
                _ai_subtitle_emphasis_config = None

        # ── Phase 5.7: Build AI visual intensity config ───────────────────────────
        # Runs only when ai_director_enabled=True and _ai_edit_plan is not None.
        # Config is built once per job; logged immediately.
        # Phase 5.7: Safe injection point found — visual_intensity_hint parameter
        #   added to render_part(), render_part_smart(), render_base_clip().
        #   All three accept visual_intensity_hint with default None (backward compat).
        #   Renderer OWNS the mapping from hint to known effect presets.
        #   AI passes only "low"/"medium"/"high" — never a preset name or filter string.
        # Result when applied=True: render_overrides={"visual_intensity_hint": <value>}
        # render_pipeline extracts this value and passes it to renderer calls below.
        # NEVER mutates payload. NEVER changes payload.effect_preset. NEVER touches FFmpeg.
        # If AI disabled or no hints → _ai_visual_intensity_config.applied=False → hint=None.
        _ai_visual_intensity_config = None
        if getattr(payload, "ai_director_enabled", False) and _ai_edit_plan is not None:
            try:
                from app.ai.visual_hints import build_ai_visual_intensity_config as _build_vis_int
                _ai_visual_intensity_config = _build_vis_int(_exec_hints, payload)
                _vis_reason = (
                    str(_ai_visual_intensity_config.rejected_reason)
                    if _ai_visual_intensity_config.rejected_reason
                    else "applied"
                )
                if _phase53_tracer is not None:
                    try:
                        _phase53_tracer.log_visual_intensity_applied(
                            {**_ai_visual_intensity_config.to_dict(), "reason": _vis_reason}
                        )
                    except Exception:
                        pass
                # Log decision_rejected only when NOT applied
                if not _ai_visual_intensity_config.applied and _phase53_tracer is not None:
                    try:
                        _phase53_tracer.log_decision_rejected(
                            _vis_reason,
                            detail={
                                "hint": "visual_intensity",
                                "value": _ai_visual_intensity_config.visual_intensity,
                                "phase": "5.7",
                            },
                        )
                    except Exception:
                        pass
                logger.debug(
                    "phase57_visual_intensity_config job_id=%s applied=%s intensity=%s reason=%s",
                    job_id,
                    _ai_visual_intensity_config.applied,
                    _ai_visual_intensity_config.visual_intensity,
                    _ai_visual_intensity_config.rejected_reason,
                )
                # Phase 5.7: Extract hint from render_overrides when applied=True.
                # _vis_intensity_hint is used below in per-part renderer calls.
                # When applied=False: hint is None → renderer uses effect_preset unchanged.
            except Exception as _vis57_err:
                logger.warning(
                    "phase57_visual_intensity_config_failed job_id=%s: %s", job_id, _vis57_err
                )
                _ai_visual_intensity_config = None
        elif not getattr(payload, "ai_director_enabled", False):
            # AI disabled: skip entirely, log as advisory
            if _phase53_tracer is not None:
                try:
                    _phase53_tracer.log_decision_rejected(
                        "ai_disabled",
                        detail={"hint": "visual_intensity", "phase": "5.7"},
                    )
                except Exception:
                    pass

        # ── Phase 5.7: Extract visual_intensity_hint for per-part renderer calls ──
        # When _ai_visual_intensity_config.applied=True, render_overrides contains
        # {"visual_intensity_hint": <value>}. Extract it for use in renderer calls.
        # When applied=False (disabled, invalid, user override): hint=None.
        # This local variable is read-only — payload.effect_preset is NEVER mutated.
        _vis_intensity_hint: "str | None" = None
        if (
            _ai_visual_intensity_config is not None
            and _ai_visual_intensity_config.applied
        ):
            try:
                _vis_intensity_hint = (
                    _ai_visual_intensity_config.render_overrides.get("visual_intensity_hint")
                )
            except Exception:
                _vis_intensity_hint = None

        # ── AI Execution Mode Resolution (Phase 60D) — control only ─────────────
        # Resolve BEFORE Phase 59 blocks so they can be gated correctly.
        _ai_exec_mode: str = run_phase_60d_execution_mode(_ai_edit_plan, payload, job_id)
        run_phase_60d_mode_off_rollback(_ai_edit_plan, _ai_exec_mode, job_id)

        # ── AI Render Influence (Phase 10) — bounded opt-in payload adjustments ──
        _ai_influence_report: dict = {"enabled": False}
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.director.render_influence import apply_ai_render_influence as _apply_ai_influence
                payload, _ai_influence_report = _apply_ai_influence(
                    payload,
                    _ai_edit_plan,
                    context={"job_id": job_id},
                )
                logger.info(
                    "ai_render_influence_applied job_id=%s applied=%d skipped=%d",
                    job_id,
                    len(_ai_influence_report.get("applied", [])),
                    len(_ai_influence_report.get("skipped", [])),
                )
            except Exception as _inf_err:
                _ai_influence_report = {
                    "enabled": True,
                    "applied": [],
                    "skipped": [],
                    "warnings": [f"influence_module_error:{type(_inf_err).__name__}"],
                }
                logger.warning("ai_render_influence_module_failed job_id=%s: %s", job_id, _inf_err)
        elif _ai_edit_plan is not None:
            logger.debug("ai_render_influence_skipped job_id=%s (disabled)", job_id)

        # ── AI Beat Execution (Phase 11) — metadata-only beat plan ───────────
        # → moved to app.orchestration.pipeline_ai_phases (Phase A-2)
        _ai_beat_report: dict = run_phase_11_beat_execution(_ai_edit_plan, payload, job_id)

        # Save original scored order before Phase 59C (used by Phase 59D segment gate)
        _scored_original: list = list(scored)

        # ── AI Segment Selection Promotion (Phase 59C) ───────────────────────
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.segment_promotion.segment_promotion_engine import (
                    promote_segment_selection as _promote_segments,
                )
                scored, _seg_promo = _promote_segments(
                    scored, _ai_edit_plan, payload, context={"job_id": job_id}
                )
                _promo = _seg_promo.get("segment_selection_promotion") or {}
                try:
                    _ai_edit_plan.segment_selection_promotion = _promo
                except Exception:
                    pass
                if _promo.get("applied"):
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="ai_segment_promotion_applied",
                        level="INFO",
                        message=(
                            f"AI segment promotion: {_promo.get('selected_count', 0)}"
                            f"/{_promo.get('total_count', 0)} segments reordered"
                        ),
                        step="ai_segment_promotion",
                        context=_promo,
                    )
                    logger.info(
                        "ai_segment_promotion_applied job_id=%s selected=%d total=%d conf=%.3f",
                        job_id,
                        _promo.get("selected_count", 0),
                        _promo.get("total_count", 0),
                        _promo.get("confidence", 0.0),
                    )
                else:
                    logger.debug(
                        "ai_segment_promotion_skipped job_id=%s reason=%s",
                        job_id,
                        _promo.get("reason", "not_eligible"),
                    )
            except Exception as _seg_err:
                logger.warning(
                    "ai_segment_promotion_failed job_id=%s: %s", job_id, _seg_err
                )

        # ── AI Quality Gate — Segment (Phase 59D) ────────────────────────────
        if _ai_edit_plan is not None and getattr(payload, "ai_render_influence_enabled", False) \
                and _ai_exec_mode != "off":
            try:
                from app.ai.quality_gate.quality_gate_engine import (
                    apply_segment_quality_gate as _segment_quality_gate,
                )
                scored, _seg_gate = _segment_quality_gate(
                    scored, _scored_original, _ai_edit_plan, context={"job_id": job_id}
                )
                _sg = _seg_gate.get("segment_quality_gate") or {}
                try:
                    existing_qg = getattr(_ai_edit_plan, "quality_gated_influence", {}) or {}
                    existing_qg["segment"] = _sg
                    _ai_edit_plan.quality_gated_influence = existing_qg
                except Exception:
                    pass
                if _sg.get("applied"):
                    logger.info(
                        "ai_segment_quality_gate_applied job_id=%s action=%s reverted=%s",
                        job_id,
                        _sg.get("gate_action"),
                        _sg.get("reverted"),
                    )
                else:
                    logger.debug(
                        "ai_segment_quality_gate_no_change job_id=%s action=%s",
                        job_id,
                        _sg.get("gate_action", "no_change"),
                    )
            except Exception as _qg_err:
                logger.warning(
                    "ai_segment_quality_gate_failed job_id=%s: %s", job_id, _qg_err
                )

        # ── AI advisory phases 60A–62D → moved to pipeline_ai_phases (Phase A-2) ──
        run_phase_60a_execution_metrics(_ai_edit_plan, payload, job_id)
        run_phase_60b_ab_evaluation(_ai_edit_plan, job_id)
        run_phase_60c_creator_benchmark(_ai_edit_plan, job_id)
        run_phase_61a_archetype_strategy(_ai_edit_plan, job_id)
        run_phase_61d_creator_render_strategy(_ai_edit_plan, job_id)
        run_phase_62a_outcome_tracking(_ai_edit_plan, job_id)
        run_phase_62b_preference_reinforcement(_ai_edit_plan, job_id)
        run_phase_62c_success_patterns(_ai_edit_plan, job_id)
        run_phase_62d_learning_calibration(_ai_edit_plan, job_id)

        for idx, seg in enumerate(scored, start=1):
            existing = existing_parts.get(idx, {})
            existing_status = (existing.get("status") or "").lower()
            if existing_status == "done" and payload.resume_from_last:
                continue
            upsert_job_part(
                job_id=job_id,
                part_no=idx,
                part_name=f"part_{idx:03d}",
                status=JobPartStage.QUEUED,
                progress_percent=0,
                start_sec=seg["start"],
                end_sec=seg["end"],
                duration=seg["duration"],
                viral_score=seg.get("viral_score", 0),
                motion_score=seg.get("motion_score", 0),
                hook_score=seg.get("hook_score", 0),
            )

        # UP28.1: source stat for motion path cache key — computed once, shared across all parts
        try:
            _src_stat_for_motion = source_path.stat()
        except Exception:
            _src_stat_for_motion = None

        cpu_total = os.cpu_count() or 2
        gpu_ready = nvenc_available()

        # Distinguish which options add TRUE CPU parallelism cost outside the ffmpeg vf chain.
        # - add_subtitle / text_layers: run INSIDE ffmpeg's filter pipeline; they slow each
        #   job but do not prevent N jobs from running in parallel (no extra process spawned).
        # - motion_aware_crop: runs OpenCV optical-flow as a blocking CPU pre-pass BEFORE
        #   ffmpeg; this competes directly with parallel workers on CPU.
        # - reup_mode: BGM audio subprocess; moderate overhead on CPU.
        if gpu_ready:
            # GPU handles encode; CPU cost per worker is low.
            # Only penalise the pre-pass operations that stay on CPU.
            cpu_extra = sum([
                bool(payload.motion_aware_crop),
                bool(payload.reup_mode),
            ])
            heavy_penalty = min(cpu_extra, 2)
            base = max(2, cpu_total // 3)
            hard_ceiling = 6
        else:
            # CPU-only: libx264/libx265 uses -threads 0 (all cores per worker).
            # Count all heavy opts but cap penalty at 2 (not 3) so higher core counts
            # can still unlock a second parallel worker.
            all_heavy = sum([
                bool(payload.motion_aware_crop),
                bool(payload.add_subtitle),
                bool(payload.reup_mode),
                bool(payload.text_layers),
            ])
            heavy_penalty = min(all_heavy, 2)
            base = max(1, cpu_total // 4)
            hard_ceiling = 4

        hw_cap = max(1, min(base - heavy_penalty, hard_ceiling))

        # max_parallel_parts == 0 means "adaptive / let backend decide"
        # max_parallel_parts >= 1 means user ceiling — honour it but never exceed hw_cap
        user_req = int(payload.max_parallel_parts or 0)
        if user_req >= 1:
            max_workers = max(1, min(user_req, hw_cap))
        else:
            max_workers = hw_cap

        from app.services.render_engine import _resolve_codec
        _effective_codec = _resolve_codec(payload.video_codec, encoder_mode=payload.encoder_mode)
        _job_log(
            effective_channel, job_id,
            f"Using max_workers={max_workers} "
            f"(cpu={cpu_total}, gpu={gpu_ready}, heavy_penalty={heavy_penalty}, "
            f"base={base}, hw_cap={hw_cap}, user_req={user_req}) | "
            f"codec={_effective_codec} preset={tuned['video_preset']} crf={tuned['video_crf']}",
        )
        _part_ctx = PartRenderContext(
            job_id=job_id,
            effective_channel=effective_channel,
            total_parts=total_parts,
            retry_count=retry_count,
            work_dir=work_dir,
            output_dir=output_dir,
            source_path=source_path,
            source=source,
            output_stem=_output_stem,
            payload=payload,
            existing_parts=existing_parts,
            ai_edit_plan=_ai_edit_plan,
            vis_intensity_hint=_vis_intensity_hint,
            target_platform=_target_platform,
            tuned=tuned,
            ffmpeg_threads=1,
            cancel_registry=cancel_registry,
            src_stat_for_motion=_src_stat_for_motion,
            full_srt=full_srt,
            full_srt_available=full_srt_available,
            subtitle_enabled_by_idx=subtitle_enabled_by_idx,
            subtitle_cutoff=subtitle_cutoff,
            voice_audio_path=voice_audio_path,
            mv_market=_mv_market,
            mv_cfg=_mv_cfg,
            hook_apply_enabled=_hook_apply_enabled,
            hook_applied_text=_hook_applied_text,
            hook_score=_hook_score,
            hook_overlay_enabled=_hook_overlay_enabled,
            dna_clean_visual=_dna_clean_visual,
            ai_subtitle_emphasis_config=_ai_subtitle_emphasis_config,
            normalized_text_layers=normalized_text_layers,
            voice_part_tts_attempts=_voice_part_tts_attempts,
            voice_mix_ok=_voice_mix_ok,
            sub_translate_attempts=_sub_translate_attempts,
            sub_translate_partial=_sub_translate_partial,
            sub_translate_clean=_sub_translate_clean,
            sub_translate_failed_parts=_sub_translate_failed_parts,
            recovery_notes=_recovery_notes,
        )
        # Phase A-7: render loop moved to pipeline_render_loop.run_render_loop().
        # part_ctx.ffmpeg_threads is finalized inside run_render_loop after contention throttle.
        _loop_result = run_render_loop(
            part_ctx=_part_ctx,
            scored=scored,
            source=source,
            total_parts=total_parts,
            max_workers=max_workers,
            normalized_text_layers=normalized_text_layers,
            effective_channel=effective_channel,
            job_id=job_id,
            set_stage_fn=_set_stage,
            job_semaphore=JOB_SEMAPHORE,
            render_active_lock=_render_active_lock,
            render_active_count=_render_active_count,
        )
        outputs = _loop_result.outputs
        rows = _loop_result.rows
        failed_parts = _loop_result.failed_parts

        if failed_parts and not outputs:
            raise RuntimeError(f"All parts failed ({len(failed_parts)}/{total_parts})")
        if failed_parts:
            _job_log(effective_channel, job_id, f"Partial success: {len(outputs)} done, {len(failed_parts)} failed")

        rows.sort(key=lambda x: int(x[3]))
        outputs = sorted(outputs)
        _set_stage(JobStage.WRITING_REPORT, 95, "Writing render report")
        report_path = output_dir / "render_report.xlsx"
        append_rows(report_path, ["job_id", "channel_code", "video_title", "part_no", "start", "end", "duration", "viral_score", "priority_rank", "output_file"], rows)
        _job_log(effective_channel, job_id, f"Report written: {report_path}")
        if not getattr(payload, "voice_enabled", False):
            _voice_summary = "not used"
        elif _voice_tts_failed:
            _voice_summary = "failed"
        elif _voice_mix_ok:
            _voice_summary = "applied"
        elif _voice_part_tts_attempts and not _voice_mix_ok:
            _voice_summary = "failed"
        else:
            _voice_summary = "not used"
        if not getattr(payload, "subtitle_translate_enabled", False) or not _sub_translate_attempts:
            _subtitle_translate_summary = "not used"
        elif _sub_translate_clean and not _sub_translate_partial and not _sub_translate_failed_parts:
            _subtitle_translate_summary = "applied"
        elif _sub_translate_failed_parts and not _sub_translate_clean and not _sub_translate_partial:
            _subtitle_translate_summary = "failed"
        else:
            _subtitle_translate_summary = "partial"
        _job_log(effective_channel, job_id, f"Voice: {_voice_summary}")
        _job_log(effective_channel, job_id, f"Subtitle translation: {_subtitle_translate_summary}")
        _mv_parts = [
            {
                "part_no":              _i + 1,
                "market_viral_score":   _s.get("mv_viral_score",  0),
                "market_viral_tier":    _s.get("mv_viral_tier",   ""),
                "market_viral_market":  _s.get("mv_viral_market", _mv_market),
                "market_viral_reasons": _s.get("mv_viral_reasons", []),
            }
            for _i, _s in enumerate(scored)
            if "mv_viral_score" in _s
        ]

        # ── P5-1 Output Ranking ───────────────────────────────────────────────
        _failed_idx_set = {int(f.get("part_no", 0)) for f in failed_parts}
        _rank_entries: list[dict] = []
        for _r_idx, _r_seg in enumerate(scored, start=1):
            if _r_idx in _failed_idx_set:
                continue
            _r_vt = str(_r_seg.get("variant_type") or "")
            _r_output = str(
                output_dir / (f"{_output_stem}_{_r_vt}.mp4" if _r_vt else f"{_output_stem}_part_{_r_idx:03d}.mp4")
            )
            _rank_entry = _compute_output_ranking_entry(
                _r_idx,
                _r_seg,
                _r_output,
                payload_hook_score=_hook_score,
            )
            if _r_vt:
                _rank_entry["variant_type"]  = _r_vt
                _rank_entry["variant_label"] = str(_r_seg.get("variant_label") or _r_vt.replace("_", " ").title())
            # UP15: cover frame — propagate from segment dict (set during _process_one_part)
            _r_cover_file   = str(_r_seg.get("cover_file") or "")
            _r_cover_offset = float(_r_seg.get("cover_frame_offset") or 0)
            if _r_cover_file:
                _rank_entry["cover_file"]         = _r_cover_file
                _rank_entry["cover_frame_offset"] = round(_r_cover_offset, 3)
            # UP16: CTA — propagate cta_applied / cta_text from segment dict
            if _r_seg.get("cta_applied"):
                _rank_entry["cta_applied"] = True
                _rank_entry["cta_text"]    = str(_r_seg.get("cta_text") or "")
            # Apply quality penalty from per-part validator
            _rank_raw_score = float(_rank_entry["output_score"])
            _rank_q_penalty = int(_r_seg.get("quality_penalty", 0))
            _rank_final_score = round(max(0.0, min(100.0, _rank_raw_score - _rank_q_penalty)), 1)
            _rank_entry["raw_score"] = _rank_raw_score
            _rank_entry["quality_penalty"] = _rank_q_penalty
            _rank_entry["final_score"] = _rank_final_score
            _rank_entry["output_score"] = _rank_final_score
            _rank_entry["output_rank_score"] = _rank_final_score
            _rank_entries.append(_rank_entry)
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="output_rank_computed",
                level="INFO",
                message=f"Part {_r_idx} output_score={_rank_entry['output_score']}",
                step="render.output_rank",
                context={
                    "part_no": _r_idx,
                    "output_score": _rank_entry["output_score"],
                    "output_rank_score": _rank_entry["output_rank_score"],
                    "ranking_reason": _rank_entry["ranking_reason"],
                    "ranking_components": _rank_entry["ranking_components"],
                },
            )
        _rank_entries.sort(key=lambda x: x["output_score"], reverse=True)
        if len(_rank_entries) >= 2:
            _conf_margin = _rank_entries[0]["output_score"] - _rank_entries[1]["output_score"]
        else:
            _conf_margin = 50.0
        _confidence_tier = (
            "strong" if _conf_margin >= 8 else
            "worth_testing" if _conf_margin >= 4 else
            "experimental"
        )
        if _rank_entries:
            _rank_entries[0]["confidence_tier"] = _confidence_tier
            _rank_entries[0]["score_margin"] = round(_conf_margin, 1)
        logger.info(
            "ranking_truth_audit job=%s confidence=%s margin=%.1f dominant=%s suppressed=%s",
            job_id, _confidence_tier, _conf_margin,
            _rank_entries[0].get("dominant_signal", "") if _rank_entries else "",
            _rank_entries[0].get("suppressed_signals", []) if _rank_entries else [],
        )
        for _ri, _re in enumerate(_rank_entries, start=1):
            _re["output_rank"]    = _ri
            _re["is_best_clip"]   = (_ri == 1)
            _re["is_best_output"] = (_ri == 1)
            _seg = scored[_re["part_no"] - 1]
            _seg["output_rank"] = _re["output_rank"]
            _seg["output_score"] = _re["output_score"]
            _seg["is_best_clip"] = _re["is_best_clip"]
            _seg["ranking_reason"] = _re["ranking_reason"]
        _rank_entries_ordered = sorted(_rank_entries, key=lambda x: x["part_no"])
        _best_rank_entry = _rank_entries[0] if _rank_entries else None
        _partial_warning = (
            f"{len(failed_parts)} of {total_parts} selected part(s) failed; "
            "ranking includes successful outputs only."
            if failed_parts else ""
        )
        if _partial_warning:
            for _re in _rank_entries_ordered:
                _re["partial_failure_warning"] = _partial_warning
            if _best_rank_entry:
                _best_rank_entry["partial_failure_warning"] = _partial_warning
        if cancel_registry.is_cancelled(job_id):
            raise cancel_registry.JobCancelledError()
        _rank_entries_ordered = attach_ai_visibility_summaries(_rank_entries_ordered)
        _best_rank_entry = next(
            (_entry for _entry in _rank_entries_ordered if bool(_entry.get("is_best_clip"))),
            None,
        )
        if _best_rank_entry:
            _job_log(
                effective_channel,
                job_id,
                f"Output ranking: ranked={len(_rank_entries)} "
                f"best_part_no={_best_rank_entry['part_no']} "
                f"best_output_score={_best_rank_entry['output_score']} "
                f"reason={_best_rank_entry['ranking_reason']}",
            )
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="output_ranking_completed",
                level="INFO",
                message=(
                    f"Output ranking: best=part_{_best_rank_entry['part_no']:03d} "
                    f"score={_best_rank_entry['output_score']} total={len(_rank_entries)}"
                ),
                step="render.output_rank",
                context={
                    "total_outputs":   len(_rank_entries),
                    "failed_outputs":  len(failed_parts),
                    "warning":         _partial_warning,
                    "best_part_no":    _best_rank_entry["part_no"],
                    "best_score":      _best_rank_entry["output_score"],
                    "best_reason":     _best_rank_entry["ranking_reason"],
                    "ranking_summary": [
                        {
                            "part_no": e["part_no"],
                            "rank": e["output_rank"],
                            "score": e["output_score"],
                            "reason": e["ranking_reason"],
                        }
                        for e in _rank_entries[:5]
                    ],
                },
            )

        # ── P5-2 Auto Best Export ─────────────────────────────────────────────
        _best_exports_list: list[dict] = []
        if getattr(payload, "auto_best_export_enabled", False):
            if _rank_entries:
                _abe_count = max(1, min(10, int(getattr(payload, "auto_best_export_count", 3) or 3)))
                _abe_top   = _rank_entries[:_abe_count]  # already sorted desc by score
                _best_dir  = output_dir / "best"
                try:
                    _best_dir.mkdir(parents=True, exist_ok=True)
                    for _abe in _abe_top:
                        _abe_src = Path(_abe["output_file"])
                        _abe_dst = _best_dir / f"{_output_stem}_rank_{_abe['output_rank']:02d}.mp4"
                        try:
                            shutil.copy2(str(_abe_src), str(_abe_dst))
                            _best_exports_list.append({
                                "rank":              _abe["output_rank"],
                                "part_no":           _abe["part_no"],
                                "source_file":       str(_abe_src),
                                "best_file":         str(_abe_dst),
                                "output_score":      _abe["output_score"],
                                "output_rank_score": _abe["output_rank_score"],
                                "ranking_reason":    _abe["ranking_reason"],
                            })
                        except Exception as _abe_copy_err:
                            _job_log(
                                effective_channel, job_id,
                                f"best_export copy failed part_{_abe['part_no']:03d}: {_abe_copy_err}",
                                kind="warning",
                            )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="best_export_completed",
                        level="INFO",
                        message=f"Best export: {len(_best_exports_list)}/{len(_abe_top)} files → {_best_dir}",
                        step="render.best_export",
                        context={
                            "count":          len(_best_exports_list),
                            "best_dir":       str(_best_dir),
                            "exported_files": [e["best_file"] for e in _best_exports_list],
                        },
                    )
                except Exception as _abe_err:
                    _job_log(
                        effective_channel, job_id,
                        f"best_export_failed: {_abe_err}",
                        kind="warning",
                    )
            else:
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="best_export_skipped",
                    level="INFO",
                    message="Best export skipped: no ranked outputs available",
                    step="render.best_export",
                    context={"reason": "no_ranked_outputs"},
                )

        _is_partial_success = bool(failed_parts)
        _final_status = "completed_with_errors" if _is_partial_success else "completed"
        _final_message = (
            f"Render complete: {len(outputs)}/{total_parts} clips Â· {len(failed_parts)} failed"
            if _is_partial_success else "Render completed"
        )
        if _recovery_notes:
            _final_message += " [" + "; ".join(_recovery_notes) + "]"

        # ── Phase 30: AI Output Ranking — best-effort, never blocks render ──
        _ai_output_ranking: dict = {"available": False, "mode": "recommendation_only"}
        try:
            from app.ai.output.output_ranker import rank_variant_outputs as _rank_ai_outputs
            _ai_rank_inputs = [
                {
                    "output_id": str(_re.get("part_no") or i),
                    "path": str(_re.get("output_file") or ""),
                    "variant_id": str(_re.get("variant_id") or ""),
                    "output_rank_score": float(_re.get("output_rank_score") or _re.get("output_score") or 0.0),
                    "failed": False,
                    "warnings": [],
                }
                for i, _re in enumerate(_rank_entries_ordered)
            ] + [
                {
                    "output_id": str(_fp.get("part_no") or f"failed_{i}"),
                    "path": "",
                    "variant_id": "",
                    "output_rank_score": 0.0,
                    "failed": True,
                    "warnings": [str(_fp.get("error") or "render_failed")],
                }
                for i, _fp in enumerate(failed_parts)
            ]
            _ai_rank_result = _rank_ai_outputs(
                _ai_rank_inputs,
                edit_plan=_ai_edit_plan,
                context={"job_id": job_id},
            )
            _ai_output_ranking = _ai_rank_result.to_dict()
            if _ai_edit_plan is not None:
                _ai_edit_plan.output_ranking = _ai_output_ranking
            logger.info(
                "ai_output_ranking_created job_id=%s best=%s outputs=%d",
                job_id,
                _ai_output_ranking.get("best_output_id") or "none",
                len(_ai_output_ranking.get("outputs") or []),
            )
        except Exception as _rank_err:
            logger.warning("ai_output_ranking_skipped job_id=%s: %s", job_id, _rank_err)
            _ai_output_ranking = {
                "available": False,
                "mode": "recommendation_only",
                "warnings": [f"ranking_error:{type(_rank_err).__name__}"],
            }

        # ── Phase 45: AI Render Quality Evaluation — evaluation-only, never blocks render ──
        _ai_render_quality: dict = {"available": False, "evaluation_mode": "evaluation_only"}
        try:
            from app.ai.quality.quality_evaluator import evaluate_render_quality as _eval_quality
            _quality_eval = _eval_quality(
                outputs,
                edit_plan=_ai_edit_plan,
                context={"job_id": job_id},
            )
            _ai_render_quality = _quality_eval.to_dict()
            if _ai_edit_plan is not None:
                _ai_edit_plan.render_quality_evaluation = _ai_render_quality
            logger.info(
                "ai_render_quality_evaluated job_id=%s best=%s outputs=%d",
                job_id,
                _ai_render_quality.get("best_quality_output_id") or "none",
                len(_ai_render_quality.get("output_scores") or []),
            )
        except Exception as _quality_err:
            logger.warning("ai_render_quality_evaluation_skipped job_id=%s: %s", job_id, _quality_err)
            _ai_render_quality = {
                "available": False,
                "evaluation_mode": "evaluation_only",
                "warnings": [f"quality_evaluation_error:{type(_quality_err).__name__}"],
            }

        # Phase 49A — Build stable UI-safe AI UX metadata contract
        _ai_ux_metadata: dict = {"available": False}
        try:
            from app.ai.ux.ai_ux_metadata import build_ai_ux_metadata as _build_ai_ux
            _ai_ux_metadata = _build_ai_ux(_ai_edit_plan, output_ranking=_ai_output_ranking)
        except Exception as _ux_err:
            logger.debug("ai_ux_metadata_skipped job_id=%s: %s", job_id, _ux_err)

        _result_payload = {
            "outputs": outputs,
            "render_preset": _preset_name,
            "render_preset_id": _preset_id,
            "render_preset_label": _preset_label,
            "segments": scored,
            "market_viral_parts": _mv_parts,
            "output_ranking": _rank_entries_ordered,
            "output_ranking_warning": _partial_warning,
            "best_clip": _best_rank_entry,
            "best_exports": _best_exports_list,
            "voice_summary": _voice_summary,
            "subtitle_translate_summary": _subtitle_translate_summary,
            "failed_parts": [int(f["part_no"]) for f in failed_parts],
            "failed_parts_detail": failed_parts,
            "selected_segments_count": total_parts,
            "successful_outputs_count": len(outputs),
            "failed_outputs_count": len(failed_parts),
            "is_partial_success": _is_partial_success,
            "ai_director": _ai_edit_plan.to_dict() if _ai_edit_plan is not None else {"enabled": False},
            "ai_render_influence": _ai_influence_report,
            "ai_beat_execution": _ai_beat_report,
            "story": _ai_edit_plan.story if _ai_edit_plan is not None else {},
            "preset_evolution": _ai_edit_plan.preset_evolution if _ai_edit_plan is not None else {},
            "creator_style": _ai_edit_plan.creator_style if _ai_edit_plan is not None else {},
            "ai_output_ranking": _ai_output_ranking,
            "ai_render_quality_evaluation": _ai_render_quality,
            "ai_ux": _ai_ux_metadata,
            "recovery_notes": _recovery_notes,
        }
        upsert_job(
            job_id,
            "render",
            effective_channel,
            _final_status,
            payload.model_dump(),
            _result_payload,
            stage=JobStage.DONE,
            progress_percent=100,
            message=_final_message,
        )
        # ── AI Memory write (Phase 3) — after job finalized, never blocks render ──
        if getattr(payload, "ai_director_enabled", False) or _ai_edit_plan is not None:
            try:
                from app.ai.rag.memory_writer import write_render_memory as _write_mem
                _write_mem(
                    _result_payload,
                    context={
                        "market": getattr(payload, "ai_target_market", None) or getattr(payload, "viral_market", None),
                        "mode": getattr(payload, "ai_mode", "viral_tiktok"),
                        "duration": source.get("duration", 0.0),
                    },
                )
            except Exception:
                pass

        _job_log(
            effective_channel,
            job_id,
            f"Render final summary: status={_final_status} "
            f"successful_outputs={len(outputs)} failed_outputs={len(failed_parts)} "
            f"selected_segments={total_parts}",
            kind="warning" if _is_partial_success else "info",
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.ffmpeg.success",
            level="WARNING" if _is_partial_success else "INFO",
            message="FFmpeg render completed with errors" if _is_partial_success else "FFmpeg render completed",
            step="render.ffmpeg",
            context={"outputs": len(outputs), "failed_outputs": len(failed_parts), "total_parts": total_parts},
        )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.complete_with_errors" if _is_partial_success else "render.complete",
            level="WARNING" if _is_partial_success else "INFO",
            message=_final_message,
            step="render.complete",
            duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            context={
                "outputs": len(outputs),
                "failed_outputs": len(failed_parts),
                "total_parts": total_parts,
                "is_partial_success": _is_partial_success,
                "voice_summary": _voice_summary,
                "subtitle_translate_summary": _subtitle_translate_summary,
            },
        )
    except Exception as e:
        fail_message = f"Failed at step '{current_stage}': {e}"
        tb = traceback.format_exc()
        _job_log(effective_channel, job_id, f"[ERROR_STEP] {current_stage}")
        _job_log(effective_channel, job_id, f"Render failed: {e}")
        _job_log(effective_channel, job_id, tb)
        if current_stage == JobStage.SCENE_DETECTION:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.scene.detect.error",
                level="ERROR",
                message=f"Scene detection failed: {e}",
                step="render.scene.detect",
                exception=e,
                traceback_text=tb,
            )
        if current_stage == JobStage.DOWNLOADING:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.download.error",
                level="ERROR",
                message=f"Source download failed: {e}",
                step="render.download",
                exception=e,
                traceback_text=tb,
            )
        _emit_render_event(
            channel_code=effective_channel,
            job_id=job_id,
            event="render.error",
            level="ERROR",
            message=fail_message,
            step=current_stage,
            exception=e,
            traceback_text=tb,
            duration_ms=int((datetime.utcnow() - started_at).total_seconds() * 1000),
            context={"current_stage": current_stage, "source_mode": payload.source_mode, "youtube_url": (payload.youtube_url or ""), "source_video_path": (payload.source_video_path or "")},
        )
        if current_stage in {JobStage.STARTING, JobStage.DOWNLOADING}:
            _emit_render_event(
                channel_code=effective_channel,
                job_id=job_id,
                event="render.prepare_source.error",
                level="ERROR",
                message=f"Source preparation failed: {e}",
                step="render.prepare_source.error",
                exception=e,
                traceback_text=tb,
                context={"current_stage": current_stage, "source_mode": payload.source_mode, "youtube_url": (payload.youtube_url or ""), "source_video_path": (payload.source_video_path or "")},
            )
        upsert_job(
            job_id,
            "render",
            effective_channel,
            "failed",
            payload.model_dump(),
            {"error": str(e), "failed_step": current_stage},
            stage=JobStage.FAILED,
            progress_percent=max(0, min(99, int(current_progress))),
            message=fail_message,
        )
        return
    finally:
        if payload.cleanup_temp_files:
            try:
                shutil.rmtree(work_dir, ignore_errors=True)
                _job_log(effective_channel, job_id, "Temporary files cleaned")
            except Exception as cleanup_err:
                _job_log(effective_channel, job_id, f"Temp cleanup warning: {cleanup_err}")
        # Cleanup preview session only on success — failed/cancelled renders should
        # keep the session alive so the user can retry without re-preparing the source.
        _session_render_succeeded = _final_status in ("completed", "completed_with_errors")
        if edit_session_id and _session_render_succeeded:
            try:
                cleanup_session_fn(edit_session_id)
            except Exception:
                pass
        _JOB_LOG_DIRS.pop(job_id, None)
        close_thread_conn()  # release render thread's cached DB connection
