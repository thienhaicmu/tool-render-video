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
import os
from pathlib import Path

from app.features.render.engine.visual.svg_char import char_inner
from app.features.render.engine.visual.svg_presets import preset
from app.features.render.engine.visual.svg_scene import scene_inner

logger = logging.getLogger("app.render.svg")

W, H = 1536, 1024               # default target (16:9); compose_visual accepts any w,h
_SCENE_W, _SCENE_H = 1536, 1024  # scene templates are authored at this size
_CHAR_W, _CHAR_H = 1024, 1536    # chibi char frame

# GĐ4a: slot geometry (x, scale, FACING flip, portrait reflow) is centralised in
# visual/composition.py — shared with the beat_render overlay path so a character
# stands/faces the same way in the key-visual and in the cue overlay.
_BASE_CHAR_FRAC = 0.86       # base char height as fraction of frame (slot multiplies it)


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
    v3_identity = (getattr(setting, "visual_scene_identity_id", "") or "").strip()
    if v3_identity:
        try:
            from app.features.render.engine.visual.library_v3 import resolve_scene_preview
            v3_path = resolve_scene_preview(
                v3_identity, style=(getattr(plan, "art_style", "") or "").strip()
            )
            if v3_path:
                return _embed(v3_path, w=w, h=h, cover=True)
        except Exception:
            pass
    try:
        if os.getenv("STORY_V3_ONLY", "1") == "1":
            raise RuntimeError("legacy background library disabled by STORY_V3_ONLY")
        from app.db.story_asset_repo import get_by_slug, match_asset, active_library_style
        _st = active_library_style(getattr(plan, "art_style", "") or "")
        asset = (getattr(setting, "asset", "") or "").strip()
        p = (get_by_slug(asset, "background", style=_st) if asset else None) or \
            match_asset("background", name=scene_kind, region=region, genre=genre,
                        style=(_st or None))
        img = _embed(p, w=w, h=h, cover=True) if p else ""
        if img:
            return img
    except Exception:
        pass
    if os.getenv("STORY_V3_ONLY", "1") == "1":
        # Do not silently replace an unresolved V3 identity with procedural art.
        return ""
    # procedural scene (authored at 1536×1024) scaled to COVER w×h
    sc = max(w / _SCENE_W, h / _SCENE_H)
    tx = (w - _SCENE_W * sc) / 2.0
    ty = (h - _SCENE_H * sc) / 2.0
    return f'<g transform="translate({tx:.1f},{ty:.1f}) scale({sc:.4f})">{scene_inner(scene_kind, region, genre, "")}</g>'


def _char_query(ch) -> str:
    """Free-text used to fuzzy-match a library character when the AI gave no explicit
    ``asset`` slug: archetype (controlled vocab → maps onto slug tokens) + name + gender.
    "" (no signal) → caller skips the fuzzy match so a random character is never
    substituted."""
    parts = [getattr(ch, "archetype", "") or "", getattr(ch, "name", "") or "",
             getattr(ch, "gender", "") or ""]
    return " ".join(p for p in parts if p).strip()


def _char_layer(ch, plan) -> str:
    """Character CONTENT on the 1024×1536 frame. Precedence (library-pick, symmetry with
    _bg_layer): the AI-chosen ``character.asset`` slug (embedded library PNG) → a fuzzy
    archetype/name library match → a procedural chibi from the preset. Never raises."""
    region = getattr(plan, "region", "") or ""
    genre = getattr(plan, "genre_key", "") or ""
    # V3 is opt-in. An already matched identity takes precedence over legacy
    # slug lookup, but an unavailable bridge never invents a replacement face.
    v3_identity = (getattr(ch, "visual_identity_id", "") or "").strip()
    if v3_identity:
        try:
            from app.features.render.engine.visual.library_v3 import resolve_character_preview
            v3_path = resolve_character_preview(v3_identity, framing="full_body")
            if v3_path:
                return _embed(v3_path, w=_CHAR_W, h=_CHAR_H)
        except Exception:
            pass
        # An ID with a missing artifact falls through to the deterministic V3 renderer.
    if os.getenv("STORY_V3_ONLY", "1") == "1":
        try:
            from app.features.render.engine.visual.library_v3 import build_planner_character_inner
            from app.features.render.engine.visual.library_v3.style_aliases import normalize_v3_style
            return build_planner_character_inner(
                ch, style_id=normalize_v3_style(getattr(plan, "art_style", "") or ""))
        except Exception as exc:
            logger.warning("svg_compose: V3 procedural character failed: %s", exc)
            return ""
    try:
        if os.getenv("STORY_V3_ONLY", "1") == "1":
            raise RuntimeError("legacy character library disabled by STORY_V3_ONLY")
        from app.db.story_asset_repo import get_by_slug, match_asset, active_library_style
        _st = active_library_style(getattr(plan, "art_style", "") or "")
        asset = (getattr(ch, "asset", "") or "").strip()
        q = _char_query(ch)
        p = (get_by_slug(asset, "character", style=_st) if asset else None) or \
            (match_asset("character", name=q, region=region, genre=genre,
                         transparent_only=True, style=(_st or None)) if q else None)
        img = _embed(p, w=_CHAR_W, h=_CHAR_H) if p else ""
        if img:
            return img
    except Exception:
        pass
    opts = preset(getattr(ch, "archetype", "") or "", region, genre,
                  getattr(ch, "gender", "") or "")
    return char_inner(opts)


def compose_visual(plan, visual, w: int = W, h: int = H, chars: bool = True) -> str:
    """Return an opaque w×h SVG for a Visual: background (cover) + its characters placed
    in L/C/R zones proportional to the target size. ``chars=False`` → BACKGROUND-ONLY (N4
    overlay mode composites characters per-beat at cue render instead). Aspect-aware.
    Never raises ("")."""
    try:
        w = int(w) or W
        h = int(h) or H
        setting = plan.setting(getattr(visual, "setting_id", "") or "")
        bg = _bg_layer(plan, setting, w, h)
        cids = [c for c in (getattr(visual, "character_ids", None) or [])][:3] if chars else []
        chars = ""
        from app.features.render.engine.visual.composition import layout_slots
        for (cxf, mult, flip), cid in zip(layout_slots(len(cids), w, h), cids):
            ch = plan.character(cid)
            inner = _char_layer(ch, plan)      # library-pick asset → else procedural chibi
            if not inner:
                continue
            scf = _BASE_CHAR_FRAC * mult
            sc = (scf * h) / _CHAR_H            # scale so char height ≈ scf·h
            tx = cxf * w - (_CHAR_W * sc) / 2.0
            ty = h - _CHAR_H * sc               # feet at the bottom edge
            if flip:                            # GĐ4a: side characters face the centre
                inner = f'<g transform="translate({_CHAR_W},0) scale(-1,1)">{inner}</g>'
            chars += f'<g transform="translate({tx:.1f},{ty:.1f}) scale({sc:.4f})">{inner}</g>'
        if os.getenv("STORY_V3_ONLY", "1") == "1" and not bg and not chars:
            logger.warning("svg_compose: V3 visual %s has no resolved layer", getattr(visual, "id", ""))
            return ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                f'{bg}{chars}</svg>')
    except Exception as exc:
        logger.warning("svg_compose.compose_visual failed: %s", exc)
        return ""


__all__ = ["compose_visual"]
