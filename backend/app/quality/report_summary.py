"""Quality report summary builder.

Takes pre-fetched parts_info from the caller (no direct DB access here).
Loads quality report sidecars and builds an aggregated summary.

Never raises — all errors degrade gracefully.
"""
from __future__ import annotations

import logging
from pathlib import Path

from app.quality.report_locator import load_quality_report_for_part

logger = logging.getLogger(__name__)

# Severity keys in order of priority (matches QualityIssue model)
_SEVERITIES = ("critical", "error", "warning", "info")


def _count_issues_by_severity(issues: list) -> dict:
    """Count issues by severity from a list of issue dicts."""
    counts = {s: 0 for s in _SEVERITIES}
    if not isinstance(issues, list):
        return counts
    for issue in issues:
        if not isinstance(issue, dict):
            continue
        sev = str(issue.get("severity") or "").lower()
        if sev in counts:
            counts[sev] += 1
    return counts


def build_job_quality_summary(
    job_id: str,
    parts_info: list[dict],
    include_reports: bool = False,
) -> dict:
    """Build an aggregated quality summary for all parts of a job.

    Args:
        job_id: The job identifier.
        parts_info: List of dicts with at minimum:
            {part_no: int, video_path: str | Path | None}
            Additional keys are ignored.
        include_reports: When True, embed the full report dict under "report" key.

    Returns a structured summary dict. Never raises.
    """
    try:
        parts_out = []
        total_score = 0.0
        available_count = 0

        # Aggregate severity counts across all available parts
        agg_counts = {s: 0 for s in _SEVERITIES}

        if not isinstance(parts_info, list):
            parts_info = []

        for entry in parts_info:
            try:
                if not isinstance(entry, dict):
                    continue

                part_no_raw = entry.get("part_no")
                try:
                    part_no = int(part_no_raw)
                except (TypeError, ValueError):
                    part_no = None

                video_path_raw = entry.get("video_path")
                video_path: Path | None = None
                if video_path_raw:
                    try:
                        video_path = Path(str(video_path_raw))
                    except Exception:
                        video_path = None

                report: dict | None = None
                if part_no is not None and video_path is not None:
                    try:
                        report = load_quality_report_for_part(job_id, part_no, video_path)
                    except Exception:
                        report = None

                if report is not None:
                    score = None
                    try:
                        score = float(report.get("score") or 0.0)
                    except (TypeError, ValueError):
                        score = None

                    issues = report.get("issues") or []
                    sev_counts = _count_issues_by_severity(issues)
                    issue_count = len(issues) if isinstance(issues, list) else 0

                    part_entry: dict = {
                        "part_no": part_no,
                        "available": True,
                        "score": score,
                        "issue_count": issue_count,
                        "critical_count": sev_counts["critical"],
                        "error_count": sev_counts["error"],
                        "warning_count": sev_counts["warning"],
                        "info_count": sev_counts["info"],
                    }
                    if include_reports:
                        part_entry["report"] = report
                    else:
                        part_entry["report"] = None

                    # Accumulate for summary
                    if score is not None:
                        total_score += score
                        available_count += 1
                    for sev in _SEVERITIES:
                        agg_counts[sev] += sev_counts[sev]

                else:
                    part_entry = {
                        "part_no": part_no,
                        "available": False,
                        "score": None,
                        "issue_count": 0,
                        "critical_count": 0,
                        "error_count": 0,
                        "warning_count": 0,
                        "info_count": 0,
                        "report": None,
                    }

                parts_out.append(part_entry)

            except Exception as part_exc:
                logger.debug("report_summary: part processing failed: %s", part_exc)
                # Add a minimal unavailable entry to preserve part_no when available
                try:
                    pn = int(entry.get("part_no")) if isinstance(entry, dict) else None
                except Exception:
                    pn = None
                parts_out.append({
                    "part_no": pn,
                    "available": False,
                    "score": None,
                    "issue_count": 0,
                    "critical_count": 0,
                    "error_count": 0,
                    "warning_count": 0,
                    "info_count": 0,
                    "report": None,
                })

        # Compute average score from available parts only
        average_score: float | None = None
        if available_count > 0:
            try:
                average_score = round(total_score / available_count, 1)
            except Exception:
                average_score = None

        summary = {
            "available_parts": available_count,
            "total_parts": len(parts_out),
            "average_score": average_score,
            "critical_count": agg_counts["critical"],
            "error_count": agg_counts["error"],
            "warning_count": agg_counts["warning"],
            "info_count": agg_counts["info"],
        }

        return {
            "job_id": job_id,
            "parts": parts_out,
            "summary": summary,
        }

    except Exception as exc:
        logger.warning("report_summary: build_job_quality_summary failed: %s", exc)
        return {
            "job_id": job_id,
            "parts": [],
            "summary": {
                "available_parts": 0,
                "total_parts": 0,
                "average_score": None,
                "critical_count": 0,
                "error_count": 0,
                "warning_count": 0,
                "info_count": 0,
            },
        }
