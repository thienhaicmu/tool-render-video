"""Generate V3 framing masters for a selected set of legacy identities.

SVG is generated first because it is lossless, fast to review and keeps the
identity/template proof separate from the later PNG raster delivery step.

Run from backend/: python scripts/remaster_visual_library_v3_legacy_characters.py
Optional: --region jp --limit 24
"""
from __future__ import annotations

import argparse
import hashlib
import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual.library_v3 import (  # noqa: E402
    ArtifactSpec,
    CharacterMasterSpec,
    load_manifest,
    render_identity_master,
    validate_manifest,
    write_manifest,
)
from app.features.render.engine.visual.svg_raster import save_svg_png  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SOURCE = DATA / "visual_library_v3_legacy_characters.json"
DEFAULT_OUTPUT = DATA / "visual_library_v3_legacy_characters_remastered.json"
OUTPUT_ROOT = DATA / "visual_library_v3" / "legacy_remastered"
FRAMINGS = ("full_body", "three_quarter", "waist_up", "bust", "close_up")
WIDTH, HEIGHT = 1024, 1536


def _artifact(path: Path) -> ArtifactSpec:
    return ArtifactSpec(
        path=path.relative_to(DATA).as_posix(),
        sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
        width=WIDTH,
        height=HEIGHT,
        transparent=True,
    )


def remaster(*, region: str = "", limit: int = 0, output: Path = DEFAULT_OUTPUT, input_manifest: Path | None = None) -> Path:
    source = input_manifest or (output if output.is_file() else SOURCE)
    manifest = load_manifest(source)
    selected = [item for item in manifest.characters if not region or item.region == region]
    selected = selected[:max(0, int(limit))] if limit else selected
    selected_ids = {item.id for item in selected}
    updated = []
    for identity in manifest.characters:
        if identity.id not in selected_ids:
            updated.append(identity)
            continue
        out_dir = OUTPUT_ROOT / identity.id / "masters"
        out_dir.mkdir(parents=True, exist_ok=True)
        masters = []
        for framing in FRAMINGS:
            svg = render_identity_master(identity, framing=framing)
            if not svg:
                raise RuntimeError(f"empty SVG for {identity.id}/{framing}")
            path = out_dir / f"{framing}.svg"
            path.write_text(svg, encoding="utf-8")
            preview_path = out_dir / f"{framing}.png"
            if not preview_path.is_file() and not save_svg_png(svg, preview_path, WIDTH, HEIGHT):
                raise RuntimeError(f"unable to rasterize {identity.id}/{framing}")
            masters.append(CharacterMasterSpec(
                id=f"{identity.id}.{framing}.base",
                framing=framing,
                artifact=_artifact(path),
                preview_artifact=_artifact(preview_path),
            ))
        updated.append(replace(identity, version="0.2.0", quality_state="review", masters=tuple(masters)))

    result = replace(manifest, version="0.2.0", characters=tuple(updated))
    errors = [item for item in validate_manifest(result, root=DATA) if item.severity == "error"]
    if errors:
        details = "; ".join(f"{item.location}: {item.message}" for item in errors)
        raise RuntimeError(f"remastered manifest failed validation: {details}")
    write_manifest(result, output)
    print(f"selected={len(selected)} review={sum(c.quality_state == 'review' for c in result.characters)} output={output}")
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description="Remaster legacy character identities into V3 SVG masters")
    parser.add_argument("--region", default="", help="only remaster one region, e.g. jp")
    parser.add_argument("--limit", type=int, default=0, help="maximum identities to remaster, 0 = all")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--input", type=Path, default=None, help="manifest to continue from; defaults to existing output")
    args = parser.parse_args()
    remaster(region=args.region.strip().lower(), limit=args.limit, output=args.output, input_manifest=args.input)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
