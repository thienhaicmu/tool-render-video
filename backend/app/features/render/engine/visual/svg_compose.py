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


def _bg_layer(plan, setting, w: int, h: int) -> str:
    """Background covering the w×h canvas: a matched library asset (embedded, slice-cover)
    else a procedural scene scaled to cover. Never raises."""
    scene_kind = (getattr(setting, "scene_kind", "") or (getattr(setting, "name", "") if setting else "") or "")
    region = getattr(plan, "region", "") or ""
    genre = getattr(plan, "genre_key", "") or ""
    try:
        from app.db.story_asset_repo import match_asset
        p = match_asset("background", name=scene_kind, region=region, genre=genre)
        if p and Path(p).exists() and Path(p).stat().st_size > 0:
            b64 = base64.b64encode(Path(p).read_bytes()).decode("ascii")
            mime = "image/webp" if Path(p).suffix.lower() == ".webp" else "image/png"
            return f'<image href="data:{mime};base64,{b64}" x="0" y="0" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice"/>'
    except Exception:
        pass
    # procedural scene (authored at 1536×1024) scaled to COVER w×h
    sc = max(w / _SCENE_W, h / _SCENE_H)
    tx = (w - _SCENE_W * sc) / 2.0
    ty = (h - _SCENE_H * sc) / 2.0
    return f'<g transform="translate({tx:.1f},{ty:.1f}) scale({sc:.4f})">{scene_inner(scene_kind, region, genre, "")}</g>'


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
            opts = preset(getattr(ch, "archetype", "") or "",
                          getattr(plan, "region", "") or "",
                          getattr(plan, "genre_key", "") or "",
                          getattr(ch, "gender", "") or "")
            inner = char_inner(opts)
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
