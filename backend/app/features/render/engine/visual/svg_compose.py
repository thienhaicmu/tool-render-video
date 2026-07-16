"""
svg_compose.py — compose a WIDE key-visual PNG (V3 identities + v2 procedural fallback).

A StoryPlan Visual = one wide 16:9 image that may contain characters. Background: the
setting's approved V3 scene identity (library PNG embedded) → else an AUTO-generated v2
anime scene (user ruling 2026-07-16 — an unresolved identity generates, never blanks).
Characters: the V3 character identity master → else the deterministic V3 procedural
renderer. Characters go into LEFT / CENTER / RIGHT zones (mirrors the super-prompt's
"clear LEFT/CENTER/RIGHT zones" convention). Output is one opaque SVG → rasterised to a
PNG. Pure + defensive; never raises. The pre-V3 legacy library/chibi paths were removed
2026-07-16 (recoverable from git history).
"""
from __future__ import annotations

import base64
import logging
from pathlib import Path

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


def _infer_tod(setting, visual) -> str:
    """Infer time-of-day for the procedural fallback from the text signals the plan
    already carries (identity id / setting name / visual prompt). Never raises."""
    try:
        hay = " ".join([
            (getattr(setting, "visual_scene_identity_id", "") or "") if setting else "",
            (getattr(setting, "scene_kind", "") or "") if setting else "",
            (getattr(setting, "name", "") or "") if setting else "",
            (getattr(visual, "prompt", "") or "") if visual is not None else "",
        ]).lower()
        if any(t in hay for t in ("night", "midnight", "moonlit", "đêm", "深夜", "夜")):
            return "night"
        if any(t in hay for t in ("sunset", "dusk", "twilight", "golden hour", "dawn",
                                  "hoàng hôn", "夕方", "夕暮れ")):
            return "sunset"
    except Exception:
        pass
    return "day"


def _bg_layer(plan, setting, w: int, h: int, tod: str = "") -> str:
    """Background covering the w×h canvas: the setting's V3 scene identity (embedded
    library PNG) → else an AUTO-generated v2 anime scene. Never raises."""
    scene_kind = (getattr(setting, "scene_kind", "") or (getattr(setting, "name", "") if setting else "") or "")
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
    # An unresolved V3 identity AUTO-generates a v2 anime scene (layered,
    # time-of-day lit) instead of leaving the key-visual blank — user ruling
    # 2026-07-16 superseding the earlier "block blank V3 visuals" behaviour.
    sc = max(w / _SCENE_W, h / _SCENE_H)     # authored at 1536×1024, COVER w×h
    tx = (w - _SCENE_W * sc) / 2.0
    ty = (h - _SCENE_H * sc) / 2.0
    try:
        from app.features.render.engine.visual.v2.anime_scene import anime_scene_inner
        from app.features.render.engine.visual.library_v3.style_aliases import normalize_v3_style
        inner = anime_scene_inner(
            scene_kind, tod or "day",
            normalize_v3_style(getattr(plan, "art_style", "") or ""))
        if inner:
            return f'<g transform="translate({tx:.1f},{ty:.1f}) scale({sc:.4f})">{inner}</g>'
    except Exception as exc:
        logger.warning("svg_compose: v2 anime scene fallback failed: %s", exc)
    return ""


def _char_layer(ch, plan) -> str:
    """Character CONTENT on the 1024×1536 frame: the V3 identity master (embedded
    library PNG) → else the deterministic V3 procedural renderer. An identity with a
    missing artifact falls through to procedural — a replacement face is never
    invented from the library. Never raises."""
    v3_identity = (getattr(ch, "visual_identity_id", "") or "").strip()
    if v3_identity:
        try:
            from app.features.render.engine.visual.library_v3 import resolve_character_preview
            v3_path = resolve_character_preview(v3_identity, framing="full_body")
            if v3_path:
                return _embed(v3_path, w=_CHAR_W, h=_CHAR_H)
        except Exception:
            pass
    try:
        from app.features.render.engine.visual.library_v3 import build_planner_character_inner
        from app.features.render.engine.visual.library_v3.style_aliases import normalize_v3_style
        return build_planner_character_inner(
            ch, style_id=normalize_v3_style(getattr(plan, "art_style", "") or ""))
    except Exception as exc:
        logger.warning("svg_compose: V3 procedural character failed: %s", exc)
        return ""


def compose_visual(plan, visual, w: int = W, h: int = H, chars: bool = True) -> str:
    """Return an opaque w×h SVG for a Visual: background (cover) + its characters placed
    in L/C/R zones proportional to the target size. ``chars=False`` → BACKGROUND-ONLY (N4
    overlay mode composites characters per-beat at cue render instead). Aspect-aware.
    Never raises ("")."""
    try:
        w = int(w) or W
        h = int(h) or H
        setting = plan.setting(getattr(visual, "setting_id", "") or "")
        bg = _bg_layer(plan, setting, w, h, tod=_infer_tod(setting, visual))
        cids = [c for c in (getattr(visual, "character_ids", None) or [])][:3] if chars else []
        chars = ""
        from app.features.render.engine.visual.composition import layout_slots
        for (cxf, mult, flip), cid in zip(layout_slots(len(cids), w, h), cids):
            ch = plan.character(cid)
            inner = _char_layer(ch, plan)      # V3 identity master → else V3 procedural
            if not inner:
                continue
            scf = _BASE_CHAR_FRAC * mult
            sc = (scf * h) / _CHAR_H            # scale so char height ≈ scf·h
            tx = cxf * w - (_CHAR_W * sc) / 2.0
            ty = h - _CHAR_H * sc               # feet at the bottom edge
            if flip:                            # GĐ4a: side characters face the centre
                inner = f'<g transform="translate({_CHAR_W},0) scale(-1,1)">{inner}</g>'
            chars += f'<g transform="translate({tx:.1f},{ty:.1f}) scale({sc:.4f})">{inner}</g>'
        if not bg and not chars:
            logger.warning("svg_compose: V3 visual %s has no resolved layer", getattr(visual, "id", ""))
            return ""
        return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">'
                f'{bg}{chars}</svg>')
    except Exception as exc:
        logger.warning("svg_compose.compose_visual failed: %s", exc)
        return ""


__all__ = ["compose_visual"]
