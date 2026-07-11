"""
svg_compose.py — compose a WIDE key-visual PNG from procedural parts (Phase B4).

A StoryPlan Visual = one wide 16:9 image that may contain characters. This composites a
BACKGROUND (a matched library asset embedded, else a procedural svg_scene) with the
Visual's characters placed into LEFT / CENTER / RIGHT zones (mirrors the super-prompt's
"clear LEFT/CENTER/RIGHT zones" convention). Output is one opaque SVG → rasterised to a
PNG like gpt-image returns. Pure + defensive; never raises. Static key-visual (a neutral
expression) — per-beat emotion/pose overlay is a later phase.
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

from app.features.render.engine.visual.svg_char import char_inner
from app.features.render.engine.visual.svg_presets import preset
from app.features.render.engine.visual.svg_scene import scene_inner

logger = logging.getLogger("app.render.svg")

W, H = 1536, 1024               # default target (16:9); compose_visual accepts any w,h
_SCENE_W, _SCENE_H = 1536, 1024  # scene templates are authored at this size
_CHAR_W, _CHAR_H = 1024, 1536    # chibi char frame

# per character-count: (center-x fraction of width, scale as fraction of frame height)
_ZONE_FRACS = {
    1: [(0.50, 0.86)],
    2: [(0.30, 0.72), (0.70, 0.72)],
    3: [(0.19, 0.60), (0.50, 0.60), (0.81, 0.60)],
}


def _embed(path: str, *, x: float = 0, y: float = 0, w: int = 0, h: int = 0, cover: bool = False) -> str:
    """<image> tag embedding a library PNG/webp as a base64 data URI. "" on any failure."""
    try:
        p = Path(path)
        if not (p.exists() and p.stat().st_size > 0):
            return ""
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        mime = "image/webp" if p.suffix.lower() == ".webp" else "image/png"
        par = ' preserveAspectRatio="xMidYMid slice"' if cover else ""
        return f'<image href="data:{mime};base64,{b64}" x="{x}" y="{y}" width="{w}" height="{h}"{par}/>'
    except Exception:
        return ""


def _bg_layer(plan, setting, w: int, h: int) -> str:
    """Background covering the w×h canvas. Precedence (library-pick): the AI-chosen
    ``setting.asset`` slug → a fuzzy scene_kind match → a procedural scene. Never raises."""
    scene_kind = (getattr(setting, "scene_kind", "") or (getattr(setting, "name", "") if setting else "") or "")
    region = getattr(plan, "region", "") or ""
    genre = getattr(plan, "genre_key", "") or ""
    try:
        from app.db.story_asset_repo import get_by_slug, match_asset
        asset = (getattr(setting, "asset", "") or "").strip()
        p = (get_by_slug(asset, "background") if asset else None) or \
            match_asset("background", name=scene_kind, region=region, genre=genre)
        img = _embed(p, w=w, h=h, cover=True) if p else ""
        if img:
            return img
    except Exception:
        pass
    # procedural scene (authored at 1536×1024) scaled to COVER w×h
    sc = max(w / _SCENE_W, h / _SCENE_H)
    tx = (w - _SCENE_W * sc) / 2.0
    ty = (h - _SCENE_H * sc) / 2.0
    return f'<g transform="translate({tx:.1f},{ty:.1f}) scale({sc:.4f})">{scene_inner(scene_kind, region, genre, "")}</g>'


def _char_layer(ch, plan) -> str:
    """Character CONTENT on the 1024×1536 frame. Precedence (library-pick): the AI-chosen
    ``character.asset`` slug (embedded library PNG) → a procedural chibi from the preset.
    Never raises."""
    try:
        asset = (getattr(ch, "asset", "") or "").strip()
        if asset:
            from app.db.story_asset_repo import get_by_slug
            p = get_by_slug(asset, "character")
            img = _embed(p, w=_CHAR_W, h=_CHAR_H) if p else ""
            if img:
                return img
    except Exception:
        pass
    opts = preset(getattr(ch, "archetype", "") or "",
                  getattr(plan, "region", "") or "",
                  getattr(plan, "genre_key", "") or "",
                  getattr(ch, "gender", "") or "")
    return char_inner(opts)


def compose_visual(plan, visual, w: int = W, h: int = H) -> str:
    """Return an opaque w×h SVG for a Visual: background (cover) + its characters placed
    in L/C/R zones proportional to the target size. Aspect-aware. Never raises ("")."""
    try:
        w = int(w) or W
        h = int(h) or H
        setting = plan.setting(getattr(visual, "setting_id", "") or "")
        bg = _bg_layer(plan, setting, w, h)
        cids = [c for c in (getattr(visual, "character_ids", None) or [])][:3]
        chars = ""
        for (cxf, scf), cid in zip(_ZONE_FRACS.get(len(cids), _ZONE_FRACS[3]), cids):
            ch = plan.character(cid)
            inner = _char_layer(ch, plan)      # library-pick asset → else procedural chibi
            if not inner:
                continue
            sc = (scf * h) / _CHAR_H            # scale so char height ≈ scf·h
            tx = cxf * w - (_CHAR_W * sc) / 2.0
            ty = h - _CHAR_H * sc               # feet at the bottom edge
            chars += f'<g transform="translate({tx:.1f},{ty:.1f}) scale({sc:.4f})">{inner}</g>'
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                f'{bg}{chars}</svg>')
    except Exception as exc:
        logger.warning("svg_compose.compose_visual failed: %s", exc)
        return ""


__all__ = ["compose_visual"]
