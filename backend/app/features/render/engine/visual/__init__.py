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
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger("app.render.visual")

# Providers known to this seam. v1 = local only. Adding "ai_image" / "stock" /
# "ai_video" here + a branch in resolve_scene_visual is the ONLY change needed
# to introduce a new visual source — the pipeline + scene renderer are untouched.
SUPPORTED_PROVIDERS = ("local",)
DEFAULT_PROVIDER = "local"


@dataclass
class SceneVisualRequest:
    """What the pipeline knows about a scene's visual need, handed to a provider."""
    scene_index: int
    kind: str                 # local provider: "color" | "image" | "video"
    value: str                # color hex / asset path (local); ignored by AI providers
    prompt: str               # scene.visual_hint — the AI-authored visual description
    width: int
    height: int
    fps: float
    duration_sec: float
    work_dir: str


@dataclass
class SceneVisualAsset:
    """The resolved visual for a scene. ``kind`` maps 1:1 to
    ``content_scene_render.render_content_scene``'s background_kind, and ``value``
    to background_value — so every provider returns the same shape."""
    kind: str                 # "color" | "image" | "video"
    value: str                # color spec / asset path
    provider: str = "local"   # which provider produced it (observability)


def resolve_scene_visual(
    request: SceneVisualRequest,
    *,
    provider: str = DEFAULT_PROVIDER,
) -> Optional[SceneVisualAsset]:
    """Resolve one scene's visual to an asset via the named provider. Returns a
    SceneVisualAsset or None. Never raises (Sacred Contract #3 spirit).

    Unknown providers fall back to ``local`` so a stale/未来 config value can
    never break a render."""
    p = (provider or DEFAULT_PROVIDER).strip().lower()
    if p not in SUPPORTED_PROVIDERS:
        logger.warning("visual: provider %r not supported — falling back to 'local'", provider)
        p = "local"
    try:
        if p == "local":
            from app.features.render.engine.visual.provider_local import resolve_local
            return resolve_local(request)
        # Future providers (ai_image / stock / ai_video) branch here.
        from app.features.render.engine.visual.provider_local import resolve_local
        return resolve_local(request)
    except Exception as exc:
        logger.warning("visual: resolve_scene_visual(%s) error %s — no asset", p, exc)
        return None


__all__ = [
    "SceneVisualRequest", "SceneVisualAsset", "resolve_scene_visual",
    "SUPPORTED_PROVIDERS", "DEFAULT_PROVIDER",
]
