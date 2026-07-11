"""
svg_raster.py — SVG → PNG rasterizer for the procedural art path (Phase B).

Thin wrapper over ``resvg-py`` (prebuilt Rust resvg core, the SAME engine the offline
asset library was authored against → byte-consistent output). LAZY-imported and fully
best-effort (Sacred Contract #3): a missing wheel or a malformed SVG returns None, so a
base install without ``resvg-py`` still renders via the AI / solid-background path.

Two entry points:
  • render_svg(svg, w, h, opaque_bg="")  → PNG bytes | None
  • save_svg_png(svg, out_path, w, h, opaque_bg="") → path str | None (writes atomically)
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.render.svg")

# Lazy availability flag — resolved on first use so import never fails startup.
_RESVG = None          # the resvg_py module once imported
_RESVG_TRIED = False
# The resvg-py native binding is not proven thread-safe, and its FIRST call also does a
# one-time native init. Story renders rasterise from a ThreadPoolExecutor
# (STORY_IMAGE_WORKERS), where a concurrent first-init could drop a visual (observed once
# in /verify — it degraded to a solid bg, never crashed). Serialise every native call
# through one lock: init+warm-up single-threaded, then guard each render. Raster is a few
# ms so the lost parallelism is negligible.
_LOCK = threading.Lock()
_WARMUP_SVG = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4" viewBox="0 0 4 4"><rect width="4" height="4"/></svg>'


def _resvg():
    global _RESVG, _RESVG_TRIED
    if _RESVG_TRIED:
        return _RESVG
    with _LOCK:
        if _RESVG_TRIED:                     # another thread won the race
            return _RESVG
        try:
            import resvg_py  # type: ignore
            try:
                resvg_py.svg_to_bytes(svg_string=_WARMUP_SVG, width=4, height=4)  # force native init here
            except Exception:
                pass
            _RESVG = resvg_py
        except Exception as exc:  # ImportError or a broken wheel
            logger.warning("svg_raster: resvg-py unavailable (%s) — SVG gen disabled", exc)
            _RESVG = None
        _RESVG_TRIED = True
    return _RESVG


def available() -> bool:
    """True when the rasterizer can be used (wheel importable). Never raises."""
    return _resvg() is not None


def render_svg(svg: str, width: int, height: int, opaque_bg: str = "") -> Optional[bytes]:
    """Rasterize an SVG string to PNG bytes at ``width``×``height``. ``opaque_bg`` (a hex
    colour like ``#101820``) fills the canvas for scene backgrounds; "" keeps transparency
    (characters / frames). Returns None on any failure. Never raises."""
    mod = _resvg()
    if mod is None or not (svg or "").strip():
        return None
    try:
        kwargs = {"svg_string": svg, "width": int(width), "height": int(height)}
        if (opaque_bg or "").strip():
            kwargs["background"] = opaque_bg.strip()
        with _LOCK:                          # serialise native resvg calls (thread-safety)
            out = mod.svg_to_bytes(**kwargs)
        b = bytes(out)
        return b if (len(b) >= 8 and b[:8] == b"\x89PNG\r\n\x1a\n") else None
    except Exception as exc:
        logger.warning("svg_raster.render_svg failed: %s", exc)
        return None


def save_svg_png(svg: str, out_path: "str | Path", width: int, height: int,
                 opaque_bg: str = "") -> Optional[str]:
    """Render + write the PNG atomically (``.tmp`` sidecar → os.replace). Returns the
    output path on success, else None. Never raises."""
    png = render_svg(svg, width, height, opaque_bg)
    if not png:
        return None
    try:
        p = Path(out_path)
        p.parent.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(p.suffix + ".tmp")
        tmp.write_bytes(png)
        os.replace(tmp, p)
        return str(p)
    except Exception as exc:
        logger.warning("svg_raster.save_svg_png failed path=%s: %s", out_path, exc)
        return None


__all__ = ["available", "render_svg", "save_svg_png"]
