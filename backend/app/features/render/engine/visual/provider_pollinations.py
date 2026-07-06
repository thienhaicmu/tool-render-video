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
import random
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from app.features.render.engine.visual import (
    SceneVisualAsset, SceneVisualRequest, cache_key, visual_cache_dir,
)

logger = logging.getLogger("app.render.visual.pollinations")

_BASE = "https://image.pollinations.ai/prompt/"
_MODEL = (os.getenv("CONTENT_POLLINATIONS_MODEL", "flux").strip() or "flux")
_TIMEOUT = int(os.getenv("CONTENT_POLLINATIONS_TIMEOUT", "90") or 90)
# Cap the prompt so a very long visual_prompt can't blow the URL length. The head
# of the AI prompt carries the subject/setting (the story-critical part).
_MAX_PROMPT_CHARS = int(os.getenv("CONTENT_POLLINATIONS_MAX_PROMPT", "1200") or 1200)

# Retry/backoff — parallel scene rendering can burst several requests at once and
# Pollinations (a free service) answers 429. Retry ONLY transient 429/5xx with
# exponential backoff + jitter (honouring Retry-After), so a scene isn't dropped
# to a plain background just because of a momentary rate-limit. Tunable via env;
# 0 retries restores the old single-attempt behaviour.
_RETRIES = max(0, int(os.getenv("CONTENT_POLLINATIONS_RETRIES", "3") or 3))
_BACKOFF_BASE = max(0.2, float(os.getenv("CONTENT_POLLINATIONS_BACKOFF", "2.0") or 2.0))
_BACKOFF_MAX = max(1.0, float(os.getenv("CONTENT_POLLINATIONS_BACKOFF_MAX", "30") or 30))
_RETRY_CODES = frozenset({429, 500, 502, 503, 504})
try:
    _MAX_BYTES = int(os.getenv("CONTENT_MAX_ASSET_BYTES", str(25 * 1024 * 1024)))
except Exception:
    _MAX_BYTES = 25 * 1024 * 1024


def _retry_delay(err: "urllib.error.HTTPError | None", attempt: int) -> float:
    """Backoff seconds before the next attempt. Honours a Retry-After header when
    the server sends one (capped), else exponential backoff with jitter to
    de-sync parallel scene workers. Never raises."""
    try:
        hdrs = getattr(err, "headers", None)
        ra = hdrs.get("Retry-After") if hdrs is not None else None
        if ra:
            return min(_BACKOFF_MAX, max(0.5, float(ra)))
    except (TypeError, ValueError, AttributeError):
        pass
    base = min(_BACKOFF_MAX, _BACKOFF_BASE * (2 ** attempt))
    return base + random.uniform(0.0, base * 0.5)   # jitter


def _download_with_retry(
    url: str, out_path: str, timeout: int,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> bool:
    """Download ``url`` → ``out_path`` with bounded retry on transient 429/5xx.
    Returns True on a non-empty file, False otherwise. Never raises. A non-retryable
    error (e.g. 404) or a cancelled job stops immediately."""
    for attempt in range(_RETRIES + 1):
        if cancel_check is not None:
            try:
                if cancel_check():
                    return False
            except Exception:
                pass
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "AIVideoStudio/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (opt-in provider)
                try:
                    clen = int(resp.headers.get("Content-Length") or 0)
                except Exception:
                    clen = 0
                if clen and clen > _MAX_BYTES:
                    logger.info("visual.pollinations: asset too large (%d bytes) — skipping", clen)
                    return False
                data = resp.read(_MAX_BYTES + 1)
            if not data or len(data) > _MAX_BYTES:
                return False
            Path(out_path).write_bytes(data)
            return Path(out_path).exists() and Path(out_path).stat().st_size > 0
        except urllib.error.HTTPError as e:
            if e.code in _RETRY_CODES and attempt < _RETRIES:
                delay = _retry_delay(e, attempt)
                logger.info("visual.pollinations: HTTP %s — retry %d/%d in %.1fs",
                            e.code, attempt + 1, _RETRIES, delay)
                time.sleep(delay)
                continue
            logger.info("visual.pollinations: HTTP %s — giving up", e.code)
            return False
        except Exception as e:
            if attempt < _RETRIES:
                delay = _retry_delay(None, attempt)
                logger.info("visual.pollinations: %s — retry %d/%d in %.1fs",
                            type(e).__name__, attempt + 1, _RETRIES, delay)
                time.sleep(delay)
                continue
            logger.info("visual.pollinations: download failed (%s)", e)
            return False
    return False


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
        if not _download_with_retry(
            url, str(cached), timeout=_TIMEOUT,
            cancel_check=getattr(request, "cancel_check", None),
        ):
            return None
        if not (cached.exists() and cached.stat().st_size > 0):
            return None
        return SceneVisualAsset(kind="image", value=str(cached), provider="ai_image_free")
    except Exception as exc:
        logger.info("visual.pollinations: error %s", exc)
        return None
