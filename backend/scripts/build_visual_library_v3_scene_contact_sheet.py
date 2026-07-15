"""Build a visual-review contact sheet for migrated V3 scene identities."""
from __future__ import annotations

import argparse
import base64
import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual import svg_raster  # noqa: E402
from app.features.render.engine.visual.library_v3 import load_manifest  # noqa: E402


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data" / "visual_library_v3_legacy_scenes.json"
OUT = ROOT / "artifacts" / "visual_library_v3" / "scenes_legacy_review"
CELL_W, CELL_H, LABEL_H = 320, 220, 34


def _image_data(path: Path) -> str:
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def build_sheet(manifest_path: Path = MANIFEST, *, limit: int = 0, region: str = "") -> str:
    manifest = load_manifest(manifest_path)
    identities = [item for item in manifest.scenes if not region or item.region == region]
    if limit > 0:
        identities = identities[:limit]
    width = 4 * CELL_W
    row_h = CELL_H + LABEL_H
    height = 78 + max(1, len(identities)) * row_h
    parts = [
        f'<rect width="{width}" height="{height}" fill="#151a24"/>',
        '<text x="24" y="42" fill="#f2f5fa" font-family="Arial,sans-serif" font-size="28">'
        'Visual Library V3 scene identity masters</text>',
    ]
    for row, identity in enumerate(identities):
        artifact = identity.layers.get("background")
        if not artifact:
            continue
        path = (manifest_path.parent / artifact.path).resolve()
        if path.suffix.lower() == ".svg":
            preview = next((item.get("preview_path") for item in identity.variants
                            if item.get("style_id") == identity.style_id and item.get("preview_path")), "")
            if preview:
                path = (manifest_path.parent / preview).resolve()
        if not path.is_file():
            continue
        x = row % 4 * CELL_W
        y = 78 + (row // 4) * row_h
        parts.append(f'<rect x="{x + 4}" y="{y + 4}" width="{CELL_W - 8}" height="{CELL_H - 8}" '
                     'rx="8" fill="#2b3342" stroke="#485467"/>')
        parts.append(f'<image x="{x + 8}" y="{y + 8}" width="{CELL_W - 16}" height="{CELL_H - 16}" '
                     f'preserveAspectRatio="xMidYMid slice" href="{_image_data(path)}"/>')
        label = f"{identity.id} / {identity.style_id}"
        parts.append(f'<text x="{x + CELL_W / 2:.0f}" y="{y + CELL_H + 23}" text-anchor="middle" '
                     f'fill="#cbd3df" font-family="Arial,sans-serif" font-size="13">{html.escape(label)}</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}">{"".join(parts)}</svg>')


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a V3 scene contact sheet")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=OUT)
    parser.add_argument("--limit", type=int, default=12)
    parser.add_argument("--region", default="")
    args = parser.parse_args()
    if not args.manifest.is_file():
        print(f"missing manifest: {args.manifest}")
        return 1
    args.output_dir.mkdir(parents=True, exist_ok=True)
    svg = build_sheet(args.manifest, limit=args.limit, region=args.region)
    svg_path = args.output_dir / "scene_masters.svg"
    svg_path.write_text(svg, encoding="utf-8")
    print(f"wrote {svg_path}")
    png_path = args.output_dir / "scene_masters.png"
    if svg_raster.save_svg_png(svg, png_path, 1280, max(480, 78 + ((args.limit + 3) // 4) * (CELL_H + LABEL_H)), opaque_bg="#151a24"):
        print(f"wrote {png_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
