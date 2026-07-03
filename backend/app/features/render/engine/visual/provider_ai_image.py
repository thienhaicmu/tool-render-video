"""
provider_ai_image.py — AI-image Visual Generator provider (CS-G, online, opt-in).

Given a scene's ``visual_prompt``, generates an image with Gemini Imagen (default)
or OpenAI DALL-E and returns it as an ``image`` asset. Provider chosen by
CONTENT_AI_IMAGE_PROVIDER (gemini|openai).

Opt-in + graceful: needs the provider's SDK + API key. With no SDK, no key, or an
API error it returns None → the seam falls back to the local provider. Never
raises (Sacred Contract #3 spirit). Results are cached by (provider, prompt,
size) so an identical prompt is generated once (cost control).
"""
from __future__ import annotations

import logging
import os
from typing import Optional

from app.features.render.engine.visual import (
    SceneVisualAsset, SceneVisualRequest, cache_key, visual_cache_dir,
)

logger = logging.getLogger("app.render.visual.ai_image")


def _gemini_image(prompt: str) -> Optional[bytes]:
    """Generate a PNG via Gemini Imagen. Lazy SDK import; None on any failure."""
    try:
        key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not key:
            logger.info("visual.ai_image: no GEMINI_API_KEY — skipping Imagen")
            return None
        from google import genai  # lazy — optional dep
        client = genai.Client(api_key=key)
        model = (os.getenv("CONTENT_IMAGEN_MODEL", "imagen-3.0-generate-002").strip()
                 or "imagen-3.0-generate-002")
        resp = client.models.generate_images(
            model=model, prompt=prompt,
            config={"number_of_images": 1},
        )
        imgs = getattr(resp, "generated_images", None) or []
        if not imgs:
            return None
        img = getattr(imgs[0], "image", None)
        data = getattr(img, "image_bytes", None) if img is not None else None
        return data or None
    except Exception as exc:
        logger.info("visual.ai_image: Imagen generation failed: %s", exc)
        return None


def _openai_image(prompt: str, w: int, h: int) -> Optional[bytes]:
    """Generate a PNG via OpenAI images (DALL-E). Lazy SDK import; None on failure."""
    try:
        key = (os.getenv("OPENAI_API_KEY") or "").strip()
        if not key:
            logger.info("visual.ai_image: no OPENAI_API_KEY — skipping DALL-E")
            return None
        from openai import OpenAI  # lazy — optional dep
        client = OpenAI(api_key=key)
        size = "1024x1792" if h > w else ("1792x1024" if w > h else "1024x1024")
        model = (os.getenv("CONTENT_DALLE_MODEL", "dall-e-3").strip() or "dall-e-3")
        resp = client.images.generate(model=model, prompt=prompt, size=size, n=1, response_format="b64_json")
        import base64
        b64 = resp.data[0].b64_json
        return base64.b64decode(b64) if b64 else None
    except Exception as exc:
        logger.info("visual.ai_image: DALL-E generation failed: %s", exc)
        return None


def resolve_ai_image(request: SceneVisualRequest) -> Optional[SceneVisualAsset]:
    """Generate an AI image for the scene from its visual_prompt. None on no key /
    no SDK / API error (→ local fallback). Never raises."""
    try:
        prompt = (getattr(request, "prompt", "") or "").strip()
        if not prompt:
            return None
        provider = (os.getenv("CONTENT_AI_IMAGE_PROVIDER", "").strip().lower() or "gemini")
        w, h = int(request.width), int(request.height)
        cached = visual_cache_dir() / f"{cache_key('ai_image', provider, prompt, w, h)}.png"
        if cached.exists() and cached.stat().st_size > 0:
            return SceneVisualAsset(kind="image", value=str(cached), provider="ai_image")

        data = _openai_image(prompt, w, h) if provider == "openai" else _gemini_image(prompt)
        if not data:
            return None
        cached.write_bytes(data)
        if not (cached.exists() and cached.stat().st_size > 0):
            return None
        return SceneVisualAsset(kind="image", value=str(cached), provider="ai_image")
    except Exception as exc:
        logger.info("visual.ai_image: error %s", exc)
        return None
