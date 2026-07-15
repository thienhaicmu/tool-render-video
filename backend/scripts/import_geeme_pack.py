"""
import_geeme_pack.py — import the GEE! ME free vector character pack (100 nhân vật)
into the Story offline asset library.

Source: https://github.com/yancymin/GEE-ME-free-vector-character-pack
         (site: https://geeme.vercel.app — "You can use it in any design or
         development projects. It's completely free" — designers Yorkun / Hwoma /
         Yancy Min / Charlie Liu, © G-Design)

What it does (idempotent — re-run to refresh):
  1. shallow-clones the repo to a temp dir,
  2. rasterises each ``public/people/svg/gee_me_*.svg`` → transparent RGBA PNG
     (max side 1024, aspect preserved) via the existing resvg rasteriser,
  3. writes them to ``ASSET_LIBRARY_DIR/character/us/hiendai/geeme_XXX.png`` with a
     provenance sidecar (license quote + source + tags) — the library scanner's
     documented convention (story_asset_repo),
  4. re-indexes the library and prints the result,
  5. builds a 10×10 review contact sheet at artifacts/visual_v2/sheet_geeme_pack.png.

Run from backend/:  python scripts/import_geeme_pack.py
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import ASSET_LIBRARY_DIR                     # noqa: E402
from app.db.story_asset_repo import scan_library                  # noqa: E402
from app.features.render.engine.visual import svg_raster          # noqa: E402

REPO = "https://github.com/yancymin/GEE-ME-free-vector-character-pack"
LICENSE_NOTE = ("Free for any design or development projects (GEE! ME pack statement); "
                "credit: Yorkun / Hwoma / Yancy Min / Charlie Liu, © G-Design")
DEST = Path(ASSET_LIBRARY_DIR) / "character" / "us" / "hiendai"
SHEET = Path(__file__).resolve().parents[2] / "artifacts" / "visual_v2" / "sheet_geeme_pack.png"
MAX_SIDE = 1024

_VB_RE = re.compile(r'viewBox="([\d.\s\-]+)"')


def _svg_size(svg: str) -> "tuple[int, int]":
    m = _VB_RE.search(svg)
    if m:
        parts = m.group(1).split()
        if len(parts) == 4:
            try:
                w, h = float(parts[2]), float(parts[3])
                if w > 0 and h > 0:
                    s = MAX_SIDE / max(w, h)
                    return max(1, int(w * s)), max(1, int(h * s))
            except ValueError:
                pass
    return MAX_SIDE, MAX_SIDE


def main() -> int:
    if not svg_raster.available():
        print("resvg-py unavailable — pip install resvg-py")
        return 1
    tmp = Path(tempfile.mkdtemp(prefix="geeme_"))
    try:
        print(f"cloning {REPO} ...")
        r = subprocess.run(["git", "clone", "--depth", "1", REPO, str(tmp / "repo")],
                           capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print("clone failed:", (r.stderr or "")[-400:])
            return 1
        src_dir = tmp / "repo" / "public" / "people" / "svg"
        svgs = sorted(src_dir.glob("gee_me_*.svg"))
        if not svgs:
            print("no SVGs found in repo layout — did upstream change?")
            return 1
        DEST.mkdir(parents=True, exist_ok=True)
        ok, fail = 0, []
        for f in svgs:
            n = re.sub(r"\D", "", f.stem) or f.stem
            slug = f"geeme_{int(n):03d}" if n.isdigit() else f"geeme_{f.stem}"
            out = DEST / f"{slug}.png"
            try:
                svg = f.read_text(encoding="utf-8")
                w, h = _svg_size(svg)
                if svg_raster.save_svg_png(svg, str(out), w, h):   # no opaque_bg → RGBA
                    side = {
                        "name": f"geeme character {int(n):02d}" if n.isdigit() else slug,
                        "tags": "geeme flat modern cartoon person character",
                        "transparent": True,
                        "license": LICENSE_NOTE,
                        "source": REPO,
                    }
                    out.with_suffix(".png.json").write_text(
                        json.dumps(side, ensure_ascii=False, indent=1), encoding="utf-8")
                    ok += 1
                else:
                    fail.append(f.name)
            except Exception as exc:
                fail.append(f"{f.name}: {exc}")
        print(f"rasterised {ok}/{len(svgs)}" + (f" — failed: {fail[:5]}" if fail else ""))

        res = scan_library()
        print(f"library indexed: {res}")

        # 10×10 review sheet from the rasterised PNGs.
        try:
            from PIL import Image
            cols, cell = 10, 200
            rows = (ok + cols - 1) // cols
            sheet = Image.new("RGB", (cols * cell, rows * cell), (32, 36, 44))
            i = 0
            for p in sorted(DEST.glob("geeme_*.png")):
                im = Image.open(p).convert("RGBA")
                im.thumbnail((cell - 12, cell - 12))
                x = (i % cols) * cell + (cell - im.width) // 2
                y = (i // cols) * cell + (cell - im.height) // 2
                sheet.paste(im, (x, y), im)
                i += 1
            SHEET.parent.mkdir(parents=True, exist_ok=True)
            sheet.save(SHEET)
            print(f"review sheet: {SHEET}")
        except Exception as exc:
            print(f"sheet skipped: {exc}")
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
