"""
routes/feedback.py — Clip feedback API (Phase 6) + Platform Metrics ingestion (Phase V1).

POST /api/feedback/jobs/{job_id}/parts/{part_no}  — submit or update a rating
GET  /api/feedback/jobs/{job_id}/parts/{part_no}  — get rating for one part
GET  /api/feedback/channel/{channel_code}          — list feedback for a channel
DELETE /api/feedback/jobs/{job_id}/parts/{part_no} — remove a rating
POST /api/feedback/platform-metrics               — ingest push-based platform data
GET  /api/feedback/platform-metrics/{channel_code} — aggregated platform performance

These routes are append-only from the UI perspective: the frontend POSTs when the
user clicks 👍/👎 and GETs to restore button state on reload.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.db.feedback_repo import (
    delete_clip_feedback,
    get_clip_feedback,
    list_feedback_for_channel,
    upsert_clip_feedback,
)
from app.db.platform_metrics_repo import (
    get_channel_platform_summary,
    list_platform_metrics,
    upsert_platform_metric,
)

router = APIRouter(prefix="/api/feedback", tags=["feedback"])
logger = logging.getLogger("app.routes.feedback")


# ── Request / Response schemas ────────────────────────────────────────────────

class FeedbackSubmit(BaseModel):
    rating: int = Field(..., description="1 = like, -1 = dislike")
    hook_type: str = Field("none", description="hook_type from the rendered part")
    clip_type: str = Field("unknown", description="clip_type from the rendered part")
    channel_code: str = Field("", description="channel this render belongs to")
    goal: str = Field("", description="render goal (viral/education/podcast/…)")
    start_sec: float = Field(0.0, ge=0.0)
    end_sec: float = Field(0.0, ge=0.0)
    duration_sec: float = Field(0.0, ge=0.0)


class FeedbackRecord(BaseModel):
    job_id: str
    part_no: int
    channel_code: str
    goal: str
    rating: int
    hook_type: str
    clip_type: str
    start_sec: float
    end_sec: float
    duration_sec: float
    rated_at: str


class ChannelFeedbackSummary(BaseModel):
    channel_code: str
    goal: str
    total: int
    liked: int
    disliked: int
    hook_type_scores: dict[str, float]   # hook_type → net score (likes - dislikes)
    avg_liked_position: Optional[float]  # 0-1, None if no liked clips with duration info


class PlatformMetricRecord(BaseModel):
    channel_code: str = Field(..., description="Channel identifier")
    platform: str = Field(..., description="tiktok / instagram / youtube / …")
    post_id: str = Field("", description="Platform-specific post ID (empty if unknown)")
    watch_pct: float = Field(0.0, ge=0.0, le=1.0, description="Average watch-through 0.0–1.0")
    ctr: float = Field(0.0, ge=0.0, le=1.0, description="Click-through rate 0.0–1.0")
    impressions: int = Field(0, ge=0, description="Raw impression count")
    recorded_at: str = Field("", description="ISO-8601 UTC when data was collected")


class PlatformMetricsBatchRequest(BaseModel):
    metrics: List[PlatformMetricRecord] = Field(..., min_length=1)


class PlatformMetricsSummaryResponse(BaseModel):
    channel_code: str
    platform: str
    avg_watch_pct: float
    avg_ctr: float
    platform_sample_size: int


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/parts/{part_no}", response_model=FeedbackRecord)
async def submit_feedback(job_id: str, part_no: int, body: FeedbackSubmit):
    """Submit or overwrite a rating for a rendered clip part."""
    if body.rating not in (1, -1):
        raise HTTPException(status_code=422, detail="rating must be 1 (like) or -1 (dislike)")

    ok = upsert_clip_feedback(
        job_id=job_id,
        part_no=part_no,
        channel_code=body.channel_code,
        goal=body.goal,
        rating=body.rating,
        hook_type=body.hook_type,
        clip_type=body.clip_type,
        start_sec=body.start_sec,
        end_sec=body.end_sec,
        duration_sec=body.duration_sec,
    )
    if not ok:
        raise HTTPException(status_code=500, detail="Failed to save feedback")

    record = get_clip_feedback(job_id, part_no)
    if record is None:
        raise HTTPException(status_code=500, detail="Feedback saved but could not be retrieved")
    return FeedbackRecord(**record)


@router.get("/jobs/{job_id}/parts/{part_no}", response_model=Optional[FeedbackRecord])
async def get_feedback(job_id: str, part_no: int):
    """Return the current rating for a rendered clip part, or null if not rated."""
    record = get_clip_feedback(job_id, part_no)
    if record is None:
        return None
    return FeedbackRecord(**record)


@router.delete("/jobs/{job_id}/parts/{part_no}", status_code=204)
async def remove_feedback(job_id: str, part_no: int):
    """Remove a rating (allows re-rating from neutral)."""
    delete_clip_feedback(job_id, part_no)


@router.get("/channel/{channel_code}", response_model=ChannelFeedbackSummary)
async def channel_feedback_summary(channel_code: str, goal: str = ""):
    """Return aggregated feedback stats for a channel (optionally filtered by goal)."""
    records = list_feedback_for_channel(channel_code, goal=goal, limit=500)

    liked = [r for r in records if r["rating"] == 1]
    disliked = [r for r in records if r["rating"] == -1]

    # Net score per hook_type: positive = liked more, negative = disliked more
    hook_scores: dict[str, float] = {}
    for r in records:
        ht = r.get("hook_type") or "none"
        hook_scores[ht] = hook_scores.get(ht, 0.0) + float(r["rating"])

    # Average relative position (start_sec / duration_sec) of liked clips
    avg_pos: Optional[float] = None
    pos_values = []
    for r in liked:
        dur = float(r.get("duration_sec") or 0.0)
        start = float(r.get("start_sec") or 0.0)
        if dur > 0:
            pos_values.append(start / dur)
    if pos_values:
        avg_pos = round(sum(pos_values) / len(pos_values), 3)

    return ChannelFeedbackSummary(
        channel_code=channel_code,
        goal=goal,
        total=len(records),
        liked=len(liked),
        disliked=len(disliked),
        hook_type_scores=hook_scores,
        avg_liked_position=avg_pos,
    )


# ── Platform Metrics (Phase V1) ───────────────────────────────────────────────

@router.post("/platform-metrics", status_code=201)
async def ingest_platform_metrics(body: PlatformMetricsBatchRequest):
    """Ingest push-based platform performance data (watch-time, CTR).

    Accepts a batch of metric records. External tools (Zapier, scripts) POST
    to this endpoint after collecting data from the platform's analytics API.
    No OAuth or platform credentials required — push-based only.
    """
    failed = 0
    for m in body.metrics:
        ok = upsert_platform_metric(
            channel_code=m.channel_code,
            platform=m.platform,
            post_id=m.post_id,
            watch_pct=m.watch_pct,
            ctr=m.ctr,
            impressions=m.impressions,
            recorded_at=m.recorded_at,
        )
        if not ok:
            failed += 1

    if failed == len(body.metrics):
        raise HTTPException(status_code=500, detail="All metric inserts failed")

    return {"ingested": len(body.metrics) - failed, "failed": failed}


@router.get(
    "/platform-metrics/{channel_code}",
    response_model=PlatformMetricsSummaryResponse,
)
async def get_platform_metrics_summary(channel_code: str, platform: str = ""):
    """Return aggregated platform performance summary for a channel."""
    summary = get_channel_platform_summary(channel_code, platform=platform)
    return PlatformMetricsSummaryResponse(
        channel_code=channel_code,
        platform=platform,
        avg_watch_pct=summary["avg_watch_pct"],
        avg_ctr=summary["avg_ctr"],
        platform_sample_size=summary["platform_sample_size"],
    )
