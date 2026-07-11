"""Phase B1 — SVG→PNG rasterizer wrapper (resvg-py), best-effort + degrade."""
from __future__ import annotations

import struct

import pytest

from app.features.render.engine.visual import svg_raster

_SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="40" height="30" viewBox="0 0 40 30">'
        '<circle cx="20" cy="15" r="9" fill="#e0a030"/></svg>')


def _png_dims(b: bytes):
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    w, h = struct.unpack(">II", b[16:24])
    return w, h, b[25]          # colortype (6 = RGBA)


requires_resvg = pytest.mark.skipif(not svg_raster.available(), reason="resvg-py not installed")


@requires_resvg
def test_render_valid_svg_rgba():
    b = svg_raster.render_svg(_SVG, 400, 300)
    w, h, ct = _png_dims(b)
    assert (w, h) == (400, 300) and ct == 6      # scaled to requested size, alpha present


@requires_resvg
def test_render_opaque_bg():
    b = svg_raster.render_svg(_SVG, 200, 150, opaque_bg="#101820")
    w, h, _ = _png_dims(b)
    assert (w, h) == (200, 150)


@requires_resvg
def test_save_png_atomic(tmp_path):
    out = tmp_path / "sub" / "img.png"
    res = svg_raster.save_svg_png(_SVG, out, 100, 100)
    assert res == str(out) and out.exists()
    _png_dims(out.read_bytes())
    assert not out.with_suffix(".png.tmp").exists()   # temp cleaned up


def test_empty_and_malformed_return_none():
    assert svg_raster.render_svg("", 100, 100) is None
    assert svg_raster.render_svg("   ", 100, 100) is None
    # malformed XML → resvg raises internally → None (never propagates)
    assert svg_raster.render_svg("<svg><rect width=broken></svg>", 100, 100) is None


@requires_resvg
def test_concurrent_render_all_succeed():
    # N1 fix — the Story pipeline rasterises from parallel workers. Hammer render_svg
    # from many threads at once (incl. first-init) → every call must return a valid PNG,
    # none dropped (the /verify finding).
    from concurrent.futures import ThreadPoolExecutor
    import app.features.render.engine.visual.svg_raster as sr
    # reset the one-time init so this exercises the concurrent first-init path
    sr._RESVG = None
    sr._RESVG_TRIED = False
    svgs = [f'<svg xmlns="http://www.w3.org/2000/svg" width="60" height="40" viewBox="0 0 60 40">'
            f'<circle cx="30" cy="20" r="{8 + i % 10}" fill="#4a6fa5"/></svg>' for i in range(48)]
    with ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda s: sr.render_svg(s, 300, 200), svgs))
    assert all(r and r[:8] == b"\x89PNG\r\n\x1a\n" for r in results)   # zero drops
    assert len(results) == 48


def test_degrade_when_rasterizer_absent(monkeypatch):
    # Simulate resvg-py missing: _resvg() → None → available False, render None.
    monkeypatch.setattr(svg_raster, "_RESVG_TRIED", True)
    monkeypatch.setattr(svg_raster, "_RESVG", None)
    assert svg_raster.available() is False
    assert svg_raster.render_svg(_SVG, 100, 100) is None
    assert svg_raster.save_svg_png(_SVG, "x.png", 100, 100) is None
