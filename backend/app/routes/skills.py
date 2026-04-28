"""
Skill Runner API.

POST /api/skills/jobs         — create and queue a skill job
GET  /api/skills/jobs         — list all skill jobs
GET  /api/skills/jobs/{id}   — get single skill job
GET  /api/skills/manifest     — get skill manifest with availability
"""
from __future__ import annotations

import json
import logging
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.stage import JobStage
from app.services.db import get_job, list_jobs, upsert_job
from app.services.job_manager import submit_job
from app.skills.job_events import emit_job_event
from app.skills.registry import get_manifest, get_registry

router = APIRouter(prefix="/api/skills", tags=["skills"])
logger = logging.getLogger("app.skills.routes")

_MIN_DURATION_SEC = 70.0


# ── Request schema ─────────────────────────────────────────────────────────────

class SkillJobRequest(BaseModel):
    # Source — either resolve from an existing editor session, or use a path directly
    session_id: Optional[str] = ""
    source_path: Optional[str] = ""

    output_dir: str = ""
    selected_skills: list[str] = []
    skill_options: dict = {}
    target_aspect_ratio: Optional[str] = None
    subtitle_options: Optional[dict] = None
    # Duration control — null means "use defaults"
    skill_min_duration_sec: Optional[int] = None
    skill_max_duration_sec: Optional[int] = None


# ── Manifest ───────────────────────────────────────────────────────────────────

@router.get("/manifest")
def api_skill_manifest():
    return {"skills": get_manifest()}


# ── Job listing ────────────────────────────────────────────────────────────────

@router.get("/jobs")
def api_list_skill_jobs():
    rows = list_jobs()
    return {"items": [r for r in rows if r.get("kind") == "skill_job"]}


@router.get("/jobs/{job_id}")
def api_get_skill_job(job_id: str):
    row = get_job(job_id)
    if not row or row.get("kind") != "skill_job":
        raise HTTPException(status_code=404, detail="Skill job not found")
    return row


# ── Job creation ───────────────────────────────────────────────────────────────

@router.post("/jobs")
def api_create_skill_job(payload: SkillJobRequest):
    # Resolve source path — prefer session_id so frontend never exposes disk paths
    source = (payload.source_path or "").strip()
    session_id = (payload.session_id or "").strip()

    if session_id and not source:
        source = _resolve_session_path(session_id)

    if not source:
        raise HTTPException(status_code=400, detail="source_path or valid session_id is required")
    if not Path(source).exists():
        raise HTTPException(status_code=400, detail=f"Source file not found: {source}")

    output_dir = (payload.output_dir or "").strip()
    if not output_dir:
        raise HTTPException(status_code=400, detail="output_dir is required")

    if not payload.selected_skills:
        raise HTTPException(status_code=400, detail="No skills selected")

    registry = get_registry()
    unknown = [s for s in payload.selected_skills if s not in registry]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown skills: {unknown}")

    job_id = str(uuid.uuid4())
    job_payload = {
        "source_path":            source,
        "output_dir":             output_dir,
        "selected_skills":        payload.selected_skills,
        "skill_options":          payload.skill_options,
        "target_aspect_ratio":    payload.target_aspect_ratio,
        "subtitle_options":       payload.subtitle_options,
        "session_id":             session_id,
        "skill_min_duration_sec": payload.skill_min_duration_sec,
        "skill_max_duration_sec": payload.skill_max_duration_sec,
    }

    upsert_job(
        job_id, "skill_job", "skill_runner", "queued",
        job_payload, {},
        stage=JobStage.QUEUED, progress_percent=0,
        message="Skill job queued",
    )
    logger.info(
        "skill_job_created job_id=%s skills=%s source=%s",
        job_id, payload.selected_skills, source,
    )

    submitted = submit_job(job_id, _run_skill_job, job_id, job_payload)
    if not submitted:
        raise HTTPException(status_code=409, detail="Skill job is already running")

    return {"job_id": job_id, "status": "queued", "selected_skills": payload.selected_skills}


# ── Execution ──────────────────────────────────────────────────────────────────

def _run_skill_job(job_id: str, job_payload: dict) -> None:
    """Execute selected skills sequentially in a background thread."""
    from app.services.db import update_job_progress

    selected     = job_payload.get("selected_skills", [])
    skill_options = job_payload.get("skill_options", {})
    source_path  = job_payload.get("source_path", "")
    output_dir   = job_payload.get("output_dir", "")

    # Configurable duration limits — fall back to module default for min
    min_dur = float(job_payload.get("skill_min_duration_sec") or _MIN_DURATION_SEC)
    max_dur_raw = job_payload.get("skill_max_duration_sec")
    max_dur: float | None = float(max_dur_raw) if max_dur_raw else None

    registry = get_registry()
    applied: list[str]          = []
    skipped: list[str]          = []   # unavailable / not-in-registry / graceful fallback
    failed: list[str]           = []   # threw exception during run()
    step_errors: dict[str, str] = {}
    events: list[dict]          = []
    fallback_count              = 0
    current_path                = source_path
    total_steps                 = len(selected) + 2  # +duration_prepare +finalize

    # Initialise before try so the except block can always reference them
    duration_extended = False
    dur_ctx:   dict = {}
    duration_trimmed  = False
    trim_ctx:  dict = {}

    # ── Temp work dir — all intermediate files isolated here ──────────────────
    temp_dir = Path(output_dir) / f"skill_tmp_{job_id}"
    temp_dir.mkdir(parents=True, exist_ok=True)

    def emit(event, status, *, step=None, step_index=None, progress=None,
             message="", level="info", context=None):
        rec = emit_job_event(
            job_id, "skill", event, status,
            step=step, step_index=step_index, total_steps=total_steps,
            progress=progress, message=message, level=level, context=context,
        )
        events.append(rec)
        if len(events) > 30:
            events.pop(0)

    logger.info("skill_job_started job_id=%s skills=%s", job_id, selected)

    try:
        emit("job_started", "running",
             message=f"Starting {len(selected)} skill(s)", progress=0)
        _upsert_running(job_id, job_payload, 1, "Skill job starting",
                        applied, skipped, failed, step_errors, fallback_count,
                        current_path, None, events)

        # ── Step 0: Duration prepare (min + optional max) ─────────────────────
        emit("job_step_started", "running",
             step="duration_prepare", step_index=0, progress=1,
             message="Checking video duration…")
        emit("skill_duration_configured", "running",
             step="duration_prepare", step_index=0, progress=1,
             message=f"Duration: min={min_dur}s" + (f" max={max_dur}s" if max_dur else ""),
             context={"min_sec": min_dur, "max_sec": max_dur})

        # Extend to min
        new_path, dur_ctx = _ensure_min_duration(
            source_path, str(temp_dir), min_dur, job_id,
        )
        duration_extended = bool(dur_ctx)
        if duration_extended:
            current_path = new_path
            emit("skill_duration_extended", "running",
                 step="duration_prepare", step_index=0, progress=2,
                 message=(
                     f"Extended {dur_ctx['original_duration']}s → "
                     f"{dur_ctx['final_duration']}s via {dur_ctx['strategy']}"
                 ),
                 context=dur_ctx)

        # Trim to max (if specified)
        if max_dur:
            new_path2, trim_ctx = _trim_to_max_duration(
                current_path, str(temp_dir), max_dur, job_id,
            )
            duration_trimmed = bool(trim_ctx)
            if duration_trimmed:
                current_path = new_path2
                emit("skill_duration_trimmed", "running",
                     step="duration_prepare", step_index=0, progress=2,
                     message=(
                         f"Trimmed {trim_ctx['original_duration']}s → "
                         f"{trim_ctx['final_duration']}s"
                     ),
                     context=trim_ctx)

        emit("job_step_completed", "running",
             step="duration_prepare", step_index=0, progress=3,
             context={
                 "skipped": not (duration_extended or duration_trimmed),
                 "extended": duration_extended,
                 "trimmed":  duration_trimmed,
             })
        _upsert_running(job_id, job_payload, 3, "Duration check complete",
                        applied, skipped, failed, step_errors, fallback_count,
                        current_path, None, events)

        # ── Steps 1…N: skill execution ─────────────────────────────────────────
        total = len(selected)
        for idx, skill_id in enumerate(selected):
            step_idx = idx + 1
            adapter  = registry.get(skill_id)
            label    = getattr(adapter, "label", skill_id) if adapter else skill_id

            if not adapter:
                skipped.append(skill_id)
                emit("job_step_completed", "running",
                     step=skill_id, step_index=step_idx, progress=_pct(step_idx, total_steps),
                     context={"skipped": True, "reason": "not_in_registry"})
                logger.warning("skill_skipped job_id=%s skill=%s reason=not_in_registry", job_id, skill_id)
                continue

            try:
                available = bool(adapter.check())
            except Exception:
                available = False

            if not available or getattr(adapter, "status", "available") == "unavailable":
                skipped.append(skill_id)
                pct = _pct(step_idx, total_steps)
                emit("job_step_completed", "running",
                     step=skill_id, step_index=step_idx, progress=pct,
                     context={"skipped": True, "reason": "unavailable"})
                logger.info("skill_skipped job_id=%s skill=%s reason=unavailable", job_id, skill_id)
                _upsert_running(job_id, job_payload, pct, f"Skipped {label}: unavailable",
                                applied, skipped, failed, step_errors, fallback_count,
                                current_path, skill_id, events)
                continue

            pct_start = _pct(step_idx - 1, total_steps) + 1
            update_job_progress(job_id, "running", pct_start,
                                f"Running {label}…", status="running")
            emit("job_step_started", "running",
                 step=skill_id, step_index=step_idx, progress=pct_start,
                 message=f"Running {label}…")
            logger.info("skill_step_started job_id=%s skill=%s", job_id, skill_id)

            try:
                options = skill_options.get(skill_id, {})
                ctx     = {"job_id": job_id, "source_path": source_path, "output_dir": str(temp_dir)}
                result  = adapter.run(current_path, str(temp_dir), options, ctx)
                new_path = str(result.get("output_path") or current_path)
                if new_path and Path(new_path).exists():
                    current_path = new_path

                if result.get("skipped"):
                    # Adapter ran but gracefully fell back (e.g. subtitle overlay failed)
                    skip_reason = result.get("skip_reason", f"{label} skipped due to error")
                    skipped.append(skill_id)
                    emit("job_step_failed", "running",
                         step=skill_id, step_index=step_idx, level="warn",
                         message=skip_reason)
                    emit("job_step_completed", "running",
                         step=skill_id, step_index=step_idx,
                         progress=_pct(step_idx, total_steps),
                         message=f"{label} skipped — continuing",
                         context={"skipped": True, "reason": skip_reason})
                    logger.warning("skill_graceful_skip job_id=%s skill=%s reason=%s",
                                   job_id, skill_id, skip_reason)
                else:
                    applied.append(skill_id)
                    emit("job_step_completed", "running",
                         step=skill_id, step_index=step_idx,
                         progress=_pct(step_idx, total_steps),
                         message=f"Completed {label}")
                    logger.info("skill_step_completed job_id=%s skill=%s output=%s",
                                job_id, skill_id, new_path)
            except Exception as exc:
                fallback_count += 1
                failed.append(skill_id)
                step_errors[skill_id] = str(exc)
                emit("job_step_failed", "running",
                     step=skill_id, step_index=step_idx, level="error",
                     message=str(exc), context={"error": str(exc)})
                logger.error("skill_step_failed job_id=%s skill=%s error=%s",
                             job_id, skill_id, exc, exc_info=True)

            step_msg = f"Failed {label}" if skill_id in failed else f"Completed {label}"
            _upsert_running(job_id, job_payload, _pct(step_idx, total_steps), step_msg,
                            applied, skipped, failed, step_errors, fallback_count,
                            current_path, skill_id, events)

        # ── Finalize: copy to clean output, remove temp ────────────────────────
        emit("job_step_started", "running",
             step="finalize", step_index=total_steps - 1, progress=93,
             message="Finalizing output…")

        inp       = Path(source_path)
        final_out = Path(output_dir) / f"{inp.stem}_skills_final{inp.suffix}"
        cleaned   = False

        try:
            if (current_path and
                    Path(current_path).resolve() != inp.resolve() and
                    Path(current_path).exists()):
                shutil.copy2(current_path, final_out)
                final_output_path = str(final_out)
            else:
                final_output_path = source_path  # no skills ran / all failed

            if temp_dir.exists():
                shutil.rmtree(str(temp_dir), ignore_errors=True)
                cleaned = True

            emit("job_cleanup_completed", "running",
                 step="finalize", step_index=total_steps - 1, progress=97,
                 message="Temp files cleaned",
                 context={"cleaned": cleaned, "final_output": final_output_path})
            emit("job_output_ready", "running",
                 step="finalize", step_index=total_steps - 1, progress=99,
                 message=f"Output ready: {Path(final_output_path).name}",
                 context={"output_path": final_output_path})
        except Exception as exc:
            logger.error("skill_finalize_failed job_id=%s error=%s", job_id, exc, exc_info=True)
            final_output_path = current_path

        upsert_job(
            job_id, "skill_job", "skill_runner", "completed",
            job_payload, {
                "applied_skills":   applied,
                "skipped_skills":   skipped,
                "failed_skills":    failed,
                "step_errors":      step_errors,
                "fallback_count":   fallback_count,
                "current_skill":    None,
                "output_path":      final_output_path,
                "duration_extended": duration_extended,
                "duration_context": dur_ctx,
                "duration_trimmed": duration_trimmed,
                "trim_context":     trim_ctx,
                "events":           events[-20:],
            },
            stage=JobStage.DONE, progress_percent=100,
            message="Skill job completed",
        )
        emit("job_completed", "completed", progress=100,
             message=f"Done — {len(applied)} applied, {len(failed)} failed, {len(skipped)} skipped")
        logger.info(
            "skill_job_completed job_id=%s applied=%s skipped=%s failed=%s output=%s",
            job_id, applied, skipped, failed, final_output_path,
        )

    except Exception as exc:
        if temp_dir.exists():
            shutil.rmtree(str(temp_dir), ignore_errors=True)
        emit("job_failed", "failed", level="error",
             message=str(exc), context={"error": str(exc)})
        logger.error("skill_job_failed job_id=%s error=%s", job_id, exc, exc_info=True)
        upsert_job(
            job_id, "skill_job", "skill_runner", "failed",
            job_payload, {
                "applied_skills":   applied,
                "skipped_skills":   skipped,
                "failed_skills":    failed,
                "step_errors":      step_errors,
                "fallback_count":   fallback_count,
                "current_skill":    None,
                "output_path":      current_path,
                "duration_extended": duration_extended,
                "duration_context": dur_ctx,
                "duration_trimmed": duration_trimmed,
                "trim_context":     trim_ctx,
                "error_message":    str(exc),
                "events":           events[-20:],
            },
            stage=JobStage.FAILED, progress_percent=100,
            message=f"Skill job failed: {exc}",
        )


def _pct(step_idx: int, total_steps: int) -> int:
    """Map step index to progress percent in [3, 93] range."""
    return max(3, min(93, int((step_idx / max(total_steps, 1)) * 90) + 3))


def _upsert_running(job_id, payload, pct, msg, applied, skipped, failed,
                    step_errors, fallbacks, output_path, current_skill, events):
    upsert_job(
        job_id, "skill_job", "skill_runner", "running",
        payload, {
            "applied_skills":  applied,
            "skipped_skills":  skipped,
            "failed_skills":   failed,
            "step_errors":     step_errors,
            "fallback_count":  fallbacks,
            "current_skill":   current_skill,
            "output_path":     output_path,
            "events":          events[-20:],
        },
        stage=JobStage.RUNNING, progress_percent=pct, message=msg,
    )


# ── Video duration helpers ─────────────────────────────────────────────────────

def _get_video_duration(video_path: str) -> float:
    """Return video duration in seconds via ffprobe, or 0 on failure."""
    try:
        from app.services.bin_paths import get_ffprobe_bin
        probe = get_ffprobe_bin()
        cmd = [
            probe, "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            str(video_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if r.returncode == 0:
            return float(json.loads(r.stdout).get("format", {}).get("duration", 0))
    except Exception:
        pass
    return 0.0


def _ensure_min_duration(
    input_path: str,
    temp_dir: str,
    min_sec: float,
    job_id: str,
) -> tuple[str, dict]:
    """
    If input is shorter than min_sec, loop it to meet the minimum.
    Returns (final_path, context_dict).  context_dict is empty when no action taken.
    """
    duration = _get_video_duration(input_path)
    if duration <= 0 or duration >= min_sec:
        return input_path, {}

    try:
        from app.services.bin_paths import get_ffmpeg_bin
        ffmpeg = get_ffmpeg_bin()
        inp    = Path(input_path)
        loops  = int(min_sec / duration) + 2

        # Concat-demuxer list — most reliable cross-codec loop method
        safe_path = str(inp.resolve()).replace("\\", "/")
        list_file = Path(temp_dir) / f"loop_{job_id}.txt"
        list_file.write_text(
            "\n".join(f"file '{safe_path}'" for _ in range(loops)),
            encoding="utf-8",
        )

        out = Path(temp_dir) / f"{inp.stem}_min{int(min_sec)}s{inp.suffix}"
        cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0", "-i", str(list_file),
            "-t", str(min_sec),
            "-c", "copy",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        list_file.unlink(missing_ok=True)

        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            final_dur = _get_video_duration(str(out))
            logger.info(
                "skill_duration_extended job_id=%s original=%.1fs final=%.1fs strategy=loop",
                job_id, duration, final_dur,
            )
            return str(out), {
                "original_duration": round(duration, 2),
                "final_duration":    round(final_dur, 2),
                "strategy":          "loop",
            }
    except Exception as exc:
        logger.warning("skill_duration_extend_failed job_id=%s error=%s", job_id, exc)

    return input_path, {}


def _trim_to_max_duration(
    input_path: str,
    temp_dir: str,
    max_sec: float,
    job_id: str,
) -> tuple[str, dict]:
    """
    If input is longer than max_sec, hard-trim it.
    Returns (final_path, context_dict).  context_dict is empty when no action taken.
    """
    duration = _get_video_duration(input_path)
    if duration <= 0 or duration <= max_sec:
        return input_path, {}

    try:
        from app.services.bin_paths import get_ffmpeg_bin
        ffmpeg = get_ffmpeg_bin()
        inp = Path(input_path)
        out = Path(temp_dir) / f"{inp.stem}_max{int(max_sec)}s{inp.suffix}"
        cmd = [
            ffmpeg, "-y",
            "-i", str(inp),
            "-t", str(max_sec),
            "-c", "copy",
            str(out),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if r.returncode == 0 and out.exists() and out.stat().st_size > 0:
            logger.info(
                "skill_duration_trimmed job_id=%s original=%.1fs max=%.1fs",
                job_id, duration, max_sec,
            )
            return str(out), {
                "original_duration": round(duration, 2),
                "final_duration":    round(max_sec, 2),
                "strategy":          "trim",
            }
    except Exception as exc:
        logger.warning("skill_duration_trim_failed job_id=%s error=%s", job_id, exc)

    return input_path, {}


def _resolve_session_path(session_id: str) -> str:
    """Resolve the original video path from a preview session created by /render/prepare-source."""
    try:
        from app.routes.render import _load_session
        session = _load_session(session_id)
        if session:
            return str(session.get("video_path") or "")
    except Exception as exc:
        logger.warning("Could not resolve session %s: %s", session_id, exc)
    return ""
