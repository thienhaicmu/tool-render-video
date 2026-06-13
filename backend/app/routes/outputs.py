"""
routes/outputs.py — Multi-Output Compare & Export endpoints.

Phase F — Multi-Output Compare & Export.

GET  /api/jobs/{job_id}/outputs
     Ranked list of all rendered clips for a job, merging job_parts
     (output_file, scores, timing) with render_ab_scores (rank, is_best_output).

GET  /api/jobs/{job_id}/outputs/best
     Shortcut — returns only the part with is_best_output = true.

GET  /api/jobs/{job_id}/outputs/export?part_nos=1,2,3
     ZIP download of selected clip files.
     part_nos omitted → all completed parts included.
     Files that no longer exist on disk are silently skipped.

Blast radius: LOW — new file, no existing routes modified.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.db.ab_scores_repo import list_ab_scores_for_job
from app.db.jobs_repo import get_job, list_job_parts

router = APIRouter(prefix="/api/jobs", tags=["outputs"])


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_output_item(part: dict, scores: dict) -> dict:
    """Merge a job_parts row with its render_ab_scores row (if any)."""
    part_no = int(part.get("part_no") or 0)
    score_row = scores.get(part_no, {})

    output_file = str(part.get("output_file") or "")
    file_exists = bool(output_file and Path(output_file).is_file())
    file_size_bytes = 0
    if file_exists:
        try:
            file_size_bytes = Path(output_file).stat().st_size
        except Exception:
            pass

    return {
        "part_no":           part_no,
        "part_name":         str(part.get("part_name") or ""),
        "status":            str(part.get("status") or ""),
        "output_rank":       int(score_row.get("output_rank") or 0),
        "output_rank_score": float(score_row.get("output_rank_score") or 0.0),
        "is_best_output":    bool(score_row.get("is_best_output")),
        "viral_score":       float(score_row.get("viral_score") or part.get("viral_score") or 0.0),
        "hook_score":        float(score_row.get("hook_score") or part.get("hook_score") or 0.0),
        "retention_score":   float(score_row.get("retention_score") or 0.0),
        "start_sec":         float(part.get("start_sec") or 0.0),
        "end_sec":           float(part.get("end_sec") or 0.0),
        "duration":          float(part.get("duration") or 0.0),
        "output_file":       output_file,
        "file_exists":       file_exists,
        "file_size_bytes":   file_size_bytes,
    }


def _get_job_or_404(job_id: str) -> dict:
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job not found: {job_id}")
    return job


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{job_id}/outputs")
def get_outputs(job_id: str):
    """Ranked list of all render outputs for this job."""
    _get_job_or_404(job_id)
    parts = list_job_parts(job_id)
    scores = list_ab_scores_for_job(job_id)

    items = [_build_output_item(p, scores) for p in parts]
    # Sort: ranked parts first (output_rank > 0) by rank ASC, then unranked by part_no
    ranked   = sorted([i for i in items if i["output_rank"] > 0], key=lambda x: x["output_rank"])
    unranked = sorted([i for i in items if i["output_rank"] == 0], key=lambda x: x["part_no"])
    outputs  = ranked + unranked

    completed = [i for i in items if i["status"] == "DONE" and i["file_exists"]]
    return {
        "job_id":           job_id,
        "total_parts":      len(parts),
        "completed_parts":  len(completed),
        "outputs":          outputs,
    }


@router.get("/{job_id}/outputs/best")
def get_best_output(job_id: str):
    """Return the single best-ranked output (is_best_output = true)."""
    _get_job_or_404(job_id)
    parts  = list_job_parts(job_id)
    scores = list_ab_scores_for_job(job_id)

    items = [_build_output_item(p, scores) for p in parts]
    best  = next((i for i in sorted(items, key=lambda x: x["output_rank"])
                  if i["is_best_output"]), None)
    if best is None:
        # Fallback: highest rank score among ranked items
        ranked = [i for i in items if i["output_rank"] > 0]
        best = ranked[0] if ranked else None
    if best is None:
        raise HTTPException(status_code=404, detail="No ranked outputs found for this job")
    return best


@router.get("/{job_id}/outputs/export")
def export_outputs(
    job_id: str,
    part_nos: Optional[str] = Query(None, description="Comma-separated part numbers, e.g. '1,2,3'. Omit for all."),
):
    """Stream a ZIP of the requested output clips."""
    _get_job_or_404(job_id)
    parts  = list_job_parts(job_id)
    scores = list_ab_scores_for_job(job_id)
    items  = [_build_output_item(p, scores) for p in parts]

    # Filter by requested part_nos if specified
    if part_nos:
        try:
            requested = {int(x.strip()) for x in part_nos.split(",") if x.strip()}
        except ValueError:
            raise HTTPException(status_code=422, detail="part_nos must be comma-separated integers")
        items = [i for i in items if i["part_no"] in requested]

    # Only include parts with an existing output file
    to_export = [i for i in items if i["file_exists"]]
    if not to_export:
        raise HTTPException(status_code=404, detail="No output files available for export")

    # Sort by rank so rank_01 appears first in the ZIP
    to_export.sort(key=lambda x: (x["output_rank"] if x["output_rank"] > 0 else 9999, x["part_no"]))

    # Build ZIP in memory (outputs are typically <500 MB total; use streaming for larger sets)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_STORED, allowZip64=True) as zf:
        for item in to_export:
            rank = item["output_rank"]
            part = item["part_no"]
            rank_label = f"rank_{rank:02d}_" if rank > 0 else ""
            arc_name = f"clip_{rank_label}part_{part:03d}.mp4"
            zf.write(item["output_file"], arcname=arc_name)

    buf.seek(0)
    short_id = job_id[:8]
    filename = f"job_{short_id}_clips.zip"
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
