"""
story_decision.py — Story v2 quality-tier clamp.

The v1 per-shot asset decision + budget guard (decide_shot_asset / tier_cost) went
with the v1 pipeline (S1). What survives is ``clamp_tier`` — the cost cap Story v2's
image generation applies so a visual's quality tier never exceeds STORY_IMAGE_MAX_TIER.
Rule-based (no LLM), never raises.
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger("app.render.visual.story_decision")

_TIER_RANK = {"low": 0, "medium": 1, "high": 2}


def clamp_tier(tier: str, max_tier: "str | None" = None) -> str:
    """Story v2 — cap a visual's quality tier at STORY_IMAGE_MAX_TIER (env, default
    medium) so cost stays bounded. Unknown → medium. Never raises."""
    try:
        mt = (max_tier or os.getenv("STORY_IMAGE_MAX_TIER", "medium") or "medium").strip().lower()
        t = (tier or "medium").strip().lower()
        if t not in _TIER_RANK:
            t = "medium"
        if mt not in _TIER_RANK:
            mt = "medium"
        return t if _TIER_RANK[t] <= _TIER_RANK[mt] else mt
    except Exception:
        return "medium"


__all__ = ["clamp_tier"]
