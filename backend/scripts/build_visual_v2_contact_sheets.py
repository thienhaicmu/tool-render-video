"""
build_visual_v2_contact_sheets.py — GĐ2 Visual Foundation acceptance sheets.

Renders the parts-based anime character + layered scene factories into review PNGs
under artifacts/visual_v2/ (repo root). NOTHING here touches the render pipeline —
this is the GĐ2 DoD gate: the sheets get approved by eye BEFORE any engine wiring.

Run from backend/:  python scripts/build_visual_v2_contact_sheets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.features.render.engine.visual import svg_raster                      # noqa: E402
from app.features.render.engine.visual.v2.anime_char import (                 # noqa: E402
    anime_char_inner, EMOTIONS, POSES,
)
from app.features.render.engine.visual.v2.anime_scene import (                # noqa: E402
    anime_scene_inner, SCENES, TODS,
)
from app.features.render.engine.visual.v2.look_spec import derive_look        # noqa: E402

OUT = Path(__file__).resolve().parents[2] / "artifacts" / "visual_v2"
CH_W, CH_H = 1024, 1536
SC_W, SC_H = 1536, 1024


def _sheet(cells, cols, cell_w, cell_h, title, out_name, label_h=44, bg="#20242c"):
    rows = (len(cells) + cols - 1) // cols
    W = cols * cell_w
    H = rows * (cell_h + label_h) + 60
    parts = [f'<rect width="{W}" height="{H}" fill="{bg}"/>',
             f'<text x="20" y="40" font-family="Arial" font-size="30" fill="#e8eaf0">{title}</text>']
    for i, (label, inner, iw, ih) in enumerate(cells):
        cx = (i % cols) * cell_w
        cy = 60 + (i // cols) * (cell_h + label_h)
        s = min(cell_w / iw, cell_h / ih)
        tx = cx + (cell_w - iw * s) / 2
        parts.append(f'<rect x="{cx + 2}" y="{cy}" width="{cell_w - 4}" height="{cell_h}" '
                     f'fill="#3a4050" rx="6"/>')
        parts.append(f'<g transform="translate({tx:.1f},{cy}) scale({s:.4f})">{inner}</g>')
        parts.append(f'<text x="{cx + cell_w / 2:.0f}" y="{cy + cell_h + 32}" font-family="Arial" '
                     f'font-size="22" fill="#c2c8d4" text-anchor="middle">{label}</text>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
           f'viewBox="0 0 {W} {H}">{"".join(parts)}</svg>')
    dst = OUT / out_name
    ok = svg_raster.save_svg_png(svg, str(dst), W, H, opaque_bg=bg)
    print(("OK  " if ok else "FAIL") + f" {dst}")


def sheet_identities():
    specs = [
        ("f_school", dict(gender="female", outfit="school_uniform")),
        ("m_school", dict(gender="male", outfit="school_uniform")),
        ("f_office", dict(gender="female", outfit="office_suit")),
        ("m_office", dict(gender="male", outfit="office_suit")),
        ("f_casual", dict(gender="female", outfit="tee_casual")),
        ("m_hoodie", dict(gender="male", outfit="hoodie")),
        ("f_dress", dict(gender="female", outfit="dress")),
        ("m_hanfu", dict(gender="male", outfit="hanfu_robe")),
        ("f_kimono", dict(gender="female", outfit="kimono")),
        ("m_armor", dict(gender="male", outfit="armor_light")),
        ("m_coat", dict(gender="male", outfit="coat_long")),
        ("f_apron", dict(gender="female", outfit="apron_staff")),
    ]
    cells = []
    for seed, kw in specs:
        lk = derive_look(seed, **kw)
        cells.append((f"{seed}", anime_char_inner(lk), CH_W, CH_H))
    _sheet(cells, 6, 250, 375, "IDENTITIES - 12 seeded looks (outfit fixed, rest derived)",
           "sheet_1_identities.png")


def sheet_emotions():
    lk = derive_look("hero_f", gender="female", outfit="school_uniform")
    cells = [(e, anime_char_inner(lk, emotion=e), CH_W, CH_H) for e in EMOTIONS]
    lk2 = derive_look("hero_m", gender="male", outfit="office_suit")
    cells += [(e, anime_char_inner(lk2, emotion=e), CH_W, CH_H) for e in EMOTIONS]
    _sheet(cells, 10, 220, 330, "EMOTIONS x2 identities - " + ", ".join(EMOTIONS),
           "sheet_2_emotions.png")


def sheet_poses():
    lk = derive_look("hero_m2", gender="male", outfit="hanfu_robe")
    cells = [(p, anime_char_inner(lk, pose=p), CH_W, CH_H) for p in POSES]
    lk2 = derive_look("hero_f2", gender="female", outfit="dress")
    cells += [(p, anime_char_inner(lk2, pose=p), CH_W, CH_H) for p in POSES]
    _sheet(cells, 13, 210, 315, "POSES x2 identities - " + ", ".join(POSES),
           "sheet_3_poses.png")


def sheet_ages_facing():
    cells = []
    for age in ("child", "adult", "elder"):
        for gender in ("female", "male"):
            lk = derive_look(f"{age}_{gender}", gender=gender, age=age, outfit="tee_casual")
            cells.append((f"{age} {gender}", anime_char_inner(lk), CH_W, CH_H))
    lk = derive_look("face_demo", gender="female", outfit="school_uniform")
    for facing in ("front", "right", "left"):
        cells.append((f"facing {facing}", anime_char_inner(lk, facing=facing), CH_W, CH_H))
    _sheet(cells, 9, 240, 360, "AGES x GENDER + FACING", "sheet_4_ages_facing.png")


def sheet_scenes():
    cells = []
    for kind in SCENES:
        for tod in TODS:
            cells.append((f"{kind} / {tod}", anime_scene_inner(kind, tod), SC_W, SC_H))
    _sheet(cells, 6, 384, 256, "SCENES x TOD (day / sunset / night)", "sheet_5_scenes.png")


def sheet_composed():
    """A staged shot: scene + two characters facing each other (the render's job,
    previewed here so composition/scale can be judged)."""
    combos = [
        ("street", "night", ("m_coat", dict(gender="male", outfit="coat_long")),
         ("f_office", dict(gender="female", outfit="office_suit")), "stern", "angry"),
        ("classroom", "day", ("f_school", dict(gender="female", outfit="school_uniform")),
         ("m_school", dict(gender="male", outfit="school_uniform")), "happy", "shy"),
        ("shrine", "sunset", ("m_hanfu", dict(gender="male", outfit="hanfu_robe")),
         ("f_kimono", dict(gender="female", outfit="kimono")), "neutral", "sad"),
    ]
    cells = []
    for kind, tod, (s1, k1), (s2, k2), e1, e2 in combos:
        a = derive_look(s1, **k1)
        b = derive_look(s2, **k2)
        ca = anime_char_inner(a, emotion=e1, facing="right")
        cb = anime_char_inner(b, emotion=e2, facing="left")
        scale = 0.52
        ax = 250 - CH_W * scale / 2
        bx = 1286 - CH_W * scale / 2
        y = SC_H - CH_H * scale
        inner = (anime_scene_inner(kind, tod)
                 + f'<g transform="translate({ax:.0f},{y:.0f}) scale({scale})">{ca}</g>'
                 + f'<g transform="translate({bx:.0f},{y:.0f}) scale({scale})">{cb}</g>')
        cells.append((f"{kind} / {tod}", inner, SC_W, SC_H))
    _sheet(cells, 1, 1152, 768, "COMPOSED - scene + 2 characters facing each other",
           "sheet_6_composed.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    if not svg_raster.available():
        print("resvg-py unavailable — cannot rasterise. pip install resvg-py")
        sys.exit(1)
    sheet_identities()
    sheet_emotions()
    sheet_poses()
    sheet_ages_facing()
    sheet_scenes()
    sheet_composed()
    print(f"\nSheets in: {OUT}")
