"""
story_decision.py — per-shot asset decision + budget guard (P3).

Deterministic "which source + which quality tier" for each Shot, plus a per-render
budget cap so a long chapter can't run up an unbounded gpt-image-1 bill. Rule-based
(no LLM) — predictable, testable; it only ever DOWNGRADES (cheaper tier / local),
so enabling the budget can never make a render cost MORE than requested.

Reuses Content's BudgetTracker (decision.py) — one budget abstraction across modes.
Kept separate from Content's decide_provider because Story routes on ``shot_type``
+ per-shot ``quality_tier`` (gpt-image-1) rather than Content's provider seam.

Order:
  1. Explicit local/pin override on the shot → honour it (user chose it).
  2. No visual_prompt to generate from → local.
  3. Tier = shot.quality_tier (already defaulted by shot_type at parse).
  4. Budget: if the tier's cost would exceed the remaining cap, downgrade to the
     cheapest tier that fits, else local.
"""
from __future__ import annotations

import logging
import os

from app.features.render.engine.visual.decision import BudgetTracker

logger = logging.getLogger("app.render.visual.story_decision")

# Rough gpt-image-1 per-image cost by quality tier (USD, approximate — override via
# env). Used only for the budget guard's relative downgrade decision.
_TIER_COST = {
    "low": float(os.getenv("STORY_COST_IMAGE_LOW", "0.011") or 0.011),
    "medium": float(os.getenv("STORY_COST_IMAGE_MEDIUM", "0.042") or 0.042),
    "high": float(os.getenv("STORY_COST_IMAGE_HIGH", "0.167") or 0.167),
    "auto": float(os.getenv("STORY_COST_IMAGE_MEDIUM", "0.042") or 0.042),
}
_TIER_ORDER = ("high", "medium", "low")  # richest → cheapest


def tier_cost(tier: str) -> float:
    return _TIER_COST.get((tier or "").strip().lower(), _TIER_COST["medium"])


def decide_shot_asset(shot, budget: "BudgetTracker | None" = None) -> "tuple[str, str]":
    """Return ``(asset_type, quality_tier)`` for a Shot. asset_type ∈
    {ai_image, local, pin}. Deterministic; never raises."""
    try:
        # 1. Explicit per-shot override → honour it (no generation).
        src = (getattr(shot, "visual_source", "") or "").strip().lower()
        atype = (getattr(shot, "asset_type", "") or "").strip().lower()
        if atype == "pin" or src in ("color", "image", "video"):
            return ("pin" if atype == "pin" else "local", getattr(shot, "quality_tier", "medium"))
        if atype == "local":
            return ("local", getattr(shot, "quality_tier", "medium"))

        # 2. Nothing to generate from → local.
        prompt = (getattr(shot, "visual_prompt", "") or "").strip()
        if not prompt:
            return ("local", getattr(shot, "quality_tier", "medium"))

        # 3. Tier from the shot (defaulted by shot_type at parse).
        tier = (getattr(shot, "quality_tier", "medium") or "medium").strip().lower()
        if tier not in _TIER_COST:
            tier = "medium"

        # 4. Budget guard — downgrade to the cheapest tier that fits, else local.
        if budget is not None:
            if budget.would_exceed(tier_cost(tier)):
                fit = None
                for t in _TIER_ORDER:
                    if not budget.would_exceed(tier_cost(t)):
                        fit = t
                        break
                if fit is None:
                    logger.info("story_decision: budget exhausted → shot falls back to local")
                    return ("local", tier)
                if fit != tier:
                    logger.info("story_decision: budget → downgrade tier %s→%s", tier, fit)
                    tier = fit
            budget.add(tier_cost(tier))
        return ("ai_image", tier)
    except Exception as exc:
        logger.info("story_decision: error %s — local", exc)
        return ("local", "medium")


__all__ = ["decide_shot_asset", "tier_cost", "BudgetTracker"]
