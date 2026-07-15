"""Build a deterministic artwork upgrade queue from the V3 character manifest.

This report classifies structured masters for art review. It does not activate
assets and does not perform Planner matching, scoring, or runtime selection.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import load_manifest  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_MANIFEST = ROOT / "data" / "visual_library_v3_legacy_characters_remastered.json"
DEFAULT_OUTPUT = ROOT / "data" / "visual_library_v3_character_artwork_queue.json"
REQUIRED_FRAMINGS = {"full_body", "three_quarter", "waist_up", "bust", "close_up"}
HIGH_END_PENDING_STYLES = {
    "us_editorial_clean_v1",
    "us_cinematic_v1",
    "us_storybook_v1",
}


def _dimension_scores(identity) -> dict[str, int]:
    look = identity.look
    masters = {master.framing for master in identity.masters}
    return {
        "identity_continuity": 2 if len(identity.immutable_fields) >= 4 and identity.signature_features else 1,
        "face_detail": 2 if {"face_shape", "eye_shape", "brow_shape", "nose_shape", "mouth_shape"} <= set(look) else 1,
        "silhouette": 2 if {"body_build", "height", "outfit_silhouette"} <= set(look) else 1,
        "surface_detail": 2 if {"hair_texture", "outfit_material"} <= set(look) else 1,
        "framing_coverage": 2 if REQUIRED_FRAMINGS <= masters else 0,
        "cultural_specificity": 2 if identity.style_id != "legacy_default_v1" else 0,
    }


def build_queue(manifest_path: Path) -> dict:
    manifest = load_manifest(manifest_path)
    rows = []
    for identity in manifest.characters:
        scores = _dimension_scores(identity)
        total = sum(scores.values())
        if identity.style_id in HIGH_END_PENDING_STYLES or identity.style_id == "legacy_default_v1":
            priority = "P0"
            action = "Replace structured proof artwork with a style-specific high-end character pack."
        elif min(scores.values()) < 2:
            priority = "P1"
            action = "Add missing identity detail before approving the character as active."
        else:
            priority = "P2"
            action = "Run art-direction QA and add pose/emotion variants after the base pack is approved."
        rows.append({
            "id": identity.id,
            "display_name": identity.display_name,
            "region": identity.region,
            "role": identity.role,
            "style_id": identity.style_id,
            "quality_state": identity.quality_state,
            "artwork_state": "needs_high_end_artwork" if priority == "P0" else "structured_master",
            "priority": priority,
            "score": total,
            "dimensions": scores,
            "next_action": action,
        })
    rows.sort(key=lambda row: (row["priority"], -row["score"], row["id"]))
    return {
        "manifest": manifest_path.as_posix(),
        "policy": "review is structural readiness; active requires separate art-direction approval",
        "counts": dict(sorted(Counter(row["priority"] for row in rows).items())),
        "by_region": dict(sorted(Counter(row["region"] for row in rows).items())),
        "items": rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a V3 character artwork upgrade queue")
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
