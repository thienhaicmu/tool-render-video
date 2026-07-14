"""
svg_scene_spec.py — PASTE-JSON declarative scene renderer (isolated feature).

A hand-authored ``SettingDef.scene_spec`` describes a flat background by PARAMETERS
(bg / floor / elements) instead of a hardcoded generator. ``render_scene_spec`` turns
that spec into inner SVG (opaque, 1536×1024); ``bank_scene_spec`` rasters it and saves
it into the offline asset library as a background asset (user-named slug) so it is
reused next time.

Deliberately SEPARATE from svg_scene.py — it does NOT touch the existing scene_kind /
library-asset flow. Pure str building; every entry point is defensive (never raises).
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

W, H = 1536, 1024
logger = logging.getLogger("app.render.scene_spec")

# ── defensive coercers (a bad value never breaks the SVG) ────────────────────
_COL_RE = re.compile(r"^#?[0-9a-zA-Z]{1,20}$")
_PATH_ALLOWED = re.compile(r"[^MmLlHhVvCcSsQqTtAaZz0-9 .,\-eE]")


def _n(v, d: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(d)


def _col(v, d: str = "#888") -> str:
    v = str(v or "").strip()
    return v if _COL_RE.match(v) else d


def _opacity(el) -> str:
    if "opacity" in el:
        return f' opacity="{max(0.0, min(1.0, _n(el.get("opacity"), 1.0))):.3f}"'
    return ""


def _stroke(el) -> str:
    if el.get("stroke"):
        return f' stroke="{_col(el.get("stroke"))}" stroke-width="{_n(el.get("width"), 4)}"'
    return ""


# ── one element → SVG (recursive for row / grid / group) ─────────────────────
def _element(el, ox: float = 0.0, oy: float = 0.0) -> str:
    if not isinstance(el, dict):
        return ""
    t = str(el.get("type") or el.get("shape") or "").strip().lower()
    try:
        if t == "rect":
            x, y = _n(el.get("x")) + ox, _n(el.get("y")) + oy
            rx = f' rx="{_n(el.get("r") or el.get("rx"))}"' if (el.get("r") or el.get("rx")) else ""
            return (f'<rect x="{x}" y="{y}" width="{_n(el.get("w"))}" height="{_n(el.get("h"))}"{rx} '
                    f'fill="{_col(el.get("fill"))}"{_stroke(el)}{_opacity(el)}/>')
        if t == "circle":
            return (f'<circle cx="{_n(el.get("cx")) + ox}" cy="{_n(el.get("cy")) + oy}" r="{_n(el.get("r"))}" '
                    f'fill="{_col(el.get("fill"))}"{_opacity(el)}/>')
        if t == "ellipse":
            return (f'<ellipse cx="{_n(el.get("cx")) + ox}" cy="{_n(el.get("cy")) + oy}" '
                    f'rx="{_n(el.get("rx"))}" ry="{_n(el.get("ry"))}" fill="{_col(el.get("fill"))}"{_opacity(el)}/>')
        if t == "line":
            return (f'<line x1="{_n(el.get("x1")) + ox}" y1="{_n(el.get("y1")) + oy}" '
                    f'x2="{_n(el.get("x2")) + ox}" y2="{_n(el.get("y2")) + oy}" '
                    f'stroke="{_col(el.get("stroke"))}" stroke-width="{_n(el.get("width"), 3)}"{_opacity(el)}/>')
        if t == "polygon":
            pts = " ".join(f"{_n(p[0]) + ox},{_n(p[1]) + oy}" for p in (el.get("points") or [])
                           if isinstance(p, (list, tuple)) and len(p) >= 2)
            if not pts:
                return ""
            return f'<polygon points="{pts}" fill="{_col(el.get("fill"))}"{_stroke(el)}{_opacity(el)}/>'
        if t == "path":
            d = _PATH_ALLOWED.sub("", str(el.get("d") or ""))
            if not d.strip():
                return ""
            fill = f' fill="{_col(el.get("fill"))}"' if el.get("fill") else ' fill="none"'
            return f'<path d="{d}"{fill}{_stroke(el)}{_opacity(el)}/>'
        if t == "row":                                   # 1D repeat over xs (+ optional y)
            of = el.get("of")
            y_over = el.get("y")
            out = ""
            for x in (el.get("xs") or []):
                child = dict(of) if isinstance(of, dict) else {}
                child["x"] = _n(x)
                if y_over is not None:
                    child["y"] = _n(y_over)
                out += _element(child, ox, oy)
            return out
        if t == "grid":                                  # 2D repeat over xs × ys
            of = el.get("of")
            out = ""
            for x in (el.get("xs") or []):
                for y in (el.get("ys") or []):
                    child = dict(of) if isinstance(of, dict) else {}
                    child["x"], child["y"] = _n(x), _n(y)
                    out += _element(child, ox, oy)
            return out
        if t == "group":                                 # translate/scale a sub-drawing
            gx, gy = _n(el.get("x")) + ox, _n(el.get("y")) + oy
            sc = _n(el.get("scale"), 1.0) or 1.0
            inner = "".join(_element(c) for c in (el.get("children") or []) if isinstance(c, dict))
            return f'<g transform="translate({gx},{gy}) scale({sc})">{inner}</g>'
    except Exception:
        return ""
    return ""


def _bg(spec) -> str:
    bg = spec.get("bg") if isinstance(spec.get("bg"), dict) else {}
    stops = bg.get("stops")
    if isinstance(stops, list) and stops:
        st = "".join(f'<stop offset="{_n(s[0]) if isinstance(s, (list, tuple)) else 0}" '
                     f'stop-color="{_col(s[1] if isinstance(s, (list, tuple)) and len(s) > 1 else "#888")}"/>'
                     for s in stops)
    else:
        st = (f'<stop offset="0" stop-color="{_col(bg.get("top"), "#cfe0ee")}"/>'
              f'<stop offset="1" stop-color="{_col(bg.get("bottom"), "#8a9aa8")}"/>')
    return (f'<defs><linearGradient id="ssbg" x1="0" y1="0" x2="0" y2="1">{st}</linearGradient></defs>'
            f'<rect width="{W}" height="{H}" fill="url(#ssbg)"/>')


def _floor(spec) -> str:
    fl = spec.get("floor")
    if not isinstance(fl, dict):
        return ""
    y = _n(fl.get("y"), 720)
    out = f'<rect y="{y}" width="{W}" height="{H - y}" fill="{_col(fl.get("color"), "#6a7a88")}"/>'
    if fl.get("edge"):
        out += f'<rect y="{y - 10}" width="{W}" height="12" fill="{_col(fl.get("edge"))}"/>'
    return out


def render_scene_spec(spec) -> str:
    """Declarative spec → inner SVG (opaque, 1536×1024). Pure; never raises → "" on junk."""
    if not isinstance(spec, dict):
        return ""
    try:
        out = _bg(spec)
        for el in (spec.get("elements") or []):
            out += _element(el)
        out += _floor(spec)
        if bool(spec.get("night")):
            out += f'<rect width="{W}" height="{H}" fill="#0a1226" opacity="0.34"/>'
        return out
    except Exception:
        return ""


def build_scene_spec_svg(spec) -> str:
    inner = render_scene_spec(spec)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{inner}</svg>') if inner else ""


def bank_scene_spec(spec, region: str = "", genre: str = "", slug: str = "", name: str = "") -> str:
    """Render a scene_spec → PNG → SAVE into the offline asset library as a background
    asset under ``background/{region}/{genre}/{slug}.png`` (user-named slug) and register
    it in ``story_assets``. Idempotent (existing slug → reused). Returns the slug (so the
    caller can set ``setting.asset = slug``) or "" on any failure. Never raises."""
    slug = re.sub(r"[^0-9a-zA-Z_\-]", "_", str(slug or "").strip())
    if not slug:
        return ""
    try:
        from app.features.render.engine.visual import svg_raster
        from app.db.story_asset_repo import get_by_slug, upsert_asset
        from app.core.config import ASSET_LIBRARY_DIR

        rg = re.sub(r"[^0-9a-zA-Z_\-]", "", (region or "generic")) or "generic"
        gn = re.sub(r"[^0-9a-zA-Z_\-]", "", (genre or "generic")) or "generic"
        out = Path(ASSET_LIBRARY_DIR) / "background" / rg / gn / f"{slug}.png"

        # Idempotent: a registered slug with an on-disk file → reuse, don't re-render.
        existing = get_by_slug(slug, "background")
        if existing and Path(existing).exists():
            return slug

        svg = build_scene_spec_svg(spec)
        if not svg or not svg_raster.available():
            return ""
        png = svg_raster.render_svg(svg, W, H, opaque_bg="#101820")
        if not png:
            return ""
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(png)
        upsert_asset(path=str(out), kind="background", region=(region or ""), genre=(genre or ""),
                     slug=slug, name=(name or slug), description="scene_spec", source="scene_spec")
        return slug
    except Exception as exc:
        logger.warning("bank_scene_spec failed slug=%s: %s", slug, exc)
        return ""


__all__ = ["render_scene_spec", "build_scene_spec_svg", "bank_scene_spec"]
