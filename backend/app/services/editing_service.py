"""
Editing service — trim, re-render selection, export clip.

Security invariants:
  - Never accepts raw filesystem paths from clients.
  - All source paths are resolved from DB records (job_id + part_no).
  - Export destination_dir is validated: must be absolute, within safe roots.
  - No path traversal: all paths resolved + checked with is_relative_to().
  - FFmpeg commands built from validated Path objects, never from user strings.
  - AI does NOT control any of these operations.
"""
from __future__ import annotations

import logging
import re
import shutil
import uuid
from pathlib import Path

from app.core.config import CHANNELS_DIR, TEMP_DIR
from app.services.db import get_job, list_job_parts, upsert_job
from app.services.render.clip_ops import cut_video
from app.services.render.ffmpeg_helpers import probe_video_metadata

logger = logging.getLogger("app.editing")

_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

# Minimum and maximum supported trim durations
_MIN_TRIM_DURATION_S = 1.0

# Safe roots for export destination validation
_EXPORT_SAFE_ROOTS: list[Path] = []


def _safe_export_roots() -> list[Path]:
    roots = [Path.home().resolve()]
    if CHANNELS_DIR.exists():
        roots.append(CHANNELS_DIR.resolve())
    if TEMP_DIR.exists():
        roots.append(TEMP_DIR.resolve())
    return roots


def _validate_job_id(job_id: str) -> bool:
    return bool(_JOB_ID_RE.match(job_id))


def _resolve_part_video(job_id: str, part_no: int) -> Path:
    """Resolve the output_file path for a job part from DB — never from client input."""
    parts = list_job_parts(job_id)
    part = next((p for p in parts if int(p.get("part_no", -1)) == part_no), None)
    if not part:
        raise FileNotFoundError(f"Part {part_no} not found for job {job_id}")
    raw = str(part.get("output_file") or "").strip()
    if not raw:
        raise FileNotFoundError(f"No output_file recorded for part {part_no} of job {job_id}")
    path = Path(raw).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Media file not found on disk: {path}")
    return path


def _probe_duration(path: Path) -> float:
    meta = probe_video_metadata(str(path))
    dur = meta.get("duration")
    if dur is None or float(dur) <= 0:
        raise ValueError(f"Could not determine duration for {path}")
    return float(dur)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def apply_trim(
    job_id: str,
    part_no: int,
    start_sec: float,
    end_sec: float,
    output_mode: str = "new_job",
) -> dict:
    """
    Trim a rendered clip to [start_sec, end_sec].

    output_mode="new_job":
        Saves trimmed clip under the job's output dir / trimmed/
        and returns {status, output_file, duration_sec}.
        Does NOT mutate the original file.

    Security: source path resolved from DB only.
    """
    if not _validate_job_id(job_id):
        raise ValueError("Invalid job_id")
    if part_no <= 0:
        raise ValueError("part_no must be a positive integer")

    row = get_job(job_id)
    if not row:
        raise FileNotFoundError(f"Job not found: {job_id}")

    source_path = _resolve_part_video(job_id, part_no)
    duration = _probe_duration(source_path)

    # Clamp and validate
    clamped_start = _clamp(float(start_sec), 0.0, duration)
    clamped_end = _clamp(float(end_sec), 0.0, duration)

    if clamped_end <= clamped_start:
        raise ValueError(
            f"end_sec must be greater than start_sec (got start={start_sec}, end={end_sec})"
        )
    trim_duration = clamped_end - clamped_start
    if trim_duration < _MIN_TRIM_DURATION_S:
        raise ValueError(
            f"Trim duration must be at least {_MIN_TRIM_DURATION_S}s (got {trim_duration:.2f}s)"
        )

    # Output directory: siblings to source under trimmed/
    output_dir = source_path.parent / "trimmed"
    output_dir.mkdir(parents=True, exist_ok=True)

    out_stem = f"{source_path.stem}_trim_{clamped_start:.1f}_{clamped_end:.1f}"
    output_path = output_dir / f"{out_stem}.mp4"

    cut_video(str(source_path), str(output_path), clamped_start, clamped_end)

    actual_duration = _probe_duration(output_path)
    logger.info(
        "apply_trim: job_id=%s part_no=%d start=%.2f end=%.2f output=%s",
        job_id, part_no, clamped_start, clamped_end, output_path.name,
    )

    return {
        "status": "ok",
        "job_id": job_id,
        "part_no": part_no,
        "output_file": str(output_path),
        "duration_sec": round(actual_duration, 3),
        "trim_start_sec": round(clamped_start, 3),
        "trim_end_sec": round(clamped_end, 3),
        "output_mode": output_mode,
    }


def rerender_selection(
    job_id: str,
    part_no: int,
    start_sec: float,
    end_sec: float,
    effect_preset: str | None = None,
    subtitle_style: str | None = None,
) -> dict:
    """
    Create a new render job that re-renders a selected segment of a completed part.

    The new job:
    - Reuses the source video from the original job's payload.
    - Applies the requested time range as trim bounds.
    - Stores parent_job_id linkage in its payload.
    - Returns immediately with the new job_id (async processing).
    """
    if not _validate_job_id(job_id):
        raise ValueError("Invalid job_id")
    if part_no <= 0:
        raise ValueError("part_no must be a positive integer")

    import json
    row = get_job(job_id)
    if not row:
        raise FileNotFoundError(f"Job not found: {job_id}")

    source_path = _resolve_part_video(job_id, part_no)
    duration = _probe_duration(source_path)

    clamped_start = _clamp(float(start_sec), 0.0, duration)
    clamped_end = _clamp(float(end_sec), 0.0, duration)

    if clamped_end <= clamped_start:
        raise ValueError(
            f"end_sec must be greater than start_sec (got start={start_sec}, end={end_sec})"
        )
    if (clamped_end - clamped_start) < _MIN_TRIM_DURATION_S:
        raise ValueError(
            f"Selection must be at least {_MIN_TRIM_DURATION_S}s"
        )

    # Parse original payload to inherit render settings
    try:
        original_payload = json.loads(row.get("payload_json") or "{}")
    except Exception:
        original_payload = {}

    new_job_id = f"rerender_{job_id[:20]}_{uuid.uuid4().hex[:8]}"

    # Build new payload: inherit source settings + override trim + style
    new_payload = dict(original_payload)
    new_payload["source_video_path"] = str(source_path)
    new_payload["source_mode"] = "local"
    new_payload["trim_start_sec"] = clamped_start
    new_payload["trim_end_sec"] = clamped_end
    new_payload["parent_job_id"] = job_id
    new_payload["parent_part_no"] = part_no

    if effect_preset is not None:
        new_payload["effect_preset"] = effect_preset
    if subtitle_style is not None:
        new_payload["subtitle_style"] = subtitle_style

    # Remove keys that should not be inherited
    for key in ("youtube_url", "urls"):
        new_payload.pop(key, None)

    upsert_job(
        job_id=new_job_id,
        kind="render",
        channel_code=str(row.get("channel_code") or "manual"),
        status="queued",
        payload=new_payload,
        result=None,
        stage="queued",
        progress_percent=0,
        message="Re-render selection queued",
    )

    # Submit to job queue
    try:
        from app.services.render_engine import run_render_job
        from app.services.job_manager import submit_job
        submit_job(new_job_id, run_render_job, new_job_id)
    except Exception as exc:
        logger.warning("rerender_selection: failed to enqueue job_id=%s: %s", new_job_id, exc)
        # Job is in DB as queued — will be recovered on next startup
        pass

    logger.info(
        "rerender_selection: new_job_id=%s parent=%s part=%d start=%.2f end=%.2f",
        new_job_id, job_id, part_no, clamped_start, clamped_end,
    )

    return {
        "status": "queued",
        "new_job_id": new_job_id,
        "parent_job_id": job_id,
        "parent_part_no": part_no,
        "trim_start_sec": round(clamped_start, 3),
        "trim_end_sec": round(clamped_end, 3),
    }


def export_clip(
    job_id: str,
    part_no: int,
    destination_dir: str,
) -> dict:
    """
    Copy the rendered clip to a user-specified directory.

    Security:
    - destination_dir must be an absolute path.
    - Must be within safe roots (home dir, CHANNELS_DIR, TEMP_DIR).
    - No path traversal: resolved path checked with is_relative_to().
    - Filename derived from source file only — no user-supplied filenames.
    """
    if not _validate_job_id(job_id):
        raise ValueError("Invalid job_id")
    if part_no <= 0:
        raise ValueError("part_no must be a positive integer")

    row = get_job(job_id)
    if not row:
        raise FileNotFoundError(f"Job not found: {job_id}")

    source_path = _resolve_part_video(job_id, part_no)

    # Validate destination
    if not destination_dir or not destination_dir.strip():
        raise ValueError("destination_dir must not be empty")

    try:
        dest_dir = Path(destination_dir.strip()).resolve()
    except Exception as exc:
        raise ValueError(f"Invalid destination_dir: {exc}") from exc

    if not dest_dir.is_absolute():
        raise ValueError("destination_dir must be an absolute path")

    safe_roots = _safe_export_roots()
    if not any(dest_dir == r or dest_dir.is_relative_to(r) for r in safe_roots):
        raise PermissionError(
            f"destination_dir is outside allowed export locations. "
            f"Must be within home directory or app data directories."
        )

    dest_dir.mkdir(parents=True, exist_ok=True)

    # Build output filename (source stem preserved, no user input)
    out_name = source_path.name
    dest_path = dest_dir / out_name

    # Avoid overwrite: append suffix if file exists
    if dest_path.exists():
        stem = source_path.stem
        suffix = source_path.suffix
        dest_path = dest_dir / f"{stem}_export_{uuid.uuid4().hex[:6]}{suffix}"

    shutil.copy2(str(source_path), str(dest_path))

    logger.info(
        "export_clip: job_id=%s part_no=%d source=%s dest=%s",
        job_id, part_no, source_path.name, dest_path,
    )

    return {
        "status": "ok",
        "job_id": job_id,
        "part_no": part_no,
        "source_file": source_path.name,
        "exported_to": str(dest_path),
        "destination_dir": str(dest_dir),
    }
