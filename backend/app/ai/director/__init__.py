"""
app/ai/director/ — AI edit-plan orchestration.

Public API (import from here, not from sub-modules directly):
    create_ai_edit_plan(request, context) -> AIEditPlan | None
    AIEditPlan, AIClipPlan, AISubtitlePlan, AICameraPlan, AIPacingPlan
"""
# Heavy imports are guarded — this package is safe to import even when
# optional AI deps (torch, whisper, etc.) are absent. All public
# callables return None on failure (Contract 3).

try:
    from app.ai.director.ai_director import create_ai_edit_plan
    from app.ai.director.edit_plan_schema import (
        AIEditPlan,
        AIClipPlan,
        AISubtitlePlan,
        AICameraPlan,
        AIPacingPlan,
    )
    _DIRECTOR_AVAILABLE = True
except ImportError:
    _DIRECTOR_AVAILABLE = False

__all__ = [
    "create_ai_edit_plan",
    "AIEditPlan", "AIClipPlan", "AISubtitlePlan", "AICameraPlan", "AIPacingPlan",
]
