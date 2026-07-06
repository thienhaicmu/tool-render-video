"""
engine/visual — Visual Generator provider layer for Content Mode.

Architectural principle (Content Mode spec, 2026-07-03): the AI Director
(Gemini planning) is SEPARATE from the Visual Generator (asset creation). The
Render Engine "only receives an asset — it does not care how the asset was
produced." This seam is the single interface ``run_content`` calls per scene:

    resolve_scene_visual(request, provider="local") -> SceneVisualAsset | None

so a future provider (AI image / AI video / stock) plugs in WITHOUT touching
Content Mode's pipeline or the scene renderer.

v1 ships ONLY the ``local`` provider — the user-chosen background
(color / image / video), backed by ``stages/content_background.py``. It is
fully offline (no network, no API). The ``local`` provider does not
pre-generate a clip; it declares the background (kind + value) that
``content_scene_render`` then composites. A future ``ai_image`` provider would
instead read ``request.prompt`` (the scene's visual_hint authored by Gemini),
call its API, and return ``kind="image", value=<generated image path>`` — which
the scene renderer consumes IDENTICALLY. Same contract, no refactor.

Sacred Contract #3 spirit: ``resolve_scene_visual`` never raises. The local
provider always yields an asset (falling back to opaque black on bad input).
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("app.render.visual")

# Providers known to this seam. v1 = local only. Adding "ai_image" / "stock" /
# "ai_video" here + a branch in resolve_scene_visual is the ONLY change needed
# to introduce a new visual source — the pipeline + scene renderer are untouched.
SUPPORTED_PROVIDERS = ("local", "stock", "ai_image", "ai_video", "ai_image_free")
DEFAULT_PROVIDER = "local"
# Online providers (need network; some need an API key). They are opt-in — only
# used when content_visual_provider names them — and ALWAYS fall back to 'local'
# when they produce nothing (no key / no network / no result / error), so a scene
# never fails to get an asset. ``ai_image_free`` (Pollinations) needs network but
# NO key.
_ONLINE_PROVIDERS = ("stock", "ai_image", "ai_video", "ai_image_free")
# B2 — real-image providers eligible for stepped fallback (Veo excluded: a video
# provider failing should not spin up an unrelated image generation).
_IMAGE_PROVIDERS = ("stock", "ai_image", "ai_image_free")
# Free real-image sources tried (in order) before giving up to the plain local
# background, so a momentary 429 / missing key / error on the chosen source keeps
# a real image instead of a solid colour card.
_IMAGE_FALLBACK_POOL = ("ai_image_free", "stock")
_CONTENT_VISUAL_FALLBACK = os.getenv("CONTENT_VISUAL_FALLBACK", "1") == "1"


@dataclass
class SceneVisualRequest:
    """What the pipeline knows about a scene's visual need, handed to a provider."""
    scene_index: int
    kind: str                 # local provider: "color" | "image" | "video"
    value: str                # color hex / asset path (local); ignored by AI providers
    prompt: str               # scene.visual_prompt — the AI-authored visual description
    width: int
    height: int
    fps: float
    duration_sec: float
    work_dir: str
    # CU-3: things to AVOID (scene.negative_prompt) + an overall STYLE hint
    # (plan.video_style). Consumed by the AI-image / AI-video providers; ignored
    # by local/stock. "" = no constraint.
    negative_prompt: str = ""
    style: str = ""
    # CU-11: a stable generation seed (derived from the scene's character/style)
    # so a provider that supports_seed reproduces a consistent look across scenes.
    # 0 = no seed (provider chooses).
    seed: int = 0
    # MED-2: optional "is this job cancelled?" probe. A slow online provider
    # (e.g. Veo, minutes long) polls this to abort promptly on cancel. None =
    # no cancellation wiring (local + tests).
    cancel_check: Optional[Callable[[], bool]] = field(default=None)
    # Imagen tier override for the ai_image provider: ""|fast|standard|ultra.
    # "" = provider falls back to the CONTENT_IMAGEN_TIER env, then "standard".
    # Ignored by non-Imagen providers.
    imagen_tier: str = ""


@dataclass
class SceneVisualAsset:
    """The resolved visual for a scene. ``kind`` maps 1:1 to
    ``content_scene_render.render_content_scene``'s background_kind, and ``value``
    to background_value — so every provider returns the same shape."""
    kind: str                 # "color" | "image" | "video"
    value: str                # color spec / asset path
    provider: str = "local"   # which provider produced it (observability)


def _resolve_one(provider: str, request: "SceneVisualRequest") -> Optional["SceneVisualAsset"]:
    """Call ONE online provider by name → its asset or None. Lazy imports so an
    unused provider's optional deps never load. Never raises (Sacred #3 spirit)."""
    try:
        if provider == "stock":
            from app.features.render.engine.visual.provider_stock import resolve_stock
            return resolve_stock(request)
        if provider == "ai_image":
            from app.features.render.engine.visual.provider_ai_image import resolve_ai_image
            return resolve_ai_image(request)
        if provider == "ai_video":
            from app.features.render.engine.visual.provider_ai_video import resolve_ai_video
            return resolve_ai_video(request)
        if provider == "ai_image_free":
            from app.features.render.engine.visual.provider_pollinations import resolve_pollinations
            return resolve_pollinations(request)
    except Exception as exc:
        logger.info("visual: provider %s raised %s", provider, exc)
    return None


def resolve_scene_visual(
    request: SceneVisualRequest,
    *,
    provider: str = DEFAULT_PROVIDER,
) -> Optional[SceneVisualAsset]:
    """Resolve one scene's visual to an asset via the named provider. Returns a
    SceneVisualAsset or None. Never raises (Sacred Contract #3 spirit).

    Unknown providers fall back to ``local`` so a stale/未来 config value can
    never break a render."""
    from app.features.render.engine.visual.provider_local import resolve_local
    p = (provider or DEFAULT_PROVIDER).strip().lower()
    if p not in SUPPORTED_PROVIDERS:
        logger.warning("visual: provider %r not supported — falling back to 'local'", provider)
        p = "local"
    try:
        if p == "local":
            return resolve_local(request)
        # Chosen online provider first.
        asset = _resolve_one(p, request)
        if asset is not None:
            return asset
        # B2 — stepped fallback: before the plain local background, try the other
        # FREE real-image providers (Pollinations / stock) so a momentary failure
        # (429 / no key / error) on the chosen source still yields a REAL image.
        # Only for image providers; ai_video (Veo) goes straight to local. stock
        # without a key returns None instantly, so trying it is cheap.
        if _CONTENT_VISUAL_FALLBACK and p in _IMAGE_PROVIDERS:
            for fb in _IMAGE_FALLBACK_POOL:
                if fb == p:
                    continue
                asset = _resolve_one(fb, request)
                if asset is not None:
                    logger.info("visual: provider %s produced nothing — fell back to %s", p, fb)
                    return asset
        logger.info("visual: provider %s produced no asset — falling back to local", p)
        return resolve_local(request)
    except Exception as exc:
        logger.warning("visual: resolve_scene_visual(%s) error %s — local fallback", p, exc)
        try:
            return resolve_local(request)
        except Exception:
            return None


# ── Shared helpers for online providers (cache + download) ───────────────────

def visual_cache_dir():
    """Cache dir for provider-fetched/generated images (under the render cache
    root so the periodic subdir-agnostic prune reclaims it). Never raises."""
    from pathlib import Path
    try:
        from app.core.config import CACHE_DIR
        d = Path(CACHE_DIR) / "content_visual"
    except Exception:
        from app.core.config import TEMP_DIR
        d = Path(TEMP_DIR) / "content_visual"
    d.mkdir(parents=True, exist_ok=True)
    return d


def cache_key(*parts) -> str:
    """Stable sha1 of the given parts → a filename stem. Used so the same prompt
    at the same size is fetched/generated once and reused (cost control)."""
    import hashlib
    h = hashlib.sha1("|".join(str(x) for x in parts).encode("utf-8", "ignore")).hexdigest()
    return h[:24]


def download_to(url: str, out_path: str, timeout: int = 30) -> bool:
    """Download ``url`` → ``out_path`` (stdlib urllib, no new dependency). Returns
    True on a non-empty file, False on any error. Never raises.

    Review LOW-3: caps the download at CONTENT_MAX_ASSET_BYTES (default 25 MB) —
    both via the Content-Length header (early reject) and by reading at most
    cap+1 bytes — so a provider (or a compromised URL) can't fill the disk."""
    import os
    from pathlib import Path
    try:
        max_bytes = int(os.getenv("CONTENT_MAX_ASSET_BYTES", str(25 * 1024 * 1024)))
    except Exception:
        max_bytes = 25 * 1024 * 1024
    try:
        import urllib.request
        req = urllib.request.Request(url, headers={"User-Agent": "AIVideoStudio/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (opt-in provider)
            try:
                clen = int(resp.headers.get("Content-Length") or 0)
            except Exception:
                clen = 0
            if clen and clen > max_bytes:
                logger.info("visual: asset too large (%d > %d bytes) — skipping", clen, max_bytes)
                return False
            data = resp.read(max_bytes + 1)
        if not data or len(data) > max_bytes:
            logger.info("visual: asset exceeds cap (%d bytes) — skipping", max_bytes)
            return False
        Path(out_path).write_bytes(data)
        return Path(out_path).exists() and Path(out_path).stat().st_size > 0
    except Exception as exc:
        logger.info("visual: download failed (%s): %s", url[:80], exc)
        return False


__all__ = [
    "SceneVisualRequest", "SceneVisualAsset", "resolve_scene_visual",
    "SUPPORTED_PROVIDERS", "DEFAULT_PROVIDER",
    "visual_cache_dir", "cache_key", "download_to",
]
