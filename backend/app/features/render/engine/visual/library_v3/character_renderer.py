"""Character Template V3 renderer facade.

The existing cel-shaded vector builder remains the geometry implementation for
now. This facade adds the V3 framing contract and renders each framing from the
same vector identity, so a close-up is re-rasterised rather than enlarged from
the full-body PNG.
"""
from __future__ import annotations

from xml.sax.saxutils import escape

from app.features.render.engine.visual.v2.anime_char import (
    FRAMING_VIEWBOX,
    anime_char_inner,
)
from app.features.render.engine.visual.v2.look_spec import CharacterLook, derive_look


MASTER_WIDTH = 1024
MASTER_HEIGHT = 1536


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


__all__ = ["MASTER_HEIGHT", "MASTER_WIDTH", "build_character_master", "render_identity_master"]
