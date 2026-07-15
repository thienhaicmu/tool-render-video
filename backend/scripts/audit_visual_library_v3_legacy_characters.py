"""Audit migrated character coverage without invoking matching or resolver code."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import load_manifest, validate_manifest  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "data" / "visual_library_v3_legacy_characters_remastered.json"
DEFAULT_OUTPUT = ROOT / "data" / "visual_library_v3_legacy_character_audit.json"


def audit(manifest_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    issues = validate_manifest(manifest, root=manifest_path.parent)
    characters = list(manifest.characters)
    report = {
        "manifest": manifest_path.as_posix(),
        "schema_version": manifest.schema_version,
        "library_version": manifest.version,
        "characters": len(characters),
        "masters": sum(len(item.masters) for item in characters),
        "preview_artifacts": sum(
            bool(master.preview_artifact.path)
            for item in characters for master in item.masters
        ),
        "legacy_artifacts": sum(len(item.legacy_artifacts) for item in characters),
        "by_region": dict(sorted(Counter(item.region for item in characters).items())),
        "by_quality": dict(sorted(Counter(item.quality_state for item in characters).items())),
        "by_style": dict(sorted(Counter(item.style_id for item in characters).items())),
        "by_legacy_style": dict(sorted(Counter(
            style for item in characters for style in item.compatible_style_ids
        ).items())),
        "framings": dict(sorted(Counter(
            master.framing for item in characters for master in item.masters
        ).items())),
        "preview_coverage": round(
            sum(bool(master.preview_artifact.path) for item in characters for master in item.masters)
            / max(1, sum(len(item.masters) for item in characters)), 4
        ),
        "legacy_aliases": len(manifest.legacy_aliases),
        "validation_errors": [
            {"code": issue.code, "location": issue.location, "message": issue.message}
            for issue in issues if issue.severity == "error"
        ],
        "review_candidates_needing_artwork_review": sorted(
            item.id for item in characters
            if item.quality_state == "review" and not item.signature_features
        ),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit V3 migrated character coverage")
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
