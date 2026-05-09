"""
quality_evaluator.py — AI render quality evaluation orchestrator. Phase 45.

Public API:
    evaluate_render_quality(outputs, edit_plan=None, context=None)
        -> AIRenderQualityEvaluation

Rules:
- Evaluation-only: no file mutation, no render execution, no output deletion
- Cap at 20 outputs per call
- Never raises
- No internet, no cloud AI
- Deterministic
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.ai.quality.quality_schema import AIRenderQualityEvaluation, AIRenderQualityScore
from app.ai.quality.quality_scoring import score_render_quality

logger = logging.getLogger("app.ai.quality.evaluator")

_MAX_OUTPUTS = 20


def evaluate_render_quality(
    outputs: Any,
    edit_plan: Any = None,
    context: Optional[dict] = None,
) -> AIRenderQualityEvaluation:
    """Evaluate quality across all render outputs. Never raises.

    Args:
        outputs:   list of output metadata dicts (capped at 20)
        edit_plan: AIEditPlan (or None) with Phase 1–44 signals
        context:   Optional session context

    Returns:
        AIRenderQualityEvaluation with per-output scores and best_quality_output_id
    """
    try:
        return _evaluate(outputs, edit_plan, context)
    except Exception as exc:
        logger.debug("quality_evaluator_error: %s", exc)
        return AIRenderQualityEvaluation(
            available=True,
            enabled=False,
            warnings=[f"quality_evaluator_error:{type(exc).__name__}"],
        )


def _evaluate(
    outputs: Any,
    edit_plan: Any,
    context: Optional[dict],
) -> AIRenderQualityEvaluation:
    ctx = context or {}
    warnings: list[str] = []

    if not isinstance(outputs, list):
        outputs = []

    # Cap to prevent resource exhaustion
    if len(outputs) > _MAX_OUTPUTS:
        warnings.append(f"outputs_capped_at_{_MAX_OUTPUTS}")
        outputs = outputs[:_MAX_OUTPUTS]

    scored: List[AIRenderQualityScore] = []
    for output_meta in outputs:
        score = score_render_quality(output_meta, edit_plan=edit_plan, context=ctx)
        scored.append(score)

    # Select best by highest overall_score; prefer first on tie
    best_id = ""
    if scored:
        best = max(scored, key=lambda s: s.overall_score)
        best_id = best.output_id

    enabled = len(scored) > 0

    logger.debug(
        "ai_render_quality_evaluation_done outputs=%d best_id=%s",
        len(scored), best_id,
    )

    return AIRenderQualityEvaluation(
        available=True,
        enabled=enabled,
        evaluation_mode="evaluation_only",
        output_scores=scored,
        best_quality_output_id=best_id,
        warnings=warnings,
    )
