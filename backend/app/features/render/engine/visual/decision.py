"""
decision.py — Visual provider Decision Tree + Budget guard (CU-8).

Deterministic "cheapest sufficient source" routing per scene, plus a per-render
budget cap so a long script can't run up an unbounded paid-API bill. Rule-based
(no LLM) — predictable, testable, and it only ever DOWNGRADES a paid choice, so
turning it on can never make a render cost MORE than the user asked for.

Order of preference (cheapest → richest):
    local (0) < stock (1) < ai_image (2) < ai_video/Veo (3)

Rules (in order):
  1. Explicit per-scene asset override → local (the user picked it).
  2. Job provider is offline (local) → local.
  3. No visual_prompt to generate from → local.
  4. The AI's asset_suggestion may DOWNGRADE (never upgrade): upload/local → local;
     stock → cap at stock.
  5. A short scene does not need a Veo clip → downgrade ai_video → ai_image.
  6. Budget: if the chosen provider would exceed the remaining cap, downgrade to
     the cheapest online tier that fits, else local.
"""
from __future__ import annotations

import logging
import os

from app.features.render.engine.visual.registry import get_manifest

logger = logging.getLogger("app.render.visual.decision")

# A Veo clip below this length is wasteful — an AI image + motion looks the same.
_VEO_MIN_SEC: float = max(0.0, float(os.getenv("CONTENT_VEO_MIN_SCENE_SEC", "6") or 6))

# Rough per-asset cost (relative units) for budget estimation. Override via env.
_COST = {
    "local": 0.0,
    "stock": float(os.getenv("CONTENT_COST_STOCK", "0") or 0),
    "ai_image": float(os.getenv("CONTENT_COST_AI_IMAGE", "0.04") or 0.04),
    "ai_video": float(os.getenv("CONTENT_COST_AI_VIDEO", "0.5") or 0.5),
}


def estimate_cost(provider: str) -> float:
    return _COST.get((provider or "").strip().lower(), 0.0)


class BudgetTracker:
    """Accumulates estimated paid-API spend across a render. cap<=0 → unlimited."""

    def __init__(self, cap: float = 0.0):
        self.cap = max(0.0, float(cap or 0.0))
        self.spent = 0.0

    def would_exceed(self, cost: float) -> bool:
        if self.cap <= 0:
            return False
        return (self.spent + max(0.0, cost)) > self.cap

    def add(self, cost: float) -> None:
        self.spent += max(0.0, cost)


def decide_provider(scene, job_provider: str, budget: "BudgetTracker | None" = None,
                    est_duration_sec: float = 0.0) -> str:
    """Return the provider to use for this scene. Deterministic; never raises."""
    try:
        # 1. Explicit per-scene override wins → local.
        src = (getattr(scene, "visual_source", "") or "").strip().lower()
        if src in ("color", "image", "video"):
            return "local"

        prov = (job_provider or "local").strip().lower()
        if not get_manifest(prov).online:
            return "local"

        # 3. Nothing to generate from → local.
        prompt = (getattr(scene, "visual_prompt", "") or getattr(scene, "visual_hint", "") or "").strip()
        if not prompt:
            return "local"

        # 4. AI suggestion may downgrade only.
        sug = (getattr(scene, "asset_suggestion", "") or "").strip().lower()
        if sug in ("upload", "local"):
            return "local"
        if sug == "stock" and prov in ("ai_image", "ai_video"):
            prov = "stock"

        # 5. Short scene → no Veo.
        if prov == "ai_video" and est_duration_sec and est_duration_sec < _VEO_MIN_SEC:
            prov = "ai_image"

        # 6. Budget guard — downgrade to the cheapest online tier that fits, else local.
        if budget is not None:
            if budget.would_exceed(estimate_cost(prov)):
                if prov != "stock" and get_manifest("stock").online and not budget.would_exceed(estimate_cost("stock")):
                    prov = "stock"
                    logger.info("visual.decision: budget → downgrade scene to stock")
                else:
                    logger.info("visual.decision: budget exhausted → scene falls back to local")
                    return "local"
            budget.add(estimate_cost(prov))
        return prov
    except Exception as exc:
        logger.info("visual.decision: error %s — local", exc)
        return "local"


__all__ = ["BudgetTracker", "estimate_cost", "decide_provider"]
