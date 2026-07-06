"""
provider_pollinations.py — FREE AI-image Visual Generator (Pollinations.ai).

Generates an image for a scene from its AI-authored ``visual_prompt`` via
Pollinations' free, no-key URL API (Flux-based). Opt-in
(content_visual_provider="ai_image_free"): the scene's prompt is sent to a
THIRD-PARTY service, so it is never auto-selected.

Prompt fidelity (the whole point): the scene's ``visual_prompt`` is authored
per-frame by the AI Content Director, grounded in that scene's narration + the
Story Bible character canon (CU-6). This provider sends THAT prompt verbatim
(plus the plan's style + a light quality suffix, negatives folded in since
Pollinations has no negative param) — it does NOT rewrite/enhance it, so the
image stays faithful to the story beat.

Graceful: any error → None → the seam falls back to local. Never raises (Sacred
Contract #3 spirit). Cached by (model, prompt, size, seed) so an identical frame
is generated once. Stdlib only (via the shared download_to helper).
"""
from __future__ import annotations

import logging
import os
import urllib.parse
from typing import Optional

from app.features.render.engine.visual import (
    SceneVisualAsset, SceneVisualRequest, cache_key, download_to, visual_cache_dir,
)

logger = logging.getLogger("app.render.visual.pollinations")

_BASE = "https://image.pollinations.ai/prompt/"
_MODEL = (os.getenv("CONTENT_POLLINATIONS_MODEL", "flux").strip() or "flux")
_TIMEOUT = int(os.getenv("CONTENT_POLLINATIONS_TIMEOUT", "90") or 90)
# Cap the prompt so a very long visual_prompt can't blow the URL length. The head
# of the AI prompt carries the subject/setting (the story-critical part).
_MAX_PROMPT_CHARS = int(os.getenv("CONTENT_POLLINATIONS_MAX_PROMPT", "1200") or 1200)


def _build_prompt(request: SceneVisualRequest) -> str:
    """The per-frame, story-grounded prompt actually sent: the scene's
    ``visual_prompt`` (already narration + character grounded) + the plan style +
    a light quality suffix, with any negative folded in. Capped. Never raises."""
    try:
        base = (getattr(request, "prompt", "") or "").strip()
        if not base:
            return ""
        parts = [base]
        style = (getattr(request, "style", "") or "").strip()
        if style:
            parts.append(f"{style} style")
        parts.append("cinematic, highly detailed, sharp focus")
        neg = (getattr(request, "negative_prompt", "") or "").strip()
        if neg:
            parts.append(f"avoid: {neg}")
        return ", ".join(parts)[:_MAX_PROMPT_CHARS].rstrip()
    except Exception:
        return (getattr(request, "prompt", "") or "").strip()[:_MAX_PROMPT_CHARS]


def resolve_pollinations(request: SceneVisualRequest) -> Optional[SceneVisualAsset]:
    """Generate a free AI image for the scene from its visual_prompt. None on
    empty prompt / network / download error (→ local fallback). Never raises."""
    try:
        prompt = _build_prompt(request)
        if not prompt:
            return None
        w, h = int(request.width), int(request.height)
        seed = int(getattr(request, "seed", 0) or 0)
        cached = visual_cache_dir() / f"{cache_key('pollinations', _MODEL, prompt, w, h, seed)}.jpg"
        if cached.exists() and cached.stat().st_size > 0:
            return SceneVisualAsset(kind="image", value=str(cached), provider="ai_image_free")

        params: dict = {"width": w, "height": h, "model": _MODEL, "nologo": "true", "private": "true"}
        if seed > 0:
            params["seed"] = seed  # CU-11: stable seed → consistent subject across scenes
        url = _BASE + urllib.parse.quote(prompt, safe="") + "?" + urllib.parse.urlencode(params)
        if not download_to(url, str(cached), timeout=_TIMEOUT):
            return None
        if not (cached.exists() and cached.stat().st_size > 0):
            return None
        return SceneVisualAsset(kind="image", value=str(cached), provider="ai_image_free")
    except Exception as exc:
        logger.info("visual.pollinations: error %s", exc)
        return None
