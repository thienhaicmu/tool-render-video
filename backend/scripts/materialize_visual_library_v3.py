"""Package and materialize the portable Visual Library V3.

The repository stores manifests and deterministic render recipes, not generated
PNG binaries. Running this script on a clone recreates the same V3 artifacts
under ``data/`` and writes validated runtime manifests used by Story Mode.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual import svg_raster  # noqa: E402
from app.features.render.engine.visual.library_v3 import (  # noqa: E402
    ArtifactSpec,
    load_manifest,
    render_identity_master,
    validate_manifest,
    write_manifest,
)
from app.features.render.engine.visual.library_v3.registry import ManifestValidationError  # noqa: E402
from app.features.render.engine.visual.v2.anime_scene import build_anime_scene  # noqa: E402
from app.features.render.engine.visual.v2.theme_pack import REGIONAL_SCENE_STYLE_PACKS  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
PACKAGE = ROOT / "assets" / "visual_library_v3"
SOURCE_CHARACTERS = PACKAGE / "characters.json"
SOURCE_SCENES = PACKAGE / "scenes.json"
CHARACTER_OUTPUT = DATA / "visual_library_v3_legacy_characters_approved_pilot.json"
SCENE_OUTPUT = DATA / "visual_library_v3_legacy_scenes_approved_pilot.json"
CHARACTER_ARTIFACT_ROOT = DATA / "visual_library_v3" / "legacy_remastered"
SCENE_ARTIFACT_ROOT = DATA / "visual_library_v3" / "scenes"
WIDTH, CHAR_HEIGHT, SCENE_HEIGHT = 1024, 1536, 1024


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _artifact(path: Path, *, width: int, height: int, transparent: bool) -> ArtifactSpec:
    return ArtifactSpec(
        path=path.relative_to(DATA).as_posix(),
        sha256=_hash(path), width=width, height=height, transparent=transparent,
    )


def package_sources() -> None:
    """Copy current manifests into the tracked, binary-free package directory."""
    PACKAGE.mkdir(parents=True, exist_ok=True)
    for source, destination in (
        (DATA / "visual_library_v3_legacy_characters_approved_pilot.json", SOURCE_CHARACTERS),
        (DATA / "visual_library_v3_legacy_scenes_approved_pilot.json", SOURCE_SCENES),
    ):
        if not source.is_file():
            raise FileNotFoundError(f"missing source manifest: {source}")
        payload = json.loads(source.read_text(encoding="utf-8"))
        items_key = "characters" if "characters" in payload else "scenes"
        for item in payload.get(items_key, []):
            item["legacy_artifacts"] = []
        destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"packaged={destination}")


def _source(path: Path, fallback: Path) -> Path:
    return path if path.is_file() else fallback


def materialize_characters(source: Path, *, refresh: bool) -> Path:
    manifest = load_manifest(source, strict=False)
    updated = []
    for identity in manifest.characters:
        masters = []
        for master in identity.masters:
            out_dir = CHARACTER_ARTIFACT_ROOT / identity.id / "masters"
            out_dir.mkdir(parents=True, exist_ok=True)
            svg_path = out_dir / f"{master.framing}.svg"
            png_path = out_dir / f"{master.framing}.png"
            svg = render_identity_master(identity, framing=master.framing)
            if refresh or not svg_path.is_file():
                svg_path.write_text(svg, encoding="utf-8")
            if refresh or not png_path.is_file():
                if not svg_raster.save_svg_png(svg, png_path, WIDTH, CHAR_HEIGHT):
                    raise RuntimeError(f"unable to rasterize {identity.id}/{master.framing}")
            masters.append(replace(
                master,
                artifact=_artifact(svg_path, width=WIDTH, height=CHAR_HEIGHT, transparent=True),
                preview_artifact=_artifact(png_path, width=WIDTH, height=CHAR_HEIGHT, transparent=True),
            ))
        updated.append(replace(identity, masters=tuple(masters), legacy_artifacts=()))
    result = replace(manifest, characters=tuple(updated))
    errors = [item for item in validate_manifest(result, root=DATA) if item.severity == "error"]
    if errors:
        raise ManifestValidationError(errors)
    write_manifest(result, CHARACTER_OUTPUT)
    print(f"materialized=characters count={len(updated)} manifest={CHARACTER_OUTPUT}")
    return CHARACTER_OUTPUT


def _recipe(scene_kind: str, fallback: str = "") -> str:
    value = (scene_kind or "").strip().lower()
    if value.endswith("_night"):
        value = value[:-6]
    aliases = {
        "urban_street": "street", "engineering_lab": "laboratory",
        "family_living_room": "living_room",
    }
    return aliases.get(value.removeprefix("jp_"), fallback or value.removeprefix("jp_"))


def materialize_scenes(source: Path, *, refresh: bool) -> Path:
    manifest = load_manifest(source, strict=False)
    updated = []
    for scene in manifest.scenes:
        source_variants = list(scene.variants)
        if not source_variants:
            source_variants = [{"style_id": scene.style_id, "time": "day", "recipe": _recipe(scene.scene_kind)}]
        variants = []
        styles = tuple(REGIONAL_SCENE_STYLE_PACKS.get(scene.region, (scene.style_id or "legacy_default_v1",)))
        for raw in source_variants:
            style_id = str(raw.get("style_id") or scene.style_id or styles[0])
            recipe = str(raw.get("recipe") or _recipe(scene.scene_kind))
            tod = str(raw.get("time") or "day")
            out_dir = SCENE_ARTIFACT_ROOT / scene.id / style_id
            out_dir.mkdir(parents=True, exist_ok=True)
            svg_path = out_dir / "background.svg"
            png_path = out_dir / "background.png"
            svg = build_anime_scene(recipe, tod, style_id)
            if refresh or not svg_path.is_file():
                svg_path.write_text(svg, encoding="utf-8")
            if refresh or not png_path.is_file():
                if not svg_raster.save_svg_png(svg, png_path, 1536, SCENE_HEIGHT):
                    raise RuntimeError(f"unable to rasterize {scene.id}/{style_id}")
            variants.append({
                "style_id": style_id,
                "artifact_path": svg_path.relative_to(DATA).as_posix(),
                "preview_path": png_path.relative_to(DATA).as_posix(),
                "time": tod,
                "recipe": recipe,
            })
        default = next((item for item in variants if item["style_id"] == scene.style_id), variants[0])
        default_path = DATA / default["artifact_path"]
        updated.append(replace(
            scene,
            style_id=default["style_id"],
            compatible_style_ids=tuple(item["style_id"] for item in variants),
            layers={"background": _artifact(default_path, width=1536, height=SCENE_HEIGHT, transparent=False)},
            variants=tuple(variants),
            legacy_artifacts=(),
        ))
    result = replace(manifest, scenes=tuple(updated))
    errors = [item for item in validate_manifest(result, root=DATA) if item.severity == "error"]
    if errors:
        raise ManifestValidationError(errors)
    write_manifest(result, SCENE_OUTPUT)
    print(f"materialized=scenes count={len(updated)} manifest={SCENE_OUTPUT}")
    return SCENE_OUTPUT


def materialize(*, kind: str = "all", refresh: bool = False) -> None:
    package_sources()
    if kind in ("all", "characters"):
        materialize_characters(_source(SOURCE_CHARACTERS, CHARACTER_OUTPUT), refresh=refresh)
    if kind in ("all", "scenes"):
        materialize_scenes(_source(SOURCE_SCENES, SCENE_OUTPUT), refresh=refresh)


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize the portable Visual Library V3")
    parser.add_argument("--kind", choices=("all", "characters", "scenes"), default="all")
    parser.add_argument("--refresh", action="store_true", help="regenerate existing SVG/PNG artifacts")
    args = parser.parse_args()
    materialize(kind=args.kind, refresh=args.refresh)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
