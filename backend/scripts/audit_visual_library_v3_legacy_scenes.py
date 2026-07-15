"""Audit migrated V3 scene coverage without invoking matching or resolver code."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import load_manifest, validate_manifest  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "data" / "visual_library_v3_legacy_scenes_remastered.json"
DEFAULT_OUTPUT = ROOT / "data" / "visual_library_v3_legacy_scene_audit.json"


def audit(manifest_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    issues = validate_manifest(manifest, root=manifest_path.parent)
    scenes = list(manifest.scenes)
    variant_count = sum(len(item.variants) for item in scenes)
    variant_previews = sum(
        bool(variant.get("preview_path"))
        for item in scenes for variant in item.variants
    )
    return {
        "manifest": manifest_path.as_posix(),
        "schema_version": manifest.schema_version,
        "library_version": manifest.version,
        "scenes": len(scenes),
        "legacy_artifacts": sum(len(item.legacy_artifacts) for item in scenes),
        "variants": variant_count,
        "variant_previews": variant_previews,
        "by_region": dict(sorted(Counter(item.region for item in scenes).items())),
        "by_quality": dict(sorted(Counter(item.quality_state for item in scenes).items())),
        "by_style": dict(sorted(Counter(item.style_id for item in scenes).items())),
        "review_with_safe_zones": sum(
            item.quality_state == "review" and bool(item.safe_zones) for item in scenes
        ),
        "validation_errors": [
            {"code": issue.code, "location": issue.location, "message": issue.message}
            for issue in issues if issue.severity == "error"
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit V3 migrated scene coverage")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    if not args.manifest.is_file():
        print(f"missing manifest: {args.manifest}")
        return 1
    report = audit(args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {args.output}")
    return 1 if report["validation_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
