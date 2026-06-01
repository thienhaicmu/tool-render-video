"""
app/ai/quality/ — AI render quality evaluation. Phase 45.

Public API:
    evaluate_render_quality(outputs, edit_plan, context) -> AIRenderQualityEvaluation
    AIRenderQualityEvaluation, AIRenderQualityScore

Evaluation-only. Never mutates outputs. Never raises. No internet.
"""
try:
    from app.ai.quality.quality_evaluator import evaluate_render_quality
    from app.ai.quality.quality_schema import (
        AIRenderQualityEvaluation,
        AIRenderQualityScore,
    )
    _QUALITY_AVAILABLE = True
except ImportError:
    _QUALITY_AVAILABLE = False

__all__ = [
    "evaluate_render_quality",
    "AIRenderQualityEvaluation", "AIRenderQualityScore",
]
