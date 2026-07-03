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


def _apply_style(prompt: str, style: str) -> str:
    """Prepend a style hint to a prompt (CU-3). No-op when style is empty."""
    style = (style or "").strip()
    return f"{prompt}, {style} style" if style else prompt


def _gemini_image(prompt: str, negative: str = "", style: str = "", seed: int = 0) -> Optional[bytes]:
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
        _cfg: dict = {"number_of_images": 1}
        if (negative or "").strip():
            _cfg["negative_prompt"] = negative.strip()  # Imagen supports negative_prompt
        if seed and int(seed) > 0:
            _cfg["seed"] = int(seed)                     # CU-11: consistent look
        resp = client.models.generate_images(
            model=model, prompt=_apply_style(prompt, style),
            config=_cfg,
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


def _openai_image(prompt: str, w: int, h: int, negative: str = "", style: str = "") -> Optional[bytes]:
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
        # DALL-E has no negative-prompt param — fold "avoid" + style into the text.
        _p = _apply_style(prompt, style)
        if (negative or "").strip():
            _p = f"{_p}. Avoid: {negative.strip()}"
        resp = client.images.generate(model=model, prompt=_p, size=size, n=1, response_format="b64_json")
        import base64
        b64 = resp.data[0].b64_json
        return base64.b64decode(b64) if b64 else None
    except Exception as exc:
        logger.info("visual.ai_image: DALL-E generation failed: %s", exc)
        return None


# CU-10: media intelligence. When on, a vision model checks the generated image
# actually matches the prompt; a mismatch triggers a regenerate (up to a cap).
# Default OFF (a vision call per asset is extra cost/latency). Fail-open: if the
# check can't run, the image is accepted (never blocks a render on a flaky check).
_VERIFY_ON = os.getenv("CONTENT_VERIFY_ASSETS", "0") == "1"
_VERIFY_RETRY = max(0, int(os.getenv("CONTENT_VERIFY_MAX_RETRY", "1") or 1))


def _verify_image(path: str, prompt: str) -> bool:
    """CU-10 — ask a vision model whether the image matches the prompt. Returns
    True on match OR on any inability to check (fail-open); only an explicit NO
    returns False. Never raises."""
    try:
        key = (os.getenv("GEMINI_API_KEY") or "").strip()
        if not key:
            return True
        from google import genai
        from google.genai import types
        from pathlib import Path
        client = genai.Client(api_key=key)
        model = (os.getenv("CONTENT_VERIFY_MODEL", "gemini-2.5-flash").strip() or "gemini-2.5-flash")
        img = Path(path).read_bytes()
        resp = client.models.generate_content(
            model=model,
            contents=[
                types.Part.from_bytes(data=img, mime_type="image/png"),
                f"Does this image plausibly depict: {prompt}? Answer only YES or NO.",
            ],
        )
        ans = (getattr(resp, "text", "") or "").strip().upper()
        return not ans.startswith("NO")  # reject only on an explicit NO
    except Exception as exc:
        logger.info("visual.ai_image: verify unavailable (%s) — accepting", exc)
        return True


def resolve_ai_image(request: SceneVisualRequest) -> Optional[SceneVisualAsset]:
    """Generate an AI image for the scene from its visual_prompt. None on no key /
    no SDK / API error (→ local fallback). When CONTENT_VERIFY_ASSETS is on, a
    mismatch triggers a regenerate (with a varied seed) up to a cap. Never raises."""
    try:
        prompt = (getattr(request, "prompt", "") or "").strip()
        if not prompt:
            return None
        provider = (os.getenv("CONTENT_AI_IMAGE_PROVIDER", "").strip().lower() or "gemini")
        w, h = int(request.width), int(request.height)
        cached = visual_cache_dir() / f"{cache_key('ai_image', provider, prompt, w, h)}.png"
        if cached.exists() and cached.stat().st_size > 0:
            return SceneVisualAsset(kind="image", value=str(cached), provider="ai_image")

        negative = (getattr(request, "negative_prompt", "") or "").strip()
        style = (getattr(request, "style", "") or "").strip()
        base_seed = int(getattr(request, "seed", 0) or 0)

        attempts = 1 + (_VERIFY_RETRY if _VERIFY_ON else 0)
        for attempt in range(attempts):
            # Vary the seed on retries so a rejected image is not regenerated identically.
            seed = base_seed + attempt if base_seed else 0
            data = (
                _openai_image(prompt, w, h, negative, style) if provider == "openai"
                else _gemini_image(prompt, negative, style, seed)
            )
            if not data:
                return None
            cached.write_bytes(data)
            if not (cached.exists() and cached.stat().st_size > 0):
                return None
            if not _VERIFY_ON or _verify_image(str(cached), prompt):
                return SceneVisualAsset(kind="image", value=str(cached), provider="ai_image")
            logger.info("visual.ai_image: verify rejected image (attempt %d/%d) — regenerating",
                        attempt + 1, attempts)
        # All attempts exhausted — deliver the last image (fail-open, better than none).
        return SceneVisualAsset(kind="image", value=str(cached), provider="ai_image")
    except Exception as exc:
        logger.info("visual.ai_image: error %s", exc)
        return None
