"""Build the approved offline Japanese library and two visual-review sheets.

Outputs SVG only (no paid service, no model, no network).  If resvg-py is present,
the two contact sheets are also rasterised to PNG; otherwise they can be opened
directly in a browser or rasterised by the local Edge QA command.

Run from backend/:  python scripts/build_jp_three_style_library.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual import svg_raster  # noqa: E402
from app.features.render.engine.visual.v2.anime_char import build_anime_char, anime_char_inner  # noqa: E402
from app.features.render.engine.visual.v2.anime_scene import build_anime_scene, anime_scene_inner  # noqa: E402
from app.features.render.engine.visual.v2.jp_catalog import JP_BACKGROUNDS, JP_ROLES, role_look  # noqa: E402
from app.features.render.engine.visual.v2.theme_pack import JP_STYLE_PACKS  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "artifacts" / "visual_v2_jp"
CH_W, CH_H = 1024, 1536
SC_W, SC_H = 1536, 1024


def _write(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _sheet(cells, *, cols: int, cell_w: int, cell_h: int, title: str, name: str,
           bg: str = "#171b24") -> Path:
    label_h = 52
    rows = (len(cells) + cols - 1) // cols
    width = cols * cell_w
    height = 72 + rows * (cell_h + label_h)
    parts = [f'<rect width="{width}" height="{height}" fill="{bg}"/>',
             f'<text x="24" y="44" font-family="Arial,sans-serif" font-size="30" fill="#f0f2f6">{escape(title)}</text>']
    for index, (label, inner, iw, ih) in enumerate(cells):
        x = index % cols * cell_w
        y = 72 + index // cols * (cell_h + label_h)
        scale = min((cell_w - 14) / iw, (cell_h - 12) / ih)
        tx = x + (cell_w - iw * scale) / 2
        ty = y + (cell_h - ih * scale) / 2
        parts.append(f'<rect x="{x + 5}" y="{y + 3}" width="{cell_w - 10}" height="{cell_h - 6}" rx="12" fill="#303744"/>')
        parts.append(f'<g transform="translate({tx:.2f},{ty:.2f}) scale({scale:.5f})">{inner}</g>')
        parts.append(f'<text x="{x + cell_w / 2:.1f}" y="{y + cell_h + 34}" text-anchor="middle" '
                     f'font-family="Arial,sans-serif" font-size="20" fill="#d2d8e2">{escape(label)}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
           f'viewBox="0 0 {width} {height}">{"".join(parts)}</svg>')
    path = OUT / name
    _write(path, svg)
    if svg_raster.available():
        svg_raster.save_svg_png(svg, str(path.with_suffix(".png")), width, height, opaque_bg=bg)
    return path


def build_library() -> dict:
    styles = list(JP_STYLE_PACKS)
    manifest = {"version": 1, "offline": True, "styles": styles, "characters": [], "backgrounds": []}
    for role in JP_ROLES:
        look = role_look(role["id"])
        entry = {"role_id": role["id"], "era": role["era"], "scene_id": role["scene_id"],
                 "identity": look.to_dict(), "variants": {}}
        for style_id in styles:
            rel = Path("library") / "characters" / style_id / f'{role["id"]}.svg'
            _write(OUT / rel, build_anime_char(look, style_id=style_id))
            entry["variants"][style_id] = rel.as_posix()
        manifest["characters"].append(entry)
    for bg in JP_BACKGROUNDS:
        entry = {"background_id": bg["id"], "scene": bg["scene"], "era": bg["era"], "variants": {}}
        for style_id in styles:
            rel = Path("library") / "backgrounds" / style_id / f'{bg["id"]}.svg'
            _write(OUT / rel, build_anime_scene(bg["scene"], "day", style_id))
            entry["variants"][style_id] = rel.as_posix()
        manifest["backgrounds"].append(entry)
    _write(OUT / "manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
    return manifest


def character_sheet() -> Path:
    role_ids = ("jp_police_woman", "jp_doctor_man", "jp_engineer_woman", "jp_student_girl",
                "jp_ceo_man", "jp_mother_in_law", "jp_samurai", "jp_miko")
    cells = []
    for role_id in role_ids:
        look = role_look(role_id)
        for style_id, meta in JP_STYLE_PACKS.items():
            cells.append((f'{role_id} / {meta["name"].replace("Japanese Anime ", "")}',
                          anime_char_inner(look, style_id=style_id), CH_W, CH_H))
    return _sheet(cells, cols=3, cell_w=340, cell_h=510,
                  title="Japanese character identity lock — same person, three offline styles",
                  name="sheet_characters_three_styles.svg")


def background_sheet() -> Path:
    scene_ids = ("police_office", "hospital", "laboratory", "living_room",
                 "executive_office", "train_station", "convenience_store", "traditional_house")
    cells = []
    for scene_id in scene_ids:
        for style_id, meta in JP_STYLE_PACKS.items():
            cells.append((f'{scene_id} / {meta["name"].replace("Japanese Anime ", "")}',
                          anime_scene_inner(scene_id, "day", style_id), SC_W, SC_H))
    return _sheet(cells, cols=3, cell_w=512, cell_h=342,
                  title="Japanese profession backgrounds — detail, light and shadow by style",
                  name="sheet_backgrounds_three_styles.svg")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = build_library()
    paths = (character_sheet(), background_sheet())
    print(f'Built {len(manifest["characters"])} identities x {len(manifest["styles"])} styles')
    print(f'Built {len(manifest["backgrounds"])} backgrounds x {len(manifest["styles"])} styles')
    for path in paths:
        print(path)
