"""
routes/prompt_preview.py — LLM Prompt Preview endpoint.

Phase R — LLM Prompt Preview.

POST /api/render/preview-prompt
    Build and return the LLM system + user prompts that WOULD be sent
    for a given render configuration — without launching a render job.

    Body accepts a subset of RenderRequest fields. Required:
        source_video_path (used to locate the SRT cache if available)
        OR srt_content (raw SRT text, bypasses file lookup)

    Optional:
        channel_code, hook_strength, video_type, ai_provider,
        output_count, ai_clip_min_duration_sec, ai_clip_max_duration_sec,
        target_duration, target_platform, language

    Response:
        {
          "system_prompt": "...",
          "user_prompt": "...",
          "editorial_hint": "...",
          "srt_chars": 1234,
          "truncated": false
        }

    If no SRT is available (no cache hit and no raw SRT provided) the
    response still returns the prompt structure with srt_content="".

Blast radius: LOW — new file, read-only. No render job created, no DB write,
no LLM call (prompt is built but not sent). Safe to call from the UI at any time.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.features.render.engine.pipeline.llm_stage import _build_editorial_hint
from app.features.render.ai.llm.prompts import build_render_plan_prompt, check_srt_truncation

logger = logging.getLogger("app.routes.prompt_preview")
router = APIRouter(prefix="/api/render", tags=["prompt-preview"])


class PromptPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    source_video_path: str = ""
    srt_content: str = Field("", description="Raw SRT text. When provided, bypasses cache lookup.")

    channel_code: str = "manual"
    hook_strength: str = "balanced"
    video_type: str = "auto"
    ai_provider: str = "gemini"
    output_count: int = Field(3, ge=1, le=20)
    ai_clip_min_duration_sec: float = Field(30.0, ge=1.0)
    ai_clip_max_duration_sec: float = Field(120.0, ge=1.0)
    target_duration: int = Field(0, ge=0)
    target_platform: str = ""
    language: str = "auto"


class PromptPreviewResponse(BaseModel):
    system_prompt: str
    user_prompt: str
    editorial_hint: str
    srt_chars: int
    truncated: bool


@router.post("/preview-prompt", response_model=PromptPreviewResponse)
def preview_prompt(body: PromptPreviewRequest) -> PromptPreviewResponse:
    """Return the LLM prompts that would be sent for the given config.

    No render job is created. No LLM call is made. Safe to call repeatedly.
    """
    srt_content = body.srt_content.strip()

    # If no raw SRT provided, try to find a cached transcription.
    if not srt_content and body.source_video_path:
        try:
            from app.features.render.engine.pipeline.pipeline_cache import (
                _transcription_cache_get,
            )
            cached = _transcription_cache_get(body.source_video_path, model_name="")
            if cached and isinstance(cached, str):
                srt_content = cached
        except Exception as exc:
            logger.debug("preview-prompt: cache lookup skipped: %s", exc)

    editorial_hint = ""
    try:
        editorial_hint = _build_editorial_hint(body)
    except Exception as exc:
        logger.warning("preview-prompt: editorial hint build failed: %s", exc)

    system_prompt = ""
    user_prompt = ""
    truncated = False

    if srt_content:
        try:
            trunc_info = check_srt_truncation(srt_content)
            truncated = trunc_info.get("truncated", False)
            system_prompt, user_prompt = build_render_plan_prompt(
                srt_content=srt_content,
                output_count=body.output_count,
                min_sec=body.ai_clip_min_duration_sec,
                max_sec=body.ai_clip_max_duration_sec,
                language=body.language,
                editorial_hint=editorial_hint,
                target_duration=body.target_duration,
                target_platform=body.target_platform,
            )
        except Exception as exc:
            logger.warning("preview-prompt: prompt build failed: %s", exc)
            system_prompt = f"[prompt build error: {exc}]"

    return PromptPreviewResponse(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        editorial_hint=editorial_hint,
        srt_chars=len(srt_content),
        truncated=truncated,
    )
