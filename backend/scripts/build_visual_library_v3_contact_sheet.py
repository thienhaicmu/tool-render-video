"""Build a visual-review contact sheet for the V3 pilot identities.

Run from backend/: python scripts/build_visual_library_v3_contact_sheet.py
The output is an SVG and, when resvg is installed, a PNG under artifacts/.
"""
from __future__ import annotations

import html
import argparse
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual import svg_raster  # noqa: E402
from app.features.render.engine.visual.library_v3 import load_manifest, render_identity_master  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "visual_library_v3_pilot.json"
OUT = ROOT / "artifacts" / "visual_library_v3" / "pilot"
FRAMINGS = ("full_body", "three_quarter", "waist_up", "bust", "close_up")
CELL_W, CELL_H, LABEL_H = 250, 340, 34
ET.register_namespace("", "http://www.w3.org/2000/svg")


def _inner(svg: str) -> str:
    # Parse the root first for validity, then preserve the original child XML so
    # ElementTree does not introduce ns0 prefixes that confuse embedded SVG defs.
    ET.fromstring(svg)
    start = svg.find(">")
    end = svg.rfind("</svg>")
    return svg[start + 1:end] if start >= 0 and end > start else ""


def build_sheet(manifest_path: Path = MANIFEST, *, limit: int = 0, region: str = "", quality: str = "") -> str:
    manifest = load_manifest(manifest_path)
    identities = [item for item in manifest.characters
                  if (not region or item.region == region)
                  and (not quality or item.quality_state == quality)]
    if limit > 0:
        identities = identities[:limit]
    width = len(FRAMINGS) * CELL_W
    row_h = CELL_H + LABEL_H
    height = 78 + len(identities) * row_h
    parts = [
        f'<rect width="{width}" height="{height}" fill="#151a24"/>',
        '<text x="24" y="42" fill="#f2f5fa" font-family="Arial,sans-serif" font-size="28">'
        'Visual Library V3 character identity masters</text>',
    ]
    for row, identity in enumerate(identities):
        y = 78 + row * row_h
        for col, framing in enumerate(FRAMINGS):
            x = col * CELL_W
            svg = render_identity_master(identity, framing=framing)
            if not svg:
                continue
            root = ET.fromstring(svg)
            vb = tuple(float(value) for value in root.attrib["viewBox"].split())
            _, _, view_w, view_h = vb
            scale = min((CELL_W - 18) / view_w, (CELL_H - 16) / view_h)
            tx = x + (CELL_W - view_w * scale) / 2 - vb[0] * scale
            ty = y + (CELL_H - view_h * scale) / 2 - vb[1] * scale
            parts.append(f'<rect x="{x + 4}" y="{y + 4}" width="{CELL_W - 8}" height="{CELL_H - 8}" '
                         'rx="8" fill="#2b3342" stroke="#485467"/>')
            parts.append(f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.5f})">{_inner(svg)}</g>')
            # The row identity is encoded in the sheet order; keep each cell label
            # short so long canonical IDs never collide with the next cell.
            label = framing
            parts.append(f'<text x="{x + CELL_W / 2:.0f}" y="{y + CELL_H + 24}" text-anchor="middle" '
                         f'fill="#cbd3df" font-family="Arial,sans-serif" font-size="14">{html.escape(label)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">{"".join(parts)}</svg>')


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a V3 character master contact sheet")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--limit", type=int, default=0, help="maximum identities to include")
    parser.add_argument("--region", default="", help="filter by region code")
    parser.add_argument("--quality", default="", help="filter by quality state")
    args = parser.parse_args()
    if not args.manifest.is_file():
        print(f"missing manifest: {args.manifest}")
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    svg = build_sheet(args.manifest, limit=args.limit, region=args.region, quality=args.quality)
    svg_path = args.output_dir / "character_masters.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(f"wrote {svg_path}")
    png_path = args.output_dir / "character_masters.png"
    if svg_raster.save_svg_png(svg, png_path, 1250, 850, opaque_bg="#151a24"):
        print(f"wrote {png_path}")
    else:
        print("PNG skipped: resvg-py unavailable")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
