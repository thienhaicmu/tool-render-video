"""Quality report locator — safe read-only sidecar JSON access.

Security rules enforced here:
- job_id: alphanumeric + hyphens/underscores only, max 128 chars
- part_no: positive integer only
- Resolved path MUST stay inside video_path.parent/quality/
- Never raises — all errors return None
- Never accepts a raw filesystem path from the caller
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# job_id must be alphanumeric, hyphens, or underscores only — no slashes, dots, or escapes.
_JOB_ID_RE = re.compile(r'^[A-Za-z0-9_-]{1,128}$')


def _validate_job_id(job_id: object) -> bool:
    """Return True only if job_id is a safe, non-traversal string."""
    if not isinstance(job_id, str):
        return False
    return bool(_JOB_ID_RE.match(job_id))


def _validate_part_no(part_no: object) -> bool:
    """Return True only if part_no is a strictly positive integer."""
    if not isinstance(part_no, int) or isinstance(part_no, bool):
        return False
    return part_no > 0


def find_quality_report_path(job_id: str, part_no: int, video_path: Path) -> Path | None:
    """Return the resolved sidecar JSON path if it exists and is safe.

    Path pattern: video_path.parent / "quality" / "{job_id}_part_{part_no}.json"

    Security:
    - Validates job_id and part_no before any path construction.
    - Resolves final path and verifies it stays under video_path.parent/quality/.
    - Never raises.
    """
    try:
        if not _validate_job_id(job_id):
            return None
        if not _validate_part_no(part_no):
            return None

        quality_dir = video_path.parent / "quality"
        sidecar_name = f"{job_id}_part_{part_no}.json"
        candidate = quality_dir / sidecar_name

        # Resolve both paths and verify containment (prevents symlink escapes)
        try:
            resolved_candidate = candidate.resolve()
            resolved_quality_dir = quality_dir.resolve()
        except Exception:
            return None

        # Path traversal guard: resolved path must be under the quality dir
        try:
            resolved_candidate.relative_to(resolved_quality_dir)
        except ValueError:
            logger.warning(
                "report_locator: path traversal blocked job_id=%r part_no=%r candidate=%s",
                job_id, part_no, resolved_candidate,
            )
            return None

        if not resolved_candidate.exists():
            return None

        return resolved_candidate

    except Exception as exc:
        logger.debug("report_locator: find_quality_report_path failed: %s", exc)
        return None


def load_quality_report(report_path: Path) -> dict | None:
    """Read and parse a quality report JSON file safely.

    Returns a dict or None on any error. Never raises.
    """
    try:
        raw = report_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        return data
    except Exception as exc:
        logger.debug("report_locator: load_quality_report failed path=%s: %s", report_path, exc)
        return None


def load_quality_report_for_part(job_id: str, part_no: int, video_path: Path) -> dict | None:
    """Locate and load the quality report for a rendered part.

    Combines find_quality_report_path() + load_quality_report().
    Returns dict or None. Never raises.
    """
    try:
        path = find_quality_report_path(job_id, part_no, video_path)
        if path is None:
            return None
        return load_quality_report(path)
    except Exception as exc:
        logger.debug("report_locator: load_quality_report_for_part failed: %s", exc)
        return None
