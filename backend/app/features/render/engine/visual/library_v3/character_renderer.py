"""Character Template V3 renderer facade.

The existing cel-shaded vector builder remains the geometry implementation for
now. This facade adds the V3 framing contract and renders each framing from the
same vector identity, so a close-up is re-rasterised rather than enlarged from
the full-body PNG.
"""
from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from app.features.render.engine.visual.v2.anime_char import (
    FRAMING_VIEWBOX,
    anime_char_inner,
)
from app.features.render.engine.visual.v2.look_spec import CharacterLook, derive_look


MASTER_WIDTH = 1024
MASTER_HEIGHT = 1536


_PLANNER_OUTFIT_RULES = (
    (("doctor", "physician", "medical", "nurse"), "doctor_coat"),
    (("police", "officer"), "police_uniform"),
    (("engineer", "technician", "laboratory"), "engineer_workwear"),
    (("student", "school", "child", "kid", "pupil"), "school_uniform"),
    (("office", "business", "manager", "executive", "ceo", "worker", "professional"), "office_suit"),
    (("cafe", "barista", "clerk", "staff", "innkeeper"), "apron_staff"),
    (("samurai", "miko", "geisha", "ninja", "shrine", "kimono"), "kimono"),
)


def _planner_age(value: str) -> str:
    text = (value or "").strip().lower()
    if any(token in text for token in ("child", "kid", "boy", "girl", "young")):
        return "child"
    if any(token in text for token in ("elder", "senior", "middle-aged", "middle aged", "old")):
        return "elder"
    try:
        number = int("".join(ch for ch in text if ch.isdigit()))
        if number <= 12:
            return "child"
        if number >= 55:
            return "elder"
    except (TypeError, ValueError):
        pass
    return "adult"


def _planner_outfit(character) -> str:
    text = " ".join(
        str(getattr(character, key, "") or "").strip().lower()
        for key in ("archetype", "name", "canonical_desc")
    )
    for tokens, outfit in _PLANNER_OUTFIT_RULES:
        if any(token in text for token in tokens):
            return outfit
    return "tee_casual"


def planner_character_look(character):
    """Derive a deterministic V3 look from a Planner character without an ID.

    This is a procedural V3 identity, not a legacy-library lookup. Explicit Planner
    gender/age/archetype signals win; missing dimensions are filled by ``derive_look``
    from a stable character seed so repeated renders keep the same appearance.
    """
    seed = "|".join(
        str(getattr(character, key, "") or "")
        for key in ("id", "name", "canonical_desc", "archetype", "gender", "age")
    )
    gender = (getattr(character, "gender", "") or getattr(character, "voice_gender", "") or "").strip().lower()
    return derive_look(
        seed or "planner-character",
        gender=gender,
        age=_planner_age(getattr(character, "age", "") or getattr(character, "canonical_desc", "")),
        outfit=_planner_outfit(character),
    )


def build_character_master(
    look: CharacterLook | dict | None,
    *,
    framing: str = "full_body",
    emotion: str = "neutral",
    pose: str = "stand",
    facing: str = "front",
    style_id: str | None = None,
    identity_id: str = "",
    width: int = MASTER_WIDTH,
    height: int = MASTER_HEIGHT,
) -> str:
    """Return one transparent, native-vector character master.

    ``framing`` changes the SVG viewBox, not the identity geometry. Unknown
    framings safely use ``full_body`` so a malformed planner value cannot make a
    character disappear.
    """
    try:
        frame = (framing or "full_body").strip().lower()
        if frame not in FRAMING_VIEWBOX:
            frame = "full_body"
        lk = look if isinstance(look, CharacterLook) else derive_look(
            identity_id or "character", base=dict(look or {})
        )
        inner = anime_char_inner(lk, emotion=emotion, pose=pose, facing=facing, style_id=style_id)
        if not inner:
            return ""
        x, y, w, h = FRAMING_VIEWBOX[frame]
        attrs = [
            'xmlns="http://www.w3.org/2000/svg"',
            f'width="{int(width)}"', f'height="{int(height)}"',
            f'viewBox="{x} {y} {w} {h}"',
            f'data-character-framing="{escape(frame)}"',
        ]
        if identity_id:
            attrs.append(f'data-character-id="{escape(identity_id)}"')
        return f'<svg {" ".join(attrs)}>{inner}</svg>'
    except Exception:
        return ""


def render_identity_master(identity, *, framing: str = "full_body", emotion: str = "neutral",
                           pose: str = "stand", facing: str = "front") -> str:
    """Render a V3 ``CharacterIdentitySpec`` without doing any selection."""
    return build_character_master(
        getattr(identity, "look", {}) or {},
        framing=framing,
        emotion=emotion,
        pose=pose,
        facing=facing,
        style_id=getattr(identity, "style_id", "") or None,
        identity_id=getattr(identity, "id", "") or "character",
    )


def build_planner_character_inner(character, *, emotion: str = "neutral",
                                  pose: str = "stand", facing: str = "front",
                                  style_id: str | None = None) -> str:
    """Build V3 character content for a Planner character with no identity ID."""
    look = planner_character_look(character)
    return anime_char_inner(look, emotion=emotion, pose=pose, facing=facing,
                            style_id=style_id)


def build_planner_character_master(character, *, emotion: str = "neutral",
                                   pose: str = "stand", facing: str = "front",
                                   style_id: str | None = None) -> str:
    """Build a complete V3 procedural character SVG for a Planner character."""
    return build_character_master(
        planner_character_look(character), emotion=emotion, pose=pose,
        facing=facing, style_id=style_id,
        identity_id=(getattr(character, "id", "") or getattr(character, "name", "") or "planner-character"),
    )


def render_planner_character_png(character, out_path: str | Path, *, emotion: str = "neutral",
                                pose: str = "stand", facing: str = "front",
                                style_id: str | None = None) -> str | None:
    """Rasterize a procedural V3 Planner character master to a transparent PNG."""
    from app.features.render.engine.visual.svg_raster import save_svg_png
    svg = build_planner_character_master(
        character, emotion=emotion, pose=pose, facing=facing, style_id=style_id)
    return save_svg_png(svg, out_path, MASTER_WIDTH, MASTER_HEIGHT) if svg else None


__all__ = [
    "MASTER_HEIGHT", "MASTER_WIDTH", "build_character_master", "build_planner_character_inner",
    "build_planner_character_master", "planner_character_look", "render_identity_master",
    "render_planner_character_png",
]
