"""Build a deterministic scene recipe/art-direction QA queue."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import load_manifest  # noqa: E402
from scripts.remaster_visual_library_v3_legacy_scenes import RECIPE_ALIASES, _recipe  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "data" / "visual_library_v3_legacy_scenes_remastered.json"
DEFAULT_OUTPUT = ROOT / "data" / "visual_library_v3_scene_artwork_queue.json"
OVERUSED_RECIPES = {"forest", "beach", "cafe", "shrine", "castle_hall"}


def _mode(scene_kind: str) -> tuple[str, str]:
    value = scene_kind.lower()
    for alias in RECIPE_ALIASES:
        if value.endswith(f"_{alias}"):
            return _recipe(scene_kind), f"family_alias:{alias}"
    return _recipe(scene_kind), "native"


def build_queue(manifest_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    rows = []
    recipe_counts = Counter(_recipe(item.scene_kind) for item in manifest.scenes)
    for item in manifest.scenes:
        recipe, mode = _mode(item.scene_kind)
        if mode != "native":
            priority = "P0"
            action = f"Author a dedicated {mode.split(':', 1)[1]} scene recipe; do not reuse {recipe}."
        elif recipe in OVERUSED_RECIPES and recipe_counts[recipe] >= 8:
            priority = "P1"
            action = f"Add regional geometry variation to the overused {recipe} recipe."
        else:
            priority = "P2"
            action = "Run framing, safe-zone and style contrast QA."
        rows.append({
            "id": item.id,
            "region": item.region,
            "scene_kind": item.scene_kind,
            "recipe": recipe,
            "recipe_mode": mode,
            "style_id": item.style_id,
            "quality_state": item.quality_state,
            "variants": len(item.variants),
            "priority": priority,
            "next_action": action,
        })
    rows.sort(key=lambda row: (row["priority"], row["recipe"], row["id"]))
    return {
        "manifest": manifest_path.as_posix(),
        "policy": "review means contract and artifact readiness; recipe quality still needs art-direction QA",
        "counts": dict(sorted(Counter(row["priority"] for row in rows).items())),
        "recipe_usage": dict(sorted(recipe_counts.items())),
        "items": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a V3 scene artwork QA queue")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.manifest.is_file():
        print(f"missing manifest: {args.manifest}")
        return 1
    report = build_queue(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")
    print(f"items={len(report['items'])} priorities={report['counts']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
