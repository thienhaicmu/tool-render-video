"""
Content Studio API (CS-A) — planning endpoint.

The mandatory Review workflow needs a ContentPlan BEFORE rendering, so this
router exposes a plan-only step:

    POST /api/content/plan   {script, target_duration, voice_language, tone, …}
        → {"plan": <ContentPlan dict>}   (no render)

The FE Review screen then lets the user edit that plan and submit it to the
SHARED render pipeline via /api/render/process with
``render_format="content"`` + ``content_plan_override=<edited plan JSON>`` —
run_content renders FROM the approved plan and skips the AI call.

Later CS phases add narration-preview + asset endpoints to this same router.
Sacred Contract #3: select_content_plan already returns None on any failure;
here that surfaces as a clean 502 (no unhandled raise reaches the client).
"""
from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.features.render.ai.llm import select_content_plan

logger = logging.getLogger("app.content.api")

router = APIRouter(prefix="/api/content", tags=["content"])


class ContentPlanRequest(BaseModel):
    script: str = Field(default="", description="Raw script / article / news text")
    target_duration: int = 90
    voice_language: str = "vi-VN"
    tone: str = ""
    ai_provider: Optional[str] = None
    llm_model: Optional[str] = None


@router.post("/plan")
def generate_content_plan(req: ContentPlanRequest) -> dict:
    """Generate a ContentPlan from a script WITHOUT rendering (the Review step).

    Synchronous — a single AI Director call. Returns ``{"plan": <ContentPlan
    dict>}``. 422 when the script is empty; 502 when the AI produced no usable
    plan (e.g. missing API key / provider error — select_content_plan returned
    None per Sacred Contract #3)."""
    script = (req.script or "").strip()
    if not script:
        raise HTTPException(status_code=422, detail="script is required")

    from app.core import config as _cfg
    from app.features.render.engine.pipeline.llm_stage import _resolve_api_key

    provider = (req.ai_provider or "").strip().lower() or getattr(_cfg, "AI_PROVIDER_DEFAULT", "gemini")
    api_key, _ = _resolve_api_key(req, provider)
    plan = select_content_plan(
        provider=provider,
        script=script,
        target_duration_sec=float(req.target_duration or 90),
        target_language=(req.voice_language or "vi-VN"),
        tone=(req.tone or ""),
        api_key=api_key,
        model=req.llm_model,
    )
    if plan is None or plan.scene_count() == 0:
        raise HTTPException(status_code=502, detail="AI Content Director returned no usable plan")
    return {"plan": json.loads(plan.to_json())}
