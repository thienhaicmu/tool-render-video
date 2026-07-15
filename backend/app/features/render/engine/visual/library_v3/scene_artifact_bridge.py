"""Exact bridge from an active V3 scene identity to a raster preview."""
from __future__ import annotations

import os
from pathlib import Path

from .active_catalog import load_active_catalog


def resolve_scene_preview(
    identity_id: str,
    *,
    manifest_path: str | Path | None = None,
    style: str = "",
) -> str:
    source = manifest_path or os.getenv("STORY_V3_SCENE_MANIFEST", "")
    if not source:
        from .scene_matcher import scene_manifest_path
        source = scene_manifest_path()
    if not source:
        return ""
    try:
        source_path = Path(source)
        catalog = load_active_catalog(source_path)
        scene = catalog.scene((identity_id or "").strip())
        if scene is None:
            alias = catalog.resolve_legacy_alias(identity_id)
            scene = catalog.scene(alias or "")
        if scene is None:
            return ""
        variants = list(scene.variants)
        preferred = next((item for item in variants if style and item.get("style_id") == style), None)
        variant = preferred or (variants[0] if variants else {})
        raw = str(variant.get("preview_path") or variant.get("artifact_path") or "")
        if not raw:
            return ""
        candidate = (source_path.parent / raw).resolve()
        candidate.relative_to(source_path.parent.resolve())
        return str(candidate) if candidate.is_file() else ""
    except (OSError, ValueError):
        return ""


__all__ = ["resolve_scene_preview"]
