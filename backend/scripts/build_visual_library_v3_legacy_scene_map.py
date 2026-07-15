"""Inventory legacy background files into the V3 scene identity contract.

This is an authored migration map, not a scene matcher. Style variants and
source files stay attached to one stable scene identity for later remastering.
"""
from __future__ import annotations

import hashlib
import json
import struct
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import (  # noqa: E402
    ArtifactSpec,
    SceneIdentitySpec,
    SceneTemplateSpec,
    ProvenanceSpec,
    VisualLibraryManifest,
    write_manifest,
)
from app.features.render.engine.visual.v2.theme_pack import REGIONAL_SCENE_STYLE_PACKS  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
LEGACY_ROOT = DATA / "asset_library" / "background"
OUTPUT = DATA / "visual_library_v3_legacy_scenes.json"
DEFAULT_STYLE = "legacy_default_v1"
JP_STYLES = ("jp_anime_cinematic_v1", "jp_anime_clean_v1", "jp_anime_soft_drama_v1")


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        return 0, 0
    return struct.unpack(">II", header[16:24])


def _sidecar(path: Path) -> dict:
    sidecar = path.with_suffix(path.suffix + ".json")
    try:
        return json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else {}
    except (OSError, ValueError):
        return {}


def _safe_id(*parts: str) -> str:
    value = "_".join("" if part is None else str(part) for part in parts).lower()
    value = "_".join(piece for piece in value.replace("-", "_").split("_") if piece)
    return value[:120] or "legacy_scene"


def _artifact(path: Path) -> ArtifactSpec:
    width, height = _png_size(path)
    return ArtifactSpec(
        path=path.relative_to(DATA).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        width=width,
        height=height,
        transparent=False,
    )


def _records() -> dict[tuple[str, str, str], list[tuple[Path, str, dict]]]:
    grouped: dict[tuple[str, str, str], list[tuple[Path, str, dict]]] = defaultdict(list)
    for path in sorted(LEGACY_ROOT.rglob("*.png")):
        rel = path.relative_to(DATA).parts
        if len(rel) < 4:
            continue
        region, genre, slug = rel[2], rel[3], path.stem
        style = rel[4] if len(rel) >= 6 else DEFAULT_STYLE
        grouped[(region, genre, slug)].append((path, style, _sidecar(path)))
    return grouped


def _safe_zones() -> dict:
    return {
        "16:9": {
            "subject": {"x": 0.16, "y": 0.08, "w": 0.68, "h": 0.78},
            "focal_point": {"x": 0.50, "y": 0.42},
            "subtitle": {"x": 0.06, "y": 0.82, "w": 0.88, "h": 0.13},
        },
        "9:16": {
            "subject": {"x": 0.08, "y": 0.08, "w": 0.84, "h": 0.70},
            "focal_point": {"x": 0.50, "y": 0.42},
            "subtitle": {"x": 0.08, "y": 0.80, "w": 0.84, "h": 0.14},
        },
        "1:1": {
            "subject": {"x": 0.10, "y": 0.08, "w": 0.80, "h": 0.76},
            "focal_point": {"x": 0.50, "y": 0.42},
            "subtitle": {"x": 0.08, "y": 0.82, "w": 0.84, "h": 0.12},
        },
    }


def build_manifest() -> VisualLibraryManifest:
    grouped = _records()
    styles = {DEFAULT_STYLE}
    for records in grouped.values():
        styles.update(style for _, style, _ in records)
    for region, _, _ in grouped:
        styles.update(REGIONAL_SCENE_STYLE_PACKS.get(region, ()))
    templates = tuple(
        SceneTemplateSpec(
            id=_safe_id("layered_scene_v1", style),
            version="0.1.0",
            style_id=style,
            renderer_id="visual_v3.scene",
            layer_slots=("background", "midground", "foreground", "lighting", "atmosphere"),
            supported_aspects=("16:9", "9:16", "1:1"),
            supported_shot_sizes=("wide", "medium", "close"),
            supported_times=("day", "sunset", "night"),
            supported_weather=("clear", "rain", "snow", "fog"),
        )
        for style in sorted(styles)
    )

    scenes = []
    aliases: dict[str, str] = {}
    slug_targets: dict[str, set[str]] = defaultdict(set)
    for (region, genre, slug), records in sorted(grouped.items()):
        identity_id = _safe_id(region, genre, slug)
        source_styles = tuple(sorted({style for _, style, _ in records}))
        default_style = "jp_anime_clean_v1" if "jp_anime_clean_v1" in source_styles else source_styles[0]
        primary_path, _, primary_sidecar = next(
            (record for record in records if record[1] == default_style), records[0]
        )
        legacy = tuple(_artifact(path) for path, _, _ in records)
        layers = {"background": _artifact(primary_path)}
        variants = tuple({
            "style_id": style,
            "artifact_path": next(path.relative_to(DATA).as_posix() for path, item_style, _ in records if item_style == style),
        } for style in source_styles)
        for path, _, _ in records:
            aliases[f"legacy/{path.relative_to(DATA).as_posix()}"] = identity_id
        slug_targets[slug].add(identity_id)
        name = str(primary_sidecar.get("name") or slug.replace("_", " ")).split("/")[0].strip()
        era = "historical" if genre in {"codai", "wuxia"} else "fantasy" if genre in {"fantasy", "xianxia"} else "modern"
        scenes.append(SceneIdentitySpec(
            id=identity_id,
            version="0.1.0",
            display_name=name,
            template_id=_safe_id("layered_scene_v1", default_style),
            style_id=default_style,
            compatible_style_ids=source_styles,
            region=region,
            era=era,
            scene_kind=slug,
            quality_state="draft",
            layers=layers,
            safe_zones=_safe_zones(),
            variants=variants,
            legacy_artifacts=legacy,
            provenance=ProvenanceSpec(
                source="legacy_asset_library",
                license=str(primary_sidecar.get("license") or "legacy-unverified"),
                author="legacy scene migration map",
            ),
        ))
    for slug, targets in sorted(slug_targets.items()):
        if len(targets) == 1:
            aliases[slug] = next(iter(targets))
    return VisualLibraryManifest(
        schema_version="3.0",
        library_id="story_visual_library_legacy_scenes",
        version="0.1.0",
        style_ids=tuple(sorted(styles)),
        scene_templates=templates,
        scenes=tuple(scenes),
        legacy_aliases=aliases,
    )


if __name__ == "__main__":
    manifest = build_manifest()
    write_manifest(manifest, OUTPUT)
    print(f"wrote {OUTPUT}")
    print(f"scenes={len(manifest.scenes)} legacy_artifacts={sum(len(item.legacy_artifacts) for item in manifest.scenes)} styles={len(manifest.style_ids)}")
