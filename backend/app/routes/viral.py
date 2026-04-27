from __future__ import annotations

from typing import Optional
from fastapi import APIRouter
from pydantic import BaseModel
from app.services.viral_scoring import score_part_for_market, normalize_market

router = APIRouter(prefix="/api/viral", tags=["viral"])


class ScoreRequest(BaseModel):
    text: str
    duration: Optional[float] = None
    market: str = "US"


class MultiScoreRequest(BaseModel):
    text: str
    duration: Optional[float] = None


@router.post("/score")
def api_score(req: ScoreRequest):
    """Score text for viral potential in a specific market (US / EU / JP)."""
    return score_part_for_market(req.text, req.duration, req.market)


@router.post("/score/all")
def api_score_all(req: MultiScoreRequest):
    """Score text against all three markets and return combined results."""
    return {
        market: score_part_for_market(req.text, req.duration, market)
        for market in ("US", "EU", "JP")
    }
