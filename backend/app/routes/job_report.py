"""
routes/job_report.py — Job Export Report endpoint.

Phase S — Job Export Report.

GET /api/jobs/{job_id}/report?format=json   (default)
GET /api/jobs/{job_id}/report?format=csv

Returns a comprehensive report for a completed job:
  - Job metadata (job_id, status, stage, channel_code, created_at, updated_at)
  - Per-part scores: viral_score, hook_score, retention_score, output_rank_score
  - AI decisions: ai_title, ai_reason (from result_json if available)
  - Segment timing: start_sec, end_sec, duration
  - File info: output_file existence, file_size_bytes

JSON format: { job: {...}, parts: [{...}] }
CSV  format: text/csv download with one row per part.

Blast radius: LOW — new file, read-only. No DB writes. No render changes.
"""
from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response, StreamingResponse

from app.db.ab_scores_repo import list_ab_scores_for_job
from app.db.jobs_repo import get_job, list_job_parts

logger = logging.getLogger("app.routes.job_report")
router = APIRouter(prefix="/api/jobs", tags=["job-report"])

_CSV_FIELDS = [
    "job_id", "part_no", "part_name", "status",
    "start_sec", "end_sec", "duration",
    "viral_score", "hook_score", "retention_score",
    "output_rank", "output_rank_score", "is_best_output",
    "ai_title", "ai_reason",
    "output_file", "file_exists", "file_size_bytes",
]


def _file_info(output_file: str) -> tuple[bool, int]:
    if not output_file:
        return False, 0
    p = Path(output_file)
    try:
        return p.is_file(), (p.stat().st_size if p.is_file() else 0)
    except OSError:
        return False, 0


def _build_report_parts(
    parts: list[dict],
    scores: dict,
    ai_decisions: dict,
    job_id: str,
) -> list[dict]:
    rows: list[dict] = []
    for part in parts:
        part_no = int(part.get("part_no") or 0)
        score = scores.get(part_no, {})
        ai = ai_decisions.get(part_no, {})

        output_file = str(part.get("output_file") or "")
        file_exists, file_size = _file_info(output_file)

        rows.append({
            "job_id":            job_id,
            "part_no":           part_no,
            "part_name":         str(part.get("part_name") or ""),
            "status":            str(part.get("status") or ""),
            "start_sec":         float(part.get("start_sec") or 0),
            "end_sec":           float(part.get("end_sec") or 0),
            "duration":          float(part.get("duration") or 0),
            "viral_score":       float(score.get("viral_score") or part.get("viral_score") or 0),
            "hook_score":        float(score.get("hook_score") or part.get("hook_score") or 0),
            "retention_score":   float(score.get("retention_score") or 0),
            "output_rank":       int(score.get("output_rank") or 0),
            "output_rank_score": float(score.get("output_rank_score") or 0),
            "is_best_output":    bool(score.get("is_best_output")),
            "ai_title":          str(ai.get("ai_title") or ""),
            "ai_reason":         str(ai.get("ai_reason") or ""),
            "output_file":       output_file,
            "file_exists":       file_exists,
            "file_size_bytes":   file_size,
        })
    return rows


def _extract_ai_decisions(result_json_str: str) -> dict:
    """Parse result_json for per-part ai_title / ai_reason keyed by part_no."""
    try:
        data = json.loads(result_json_str or "{}")
        clips = data.get("clips") or []
        return {
            int(c.get("part_no", 0)): {
                "ai_title":  str(c.get("ai_title") or ""),
                "ai_reason": str(c.get("ai_reason") or ""),
            }
            for c in clips if isinstance(c, dict)
        }
    except Exception:
        return {}


@router.get("/{job_id}/report")
def get_job_report(
    job_id: str,
    format: str = Query("json", description="Response format: 'json' or 'csv'"),
):
    """Export a comprehensive report for a job."""
    job = get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")

    if format.lower() not in ("json", "csv"):
        raise HTTPException(status_code=422, detail="format must be 'json' or 'csv'")

    parts = list_job_parts(job_id)
    scores = list_ab_scores_for_job(job_id)
    ai_decisions = _extract_ai_decisions(str(job.get("result_json") or ""))

    report_parts = _build_report_parts(parts, scores, ai_decisions, job_id)

    if format.lower() == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(report_parts)
        buf.seek(0)
        filename = f"job_{job_id[:8]}_report.csv"
        return StreamingResponse(
            iter([buf.getvalue()]),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # JSON response
    job_meta = {
        "job_id":       str(job.get("job_id") or ""),
        "status":       str(job.get("status") or ""),
        "stage":        str(job.get("stage") or ""),
        "channel_code": str(job.get("channel_code") or ""),
        "created_at":   str(job.get("created_at") or ""),
        "updated_at":   str(job.get("updated_at") or ""),
    }
    return {
        "job":   job_meta,
        "parts": report_parts,
    }
