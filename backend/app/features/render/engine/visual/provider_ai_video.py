"""
provider_ai_video.py — AI-video Visual Generator provider (CS-G / Veo, online, opt-in).

Given a scene's ``visual_prompt``, generates a short video clip with Google Veo
(google-genai ``generate_videos`` long-running operation) and returns it as a
``video`` asset. The render composites it as a video background (looped / cut to
the scene duration by content_background), so Ken Burns is not applied.

Opt-in + graceful: needs the google-genai SDK + GEMINI_API_KEY. With no SDK, no
key, a timeout, or any error it returns None → the seam falls back to the local
provider. Never raises (Sacred Contract #3 spirit). Cached by (prompt, size) so
an identical prompt is generated once (Veo is slow + costly).

Note: Veo generation is a minutes-long async op; each scene using this provider
blocks on it. It is strictly opt-in (content_visual_provider="ai_video").
"""
from __future__ import annotations

import logging
import os
import time
from pathlib import Path
from typing import Optional

from app.features.render.engine.visual import (
    SceneVisualAsset, SceneVisualRequest, cache_key, download_to, visual_cache_dir,
)

logger = logging.getLogger("app.render.visual.ai_video")

_TIMEOUT = int(os.getenv("CONTENT_VEO_TIMEOUT", "300"))
_POLL = max(2, int(os.getenv("CONTENT_VEO_POLL", "10")))


def _veo_generate_to(prompt: str, w: int, h: int, out_path: str, cancel_check=None) -> bool:
    """Generate a Veo clip for ``prompt`` → ``out_path``. True on success, False on
    no key / no SDK / timeout / cancel / error. Never raises. ``cancel_check`` (if
    given) is polled each tick so a cancelled job aborts the minutes-long op."""
    try:
        key = (os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY") or "").strip()
        if not key:
            logger.info("visual.ai_video: no GEMINI_API_KEY — skipping Veo")
            return False
        from google import genai  # lazy — optional dep
        client = genai.Client(api_key=key)
        model = (os.getenv("CONTENT_VEO_MODEL", "veo-3.0-generate-001").strip()
                 or "veo-3.0-generate-001")
        aspect = "9:16" if h >= w else "16:9"
        try:
            from google.genai import types
            config = types.GenerateVideosConfig(aspect_ratio=aspect, number_of_videos=1)
        except Exception:
            config = {"aspect_ratio": aspect, "number_of_videos": 1}

        op = client.models.generate_videos(model=model, prompt=prompt, config=config)
        waited = 0
        while not getattr(op, "done", False) and waited < _TIMEOUT:
            if callable(cancel_check) and cancel_check():
                logger.info("visual.ai_video: cancelled — aborting Veo poll")
                return False
            time.sleep(_POLL)
            waited += _POLL
            try:
                op = client.operations.get(op)
            except Exception as e:
                logger.info("visual.ai_video: poll failed: %s", e)
                break
        if not getattr(op, "done", False):
            logger.info("visual.ai_video: Veo op not done within %ss", _TIMEOUT)
            return False

        resp = getattr(op, "response", None) or getattr(op, "result", None)
        vids = getattr(resp, "generated_videos", None) or []
        if not vids:
            return False
        video = getattr(vids[0], "video", None) or vids[0]

        # Prefer inline bytes (download the file handle first when needed).
        try:
            client.files.download(file=video)
        except Exception:
            pass
        data = getattr(video, "video_bytes", None)
        if data:
            Path(out_path).write_bytes(data)
            return Path(out_path).exists() and Path(out_path).stat().st_size > 0

        # Fallback: a URI to fetch.
        uri = getattr(video, "uri", None)
        if uri:
            return download_to(str(uri), out_path, timeout=min(120, _TIMEOUT))
        return False
    except Exception as exc:
        logger.info("visual.ai_video: Veo generation failed: %s", exc)
        return False


def resolve_ai_video(request: SceneVisualRequest) -> Optional[SceneVisualAsset]:
    """Generate an AI video for the scene from its visual_prompt. None on no key /
    no SDK / timeout / error (→ local fallback). Never raises."""
    try:
        prompt = (getattr(request, "prompt", "") or "").strip()
        if not prompt:
            return None
        w, h = int(request.width), int(request.height)
        cached = visual_cache_dir() / f"{cache_key('ai_video', prompt, w, h)}.mp4"
        if cached.exists() and cached.stat().st_size > 0:
            return SceneVisualAsset(kind="video", value=str(cached), provider="ai_video")
        if not _veo_generate_to(prompt, w, h, str(cached), cancel_check=getattr(request, "cancel_check", None)):
            return None
        if not (cached.exists() and cached.stat().st_size > 0):
            return None
        return SceneVisualAsset(kind="video", value=str(cached), provider="ai_video")
    except Exception as exc:
        logger.info("visual.ai_video: error %s", exc)
        return None
