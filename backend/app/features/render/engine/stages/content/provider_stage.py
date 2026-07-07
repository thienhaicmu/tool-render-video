"""
provider_stage.py — CU-8/9 per-scene visual-provider decision pre-pass (CM-6
extract). Deterministically picks the cheapest-sufficient provider per scene
under a per-render budget, and resolves the parallel-render worker cap. Pure
logic (no I/O); the budget tracker is returned so finalize can report spend.
"""
from __future__ import annotations

import os

from app.features.render.engine.visual.decision import BudgetTracker, decide_provider


def plan_scene_providers(payload, scenes, visual_provider: str):
    """Return ``(budget, scene_providers, max_workers)``:

    - ``budget`` — the BudgetTracker used for the decisions (cap from the payload,
      else CONTENT_AI_BUDGET env; 0 = unlimited). Returned so finalize can report
      the accumulated spend.
    - ``scene_providers`` — ``{1-based scene index: provider}``. Only ever
      DOWNGRADES the user's provider (never costs more).
    - ``max_workers`` — parallel scene-render cap: the payload's
      ``max_parallel_parts`` (clamped to CPU) if set, else
      ``min(CONTENT_MAX_PARALLEL, cpu)``.
    """
    budget = BudgetTracker(
        float(getattr(payload, "content_ai_budget", 0.0) or 0.0)
        or float(os.getenv("CONTENT_AI_BUDGET", "0") or 0)
    )
    scene_providers: dict[int, str] = {}
    for _si, _s in enumerate(scenes, start=1):
        scene_providers[_si] = decide_provider(
            _s, visual_provider, budget,
            float(getattr(_s, "est_duration_sec", 0.0) or 0.0),
        )

    try:
        _user_req = int(getattr(payload, "max_parallel_parts", 0) or 0)
    except Exception:
        _user_req = 0
    _cpu = os.cpu_count() or 4
    _cap = max(1, min(int(os.getenv("CONTENT_MAX_PARALLEL", "3") or 3), _cpu))
    max_workers = max(1, min(_user_req, _cpu)) if _user_req > 0 else _cap
    return budget, scene_providers, max_workers
