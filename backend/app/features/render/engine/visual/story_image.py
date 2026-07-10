"""
story_image.py — Story Mode image generation via OpenAI gpt-image-1 (P3).

Kept SEPARATE from Content Mode's provider_ai_image.py (which serves the
SceneVisualRequest seam and is Imagen/DALL-E oriented) so Content is never
touched. Story needs two things Content's provider does not carry per request:
  1. a per-shot QUALITY TIER (low/medium/high → gpt-image-1 ``quality``), and
  2. REFERENCE IMAGES (a character's pinned reference sheet) fed to gpt-image-1's
     image-edit endpoint so the same character looks consistent across shots.

Opt-in + graceful (Sacred Contract #3 spirit): needs the openai SDK + a key. With
no SDK / no key / any API error it returns None → the caller falls back to a local
background. Never raises. Results are cached by (prompt, size, quality, refs).
"""
from __future__ import annotations

import base64
import logging
import os
from pathlib import Path
from typing import Optional

from app.features.render.engine.visual import cache_key, visual_cache_dir

logger = logging.getLogger("app.render.visual.story_image")

# gpt-image-1 quality tier per shot importance (§7 decision 5). "auto" left to the
# model. establishing→low, medium→medium, close_up/hero→high (set on the Shot).
_QUALITY_TIERS = ("low", "medium", "high", "auto")


def _model() -> str:
    """gpt-image-1 model id. Override via STORY_IMAGE_MODEL. Never raises."""
    return (os.getenv("STORY_IMAGE_MODEL", "gpt-image-1").strip() or "gpt-image-1")


def _openai_client():
    """Return an OpenAI client, or None when no key / no SDK. Never raises."""
    key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not key:
        logger.info("story_image: no OPENAI_API_KEY — skipping gpt-image-1")
        return None
    try:
        from openai import OpenAI  # lazy — optional dep
        return OpenAI(api_key=key, timeout=120)
    except Exception as exc:
        logger.info("story_image: openai SDK unavailable (%s)", exc)
        return None


def _size(w: int, h: int) -> str:
    """Nearest gpt-image-1 supported size for the target canvas."""
    try:
        w, h = int(w or 0), int(h or 0)
    except Exception:
        return "1024x1024"
    if h > w:
        return "1024x1536"
    if w > h:
        return "1536x1024"
    return "1024x1024"


def _norm_tier(tier: str) -> str:
    t = (tier or "").strip().lower()
    return t if t in _QUALITY_TIERS else "medium"


def generate_image_bytes(
    prompt: str,
    width: int,
    height: int,
    quality: str = "medium",
    reference_paths: "Optional[list[str]]" = None,
    negative: str = "",
) -> Optional[bytes]:
    """Generate one PNG via gpt-image-1. When ``reference_paths`` has usable files,
    the image-EDIT endpoint conditions generation on them (character consistency);
    otherwise the plain generate endpoint is used. Returns bytes or None. Never
    raises."""
    client = _openai_client()
    if client is None:
        return None
    p = (prompt or "").strip()
    if not p:
        return None
    if (negative or "").strip():
        p = f"{p}. Avoid: {negative.strip()}"
    try:
        model = _model()
        size = _size(width, height)
        q = _norm_tier(quality)
        refs = [r for r in (reference_paths or []) if r and Path(r).exists() and Path(r).stat().st_size > 0]
        if refs:
            files = [open(r, "rb") for r in refs[:4]]  # cap references
            try:
                resp = client.images.edit(model=model, image=files, prompt=p, size=size)
            finally:
                for f in files:
                    try:
                        f.close()
                    except Exception:
                        pass
        else:
            resp = client.images.generate(model=model, prompt=p, size=size, quality=q)
        b64 = resp.data[0].b64_json
        return base64.b64decode(b64) if b64 else None
    except Exception as exc:
        logger.info("story_image: gpt-image-1 generation failed: %s", exc)
        return None


def _reference_paths_for_shot(shot, bible) -> "list[str]":
    """Collect pinned reference-sheet paths for the characters present in a shot."""
    out: list[str] = []
    if bible is None:
        return out
    try:
        for cid in (getattr(shot, "characters", None) or []):
            c = bible.character(cid)
            ref = (getattr(c, "reference_image_path", "") or "").strip() if c is not None else ""
            if ref and Path(ref).exists() and ref not in out:
                out.append(ref)
    except Exception:
        pass
    return out


def generate_shot_image(
    shot,
    bible,
    art_style: str,
    width: int,
    height: int,
    out_path: str,
    variant: int = 0,
) -> Optional[str]:
    """Generate the image for one Shot → ``out_path``. Uses the shot's quality_tier
    + any present character's reference sheet (consistency). Returns the written
    path or None (→ caller falls back to a local background). Cached by
    (prompt, size, quality, refs, variant). Never raises.

    ``variant`` (>0) nudges the prompt + cache key so a Vision-QA-rejected image is
    REGENERATED as a genuinely different take rather than served from cache."""
    try:
        prompt = (getattr(shot, "visual_prompt", "") or "").strip()
        if not prompt:
            return None
        if (art_style or "").strip():
            prompt = f"{prompt}, {art_style.strip()} style"
        if variant and variant > 0:
            prompt = f"{prompt}. (alternative composition {variant})"
        tier = _norm_tier(getattr(shot, "quality_tier", "medium"))
        refs = _reference_paths_for_shot(shot, bible)
        w, h = int(width), int(height)
        # Cache: same prompt+size+tier+refs+variant → generated once (cost control).
        ckey = cache_key("story_image", _model(), prompt, w, h, tier, "|".join(refs), variant)
        cached = visual_cache_dir() / f"{ckey}.png"
        if cached.exists() and cached.stat().st_size > 0:
            _copy(cached, out_path)
            return out_path
        data = generate_image_bytes(
            prompt, w, h, quality=tier, reference_paths=refs,
            negative=(getattr(shot, "negative_prompt", "") or ""),
        )
        if not data:
            return None
        cached.write_bytes(data)
        if not (cached.exists() and cached.stat().st_size > 0):
            return None
        _copy(cached, out_path)
        return out_path
    except Exception as exc:
        logger.info("story_image: generate_shot_image error %s", exc)
        return None


def _copy(src, dst: str) -> None:
    try:
        import shutil
        Path(dst).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src), dst)
    except Exception as exc:
        logger.info("story_image: copy failed %s", exc)


def _pollinations_visual(visual, art_style: str, width: int, height: int,
                         out_path: str, seed: int) -> Optional[str]:
    """FREE image path (Phase 2) — generate ONE Visual via Pollinations/Flux and copy
    it to ``out_path``. No reference-image conditioning (URL API), so this is the
    draft/low-cost provider. Returns the path or None. Never raises."""
    try:
        prompt = (getattr(visual, "prompt", "") or "").strip()
        if not prompt:
            return None
        from app.features.render.engine.visual import SceneVisualRequest
        from app.features.render.engine.visual.provider_pollinations import resolve_pollinations
        req = SceneVisualRequest(
            scene_index=0, kind="image", value="", prompt=prompt,
            width=int(width), height=int(height), fps=30.0, duration_sec=0.0,
            work_dir="", negative_prompt=(getattr(visual, "negative_prompt", "") or ""),
            style=(art_style or ""), seed=int(seed or 0),
        )
        asset = resolve_pollinations(req)
        src = getattr(asset, "value", "") if asset is not None else ""
        if not src or not Path(src).exists() or Path(src).stat().st_size <= 0:
            return None
        _copy(src, out_path)
        return out_path if (Path(out_path).exists() and Path(out_path).stat().st_size > 0) else None
    except Exception as exc:
        logger.info("story_image: pollinations visual error %s", exc)
        return None


def generate_visual_image(
    visual,
    refs: "dict[str, str] | None",
    art_style: str,
    width: int,
    height: int,
    out_path: str,
    seed: int = 0,
    provider: str = "gpt_image",
) -> Optional[str]:
    """Story v2 — generate the image for ONE Visual → ``out_path``.

    ``provider`` (Phase 2): "gpt_image" (default — gpt-image-1, character-consistent
    via the reference sheets in ``refs``, paid) or "pollinations" (free Flux, $0, no
    reference conditioning). Returns the written path or None (→ caller falls back to
    a local background). gpt_image is cached by (prompt, size, tier, refs, seed);
    pollinations by its own (prompt, size, seed). Never raises."""
    if (provider or "").strip().lower() == "pollinations":
        return _pollinations_visual(visual, art_style, width, height, out_path, seed)
    try:
        prompt = (getattr(visual, "prompt", "") or "").strip()
        if not prompt:
            return None
        if (art_style or "").strip():
            prompt = f"{prompt}, {art_style.strip()} style"
        from app.features.render.engine.visual.story_decision import clamp_tier
        tier = clamp_tier(getattr(visual, "tier", "medium"))
        refs = refs or {}
        # Character refs first (primary consistency), then the environment ref (G6) so
        # the location stays consistent too; capped downstream at 4 by image-edit.
        _ref_ids = list(getattr(visual, "character_ids", None) or [])
        _sid = (getattr(visual, "setting_id", "") or "").strip()
        if _sid:
            _ref_ids.append(_sid)
        ref_paths = [refs[c] for c in _ref_ids
                     if refs.get(c) and Path(refs[c]).exists() and Path(refs[c]).stat().st_size > 0]
        w, h = int(width), int(height)
        ckey = cache_key("story_visual", _model(), prompt, w, h, tier, "|".join(ref_paths), seed)
        cached = visual_cache_dir() / f"{ckey}.png"
        if cached.exists() and cached.stat().st_size > 0:
            _copy(cached, out_path)
            return out_path
        data = generate_image_bytes(
            prompt, w, h, quality=tier, reference_paths=ref_paths,
            negative=(getattr(visual, "negative_prompt", "") or ""),
        )
        if not data:
            return None
        cached.write_bytes(data)
        if not (cached.exists() and cached.stat().st_size > 0):
            return None
        _copy(cached, out_path)
        return out_path
    except Exception as exc:
        logger.info("story_image: generate_visual_image error %s", exc)
        return None


__all__ = ["generate_image_bytes", "generate_shot_image", "generate_visual_image", "_openai_client"]
