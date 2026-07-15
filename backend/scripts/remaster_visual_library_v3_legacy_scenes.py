"""Remaster selected legacy scenes with the offline layered scene renderer."""
from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual import svg_raster  # noqa: E402
from app.features.render.engine.visual.library_v3 import (  # noqa: E402
    ArtifactSpec,
    load_manifest,
    validate_manifest,
    write_manifest,
)
from app.features.render.engine.visual.v2.anime_scene import SCENES, build_anime_scene  # noqa: E402
from app.features.render.engine.visual.v2.theme_pack import REGIONAL_SCENE_STYLE_PACKS  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SOURCE = DATA / "visual_library_v3_legacy_scenes.json"
DEFAULT_OUTPUT = DATA / "visual_library_v3_legacy_scenes_remastered.json"
OUTPUT_ROOT = DATA / "visual_library_v3" / "scenes"
JP_STYLES = ("jp_anime_clean_v1", "jp_anime_cinematic_v1", "jp_anime_soft_drama_v1")
WIDTH, HEIGHT = 1536, 1024

RECIPE_ALIASES = {}


def _artifact(path: Path) -> ArtifactSpec:
    return ArtifactSpec(
        path=path.relative_to(DATA).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        width=WIDTH,
        height=HEIGHT,
        transparent=False,
    )


def _recipe(scene_kind: str) -> str:
    value = (scene_kind or "").strip().lower()
    if value.endswith("_night"):
        value = value[:-6]
    for candidate in SCENES:
        if value == candidate or value.endswith(f"_{candidate}"):
            return candidate
    aliases = {
        "urban_street": "street",
        "engineering_lab": "laboratory",
        "family_living_room": "living_room",
        **RECIPE_ALIASES,
    }
    stripped = value.removeprefix("jp_")
    if stripped in aliases:
        return aliases[stripped]
    for alias, recipe in aliases.items():
        if value.endswith(f"_{alias}"):
            return recipe
    return ""


def _styles_for_region(region: str) -> tuple[str, ...]:
    return tuple(REGIONAL_SCENE_STYLE_PACKS.get(region, ("legacy_default_v1",)))


def _default_style(scene, styles: tuple[str, ...]) -> str:
    if scene.region == "cn":
        if "xianxia" in scene.scene_kind or "fantasy" in scene.scene_kind:
            return "cn_xianxia_ink_v1"
        if "ngontinh" in scene.scene_kind:
            return "cn_romance_soft_v1"
        return "cn_wuxia_cinematic_v1"
    return styles[0]


def remaster(*, region: str = "jp", limit: int = 0, output: Path = DEFAULT_OUTPUT,
             input_manifest: Path | None = None, refresh_previews: bool = False) -> Path:
    source = input_manifest or (output if output.is_file() else SOURCE)
    manifest = load_manifest(source)
    selected = [item for item in manifest.scenes if item.region == region and _recipe(item.scene_kind)]
    if limit:
        selected = selected[:max(0, int(limit))]
    selected_ids = {item.id for item in selected}
    updated = []
    for scene in manifest.scenes:
        if scene.id not in selected_ids:
            updated.append(scene)
            continue
        recipe = _recipe(scene.scene_kind)
        variants = []
        styles = _styles_for_region(scene.region)
        for style_id in styles:
            out_dir = OUTPUT_ROOT / scene.id / style_id
            out_dir.mkdir(parents=True, exist_ok=True)
            svg = build_anime_scene(recipe, "day", style_id)
            svg_path = out_dir / "background.svg"
            png_path = out_dir / "background.png"
            svg_path.write_text(svg, encoding="utf-8")
            if (refresh_previews or not png_path.is_file()) and not svg_raster.save_svg_png(svg, png_path, WIDTH, HEIGHT):
                raise RuntimeError(f"unable to rasterize {scene.id}/{style_id}")
            variants.append({
                "style_id": style_id,
                "artifact_path": svg_path.relative_to(DATA).as_posix(),
                "preview_path": png_path.relative_to(DATA).as_posix(),
                "time": "day",
                "recipe": recipe,
            })
        default_style = _default_style(scene, styles)
        clean = next(item for item in variants if item["style_id"] == default_style)
        clean_path = DATA / clean["artifact_path"]
        updated.append(replace(
            scene,
            version="0.2.0",
            style_id=default_style,
            compatible_style_ids=styles,
            quality_state="review",
            layers={"background": _artifact(clean_path)},
            variants=tuple(variants),
        ))

    result = replace(manifest, version="0.2.0", scenes=tuple(updated))
    errors = [issue for issue in validate_manifest(result, root=DATA) if issue.severity == "error"]
    if errors:
        details = "; ".join(f"{issue.location}: {issue.message}" for issue in errors)
        raise RuntimeError(f"remastered scene manifest failed validation: {details}")
    write_manifest(result, output)
    print(f"selected={len(selected)} review={sum(item.quality_state == 'review' for item in result.scenes)} output={output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Remaster V3 legacy scenes with layered SVG recipes")
    parser.add_argument("--region", default="jp")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--refresh-previews", action="store_true")
    args = parser.parse_args()
    remaster(region=args.region.strip().lower(), limit=args.limit, input_manifest=args.input,
             output=args.output, refresh_previews=args.refresh_previews)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
