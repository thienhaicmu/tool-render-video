"""Run the final pre-matching integrity gate for the V3 visual library."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import load_manifest, validate_manifest  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
CHARACTER_MANIFEST = ROOT / "data" / "visual_library_v3_legacy_characters_remastered.json"
SCENE_MANIFEST = ROOT / "data" / "visual_library_v3_legacy_scenes_remastered.json"
OUTPUT = ROOT / "data" / "visual_library_v3_release_gate.json"
REQUIRED_FRAMINGS = {"full_body", "three_quarter", "waist_up", "bust", "close_up"}


def _issues(manifest, path: Path) -> list[dict]:
    return [
        {"code": issue.code, "location": issue.location, "message": issue.message}
        for issue in validate_manifest(manifest, root=path.parent)
        if issue.severity == "error"
    ]


def build_report(character_path: Path, scene_path: Path) -> dict:
    chars = load_manifest(character_path)
    scenes = load_manifest(scene_path)
    character_masters = [master for item in chars.characters for master in item.masters]
    scene_variants = [variant for item in scenes.scenes for variant in item.variants]
    char_checks = {
        "all_review_or_active": all(item.quality_state in {"review", "active"} for item in chars.characters),
        "required_framings": all(REQUIRED_FRAMINGS <= {master.framing for master in item.masters} for item in chars.characters),
        "preview_coverage": sum(bool(master.preview_artifact.path) for master in character_masters) / max(1, len(character_masters)),
        "legacy_artifacts": sum(len(item.legacy_artifacts) for item in chars.characters),
        "validation_errors": _issues(chars, character_path),
    }
    scene_checks = {
        "all_review_or_active": all(item.quality_state in {"review", "active"} for item in scenes.scenes),
        "safe_zones": all(bool(item.safe_zones) for item in scenes.scenes),
        "variant_preview_coverage": sum(bool(variant.get("preview_path")) for variant in scene_variants) / max(1, len(scene_variants)),
        "legacy_artifacts": sum(len(item.legacy_artifacts) for item in scenes.scenes),
        "validation_errors": _issues(scenes, scene_path),
    }
    passed = (
        char_checks["all_review_or_active"]
        and char_checks["required_framings"]
        and char_checks["preview_coverage"] == 1.0
        and not char_checks["validation_errors"]
        and scene_checks["all_review_or_active"]
        and scene_checks["safe_zones"]
        and scene_checks["variant_preview_coverage"] == 1.0
        and not scene_checks["validation_errors"]
    )
    return {
        "status": "pass" if passed else "fail",
        "policy": "review is structural readiness; active approval and Planner matching remain separate gates",
        "matching_touched": False,
        "characters": {
            "identities": len(chars.characters),
            "masters": len(character_masters),
            "styles": len(chars.style_ids),
            "checks": char_checks,
        },
        "scenes": {
            "identities": len(scenes.scenes),
            "variants": len(scene_variants),
            "styles": len(scenes.style_ids),
            "checks": scene_checks,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run V3 visual library pre-matching release gate")
    parser.add_argument("--characters", type=Path, default=CHARACTER_MANIFEST)
    parser.add_argument("--scenes", type=Path, default=SCENE_MANIFEST)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    if not args.characters.is_file() or not args.scenes.is_file():
        print("missing character or scene manifest")
        return 1
    report = build_report(args.characters, args.scenes)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"wrote {args.output}")
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
