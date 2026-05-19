from fastapi import APIRouter
from pydantic import BaseModel
from app.services.db import get_creator_prefs, upsert_creator_prefs

router = APIRouter()


class _PrefsBody(BaseModel):
    prefs: dict = {}


@router.get("/api/creator/preferences")
def api_get_creator_prefs():
    return {"prefs": get_creator_prefs()}


@router.put("/api/creator/preferences")
def api_put_creator_prefs(body: _PrefsBody):
    saved = upsert_creator_prefs(body.prefs)
    return {"prefs": saved}


@router.get("/api/feedback/summary")
def api_get_feedback_summary():
    """Read-only summary of accumulated feedback patterns for the UI visibility layer.

    Reads feedback_memory.json. Returns zeros/unavailable when file is missing or
    corrupt — never raises.
    """
    try:
        from app.ai.feedback.feedback_memory import load_feedback_memory
        memory = load_feedback_memory()
        pattern_counts = memory.get("pattern_counts", {}) or {}
        total_exports = int(memory.get("total_exports", 0))
        total_signals = int(memory.get("total_signals", 0))

        exported_ranks = list(pattern_counts.get("exported_ranks", []))
        avg_rank = round(sum(exported_ranks) / len(exported_ranks), 1) if exported_ranks else 0.0

        def _top(cat: str) -> str:
            d = pattern_counts.get(cat, {})
            return max(d, key=lambda k: d[k]) if isinstance(d, dict) and d else ""

        return {
            "available": True,
            "total_signals": total_signals,
            "total_exports": total_exports,
            "avg_export_rank": avg_rank,
            "dominant_subtitle_style": _top("subtitle_style"),
            "dominant_pacing_style":   _top("pacing_style"),
            "dominant_creator_style":  _top("creator_style"),
            "biases_active": total_exports >= 3,
        }
    except Exception:
        return {"available": False, "total_exports": 0, "biases_active": False}
