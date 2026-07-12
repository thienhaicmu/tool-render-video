"""
gen_svg_library.py — deterministic, offline generator for the procedural SVG asset
library (Task: richer characters / frames / expressions / forms).

It renders characters (via svg_char + svg_presets), a set of decorative FRAMES (inline
SVG), and emotion/pose VARIANTS, writing PNGs under ASSET_LIBRARY_DIR following the scan
convention ``{kind}/{region}/{genre|style}/{slug}.png`` + a ``{slug}.json`` sidecar with
a rich ``desc`` (feeds build_library_catalog and the fuzzy match_asset). It is ADDITIVE:
a file that already exists is skipped, so the hand-curated originals are never touched.

Because it uses the SAME builders the render uses, library art == procedural art — the
value is: (a) named slugs the AI can library-pick, (b) fuzzy-match targets, (c) baked
emotion/pose variants. Run from backend/:  python scripts/gen_svg_library.py [--force]
then it re-scans automatically.

Pure offline ($0). Requires resvg-py (already in requirements.txt).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))    # backend/ on path

from app.core.config import ASSET_LIBRARY_DIR                    # noqa: E402
from app.features.render.engine.visual.svg_char import build_char, emotion_expr  # noqa: E402
from app.features.render.engine.visual.svg_presets import preset  # noqa: E402
from app.features.render.engine.visual import svg_raster          # noqa: E402

FORCE = "--force" in sys.argv
ROOT = Path(ASSET_LIBRARY_DIR)

_REGION_NAME = {"cn": "Chinese", "jp": "Japanese", "ko": "Korean", "vi": "Vietnamese",
                "eu": "European", "us": "American", "generic": ""}
_GENRE_NAME = {"wuxia": "wuxia martial-arts", "xianxia": "xianxia cultivation",
               "codai": "historical period", "hiendai": "modern-day", "fantasy": "fantasy",
               "horror": "horror", "ngontinh": "romance"}
EMOTIONS = ("happy", "angry", "sad", "surprised")
POSES = ("wave", "cheer", "point", "hip")

# archetype -> [(region, genre, [genders]), ...]  (sensible homes; both genders where apt)
HOMES: dict = {
    # cổ trang / spiritual
    "monk":         [("cn", "wuxia", ["male"]), ("jp", "codai", ["male"]), ("vi", "codai", ["male"])],
    "monk_warrior": [("cn", "wuxia", ["male"])],
    "assassin":     [("cn", "wuxia", ["male", "female"]), ("jp", "codai", ["male"])],
    "merchant":     [("cn", "codai", ["male"]), ("vi", "codai", ["male"])],
    # mythic / fantasy
    "archer":       [("eu", "fantasy", ["male", "female"]), ("ko", "codai", ["female"])],
    "ranger":       [("eu", "fantasy", ["male", "female"])],
    "orc":          [("eu", "fantasy", ["male"])],
    "demon":        [("eu", "fantasy", ["male", "female"]), ("jp", "fantasy", ["male"])],
    "angel":        [("eu", "fantasy", ["female", "male"])],
    "fairy":        [("eu", "fantasy", ["female"]), ("vi", "fantasy", ["female"])],
    "pirate":       [("eu", "fantasy", ["male"]), ("us", "codai", ["male"])],
    "bard":         [("eu", "fantasy", ["male", "female"])],
    # modern professions
    "doctor":       [("us", "hiendai", ["male", "female"]), ("ko", "hiendai", ["female"])],
    "police":       [("us", "hiendai", ["male", "female"])],
    "firefighter":  [("us", "hiendai", ["male"])],
    "farmer":       [("vi", "hiendai", ["male", "female"]), ("us", "hiendai", ["male"])],
    "detective":    [("us", "hiendai", ["male"]), ("eu", "hiendai", ["male"])],
    "maid":         [("jp", "hiendai", ["female"]), ("eu", "codai", ["female"])],
    "robot":        [("us", "hiendai", ["male"]), ("jp", "hiendai", ["male"])],
    # gap-fills for existing archetypes in under-covered contexts
    "swordsman":    [("cn", "wuxia", ["female"]), ("jp", "codai", ["male"])],
    "heroine":      [("cn", "xianxia", ["female"])],
    "scholar":      [("cn", "codai", ["male"]), ("vi", "codai", ["male"])],
    "general":      [("cn", "codai", ["male"]), ("ko", "codai", ["male"])],
    "knight":       [("eu", "codai", ["male", "female"])],
    "mage":         [("eu", "fantasy", ["male", "female"])],
    "witch":        [("eu", "horror", ["female"])],
    "teacher":      [("vi", "hiendai", ["female"]), ("cn", "hiendai", ["male"])],
    "nurse":        [("jp", "hiendai", ["female"])],
    "idol":         [("ko", "hiendai", ["female"]), ("jp", "hiendai", ["female"])],
}
# archetypes that get the full emotion + pose variant set (protagonist-class)
VARIANT_ARCHETYPES = {"swordsman", "heroine", "knight", "mage", "archer", "demon",
                      "angel", "assassin", "detective", "idol"}


def _desc(archetype: str, region: str, genre: str, gender: str) -> str:
    rn = _REGION_NAME.get(region, "")
    gn = _GENRE_NAME.get(genre, genre)
    at = archetype.replace("_", " ")
    return " ".join(x for x in (rn, gn, at, gender) if x).strip()


def _save(svg: str, rel: str, desc: str, transparent: bool = True) -> bool:
    """Raster ``svg`` → ROOT/rel (skip if exists unless --force). Writes a .json sidecar
    with desc + transparent. Returns True if a NEW file was written."""
    out = ROOT / rel
    if out.exists() and not FORCE:
        return False
    out.parent.mkdir(parents=True, exist_ok=True)
    png = svg_raster.render_svg(svg, 1024, 1536, opaque_bg=None) if transparent else \
        svg_raster.render_svg(svg, 1024, 1536, opaque_bg="#101820")
    if not png:
        print("  ! raster failed:", rel)
        return False
    out.write_bytes(png)
    out.with_suffix(out.suffix + ".json").write_text(
        json.dumps({"desc": desc, "transparent": transparent}), encoding="utf-8")
    return True


def gen_characters() -> int:
    n = 0
    for arch, homes in HOMES.items():
        for region, genre, genders in homes:
            for gender in genders:
                slug = f"{region}_{genre}_{arch}_{gender}"
                opts = preset(arch, region, genre, gender)
                desc = _desc(arch, region, genre, gender)
                if _save(build_char(opts), f"character/{region}/{genre}/{slug}.png", desc):
                    n += 1
                if arch in VARIANT_ARCHETYPES:
                    for emo in EMOTIONS:
                        o = dict(opts); o["expr"] = emotion_expr(emo)
                        if _save(build_char(o), f"character/{region}/{genre}/{slug}_{emo}.png",
                                 f"{desc} ({emo})"):
                            n += 1
                    for pose in POSES:
                        o = dict(opts); o["pose"] = pose
                        if _save(build_char(o), f"character/{region}/{genre}/{slug}_{pose}.png",
                                 f"{desc} ({pose} pose)"):
                            n += 1
    return n


# ── decorative frames (inline SVG, 1024×1536, transparent over the video) ────────
def _frames() -> dict:
    def corners(draw: str, inset: int = 66) -> str:
        pts = [(inset, inset, 1, 1), (1024 - inset, inset, -1, 1),
               (inset, 1536 - inset, 1, -1), (1024 - inset, 1536 - inset, -1, -1)]
        return "".join(f'<g transform="translate({x},{y}) scale({sx},{sy})">{draw}</g>'
                       for x, y, sx, sy in pts)
    return {
        "frame/romance/sparkle_hearts_corners.png": (
            '<g fill="#f6a5c0">' + corners(
                '<path d="M0 24 Q0 0 22 0 Q44 0 44 24 Q44 48 0 84 Q-44 48 -44 24 Q-44 0 -22 0 Q0 0 0 24 Z" '
                'transform="translate(60,60) scale(0.9)"/>') +
            '</g><g fill="#f7d24a">' +
            "".join(f'<circle cx="{x}" cy="{y}" r="{r}"/>'
                    for x, y, r in [(150, 300, 6), (874, 360, 7), (120, 1200, 6), (900, 1150, 8),
                                    (512, 90, 5), (512, 1446, 5)]) + '</g>'),
        "frame/comic/halftone_corners.png": (
            '<g fill="#1a1a1a">' + corners(
                "".join(f'<circle cx="{i*22}" cy="{j*22}" r="{max(2,7-(i+j))}"/>'
                        for i in range(6) for j in range(6) if i + j < 7)) + '</g>'),
        "frame/artdeco/deco_border.png": (
            '<g fill="none" stroke="#c9a227" stroke-width="6">'
            '<rect x="58" y="58" width="908" height="1420" rx="4"/>'
            '<rect x="80" y="80" width="864" height="1376" rx="2"/></g>'
            '<g fill="#c9a227">' + corners(
                '<path d="M0 0 L120 0 L120 16 L16 16 L16 120 L0 120 Z"/>'
                '<path d="M40 40 L84 40 L84 52 L52 52 L52 84 L40 84 Z"/>') + '</g>'),
        "frame/scifi/grid_hud.png": (
            '<g fill="none" stroke="#4fd8e6" stroke-width="4" opacity="0.85">'
            '<rect x="50" y="50" width="924" height="1436" rx="10"/></g>'
            '<g fill="none" stroke="#4fd8e6" stroke-width="6">' + corners(
                '<path d="M0 150 L0 0 L150 0"/><path d="M0 60 L44 60 M60 0 L60 44"/>'
                '<rect x="18" y="18" width="16" height="16"/>') + '</g>'),
        "frame/film/filmstrip_sides.png": (
            '<g fill="#141414"><rect x="0" y="0" width="70" height="1536"/>'
            '<rect x="954" y="0" width="70" height="1536"/></g><g fill="#f4f4f4">' +
            "".join(f'<rect x="16" y="{y}" width="38" height="48" rx="6"/>'
                    f'<rect x="970" y="{y}" width="38" height="48" rx="6"/>' for y in range(30, 1536, 96)) +
            '</g>'),
        "frame/polaroid/photo_border.png": (
            '<g fill="none" stroke="#fbfbf6" stroke-width="44"><rect x="22" y="22" width="980" height="1360"/></g>'
            '<rect x="44" y="1392" width="936" height="120" fill="#fbfbf6"/>'),
        "frame/vintage/ornate_gold_corners.png": (
            '<g fill="none" stroke="#b8963a" stroke-width="7">' + corners(
                '<path d="M0 160 Q0 0 160 0"/><path d="M20 130 Q90 130 100 60 Q104 30 78 34 Q54 40 66 74 Q78 104 130 96"/>') +
            '</g>'),
        "frame/nature/leaf_vine_sides.png": (
            '<g fill="#5a8f4a">' +
            "".join(f'<ellipse cx="{x}" cy="{y}" rx="26" ry="12" transform="rotate({rot} {x} {y})"/>'
                    for i, y in enumerate(range(120, 1500, 130))
                    for x, rot in [(70, 30 if i % 2 else -30), (954, -30 if i % 2 else 30)]) +
            '</g><g fill="none" stroke="#3f6a34" stroke-width="6"><path d="M70 80 Q90 768 70 1456"/>'
            '<path d="M954 80 Q934 768 954 1456"/></g>'),
    }


def gen_frames() -> int:
    n = 0
    for rel, svg in _frames().items():
        style = rel.split("/")[1]
        name = Path(rel).stem.replace("_", " ")
        if _save(f'<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1536" '
                 f'viewBox="0 0 1024 1536">{svg}</svg>', rel, f"{style} decorative frame {name}"):
            n += 1
    return n


def main() -> None:
    if not svg_raster.available():
        print("resvg-py not available — cannot rasterise. pip install resvg-py")
        sys.exit(1)
    print("ASSET_LIBRARY_DIR:", ROOT, "(force)" if FORCE else "(additive)")
    c = gen_characters()
    f = gen_frames()
    print(f"generated: {c} character files, {f} frame files")
    from app.db.connection import init_db
    from app.db import story_asset_repo as repo
    init_db()
    res = repo.scan_library()
    print("scan:", res)


if __name__ == "__main__":
    main()
