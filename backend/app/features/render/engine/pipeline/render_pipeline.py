
# Sprint 6.D dead-import cleanup: most heavy service-level imports that
# the original run_render_pipeline used directly now live inside the
# extracted stage modules (orchestration/pipeline_*.py and
# orchestration/stages/part_*.py). Imports retained below split into
# two groups:
#   1. Symbols actually used by run_render_pipeline body or module-level
#      constants (e.g. JOB_SEMAPHORE, _MAX_CONCURRENT_JOBS).
#   2. Re-exports preserved for external consumers — routes/render.py
#      imports several render_events / qa_pipeline / pipeline_config
#      symbols from here, and the tests/* suite imports asset / audio /
#      qa / event helpers from this module's namespace. These are
#      marked with a noqa comment carrying the F401 code.
import hashlib
import os
import shutil
import subprocess  # noqa: F401 (re-exported for mock.patch in tests/test_render_pipeline_guards.py)
import threading
import time
import traceback
import logging
from datetime import datetime
from pathlib import Path
from typing import Callable

from fastapi import HTTPException

from app.models.schemas import RenderRequest
from app.db.connection import close_thread_conn
from app.db.jobs_repo import (
    batch_upsert_job_parts_queued,
    list_job_parts,
    update_job_progress,
    upsert_job,
)
from app.features.render.engine.subtitle.transcription.whisper import has_audio_stream
from app.features.render.engine.encoder.ffmpeg_helpers import nvenc_available
from app.jobs import cancel as cancel_registry
from app.jobs.manager import MAX_CONCURRENT_JOBS as _MAX_CONCURRENT_JOBS
from app.features.render.engine.pipeline.report_service import append_rows
from app.core.config import TEMP_DIR
from app.core.stage import JobStage
from app.features.render.ai.visibility.ai_visibility_summary import attach_ai_visibility_summaries
from app.services.metrics import RENDER_STAGE_DURATION
from app.features.render.engine.pipeline.remotion_adapter import (  # noqa: F401 (re-exported for mock.patch in tests/test_remotion_adapter.py)
    generate_hook_intro,
    prepend_intro_clip,
)
from app.features.render.engine.pipeline.render_events import (
    _JOB_LOG_DIRS,  # noqa: F401 (re-exported for tests/test_asset_pipeline.py)
    _append_json_line,  # noqa: F401 (re-exported for routes/render.py)
    _emit_render_event,
    _event_from_stage,
    _job_log,
    register_job_log_dir,
    unregister_job_log_dir,
    _render_progress_timer,  # noqa: F401 (re-exported for tests/test_render_events.py + test_render_pipeline_guards.py)
    _resolve_job_log_dir,
    _safe_unlink,
)
from app.features.render.engine.pipeline.asset_pipeline import (  # noqa: F401 (re-exported for tests/test_asset_pipeline.py + test_remotion_adapter.py)
    _maybe_append_asset_outro,
    _maybe_apply_asset_logo,
    _maybe_prepend_asset_intro,
    _maybe_prepend_remotion_hook_intro,
)
from app.features.render.engine.pipeline.audio_cleanup import (
    _maybe_cleanup_narration_audio,  # noqa: F401 (re-exported for tests/test_audio_cleanup_pipeline.py + test_audio_pipeline.py)
)
from app.features.render.engine.pipeline.qa_pipeline import (  # noqa: F401 (re-exported for tests/test_qa_pipeline.py::test_qa_functions_re_exported_from_render_pipeline asserts all 7)
    _assess_output_quality,
    _duration_tolerance,
    _failed_part_progress,
    _render_part_failure_detail,
    _resume_output_valid,
    _stall_deadline,
    _validate_render_output,
)
from app.features.render.engine.pipeline.pipeline_finalize import FinalizeContext, run_render_finalize
from app.features.render.engine.pipeline.pipeline_setup import setup_render_pipeline, prepare_output_dir
from app.features.render.engine.pipeline.pipeline_source_prep import prepare_render_source
from app.features.render.engine.pipeline.pipeline_narration import run_manual_voice_tts
from app.features.render.engine.stages.part_renderer import PartRenderContext  # noqa: F401 (passed via PartRenderContext init in run_render_loop)
from app.features.render.engine.pipeline.pipeline_render_loop import run_render_loop
# pipeline_pre_render removed in Phase F1 — all jobs now use llm_pipeline.
from app.features.render.engine.pipeline.llm_pipeline import run_llm_pre_render
from app.features.render.engine.pipeline.llm_stage import (
    _build_editorial_hint,
    _resolve_api_key as _resolve_llm_api_key,
)
from app.features.render.engine.pipeline.pipeline_cache import (
    _transcription_cache_get,
    _transcription_cache_put,
)
from app.features.render.engine.pipeline.pipeline_ranking import (
    _compute_output_ranking_entry,
    _resolve_rank_from_plan,
)
from app.features.render.engine.pipeline.pipeline_segment_selection import _get_effective_playback_speed as _get_llm_speed
from app.features.render.engine.pipeline.pipeline_config import (
    _resolve_profile,
    _probe_video_duration,  # noqa: F401 (re-exported for routes/render.py)
)
# Sprint 4.D — RenderPlan AI-emission wire-up. Sprint 4.H removed the
# Sprint 2.2 builder shim that previously ran as the fallback path; when
# the LLM_EMIT_RENDER_PLAN flag is OFF (default) ctx.render_plan stays
# None and the Sprint 4.E/F/G stage resolvers fall back to the legacy
# payload-derived logic — Sacred Contract #2 baseline preservation.
from app.features.render.ai.llm import select_render_plan as _llm_select_render_plan
from app.db.jobs_repo import get_render_plan, update_render_plan


# Sprint 4.D — feature flag: when ON (default since Sprint 7.6a), ask the LLM
# to emit a full RenderPlan (clips + subtitle_policy + camera_strategy +
# audio_plan + overlays) via ai.llm.select_render_plan. If the AI returns a
# RenderPlan we use it directly; if it returns None, the ai_emission_empty
# guard (below) raises RuntimeError and the job fails. There is no heuristic
# fallback — the Sprint 2.2 builder shim was removed in Sprint 4.H.
# When LLM_EMIT_RENDER_PLAN=0 (non-default override), _render_plan stays None
# and the stage resolvers fall back to payload-derived logic, preserving
# Sacred Contract #2 baseline behaviour byte-identical.
# See docs/review/SPRINT_7_6a_LLM_FLAG_FLIP_2026-06-05.md.
_FEATURE_LLM_EMIT_RENDER_PLAN: bool = os.getenv("LLM_EMIT_RENDER_PLAN", "1") == "1"

logger = logging.getLogger("app.render")


# _safe_output_name, _smart_output_stem,
# _select_cover_frame_time, _select_cta_text, _append_cta_block_to_srt,
# _get_effective_playback_speed, _read_srt_meta, _build_variant_segments,
# _aspect_play_res_y, _apply_subtitle_edits_to_srt, _PLATFORM_PROFILES,
# _PLAY_RES_Y_MAP, _VARIANT_AGGRESSIVE_SUB, _VARIANT_STORY_SUB,
# _CTA_TEXTS, _CTA_AUTO_TYPE
# → moved to app.features.render.engine.pipeline.pipeline_helpers (Phase A-1)

# _RENDER_CACHE_TTL_SEC, _render_cache_key, _scene_cache_get/put,
# _transcription_cache_get/put, _score_cache_get/put
# → moved to app.features.render.engine.pipeline.pipeline_cache (C-1)

# resolve_combined_score_weights, _score_component, _first_score,
# _RANKING_WEIGHTS, _output_ranking_detail, _output_ranking_reason,
# _compute_output_ranking_entry
# → moved to app.features.render.engine.pipeline.pipeline_ranking (C-1)

# _maybe_prepend_remotion_hook_intro, _maybe_prepend_asset_intro,
# _maybe_append_asset_outro, _maybe_apply_asset_logo
# → moved to app.features.render.engine.pipeline.asset_pipeline (Phase 4B)

# _maybe_cleanup_narration_audio → moved to app.features.render.engine.pipeline.audio_cleanup (Phase 4D)


# _PROGRESS_TICK_SEC, _render_progress_timer → moved to app.features.render.engine.pipeline.render_events (Phase 4D)

# _resume_output_valid → moved to app.features.render.engine.pipeline.qa_pipeline (Phase 4C)


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


# _apply_subtitle_edits_to_srt → moved to app.features.render.engine.pipeline.pipeline_helpers (Phase A-1)

# _duration_tolerance, _stall_deadline → moved to app.features.render.engine.pipeline.qa_pipeline (Phase 4C)


# _render_progress_timer → moved to app.features.render.engine.pipeline.render_events (Phase 4D)


# HIGH_MOTION_MIN_SCORE, HIGH_MOTION_MIN_KEEP → moved to pipeline_pre_render (Phase A-6)
# _JOB_LOG_DIRS, _job_log, _append_json_line, _render_error_code, _emit_render_event
# → moved to app.features.render.engine.pipeline.render_events (Phase 4B)


# _event_from_stage, _resolve_job_log_dir → moved to app.features.render.engine.pipeline.render_events (Phase 4D)


def _validate_text_layers_or_400(payload: RenderRequest) -> list[dict]:
    from app.features.render.engine.overlay.text_overlay import normalize_text_layers
    try:
        raw_layers = [x.model_dump() if hasattr(x, "model_dump") else dict(x) for x in (payload.text_layers or [])]
        return normalize_text_layers(raw_layers)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid text_layers: {exc}") from exc


# Sprint 7.6 FULL (2026-06-05) — derive scored list from RenderPlan.clips
# when AI emission succeeded. Field-shape MUST match _to_scored_dict at
# llm_stage.py:263 key-for-key so downstream consumers (pipeline_segment_
# selection, pipeline_ranking, every stages/part_*.py) see no contract
# change. Intentional divergence: source="render_plan" vs legacy "llm" —
# zero string-match consumers (grep audit). NEVER raises (Sacred Contract
# #3 spirit): any unexpected error returns fallback_scored unchanged so
# the render keeps moving.
# See docs/review/SPRINT_7_6_FULL_PLAN_2026-06-05.md.
def _ranges_overlap(a_start: float, a_end: float, b_start: float, b_end: float) -> bool:
    """Two half-open ranges [a_start, a_end) and [b_start, b_end) overlap
    iff a_start < b_end AND b_start < a_end.

    Strategic-1b — Audit 2026-06-08 closure (Batch A V8-A12 follow-up).
    The exclude / lock filter uses strict (non-inclusive) endpoints
    so adjoining ranges (e.g. clip [10, 20] and exclude [20, 30])
    do NOT count as overlap — the operator's intent for an exclude
    range like 'avoid this 10-second window' shouldn't reject a
    clip that ENDS exactly where the exclude starts.
    """
    return a_start < b_end and b_start < a_end


def _coerce_range(entry) -> "tuple[float, float] | None":
    """Coerce an arbitrary dict to (start_sec, end_sec) tuple or None.

    Defensive against payloads from stored job records that may carry
    legacy shapes or partial data. Sacred Contract #3 spirit applies
    to the clip_lock/exclude pipeline — bad input is silently
    skipped, never raised.
    """
    if not isinstance(entry, dict):
        return None
    try:
        start = float(entry.get("start_sec"))
        end = float(entry.get("end_sec"))
    except (TypeError, ValueError):
        return None
    if start < 0 or end <= start:
        return None
    return start, end


def _apply_clip_lock_exclude_filter(
    scored: list,
    clip_lock,
    clip_exclude,
    *,
    channel_code: str = "",
    job_id: str = "",
) -> list:
    """Strategic-1b — Audit 2026-06-08 closure (Batch A V8-A12 follow-up).

    The local-side defence-in-depth filter that complements
    Strategic-1's LLM-prompt wiring. Strategic-1 instructs the model
    to honour the operator's clip_lock and clip_exclude ranges via
    the HARD LOCKED RANGES and HARD EXCLUDED RANGES prompt sections;
    this filter VERIFIES the model's emission and enforces the rule
    on the BE side regardless of what the model returned.

    Two rules:

    1. EXCLUDE — drop any clip whose [start, end) overlaps any
       supplied exclude range. The drop is logged via _job_log AND
       emitted as a structured render event (forensic value).

    2. LOCK — verify that at least one surviving clip overlaps each
       supplied lock range. Uncovered locks are logged AND emitted
       as a warning event so the operator (and downstream consumers)
       can see the gap. The filter does NOT synthesise a new clip
       to cover an uncovered lock — that would require segmenting
       the source again; instead it emits a render event the FE can
       render as a 'lock uncovered' warning badge.

    Sacred Contract #3 spirit: the helper NEVER raises into the
    pipeline. Any unexpected error returns the input scored list
    unchanged so the render keeps moving.

    Args:
        scored: the post-AI clip list (as built by _scored_from_render_plan).
        clip_lock: list of {start_sec, end_sec} dicts, or None / [].
        clip_exclude: same shape.
        channel_code, job_id: for event emission. Falsy values
            suppress the event emit (test-friendly).

    Returns:
        The filtered scored list. Identical to input when no
        ranges were supplied OR every clip survived.
    """
    try:
        if not scored:
            return scored
        if not clip_lock and not clip_exclude:
            return scored

        excludes: list[tuple[float, float]] = []
        for entry in (clip_exclude or []):
            rng = _coerce_range(entry)
            if rng is not None:
                excludes.append(rng)
        locks: list[tuple[float, float]] = []
        for entry in (clip_lock or []):
            rng = _coerce_range(entry)
            if rng is not None:
                locks.append(rng)

        # ── Exclude pass ────────────────────────────────────────────
        kept: list[dict] = []
        for clip in scored:
            try:
                c_start = float(clip.get("start", 0) or 0)
                c_end = float(clip.get("end", 0) or 0)
            except (TypeError, ValueError):
                # Malformed clip dict — keep it; the rest of the
                # pipeline already tolerates bad coords.
                kept.append(clip)
                continue
            offending = next(
                (rng for rng in excludes if _ranges_overlap(c_start, c_end, rng[0], rng[1])),
                None,
            )
            if offending is None:
                kept.append(clip)
                continue
            # Drop. Log + emit.
            _drop_msg = (
                f"clip_exclude filter dropped clip "
                f"start={c_start:.1f}s end={c_end:.1f}s "
                f"overlaps exclude [{offending[0]:.1f}s, {offending[1]:.1f}s]"
            )
            try:
                if channel_code and job_id:
                    _job_log(channel_code, job_id, _drop_msg, kind="warning")
                    _emit_render_event(
                        channel_code=channel_code,
                        job_id=job_id,
                        event="render.plan.exclude_filter_applied",
                        level="WARNING",
                        message=_drop_msg,
                        step="render.llm_pipeline",
                        context={
                            "clip_start_sec": c_start,
                            "clip_end_sec":   c_end,
                            "exclude_start_sec": offending[0],
                            "exclude_end_sec":   offending[1],
                        },
                    )
            except Exception:
                pass  # log emission failure must not break the filter

        # ── Lock pass ───────────────────────────────────────────────
        # Uncovered-lock warnings run after the exclude pass so the
        # "covered" check uses the post-filter clip set.
        for lock_start, lock_end in locks:
            covered = any(
                _ranges_overlap(
                    float(clip.get("start", 0) or 0),
                    float(clip.get("end", 0) or 0),
                    lock_start,
                    lock_end,
                )
                for clip in kept
            )
            if covered:
                continue
            _uncovered_msg = (
                f"clip_lock uncovered: no surviving clip overlaps "
                f"[{lock_start:.1f}s, {lock_end:.1f}s]"
            )
            try:
                if channel_code and job_id:
                    _job_log(channel_code, job_id, _uncovered_msg, kind="warning")
                    _emit_render_event(
                        channel_code=channel_code,
                        job_id=job_id,
                        event="render.plan.lock_uncovered_warning",
                        level="WARNING",
                        message=_uncovered_msg,
                        step="render.llm_pipeline",
                        context={
                            "lock_start_sec": lock_start,
                            "lock_end_sec":   lock_end,
                        },
                    )
            except Exception:
                pass

        return kept
    except Exception as exc:
        # Sacred Contract #3 spirit — never let an unexpected error
        # in the filter break a render. Log + degrade gracefully.
        try:
            logger.warning(
                "clip_lock_exclude_filter unexpected error (non-fatal): %s", exc,
            )
        except Exception:
            pass
        return scored


def _scored_from_render_plan(render_plan, fallback_scored: list) -> list:
    try:
        if render_plan is None or not getattr(render_plan, "clips", None):
            return fallback_scored
        derived: list[dict] = []
        for clip in render_plan.clips:
            _base = float(getattr(clip, "score", 0.0) or 0.0) * 100.0
            _viral = (float(getattr(clip, "viral_score", 0.0) or 0.0) * 100.0) or _base
            _hook = (float(getattr(clip, "hook_score", 0.0) or 0.0) * 100.0) or _base
            _ret = (float(getattr(clip, "retention_score", 0.0) or 0.0) * 100.0) or _base
            _start = float(getattr(clip, "start", 0.0) or 0.0)
            _end = float(getattr(clip, "end", 0.0) or 0.0)
            _cover = float(getattr(clip, "cover_offset_ratio", 0.0) or 0.0)
            derived.append({
                "start":    _start,
                "end":      _end,
                "duration": _end - _start,
                "viral_score":     _viral,
                "hook_score":      _hook,
                "motion_score":    50.0,
                "diversity_score": 50.0,
                "retention_score": _ret,
                "audio_energy":    50.0,
                "clip_name": str(getattr(clip, "clip_name", "") or ""),
                "ai_title":  str(getattr(clip, "title", "") or ""),
                "ai_reason": str(getattr(clip, "reason", "") or ""),
                "source":    "render_plan",
                "ai_subtitle_style":  str(getattr(clip, "subtitle_style", "") or ""),
                "content_type_hint":  str(getattr(clip, "content_type", "") or ""),
                "hook_type":          str(getattr(clip, "hook_type", "") or ""),
                "cover_hint_ratio":   _cover if _cover > 0 else None,
                "speech_density_score": float(getattr(clip, "speech_density", 0.0) or 0.0) * 100.0,
                "duration_fit_score": float(getattr(clip, "duration_fit", 0.0) or 0.0) * 100.0,
            })
        return derived
    except Exception:
        return fallback_scored


# _resolve_profile, _probe_video_duration, extract_text_from_srt,
# _reserve_source_path_in_dir, _reserve_source_path,
# _sanitize_channel_subdir, _resolve_output_dir
# → moved to app.features.render.engine.pipeline.pipeline_config (C-1)

# _safe_unlink → moved to app.features.render.engine.pipeline.render_events (Phase 4B)

# _failed_part_progress → moved to app.features.render.engine.pipeline.qa_pipeline (Phase 4C)

# _validate_render_output → moved to app.features.render.engine.pipeline.qa_pipeline (Phase 4C)

# _assess_output_quality → moved to app.features.render.engine.pipeline.qa_pipeline (Phase 4C)

# _render_part_failure_detail → moved to app.features.render.engine.pipeline.qa_pipeline (Phase 4C)


def run_render_pipeline(
    job_id: str,
    payload: RenderRequest,
    resume_mode: bool = False,
    *,
    load_session_fn: Callable,
    cleanup_session_fn: Callable,
):
    # Sprint 6.D-1.1: payload normalization + channel resolution moved
    # to orchestration/pipeline_setup.py. The local aliases below preserve
    # the names used throughout the rest of this function.
    _setup = setup_render_pipeline(payload)
    effective_channel    = _setup.effective_channel
    started_at           = _setup.started_at
    _mv_cfg              = _setup.mv_cfg
    _mv_market           = _setup.mv_market
    _hook_apply_enabled  = _setup.hook_apply_enabled
    _hook_applied_text   = _setup.hook_applied_text
    _hook_score          = _setup.hook_score
    _hook_overlay_enabled = _setup.hook_overlay_enabled
    output_dir           = _setup.output_dir
    # Sprint 6.D-1.2: mkdir + render.output.prepare.{start,success,error}
    # WebSocket emits moved to orchestration/pipeline_setup.prepare_output_dir.
    prepare_output_dir(job_id, effective_channel, output_dir)
    register_job_log_dir(job_id, _resolve_job_log_dir(output_dir, effective_channel))
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    tuned = _resolve_profile(payload)
    retry_count = max(0, min(5, int(payload.retry_count)))
    current_stage = JobStage.STARTING
    current_progress = 1
    # Perf-opt Phase 1 — job-level stage timing. Observed only on stage
    # transition so stage names get one observation per visit (a stage
    # is re-entered ≤ once in practice). Wrapped in try/except so a
    # metric backend issue never affects the orchestrator.
    _stage_t0 = time.perf_counter()

    def _set_stage(stage: str, progress: int, message: str):
        nonlocal current_stage, current_progress, _stage_t0
        if stage != current_stage:
            try:
                RENDER_STAGE_DURATION.labels(stage=str(current_stage)).observe(
                    time.perf_counter() - _stage_t0
                )
            except Exception:
                pass
            _stage_t0 = time.perf_counter()
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
        f"Render started | resume={resume_mode} | profile={payload.render_profile} | codec={payload.video_codec} | reup_mode={payload.reup_mode} | source_mode={payload.source_mode}",
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
            job_id, JobStage.STARTING, 0,
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
        # Sprint 6.D-1.3: source preparation moved to
        # orchestration/pipeline_source_prep.prepare_render_source.
        # Exceptions still propagate up to this outer try/except — current_stage
        # is mutated via _set_stage closure inside the helper.
        _source_prep = prepare_render_source(
            job_id=job_id,
            effective_channel=effective_channel,
            payload=payload,
            work_dir=work_dir,
            output_dir=output_dir,
            hook_applied_text=_hook_applied_text,
            set_stage=_set_stage,
            load_session_fn=load_session_fn,
        )
        source                  = _source_prep.source
        source_path             = _source_prep.source_path
        edit_session_id         = _source_prep.edit_session_id
        _output_stem            = _source_prep.output_stem

        voice_audio_path = None
        _voice_tts_failed = False
        _voice_mix_ok = []
        _voice_part_tts_attempts = []
        _sub_translate_attempts = []
        _sub_translate_clean = []
        _sub_translate_partial = []
        _sub_translate_failed_parts = []
        _recovery_notes: list[str] = []   # UP24: accumulate fallback events for observability
        # Sprint 6.D-1.4: manual-source AI voice TTS moved to
        # orchestration/pipeline_narration.run_manual_voice_tts.
        # State init (voice_audio_path / _voice_tts_failed / _voice_mix_ok / ...)
        # stays above because per-part loop + downstream subtitle code mutate them.
        voice_audio_path, _voice_tts_failed = run_manual_voice_tts(
            payload=payload,
            job_id=job_id,
            effective_channel=effective_channel,
            current_stage=current_stage,
            current_progress=current_progress,
            recovery_notes=_recovery_notes,
        )

        _emit_render_event(
            channel_code=effective_channel, job_id=job_id,
            event="llm_pipeline.mode_active", level="INFO",
            message="LLM pipeline: AI is sole segment authority",
            step="render.llm_pipeline",
        )
        _pre = run_llm_pre_render(
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
            skip_segment_selection=_FEATURE_LLM_EMIT_RENDER_PLAN,
        )
        full_srt = _pre.full_srt
        full_srt_available = _pre.full_srt_available
        _early_transcription_done = _pre.early_transcription_done
        scored = _pre.scored
        total_parts = _pre.total_parts
        _target_platform = _pre.target_platform
        _dna_clean_visual = _pre.dna_clean_visual
        _seg_min_sec = _pre.seg_min_sec
        _seg_max_sec = _pre.seg_max_sec
        # full_srt and full_srt_available initialized before scene detection (Phase 45 hoist).
        # _early_transcription_done=True means Phase 45 already ran Whisper — subtitle block skips.

        # Sprint 4.D + 4.H — RenderPlan acquisition (AI-emission only).
        # When LLM_EMIT_RENDER_PLAN=1 (default since Sprint 7.6a) the
        # orchestrator calls ai.llm.select_render_plan and persists the plan.
        # When LLM_EMIT_RENDER_PLAN=0 (non-default override), _render_plan
        # stays None and stage resolvers use payload-derived logic.
        # The Sprint 2.2 builder shim was removed in Sprint 4.H.
        # Outer try/except is the Sacred Contract #3 belt-and-braces.
        _render_plan = None
        _ai_fallback_reasons: list[str] = []
        try:
            # Resume path: when retrying/resuming a job that already ran the LLM,
            # load the persisted RenderPlan from DB and skip the LLM call entirely.
            # This saves 5-30s of LLM latency + API token cost on every retry.
            if _FEATURE_LLM_EMIT_RENDER_PLAN and getattr(payload, "resume_from_last", False):
                try:
                    from app.domain.render_plan import RenderPlan as _RP
                    _existing_json = get_render_plan(job_id)
                    if _existing_json:
                        _render_plan = _RP.from_json(_existing_json)
                        if _render_plan is not None:
                            logger.info(
                                "render_plan: resume hit — reusing persisted plan (clips=%d, skip LLM)",
                                len(_render_plan.clips),
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="render.plan.resumed",
                                level="INFO",
                                message=f"RenderPlan loaded from DB (resume — LLM skipped, clips={len(_render_plan.clips)})",
                                step="render.llm_pipeline",
                                context={"clips_count": len(_render_plan.clips), "reason": "resume_from_last"},
                            )
                except Exception as _resume_exc:
                    logger.warning("render_plan: resume load failed (non-fatal): %s", _resume_exc)
                    _render_plan = None

            if _render_plan is None and _FEATURE_LLM_EMIT_RENDER_PLAN:
                try:
                    from app.core import config as _ai_cfg
                    _ai_provider = (getattr(payload, "ai_provider", "") or "").strip().lower() \
                        or getattr(_ai_cfg, "AI_PROVIDER_DEFAULT", "gemini")
                    _ai_api_key, _ = _resolve_llm_api_key(payload, _ai_provider)
                    _ai_srt_content = ""
                    if full_srt_available and full_srt and Path(full_srt).exists():
                        try:
                            _ai_srt_content = Path(full_srt).read_text(encoding="utf-8")
                        except Exception:
                            _ai_srt_content = ""
                    if _ai_srt_content:
                        from app.features.render.ai.llm.prompts import check_srt_truncation as _check_trunc
                        _trunc = _check_trunc(_ai_srt_content)
                        if _trunc["truncated"]:
                            logger.warning(
                                "render_plan: transcript truncated — %d%% shown to AI (%d of %d chars)",
                                _trunc["shown_pct"], _trunc["shown_chars"], _trunc["original_chars"],
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="transcript_truncated",
                                level="WARNING",
                                message=(
                                    f"Transcript truncated: only {_trunc['shown_pct']}% shown to AI "
                                    f"({_trunc['shown_chars']:,} of {_trunc['original_chars']:,} chars). "
                                    f"Clips from the truncated portion will not be considered."
                                ),
                                step="render.llm_pipeline",
                                context=_trunc,
                            )
                    _ai_video_duration = float(source.get("duration") or 0.0)
                    try:
                        _ai_editorial_hint = _build_editorial_hint(payload)
                    except Exception:
                        _ai_editorial_hint = ""
                    # OPT-02: LLM plan cache — skip API call when same content
                    # was rendered before (different job_id, same params).
                    from app.features.render.engine.pipeline.pipeline_cache import (
                        _llm_plan_cache_get,
                        _llm_plan_cache_put,
                        _llm_plan_cache_key,
                    )
                    from app.domain.render_plan import RenderPlan as _RP_cache
                    _llm_out_count = int(getattr(payload, "output_count", 1) or 1)
                    _llm_model = str(getattr(payload, "llm_model", "") or "")
                    _llm_target_dur = int(getattr(payload, "target_duration", 0) or 0)
                    _llm_clip_lock = getattr(payload, "clip_lock", None) or None
                    _llm_clip_excl = getattr(payload, "clip_exclude", None) or None
                    _llm_tgt_plat = str(getattr(payload, "target_platform", "") or "").lower()
                    # S5 — creator preference hints (B+C: surfaced to the
                    # prompt + included in the cache key so changing them
                    # invalidates the cache).
                    _llm_video_type = str(getattr(payload, "video_type", "auto") or "auto")
                    _llm_hook_strength = str(getattr(payload, "hook_strength", "balanced") or "balanced")
                    _llm_market = str(getattr(payload, "ai_target_market", "") or "")
                    _llm_sub_emph_val = getattr(payload, "subtitle_emphasis", None)
                    _llm_sub_emph = str(_llm_sub_emph_val) if _llm_sub_emph_val else ""
                    _llm_multi_variant = bool(getattr(payload, "multi_variant", False))
                    _llm_structure_bias_val = getattr(payload, "structure_bias", None)
                    _llm_structure_bias = str(_llm_structure_bias_val) if _llm_structure_bias_val else ""
                    # Scale source-clip duration limits by the platform speed so the
                    # AI selects segments that produce outputs within the user's desired
                    # duration range after rendering. e.g. user wants 45–60s output on
                    # TikTok (1.08×) → tell AI to find 48.6–64.8s source segments.
                    _llm_plat_speed = _get_llm_speed(payload, _llm_tgt_plat)
                    _llm_min_sec = float(_seg_min_sec) * _llm_plat_speed
                    _llm_max_sec = float(_seg_max_sec) * _llm_plat_speed
                    _llm_cache_key = _llm_plan_cache_key(
                        srt_content=_ai_srt_content,
                        output_count=_llm_out_count,
                        min_sec=_llm_min_sec,
                        max_sec=_llm_max_sec,
                        target_platform=_llm_tgt_plat,
                        provider=_ai_provider,
                        model=_llm_model,
                        editorial_hint=_ai_editorial_hint,
                        target_duration=_llm_target_dur,
                        clip_lock_repr=str(_llm_clip_lock),
                        clip_exclude_repr=str(_llm_clip_excl),
                        language=getattr(payload, "llm_language", "auto") or "auto",
                        # S5 — creator preferences (B+C)
                        video_type=_llm_video_type,
                        hook_strength=_llm_hook_strength,
                        ai_target_market=_llm_market,
                        subtitle_emphasis=_llm_sub_emph,
                        multi_variant=_llm_multi_variant,
                        structure_bias=_llm_structure_bias,
                    )
                    # Diagnostic emit: surface every input that goes into the
                    # cache key so a user can grep the log to verify which
                    # values produced this key. The 3 fields the user most
                    # commonly tunes are shown first; the rest are in
                    # cache_inputs so nothing is hidden. SRT shows hash only
                    # (full content is 100 KB+).
                    _ai_srt_hash = hashlib.sha256(_ai_srt_content.encode("utf-8")).hexdigest()[:16]
                    _job_log(
                        effective_channel, job_id,
                        f"llm_plan.cache.lookup key={_llm_cache_key[:12]} "
                        f"output_count={_llm_out_count} "
                        f"min_sec_raw={_seg_min_sec} max_sec_raw={_seg_max_sec} "
                        f"min_sec_scaled={_llm_min_sec:.1f} max_sec_scaled={_llm_max_sec:.1f} "
                        f"plat_speed={_llm_plat_speed:.3f} platform={_llm_tgt_plat} "
                        f"provider={_ai_provider} srt_hash={_ai_srt_hash}",
                    )
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="render.plan.cache_lookup",
                        level="INFO",
                        message=f"LLM plan cache lookup key={_llm_cache_key[:12]}",
                        step="render.llm_pipeline",
                        context={
                            "cache_key": _llm_cache_key,
                            "output_count": _llm_out_count,
                            "min_part_sec_raw": int(_seg_min_sec),
                            "max_part_sec_raw": int(_seg_max_sec),
                            "min_sec_scaled": round(_llm_min_sec, 1),
                            "max_sec_scaled": round(_llm_max_sec, 1),
                            "platform_speed": round(_llm_plat_speed, 3),
                            "target_platform": _llm_tgt_plat,
                            "provider": _ai_provider,
                            "model": _llm_model,
                            "target_duration": _llm_target_dur,
                            "language": getattr(payload, "llm_language", "auto") or "auto",
                            "srt_hash": _ai_srt_hash,
                            "srt_chars": len(_ai_srt_content),
                            "editorial_hint_len": len(_ai_editorial_hint or ""),
                            "clip_lock_count": len(_llm_clip_lock or []),
                            "clip_exclude_count": len(_llm_clip_excl or []),
                        },
                    )
                    _cached_plan_json = _llm_plan_cache_get(_llm_cache_key)
                    if _cached_plan_json:
                        _render_plan = _RP_cache.from_json(_cached_plan_json)
                        if _render_plan is not None:
                            logger.info(
                                "render_plan: llm_cache hit — skipping LLM call (clips=%d)",
                                len(_render_plan.clips),
                            )
                            _job_log(
                                effective_channel, job_id,
                                f"llm_plan.cache.HIT key={_llm_cache_key[:12]} "
                                f"clips={len(_render_plan.clips)} "
                                f"— reusing plan from prior render with identical inputs",
                            )
                            _emit_render_event(
                                channel_code=effective_channel,
                                job_id=job_id,
                                event="render.plan.cache_hit",
                                level="INFO",
                                message=f"RenderPlan from LLM cache (clips={len(_render_plan.clips)}, LLM skipped)",
                                step="render.llm_pipeline",
                                context={
                                    "clips_count": len(_render_plan.clips),
                                    "reason": "llm_response_cache",
                                    "cache_key": _llm_cache_key,
                                    "output_count": _llm_out_count,
                                    "min_part_sec_raw": int(_seg_min_sec),
                                    "max_part_sec_raw": int(_seg_max_sec),
                                },
                            )
                    if _render_plan is None and _cached_plan_json is None:
                        _job_log(
                            effective_channel, job_id,
                            f"llm_plan.cache.MISS key={_llm_cache_key[:12]} "
                            f"— will call {_ai_provider} (one or more inputs differ from any prior render)",
                        )

                    if _render_plan is None:
                        logger.info(
                            "render_plan: LLM_EMIT_RENDER_PLAN=1 — attempting AI emission (provider=%s)",
                            _ai_provider,
                        )
                        _render_plan = _llm_select_render_plan(
                            provider=_ai_provider,
                            srt_content=_ai_srt_content,
                            output_count=_llm_out_count,
                            min_sec=_llm_min_sec,
                            max_sec=_llm_max_sec,
                            video_duration=_ai_video_duration,
                            api_key=_ai_api_key,
                            model=getattr(payload, "llm_model", None) or None,
                            language=getattr(payload, "llm_language", "auto") or "auto",
                            editorial_hint=_ai_editorial_hint,
                            target_duration=_llm_target_dur,
                            clip_lock=_llm_clip_lock,
                            clip_exclude=_llm_clip_excl,
                            target_platform=_llm_tgt_plat,
                            # S5 — creator preferences (B+C)
                            video_type=_llm_video_type,
                            hook_strength=_llm_hook_strength,
                            ai_target_market=_llm_market,
                            subtitle_emphasis=(_llm_sub_emph or None),
                            multi_variant=_llm_multi_variant,
                            structure_bias=(_llm_structure_bias or None),
                        )
                        if _render_plan is not None:
                            _llm_plan_cache_put(_llm_cache_key, _render_plan.to_json())
                    if _render_plan is not None:
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="render.plan.ai_emitted",
                            level="INFO",
                            message="RenderPlan emitted by AI",
                            step="render.llm_pipeline",
                            context={
                                "clips_count": len(_render_plan.clips),
                                "schema_version": _render_plan.schema_version,
                                "provider": _ai_provider,
                            },
                        )
                    else:
                        # Sprint 4.H — shim path retired. ctx.render_plan
                        # stays None and the stage resolvers fall back
                        # to the legacy payload-derived logic. Event
                        # name kept for backward compat with operator
                        # tooling that grepped for it during 4.D-4.G.
                        _ai_fallback_reasons.append(f"{_ai_provider}=returned_none")
                        _emit_render_event(
                            channel_code=effective_channel,
                            job_id=job_id,
                            event="render.plan.ai_fallback",
                            level="WARNING",
                            message="AI emission returned None — render_plan left unset",
                            step="render.llm_pipeline",
                            context={"reason": "select_render_plan_returned_none"},
                        )
                except Exception as _ai_exc:
                    logger.warning("render_plan AI emission failed (non-fatal): %s", _ai_exc)
                    _render_plan = None
                    _ai_fallback_reasons.append(f"{_ai_provider}={type(_ai_exc).__name__}")
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="render.plan.ai_fallback",
                        level="WARNING",
                        message=f"AI emission raised — render_plan left unset: {_ai_exc}",
                        step="render.llm_pipeline",
                        context={
                            "reason": "exception",
                            "error_type": type(_ai_exc).__name__,
                        },
                    )

            # Sprint 4.H — persistence runs only when AI emission
            # succeeded. Flag-OFF / AI-failed jobs leave the
            # render_plan_json column NULL (additive-schema safe).
            if _render_plan is not None:
                update_render_plan(job_id, _render_plan.to_json())
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.plan.persisted",
                    level="INFO",
                    message="RenderPlan persisted",
                    step="render.llm_pipeline",
                    context={
                        "clips_count": len(_render_plan.clips),
                        "schema_version": _render_plan.schema_version,
                    },
                )
        except Exception as _plan_exc:
            # Defensive guard around the whole block. select_render_plan
            # + update_render_plan are themselves never-raise, but a
            # future refactor must not be able to take down a render
            # via the wire-up itself.
            logger.warning("render_plan wire-up failed (non-fatal): %s", _plan_exc)
            _render_plan = None

        # Sprint 7.6 FULL — derive scored from RenderPlan when AI emit
        # succeeded. NO-OP when _render_plan is None (legacy fallback
        # path unchanged) — pinned by tests/test_render_pipeline_scored_
        # from_render_plan.py.
        if _render_plan is not None:
            _scored_before = scored
            scored = _scored_from_render_plan(_render_plan, fallback_scored=scored)
            # Strategic-1b — Audit 2026-06-08 closure (Batch A V8-A12
            # follow-up). Local-side defence-in-depth: after the
            # LLM-derived scored list is built, run the operator's
            # clip_lock / clip_exclude ranges through the BE filter.
            # Strategic-1 wired the constraints into the prompt; this
            # call verifies the LLM honoured them and drops any clip
            # that overlaps an exclude range. Uncovered locks surface
            # as render events so the FE can render a warning. The
            # filter is a no-op when neither field is set OR scored
            # was unchanged by _scored_from_render_plan; never raises.
            try:
                _scored_post_filter = _apply_clip_lock_exclude_filter(
                    scored,
                    getattr(payload, "clip_lock", None) or None,
                    getattr(payload, "clip_exclude", None) or None,
                    channel_code=effective_channel,
                    job_id=job_id,
                )
                if _scored_post_filter is not scored:
                    scored = _scored_post_filter
            except Exception as _filter_exc:
                logger.warning(
                    "clip_lock_exclude wire-up failed (non-fatal): %s", _filter_exc,
                )
            if scored is not _scored_before:
                total_parts = len(scored)
                _emit_render_event(
                    channel_code=effective_channel,
                    job_id=job_id,
                    event="render.plan.scored_derived",
                    level="INFO",
                    message=f"scored derived from RenderPlan: {len(scored)} clips",
                    step="render.llm_pipeline",
                    context={
                        "clips_count": len(scored),
                        "source": "render_plan",
                        "fallback_count": len(_scored_before),
                    },
                )

        # Inject AI hook overlays from RenderPlan into normalized_text_layers.
        # kind=hook entries become a top-center text-layer (Bungee 48pt,
        # 0-2.5s). kind=cta entries are consumed in part_asset_planner.py
        # at the CTA-text resolution step (Strategic-3 — Audit
        # 2026-06-08 closure): the AI's overlays[kind=cta].type biases
        # the _cta_type when the operator hasn't set an explicit
        # cta_type (priority: operator > AI overlays.type > hook_type
        # bias > library default). The actual CTA text comes from the
        # local CTA library lookup, not from this loop.
        # Failure is non-fatal: render continues without AI overlays.
        if _render_plan is not None and _render_plan.overlays:
            _ai_overlay_layers = []
            for _ov in _render_plan.overlays:
                if str(_ov.get("kind") or "").strip().lower() == "hook":
                    _ov_text = str(_ov.get("text") or "").strip()[:60]
                    if _ov_text:
                        _ai_overlay_layers.append({
                            "id": "ai_hook_overlay",
                            "text": _ov_text,
                            "font_family": "Bungee",
                            "font_size": 48,
                            "color": "#FFFFFF",
                            "position": "top-center",
                            "x_percent": 50.0,
                            "y_percent": 20.0,
                            "alignment": "center",
                            "bold": False,
                            "outline": {"enabled": True, "thickness": 4},
                            "shadow": {"enabled": False, "offset_x": 0, "offset_y": 0},
                            "background": {"enabled": True, "color": "#000000CC", "padding": 16},
                            "start_time": 0.0,
                            "end_time": 2.5,
                            "order": -10,
                        })
            if _ai_overlay_layers:
                try:
                    from app.features.render.engine.overlay.text_overlay import normalize_text_layers as _norm_layers
                    _normalized_ai = _norm_layers(_ai_overlay_layers)
                    normalized_text_layers = normalized_text_layers + _normalized_ai
                    _emit_render_event(
                        channel_code=effective_channel,
                        job_id=job_id,
                        event="render_plan.overlays_applied",
                        level="INFO",
                        message=f"RenderPlan hook overlay injected ({len(_normalized_ai)} layer(s))",
                        step="render.llm_pipeline",
                        context={"overlay_count": len(_normalized_ai)},
                    )
                    _job_log(
                        effective_channel, job_id,
                        f"render_plan.overlays_applied: {len(_normalized_ai)} AI hook overlay(s) added",
                    )
                except Exception as _ov_exc:
                    logger.warning("render_plan: overlay injection failed (non-fatal): %s", _ov_exc)

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
            ranked_scores = sorted([round(float(s.get("viral_score", 0) or 0) * 100) for s in scored], reverse=True)
            subtitle_cutoff = max(subtitle_cutoff, ranked_scores[min(subtitle_top_count - 1, len(ranked_scores) - 1)])
        _job_log(effective_channel, job_id, f"Subtitle viral cutoff={subtitle_cutoff}, top_count={subtitle_top_count}")

        subtitle_enabled_by_idx = {}
        for idx, seg in enumerate(scored, start=1):
            subtitle_enabled_by_idx[idx] = payload.add_subtitle and (
                (not payload.subtitle_only_viral_high) or round(float(seg.get("viral_score", 0) or 0) * 100) >= subtitle_cutoff
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


        # Perf-opt Phase 8 (R13) — batch the QUEUED-state seeding for all
        # parts into a single transaction. Same ON CONFLICT semantics as
        # the per-row helper so a resume keeps the DONE rows intact (the
        # comprehension filters them out). Drops N commits to 1 → ~50 ms
        # off the cold-start path on a 10-part job.
        _seed_rows = [
            {
                "job_id": job_id,
                "part_no": idx,
                "part_name": f"part_{idx:03d}",
                "start_sec": seg["start"],
                "end_sec": seg["end"],
                "duration": seg["duration"],
                "viral_score": seg.get("viral_score", 0),
                "motion_score": seg.get("motion_score", 0),
                "hook_score": seg.get("hook_score", 0),
            }
            for idx, seg in enumerate(scored, start=1)
            if not (
                (existing_parts.get(idx, {}).get("status") or "").lower() == "done"
                and payload.resume_from_last
            )
        ]
        batch_upsert_job_parts_queued(_seed_rows)

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
            # GPU handles encode; CPU is free during the NVENC encode phase.
            # motion_aware_crop is a CPU pre-pass that finishes BEFORE ffmpeg starts;
            # while clip N is encoding on GPU, clip N+1 can run motion_crop on CPU
            # without conflict — so it does NOT count as a parallel penalty here.
            # Only reup_mode (BGM audio subprocess) overlaps with encode on CPU.
            cpu_extra = sum([
                bool(payload.reup_mode),
            ])
            heavy_penalty = min(cpu_extra, 1)
            base = max(2, cpu_total // 3)
            # B1-OPT-6 (2026-06-28): cap GPU-mode workers at NVENC session limit
            # (default 3, hardware-bound). The old ceiling of 6 spawned workers
            # that immediately blocked on NVENC_SEMAPHORE.acquire(), wasting
            # threads + RAM with no throughput gain. Override via
            # NVENC_MAX_SESSIONS env (must match GPU class — RTX 30/40 = 3,
            # RTX A-series / paid SDK = 5+).
            import os as _os
            _nvenc_cap = max(1, int(_os.getenv("NVENC_MAX_SESSIONS", "3")))
            hard_ceiling = _nvenc_cap
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

        from app.features.render.engine.encoder.ffmpeg_helpers import _resolve_codec
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
            normalized_text_layers=normalized_text_layers,
            voice_part_tts_attempts=_voice_part_tts_attempts,
            voice_mix_ok=_voice_mix_ok,
            sub_translate_attempts=_sub_translate_attempts,
            sub_translate_partial=_sub_translate_partial,
            sub_translate_clean=_sub_translate_clean,
            sub_translate_failed_parts=_sub_translate_failed_parts,
            recovery_notes=_recovery_notes,
            render_plan=_render_plan,
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

        if not outputs and not failed_parts:
            # T1.1 — Audit 2026-06-08 closure (Batch A V9-C1/C2 — CRITICAL
            # false success). When the render loop produces zero outputs
            # AND zero failures, the AI emission was empty: the LLM
            # returned None, or the parser's range/score filters
            # rejected every clip. Without this guard the pipeline
            # marches on to finalize and writes status="completed" with
            # outputs=[] — the silent success-toast path that hides
            # total AI failure from the user. Raising here routes the
            # job through the outer except → status="failed", stage=
            # FAILED, FE shows failure state.
            # Phân biệt 3 nguyên nhân 0-output để remedy không dẫn sai
            # (review 2026-06-20). _ai_fallback_reasons chỉ được điền khi
            # AI emission thất bại/raise — các nguyên nhân khác (parser lọc
            # hết clip dù AI đã phản hồi, plan cache/resume rỗng, hay
            # flag-OFF legacy selection) để list rỗng, nên chỉ trường hợp
            # AI-emission-fail mới gợi ý kiểm tra API key.
            _remedy_keys = (
                " Verify API keys in server .env (OpenAI sk-, Claude sk-ant-, "
                "Gemini AIza/AQ.) or test via Configure → AI panel → Test connection."
            )
            if _ai_fallback_reasons:
                _reason_hint = ", ".join(_ai_fallback_reasons)
                _remedy = _remedy_keys
            elif not _FEATURE_LLM_EMIT_RENDER_PLAN:
                _reason_hint = (
                    "ai_emission_disabled (LLM_EMIT_RENDER_PLAN=0); "
                    "legacy segment selection produced no clips"
                )
                _remedy = ""
            elif _render_plan is not None:
                _reason_hint = (
                    "ai_responded_but_all_clips_filtered "
                    "(check segment duration / score thresholds)"
                )
                _remedy = ""
            else:
                _reason_hint = "no_ai_response"
                _remedy = _remedy_keys
            raise RuntimeError(
                f"ai_emission_empty: 0 outputs produced and 0 parts attempted "
                f"(total_parts={total_parts}). AI provider chain: {_reason_hint}.{_remedy}"
            )
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
        # Sprint 4.G — resolve plan-derived rank mapping BEFORE the
        # per-part loop so each output_rank_computed event carries the
        # same `rank_source` tag. Resolver returns (None, "fallback")
        # when LLM_EMIT_RENDER_PLAN env != "1" — Contract #2 baseline
        # safe (Sprint 2.2 shim ranks cannot leak when flag is OFF).
        _plan_rank_map, _rank_source_tag = _resolve_rank_from_plan(
            _render_plan, scored, _failed_idx_set
        )
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
                # Strategic-1c — Audit 2026-06-08 closure. Apply the
                # operator's structure_bias selection to the per-clip
                # ranking formula. None / unknown values default to
                # the 'balanced' set (pre-Strategic-1c weights).
                structure_bias=getattr(payload, "structure_bias", None),
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
                    # Sprint 4.G — surface the rank-source tag so
                    # downstream WS consumers can attribute the choice.
                    "rank_source": _rank_source_tag,
                },
            )
        # Sprint 4.G — rank assignment split into two branches.
        # When the resolver returned a plan-derived mapping, ranks come
        # from there and entries are sorted by output_rank ascending.
        # Otherwise the legacy score-descending sort + enumerate path
        # runs verbatim. Sacred Contract #1 keys (`output_rank_score`,
        # `is_best_output`, `is_best_clip`) are set unconditionally in
        # both branches.
        if _plan_rank_map is not None:
            for _re in _rank_entries:
                _re["output_rank"]    = _plan_rank_map[_re["part_no"]]
                _re["is_best_clip"]   = (_re["output_rank"] == 1)
                _re["is_best_output"] = (_re["output_rank"] == 1)
            _rank_entries.sort(key=lambda x: x["output_rank"])
        else:
            _rank_entries.sort(key=lambda x: x["output_score"], reverse=True)
            for _ri, _re in enumerate(_rank_entries, start=1):
                _re["output_rank"]    = _ri
                _re["is_best_clip"]   = (_ri == 1)
                _re["is_best_output"] = (_ri == 1)
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
            "ranking_truth_audit job=%s confidence=%s margin=%.1f dominant=%s suppressed=%s rank_source=%s",
            job_id, _confidence_tier, _conf_margin,
            _rank_entries[0].get("dominant_signal", "") if _rank_entries else "",
            _rank_entries[0].get("suppressed_signals", []) if _rank_entries else [],
            _rank_source_tag,
        )
        # Mirror rank assignments back to `scored` seg dicts (both paths).
        for _re in _rank_entries:
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
                    # Sprint 4.G — tag the rank provenance for operators.
                    "rank_source":     _rank_source_tag,
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

        # ── Finalize (Sprint 6.D-1.5) ─────────────────────────────────────────
        # Auto Best Export + result_json assembly + terminal upsert_job +
        # opportunistic DB backup + render.ffmpeg.success / render.complete
        # WS events. Extracted verbatim to orchestration/pipeline_finalize.py.
        _final_status = run_render_finalize(FinalizeContext(
            job_id=job_id,
            effective_channel=effective_channel,
            payload=payload,
            started_at=started_at,
            output_dir=output_dir,
            output_stem=_output_stem,
            outputs=outputs,
            failed_parts=failed_parts,
            total_parts=total_parts,
            scored=scored,
            recovery_notes=_recovery_notes,
            rank_entries=_rank_entries,
            rank_entries_ordered=_rank_entries_ordered,
            best_rank_entry=_best_rank_entry,
            partial_warning=_partial_warning,
            preset_name=_preset_name,
            preset_id=_preset_id,
            preset_label=_preset_label,
            mv_parts=_mv_parts,
            voice_summary=_voice_summary,
            subtitle_translate_summary=_subtitle_translate_summary,
            render_plan=_render_plan,
            # Strategic-4 — Audit 2026-06-08 closure. The rank-source tag
            # was already computed at line 1160 and surfaced in per-entry
            # WS events; threading it through here gates the result_json
            # ranking_metadata block. See pipeline_finalize.py for the
            # persisted shape.
            rank_source=_rank_source_tag,
        ))
    except cancel_registry.JobCancelledError:
        # Sacred Contract #4: a cancelled job MUST write status='cancelled'
        # (not 'failed') so the FE + history can distinguish user-cancel
        # from a real failure. The outer process_render handler
        # (_common.py) catches this and writes JobStage.CANCELLED. Without
        # this passthrough, the broad `except Exception` below swallows the
        # JobCancelledError, writes status='failed', and returns — leaving
        # the outer handler blind. Confirmed root cause of job 9289722b
        # appearing as "Failed" in the UI despite being a cancel.
        raise
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
            def _bg_cleanup(_wd=work_dir, _ch=effective_channel, _jid=job_id):
                try:
                    shutil.rmtree(_wd, ignore_errors=True)
                    _job_log(_ch, _jid, "Temporary files cleaned (background)")
                except Exception as _ce:
                    _job_log(_ch, _jid, f"Temp cleanup warning: {_ce}")
            threading.Thread(target=_bg_cleanup, daemon=True,
                             name=f"cleanup_{job_id[:8]}").start()
        # Cleanup preview session only on success — failed/cancelled renders should
        # keep the session alive so the user can retry without re-preparing the source.
        _session_render_succeeded = _final_status in ("completed", "completed_with_errors")
        if edit_session_id and _session_render_succeeded:
            try:
                cleanup_session_fn(edit_session_id)
            except Exception:
                pass
        unregister_job_log_dir(job_id)
        close_thread_conn()  # release render thread's cached DB connection
