"""Remaster the V3 pilot identities into versioned framing artifacts.

Run from backend/: python scripts/remaster_visual_library_v3_pilot.py
This writes local generated artifacts under data/ (ignored by git) and leaves
the identities in ``review`` until a human approves the contact sheet.
"""
from __future__ import annotations

import hashlib
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


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
SOURCE_MANIFEST = DATA / "visual_library_v3_pilot.json"
OUTPUT_MANIFEST = DATA / "visual_library_v3_pilot_remastered.json"
OUTPUT_ROOT = DATA / "visual_library_v3" / "characters"
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


def remaster() -> Path:
    manifest = load_manifest(SOURCE_MANIFEST)
    if not svg_raster.available():
        raise RuntimeError("resvg-py is required to create remastered PNG masters")

    remastered = []
    for identity in manifest.characters:
        out_dir = OUTPUT_ROOT / identity.id / "masters"
        out_dir.mkdir(parents=True, exist_ok=True)
        masters = []
        for framing in FRAMINGS:
            svg = render_identity_master(identity, framing=framing)
            if not svg:
                raise RuntimeError(f"renderer returned empty SVG for {identity.id}/{framing}")
            svg_path = out_dir / f"{framing}.svg"
            png_path = out_dir / f"{framing}.png"
            svg_path.write_text(svg, encoding="utf-8")
            if not svg_raster.save_svg_png(svg, png_path, WIDTH, HEIGHT):
                raise RuntimeError(f"PNG rasterization failed for {identity.id}/{framing}")
            masters.append(replace(
                identity.masters[0] if identity.masters else None,
                id=f"{identity.id}.{framing}.base",
                framing=framing,
                artifact=_artifact(png_path),
            ))
        remastered.append(replace(
            identity,
            version="0.2.0",
            quality_state="review",
            masters=tuple(masters),
            provenance=replace(
                identity.provenance,
                source=f"remastered_from:{identity.provenance.source}",
                author="Visual Library V3 renderer pilot",
            ),
        ))

    output = replace(manifest, version="0.2.0", characters=tuple(remastered))
    errors = [item for item in validate_manifest(output, root=DATA) if item.severity == "error"]
    if errors:
        details = "; ".join(f"{item.location}: {item.message}" for item in errors)
        raise RuntimeError(f"remastered manifest failed validation: {details}")
    write_manifest(output, OUTPUT_MANIFEST)
    return OUTPUT_MANIFEST


if __name__ == "__main__":
    print(f"wrote {remaster()}")
