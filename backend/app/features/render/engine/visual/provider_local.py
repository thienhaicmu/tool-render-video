"""
provider_local.py — the "local" Visual Generator provider (Content Mode v1).

The user picks a background (solid color / still image / looping video); this
provider simply DECLARES that background as the scene's visual asset. It does no
network I/O and no asset generation — ``content_scene_render`` builds the actual
clip from the returned (kind, value). Fully offline.

This is the first concrete implementation of the ``engine.visual`` seam. A
future ``ai_image`` / ``stock`` / ``ai_video`` provider lives beside this file,
reads ``request.prompt``, and returns an asset with the same shape — so the
pipeline and scene renderer never change.

Sacred Contract #3 spirit: never raises. Bad input degrades to opaque black.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from app.features.render.engine.visual import SceneVisualAsset, SceneVisualRequest
from app.features.render.engine.stages.content_background import (
    KIND_COLOR, KIND_IMAGE, KIND_VIDEO,
)

logger = logging.getLogger("app.render.visual.local")

_VALID_KINDS = (KIND_COLOR, KIND_IMAGE, KIND_VIDEO)
_DEFAULT_COLOR = "#000000"


def resolve_local(request: SceneVisualRequest) -> Optional[SceneVisualAsset]:
    """Return the user-chosen background as this scene's visual asset. Never raises.

    - kind "color": ``value`` is a color (hex / named); always usable.
    - kind "image"/"video": ``value`` must be an existing asset path; if it is
      missing, degrade to a black color background so the render still produces a
      valid scene rather than failing (partial-quality > hard failure)."""
    try:
        kind = (getattr(request, "kind", "") or KIND_COLOR).strip().lower()
        value = (getattr(request, "value", "") or "").strip()
        if kind not in _VALID_KINDS:
            kind = KIND_COLOR

        if kind == KIND_COLOR:
            return SceneVisualAsset(kind=KIND_COLOR, value=(value or _DEFAULT_COLOR), provider="local")

        # image / video need a real asset on disk.
        if value and Path(value).exists() and Path(value).stat().st_size > 0:
            return SceneVisualAsset(kind=kind, value=value, provider="local")

        logger.warning(
            "visual.local: %s asset missing (%r) for scene %s — degrading to black color",
            kind, value, getattr(request, "scene_index", "?"),
        )
        return SceneVisualAsset(kind=KIND_COLOR, value=_DEFAULT_COLOR, provider="local")
    except Exception as exc:
        logger.warning("visual.local: resolve_local error %s — black fallback", exc)
        return SceneVisualAsset(kind=KIND_COLOR, value=_DEFAULT_COLOR, provider="local")
