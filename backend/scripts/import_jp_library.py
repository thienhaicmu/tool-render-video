"""
import_jp_library.py — đồng bộ bộ JP three-style (artifacts/visual_v2_jp) vào thư
viện asset chung, theo KIẾN TRÚC STYLE-AWARE mới:

    asset_library/character/jp/{genre}/{style}/{slug}.png
    asset_library/background/jp/{genre}/{style}/{slug}.png
    (genre: era modern → hiendai, historical → codai; style = style-pack id)

Sidecar mỗi file lấy metadata THẬT từ manifest.json + jp_catalog (label JA/EN,
keywords JA/EN/ZH, gender/age/outfit/scene) → catalog AI + resolver matching đa
ngôn ngữ hoạt động ngay. Idempotent — chạy lại để refresh sau khi rebuild bộ nguồn
(scripts/build_jp_three_style_library.py).

Run from backend/:  python scripts/import_jp_library.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import ASSET_LIBRARY_DIR                              # noqa: E402
from app.db.story_asset_repo import scan_library                           # noqa: E402
from app.features.render.engine.visual import svg_raster                   # noqa: E402
from app.features.render.engine.visual.v2.jp_catalog import (              # noqa: E402
    JP_BACKGROUNDS, JP_ROLES,
)

SRC = Path(__file__).resolve().parents[2] / "artifacts" / "visual_v2_jp"
LICENSE_NOTE = "In-house procedural JP theme pack (build_jp_three_style_library.py) — full rights"
_ERA_GENRE = {"modern": "hiendai", "historical": "codai"}
_VB_RE = re.compile(r'viewBox="([\d.\s\-]+)"')
MAX_SIDE = 1024

_ROLE = {r["id"]: r for r in JP_ROLES}
_BG = {b["id"]: b for b in JP_BACKGROUNDS}


def _svg_size(svg: str) -> "tuple[int, int]":
    m = _VB_RE.search(svg)
    if m:
        p = m.group(1).split()
        if len(p) == 4:
            try:
                w, h = float(p[2]), float(p[3])
                if w > 0 and h > 0:
                    s = MAX_SIDE / max(w, h)
                    return max(1, int(w * s)), max(1, int(h * s))
            except ValueError:
                pass
    return MAX_SIDE, MAX_SIDE


def _sidecar(meta: dict, extra_tags: str, desc: str, transparent: bool) -> dict:
    return {
        "name": meta.get("name", ""),
        "tags": extra_tags,
        "desc": desc[:200],
        "transparent": transparent,
        "license": LICENSE_NOTE,
        "source": "artifacts/visual_v2_jp (manifest v1)",
    }


def _write(svg_path: Path, dst: Path, side: dict, transparent: bool) -> bool:
    svg = svg_path.read_text(encoding="utf-8")
    w, h = _svg_size(svg)
    dst.parent.mkdir(parents=True, exist_ok=True)
    ok = svg_raster.save_svg_png(svg, str(dst), w, h) if transparent else \
        svg_raster.save_svg_png(svg, str(dst), w, h, opaque_bg="#101820")
    if ok:
        dst.with_suffix(".png.json").write_text(
            json.dumps(side, ensure_ascii=False, indent=1), encoding="utf-8")
    return bool(ok)


def main() -> int:
    if not svg_raster.available():
        print("resvg-py unavailable")
        return 1
    manifest = json.loads((SRC / "manifest.json").read_text(encoding="utf-8"))
    lib = Path(ASSET_LIBRARY_DIR)
    ok = 0
    fail: list = []

    for ch in manifest.get("characters", []):
        rid = ch.get("role_id", "")
        role = _ROLE.get(rid, {})
        ident = ch.get("identity", {}) or {}
        genre = _ERA_GENRE.get(ch.get("era", "modern"), "hiendai")
        kw = " ".join(role.get("keywords", ()))
        tags = " ".join(x for x in (
            "jp", ident.get("gender", role.get("gender", "")),
            ident.get("age", role.get("age", "")), role.get("outfit", ""),
            ch.get("era", ""), kw) if x)
        desc = f"{role.get('label_en', rid)} ({role.get('label_ja', '')}); {kw}"
        side = _sidecar({"name": f"{role.get('label_en', rid)} / {role.get('label_ja', '')}"},
                        tags, desc, transparent=True)
        for style, rel in (ch.get("variants") or {}).items():
            src = SRC / rel
            if not src.exists():
                fail.append(rel)
                continue
            dst = lib / "character" / "jp" / genre / style / f"{rid}.png"
            ok += 1 if _write(src, dst, side, transparent=True) else 0

    for bg in manifest.get("backgrounds", []):
        bid = bg.get("id") or bg.get("background_id", "")
        meta = _BG.get(bid, {})
        genre = _ERA_GENRE.get(bg.get("era", meta.get("era", "modern")), "hiendai")
        kw = " ".join(meta.get("keywords", ()))
        tags = " ".join(x for x in ("jp", meta.get("scene", ""), bg.get("era", ""), kw) if x)
        desc = f"{meta.get('label_ja', bid)}; {kw}"
        side = _sidecar({"name": f"{bid} / {meta.get('label_ja', '')}"},
                        tags, desc, transparent=False)
        for style, rel in (bg.get("variants") or {}).items():
            src = SRC / rel
            if not src.exists():
                fail.append(rel)
                continue
            dst = lib / "background" / "jp" / genre / style / f"{bid}.png"
            ok += 1 if _write(src, dst, side, transparent=False) else 0

    print(f"imported {ok} file(s)" + (f" — missing: {fail[:5]}" if fail else ""))
    print("re-index:", scan_library())
    return 0 if not fail else 2


if __name__ == "__main__":
    sys.exit(main())
