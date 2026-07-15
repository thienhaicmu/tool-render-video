"""Exact V3 identity-to-artifact bridge for the existing compositor.

This bridge performs no matching. It accepts an already resolved active
identity, loads its manifest, and returns a verified raster preview path for a
requested framing. Keeping this separate makes runtime rollout reversible.
"""
from __future__ import annotations

import os
from pathlib import Path

from .active_catalog import ActiveCatalog, load_active_catalog


def resolve_character_preview(
    identity_id: str,
    *,
    manifest_path: str | Path | None = None,
    framing: str = "full_body",
) -> str:
    """Return an existing active character preview path, or ``""`` safely."""
    source = manifest_path or os.getenv("STORY_V3_CHARACTER_MANIFEST", "")
    if not source:
        from .planner_matcher import configured_manifest_path
        source = configured_manifest_path()
    if not source:
        return ""
    try:
        source_path = Path(source)
        catalog = load_active_catalog(source_path)
        target = catalog.character((identity_id or "").strip())
        if target is None:
            alias = catalog.resolve_legacy_alias(identity_id)
            target = catalog.character(alias or "")
        if target is None:
            return ""
        master = next((item for item in target.masters if item.framing == framing), None)
        master = master or next((item for item in target.masters if item.framing == "full_body"), None)
        if master is None:
            return ""
        artifact = master.preview_artifact if master.preview_artifact.path else master.artifact
        candidate = (source_path.parent / artifact.path).resolve()
        candidate.relative_to(source_path.parent.resolve())
        return str(candidate) if candidate.is_file() else ""
    except (OSError, ValueError):
        return ""


__all__ = ["resolve_character_preview"]
