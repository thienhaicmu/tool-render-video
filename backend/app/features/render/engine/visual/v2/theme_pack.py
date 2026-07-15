"""Three Japanese-anime art directions shared by characters and scenes.

The geometry and :class:`CharacterLook` stay unchanged.  A theme only controls
colour treatment, light, depth and shadow, so switching theme can never replace
one character with another.  Everything is deterministic, offline SVG.
"""
from __future__ import annotations

import itertools


STYLE_CLEAN = "jp_anime_clean_v1"
STYLE_CINEMATIC = "jp_anime_cinematic_v1"
STYLE_SOFT_DRAMA = "jp_anime_soft_drama_v1"
DEFAULT_JP_STYLE = STYLE_CLEAN

JP_STYLE_PACKS = {
    STYLE_CLEAN: {
        "name": "Japanese Anime Clean",
        "desc": "Nét sạch, màu rõ, cel-shading cân bằng; phù hợp nội dung giải thích và đời thường.",
        "mood": "clear",
    },
    STYLE_CINEMATIC: {
        "name": "Japanese Anime Cinematic",
        "desc": "Tương phản sâu, rim light và bóng có chiều sâu; phù hợp drama, bí ẩn và cao trào.",
        "mood": "dramatic",
    },
    STYLE_SOFT_DRAMA: {
        "name": "Japanese Anime Soft Drama",
        "desc": "Bảng màu ấm, pastel và ánh sáng mềm; phù hợp gia đình, tình cảm và chữa lành.",
        "mood": "gentle",
    },
}

_ALIASES = {
    "anime": STYLE_CLEAN,
    "clean": STYLE_CLEAN,
    "cinematic": STYLE_CINEMATIC,
    "soft": STYLE_SOFT_DRAMA,
    "soft_drama": STYLE_SOFT_DRAMA,
}
_UID = itertools.count(1)


def resolve_jp_style(style_id: str | None) -> str:
    value = (style_id or "").strip().lower()
    value = _ALIASES.get(value, value)
    return value if value in JP_STYLE_PACKS else DEFAULT_JP_STYLE


def list_jp_styles() -> list[dict]:
    return [{"id": sid, **meta} for sid, meta in JP_STYLE_PACKS.items()]


def wrap_character(inner: str, style_id: str | None) -> str:
    """Apply an art direction without adding an opaque background."""
    sid = resolve_jp_style(style_id)
    uid = f"jpc{next(_UID)}"
    if sid == STYLE_CINEMATIC:
        defs = (
            f'<defs><filter id="{uid}_fx" x="-30%" y="-20%" width="170%" height="160%" '
            'color-interpolation-filters="sRGB">'
            '<feColorMatrix type="saturate" values="1.16"/>'
            '<feComponentTransfer><feFuncR type="linear" slope="1.12" intercept="-0.045"/>'
            '<feFuncG type="linear" slope="1.08" intercept="-0.035"/>'
            '<feFuncB type="linear" slope="1.04" intercept="-0.025"/></feComponentTransfer>'
            '<feDropShadow dx="18" dy="24" stdDeviation="13" flood-color="#07111f" flood-opacity="0.38"/>'
            '</filter></defs>'
        )
        return f'{defs}<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
    if sid == STYLE_SOFT_DRAMA:
        defs = (
            f'<defs><filter id="{uid}_fx" x="-25%" y="-20%" width="155%" height="155%" '
            'color-interpolation-filters="sRGB">'
            '<feColorMatrix type="saturate" values="0.86"/>'
            '<feComponentTransfer><feFuncR type="linear" slope="0.94" intercept="0.055"/>'
            '<feFuncG type="linear" slope="0.95" intercept="0.035"/>'
            '<feFuncB type="linear" slope="0.92" intercept="0.045"/></feComponentTransfer>'
            '<feDropShadow dx="10" dy="18" stdDeviation="16" flood-color="#7e516b" flood-opacity="0.22"/>'
            '</filter></defs>'
        )
        return f'{defs}<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
    defs = (
        f'<defs><filter id="{uid}_fx" x="-20%" y="-15%" width="145%" height="145%" '
        'color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="1.04"/>'
        '<feDropShadow dx="8" dy="14" stdDeviation="8" flood-color="#17202c" flood-opacity="0.20"/>'
        '</filter></defs>'
    )
    return f'{defs}<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'


def wrap_scene(inner: str, style_id: str | None, width: int, height: int) -> str:
    """Apply matching light/shadow treatment to a complete scene."""
    sid = resolve_jp_style(style_id)
    uid = f"jps{next(_UID)}"
    if sid == STYLE_CINEMATIC:
        return (
            f'<defs><filter id="{uid}_fx" color-interpolation-filters="sRGB">'
            '<feColorMatrix type="saturate" values="1.18"/>'
            '<feComponentTransfer><feFuncR type="linear" slope="1.12" intercept="-0.05"/>'
            '<feFuncG type="linear" slope="1.08" intercept="-0.045"/>'
            '<feFuncB type="linear" slope="1.06" intercept="-0.04"/></feComponentTransfer></filter>'
            f'<linearGradient id="{uid}_beam" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#d8efff" stop-opacity="0.25"/>'
            '<stop offset="0.48" stop-color="#9bc7ff" stop-opacity="0.04"/>'
            '<stop offset="1" stop-color="#081225" stop-opacity="0.24"/></linearGradient>'
            f'<radialGradient id="{uid}_vig"><stop offset="0.56" stop-color="#000" stop-opacity="0"/>'
            '<stop offset="1" stop-color="#020713" stop-opacity="0.38"/></radialGradient>'
            f'<pattern id="{uid}_grain" width="17" height="17" patternUnits="userSpaceOnUse">'
            '<circle cx="3" cy="5" r="0.8" fill="#fff" opacity="0.12"/>'
            '<circle cx="13" cy="11" r="0.7" fill="#07111e" opacity="0.12"/></pattern></defs>'
            f'<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
            f'<rect width="{width}" height="{height}" fill="url(#{uid}_beam)"/>'
            f'<path d="M0 {height} L0 {height * .86:.0f} L{width * .38:.0f} {height} Z" fill="#08101c" opacity="0.18"/>'
            f'<rect width="{width}" height="{height}" fill="url(#{uid}_vig)"/>'
            f'<rect width="{width}" height="{height}" fill="url(#{uid}_grain)" opacity="0.22"/>'
        )
    if sid == STYLE_SOFT_DRAMA:
        return (
            f'<defs><filter id="{uid}_fx" color-interpolation-filters="sRGB">'
            '<feColorMatrix type="saturate" values="0.84"/>'
            '<feComponentTransfer><feFuncR type="linear" slope="0.93" intercept="0.07"/>'
            '<feFuncG type="linear" slope="0.95" intercept="0.045"/>'
            '<feFuncB type="linear" slope="0.91" intercept="0.055"/></feComponentTransfer></filter>'
            f'<linearGradient id="{uid}_wash" x1="0" y1="0" x2="1" y2="1">'
            '<stop offset="0" stop-color="#fff4dc" stop-opacity="0.20"/>'
            '<stop offset="0.6" stop-color="#ffdce8" stop-opacity="0.08"/>'
            '<stop offset="1" stop-color="#b9c9ee" stop-opacity="0.10"/></linearGradient>'
            f'<radialGradient id="{uid}_bloom"><stop offset="0" stop-color="#fff" stop-opacity="0.22"/>'
            '<stop offset="1" stop-color="#fff" stop-opacity="0"/></radialGradient></defs>'
            f'<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
            f'<rect width="{width}" height="{height}" fill="url(#{uid}_wash)"/>'
            f'<ellipse cx="{width * .22:.0f}" cy="{height * .18:.0f}" rx="{width * .32:.0f}" '
            f'ry="{height * .34:.0f}" fill="url(#{uid}_bloom)"/>'
        )
    return (
        f'<defs><filter id="{uid}_fx" color-interpolation-filters="sRGB">'
        '<feColorMatrix type="saturate" values="1.04"/></filter></defs>'
        f'<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
        f'<path d="M0 {height} L0 {height * .94:.0f} L{width * .26:.0f} {height} Z" '
        'fill="#233044" opacity="0.08"/>'
    )


__all__ = [
    "STYLE_CLEAN", "STYLE_CINEMATIC", "STYLE_SOFT_DRAMA", "DEFAULT_JP_STYLE",
    "JP_STYLE_PACKS", "resolve_jp_style", "list_jp_styles", "wrap_character", "wrap_scene",
]
