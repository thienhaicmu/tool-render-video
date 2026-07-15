"""
GĐ2 hướng A — Lottie character-pack engine (visual/v2/lottie_pack.py).

Pins: manifest discovery/load, action fallback chain, identity RECOLOR (declared
palette hex → CharacterLook slot colour), master render (RGBA + alpha), frame
sequence (count / loop / content-addressed cache reuse), styles-registry
integration ("lottie:{id}" + graceful fallback), and renderer-absent degradation.

Skips render assertions when rlottie-python is not installed (optional dep).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.features.render.engine.visual.v2 import lottie_pack as lp
from app.features.render.engine.visual.v2.look_spec import derive_look
from app.features.render.engine.visual.v2.styles import list_styles, render_character

FIXTURES = Path(__file__).parent / "fixtures" / "style_packs"

needs_rlottie = pytest.mark.skipif(not lp.available(), reason="rlottie-python not installed")


@pytest.fixture(autouse=True)
def _packs_dir(monkeypatch):
    monkeypatch.setenv("STYLE_PACKS_DIR", str(FIXTURES))


def test_list_and_load_pack():
    packs = lp.list_packs()
    assert any(p["id"] == "sample" for p in packs)
    pack = lp.load_pack("sample")
    assert pack is not None and pack.name == "Sample Pack" and pack.fps == 30
    assert lp.load_pack("missing") is None


def test_resolve_action_fallback():
    pack = lp.load_pack("sample")
    assert pack.resolve_action("stand", "neutral")["loop"] is True
    assert pack.resolve_action("wave", "neutral")["loop"] is False
    assert pack.resolve_action("unknown_pose", "neutral") is not None      # "*" fallback


def test_color_replacement_map():
    look = derive_look("x", base={"outfit_primary": "#ff0000"})
    rep = lp._build_replacements({"#3380cc": ["outfit_primary", 1.0]}, look)
    assert rep["#3380cc"] == pytest.approx([1.0, 0.0, 0.0])
    # factor applies shade(); unknown slot is skipped
    rep2 = lp._build_replacements({"#3380cc": ["outfit_primary", 0.5], "#111111": ["nope", 1.0]}, look)
    assert rep2["#3380cc"][0] == pytest.approx(0.498, abs=0.01)
    assert "#111111" not in rep2


@needs_rlottie
def test_render_master_recolors_and_has_alpha(tmp_path):
    look = derive_look("x", base={"outfit_primary": "#ff0000"})
    out = lp.render_master("sample", look, out_path=tmp_path / "m.png", width=200, height=200)
    assert out and Path(out).exists()
    from PIL import Image
    im = Image.open(out).convert("RGBA")
    center = im.getpixel((100, 100))
    corner = im.getpixel((2, 2))
    assert center[0] > 200 and center[1] < 80 and center[2] < 80     # recolored red
    assert corner[3] == 0                                            # transparent bg


@needs_rlottie
def test_render_frames_count_and_cache(tmp_path, monkeypatch):
    monkeypatch.setattr(lp, "_RENDER_CACHE", tmp_path)
    look = derive_look("y")
    frames = lp.render_frames("sample", look, duration_sec=0.5, fps=10, width=100, height=100)
    assert len(frames) == 5 and all(Path(f).exists() for f in frames)
    seq_dir = Path(frames[0]).parent
    assert (seq_dir / ".done").exists()
    # cache hit: same args → same directory, no extra dirs created
    frames2 = lp.render_frames("sample", look, duration_sec=0.5, fps=10, width=100, height=100)
    assert frames2 == frames
    assert len(list(tmp_path.iterdir())) == 1


@needs_rlottie
def test_styles_registry_lists_and_renders_pack():
    ids = [s["id"] for s in list_styles()]
    assert "lottie:sample" in ids and "anime" in ids
    meta = next(s for s in list_styles() if s["id"] == "lottie:sample")
    assert meta["animated"] is True
    look = derive_look("z")
    inner = render_character("lottie:sample", look)
    assert inner.startswith("<image ") and "base64" in inner


def test_registry_falls_back_when_pack_missing():
    look = derive_look("z")
    inner = render_character("lottie:not_installed", look)
    assert inner and "<image" not in inner        # procedural DEFAULT_STYLE took over


def test_degrades_without_rlottie(monkeypatch, tmp_path):
    monkeypatch.setattr(lp, "_RLOTTIE", False)
    assert lp.available() is False
    assert lp.render_master("sample", derive_look("a"), out_path=tmp_path / "m.png") is None
    assert lp.render_frames("sample", derive_look("a"), duration_sec=1.0) == []
    assert lp.char_image_inner("sample", derive_look("a")) == ""


def test_lottie_pack_not_imported_by_render_paths():
    root = Path(__file__).resolve().parents[1] / "app" / "features" / "render" / "engine"
    hits = []
    for p in root.rglob("*.py"):
        if "visual" + "\\" + "v2" in str(p) or "visual/v2" in str(p).replace("\\", "/"):
            continue
        if "lottie_pack" in p.read_text(encoding="utf-8", errors="ignore"):
            hits.append(str(p))
    assert not hits, f"lottie packs must stay unwired until samples are approved: {hits}"
