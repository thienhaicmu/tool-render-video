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

W, H = 1536, 1024

# (translate_x, translate_y, scale) per character count — char frame is 1024×1536.
_ZONES = {
    1: [(441, 44, 0.638)],
    2: [(179, 179, 0.55), (795, 179, 0.55)],
    3: [(135, 287, 0.48), (523, 287, 0.48), (911, 287, 0.48)],
}


def _bg_layer(plan, setting) -> str:
    """Background inner SVG: a matched library asset (embedded) else a procedural scene."""
    scene_kind = (getattr(setting, "scene_kind", "") or (getattr(setting, "name", "") if setting else "") or "")
    region = getattr(plan, "region", "") or ""
    genre = getattr(plan, "genre_key", "") or ""
    # try a stock library background first (embed as an <image>)
    try:
        from app.db.story_asset_repo import match_asset
        p = match_asset("background", name=scene_kind, region=region, genre=genre)
        if p and Path(p).exists() and Path(p).stat().st_size > 0:
            b64 = base64.b64encode(Path(p).read_bytes()).decode("ascii")
            ext = Path(p).suffix.lower().lstrip(".")
            mime = "image/webp" if ext == "webp" else "image/png"
            return f'<image href="data:{mime};base64,{b64}" x="0" y="0" width="{W}" height="{H}" preserveAspectRatio="xMidYMid slice"/>'
    except Exception:
        pass
    return scene_inner(scene_kind, region, genre, "")


def compose_visual(plan, visual) -> str:
    """Return a wide (1536×1024, opaque) SVG for a Visual: background + its characters
    placed in L/C/R zones. Never raises (returns "" on total failure)."""
    try:
        setting = plan.setting(getattr(visual, "setting_id", "") or "")
        bg = _bg_layer(plan, setting)
        cids = [c for c in (getattr(visual, "character_ids", None) or [])][:3]
        chars = ""
        zones = _ZONES.get(len(cids), _ZONES[3])
        for (tx, ty, sc), cid in zip(zones, cids):
            ch = plan.character(cid)
            opts = preset(getattr(ch, "archetype", "") or "",
                          getattr(plan, "region", "") or "",
                          getattr(plan, "genre_key", "") or "",
                          getattr(ch, "gender", "") or "")
            inner = char_inner(opts)
            if inner:
                chars += f'<g transform="translate({tx},{ty}) scale({sc})">{inner}</g>'
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
                f'{bg}{chars}</svg>')
    except Exception as exc:
        logger.warning("svg_compose.compose_visual failed: %s", exc)
        return ""


__all__ = ["compose_visual"]
