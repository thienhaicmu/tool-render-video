"""Promote an explicit, reviewable V3 art batch to ``active``.

This changes quality state only. It does not select assets, match Planner
output, or wire any runtime resolver.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import load_manifest, validate_manifest, write_manifest  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
CHARACTER_INPUT = DATA / "visual_library_v3_legacy_characters_remastered.json"
SCENE_INPUT = DATA / "visual_library_v3_legacy_scenes_remastered.json"


def approve(*, kind: str, region: str, limit: int, input_path: Path, output_path: Path) -> Path:
    manifest = load_manifest(input_path)
    items = list(manifest.characters if kind == "characters" else manifest.scenes)
    candidates = [item for item in items if item.region == region and item.quality_state == "review"]
    selected_ids = {item.id for item in candidates[:max(0, limit)]}
    updated = tuple(
        replace(item, quality_state="active") if item.id in selected_ids else item
        for item in items
    )
    result = replace(
        manifest,
        characters=updated if kind == "characters" else manifest.characters,
        scenes=updated if kind == "scenes" else manifest.scenes,
    )
    errors = [issue for issue in validate_manifest(result, root=DATA) if issue.severity == "error"]
    if errors:
        details = "; ".join(f"{issue.location}: {issue.message}" for issue in errors)
        raise RuntimeError(f"approval manifest failed validation: {details}")
    write_manifest(result, output_path)
    print(f"kind={kind} selected={len(selected_ids)} active={sum(item.quality_state == 'active' for item in updated)} output={output_path}")
    return output_path


def main() -> int:
    parser = argparse.ArgumentParser(description="Approve an explicit V3 pilot batch")
    parser.add_argument("--kind", choices=("characters", "scenes"), required=True)
    parser.add_argument("--region", default="jp")
    parser.add_argument("--limit", type=int, default=6)
    parser.add_argument("--input", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    default_input = CHARACTER_INPUT if args.kind == "characters" else SCENE_INPUT
    default_output = DATA / (
        "visual_library_v3_legacy_characters_approved_pilot.json"
        if args.kind == "characters" else "visual_library_v3_legacy_scenes_approved_pilot.json"
    )
    approve(
        kind=args.kind,
        region=args.region.strip().lower(),
        limit=args.limit,
        input_path=args.input or default_input,
        output_path=args.output or default_output,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
