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
STYLE_US_EDITORIAL = "us_editorial_clean_v1"
STYLE_US_CINEMATIC = "us_cinematic_v1"
STYLE_US_STORYBOOK = "us_storybook_v1"
DEFAULT_US_STYLE = STYLE_US_EDITORIAL
STYLE_CN_WUXIA = "cn_wuxia_cinematic_v1"
STYLE_CN_XIANXIA = "cn_xianxia_ink_v1"
STYLE_CN_ROMANCE = "cn_romance_soft_v1"
STYLE_EU_FANTASY = "eu_fantasy_cinematic_v1"
STYLE_EU_HORROR = "eu_horror_atmospheric_v1"
STYLE_KO_DRAMA = "ko_drama_soft_v1"
STYLE_VI_DRAMA = "vi_drama_warm_v1"

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

US_STYLE_PACKS = {
    STYLE_US_EDITORIAL: {
        "name": "US Editorial Clean",
        "desc": "Crisp linework, neutral contrast and restrained shadows for contemporary roles.",
        "mood": "clear",
    },
    STYLE_US_CINEMATIC: {
        "name": "US Cinematic",
        "desc": "Deeper contrast, cooler rim light and stronger depth for action and thriller roles.",
        "mood": "dramatic",
    },
    STYLE_US_STORYBOOK: {
        "name": "US Storybook",
        "desc": "Softer saturation and warm lift for family, education and light adventure roles.",
        "mood": "gentle",
    },
}

REGIONAL_SCENE_STYLE_PACKS = {
    "jp": (STYLE_CLEAN, STYLE_CINEMATIC, STYLE_SOFT_DRAMA),
    "cn": (STYLE_CN_WUXIA, STYLE_CN_XIANXIA, STYLE_CN_ROMANCE),
    "eu": (STYLE_EU_FANTASY, STYLE_EU_HORROR),
    "ko": (STYLE_KO_DRAMA,),
    "vi": (STYLE_VI_DRAMA,),
    "us": (STYLE_US_EDITORIAL, STYLE_US_CINEMATIC, STYLE_US_STORYBOOK),
}

REGIONAL_STYLE_PACKS = {
    STYLE_CN_WUXIA: {"name": "Chinese Wuxia Cinematic", "desc": "Ink-edged martial atmosphere with strong depth.", "mood": "dramatic"},
    STYLE_CN_XIANXIA: {"name": "Chinese Xianxia Ink", "desc": "Cool luminous fantasy with layered haze.", "mood": "mystic"},
    STYLE_CN_ROMANCE: {"name": "Chinese Romance Soft", "desc": "Warm restrained light for intimate historical drama.", "mood": "gentle"},
    STYLE_EU_FANTASY: {"name": "European Fantasy Cinematic", "desc": "Deep environmental contrast for fantasy settings.", "mood": "dramatic"},
    STYLE_EU_HORROR: {"name": "European Horror Atmospheric", "desc": "Low saturation, cool shadows and restrained menace.", "mood": "dark"},
    STYLE_KO_DRAMA: {"name": "Korean Drama Soft", "desc": "Clean daylight and soft emotional contrast.", "mood": "gentle"},
    STYLE_VI_DRAMA: {"name": "Vietnamese Drama Warm", "desc": "Warm domestic light with grounded contrast.", "mood": "warm"},
}

STYLE_PACKS = {**JP_STYLE_PACKS, **US_STYLE_PACKS, **REGIONAL_STYLE_PACKS}

_ALIASES = {
    "anime": STYLE_CLEAN,
    "clean": STYLE_CLEAN,
    "cinematic": STYLE_CINEMATIC,
    "soft": STYLE_SOFT_DRAMA,
    "soft_drama": STYLE_SOFT_DRAMA,
    "editorial": STYLE_US_EDITORIAL,
    "us_editorial": STYLE_US_EDITORIAL,
    "us_cinematic": STYLE_US_CINEMATIC,
    "storybook": STYLE_US_STORYBOOK,
    "us_storybook": STYLE_US_STORYBOOK,
    "wuxia": STYLE_CN_WUXIA,
    "xianxia": STYLE_CN_XIANXIA,
    "cn_romance": STYLE_CN_ROMANCE,
    "eu_fantasy": STYLE_EU_FANTASY,
    "eu_horror": STYLE_EU_HORROR,
    "ko_drama": STYLE_KO_DRAMA,
    "vi_drama": STYLE_VI_DRAMA,
}

_CINEMATIC_SCENE_STYLES = {
    STYLE_CINEMATIC, STYLE_US_CINEMATIC, STYLE_CN_WUXIA,
    STYLE_EU_FANTASY,
}
_SOFT_SCENE_STYLES = {
    STYLE_SOFT_DRAMA, STYLE_US_STORYBOOK, STYLE_CN_ROMANCE,
    STYLE_KO_DRAMA, STYLE_VI_DRAMA,
}
_DARK_SCENE_STYLES = {STYLE_EU_HORROR}
_MYSTIC_SCENE_STYLES = {STYLE_CN_XIANXIA}
_UID = itertools.count(1)


def resolve_jp_style(style_id: str | None) -> str:
    value = (style_id or "").strip().lower()
    value = _ALIASES.get(value, value)
    return value if value in JP_STYLE_PACKS else DEFAULT_JP_STYLE


def resolve_style(style_id: str | None) -> str:
    value = (style_id or "").strip().lower()
    value = _ALIASES.get(value, value)
    if value in STYLE_PACKS:
        return value
    return DEFAULT_JP_STYLE


def list_jp_styles() -> list[dict]:
    return [{"id": sid, **meta} for sid, meta in JP_STYLE_PACKS.items()]


def list_styles() -> list[dict]:
    return [{"id": sid, **meta} for sid, meta in STYLE_PACKS.items()]


def wrap_character(inner: str, style_id: str | None) -> str:
    """Apply an art direction without adding an opaque background."""
    sid = resolve_style(style_id)
    uid = f"jpc{next(_UID)}"
    if sid == STYLE_US_CINEMATIC:
        defs = (
            f'<defs><filter id="{uid}_fx" x="-30%" y="-20%" width="170%" height="160%" '
            'color-interpolation-filters="sRGB">'
            '<feColorMatrix type="saturate" values="1.08"/>'
            '<feComponentTransfer><feFuncR type="linear" slope="1.08" intercept="-0.025"/>'
            '<feFuncG type="linear" slope="1.05" intercept="-0.02"/>'
            '<feFuncB type="linear" slope="1.10" intercept="-0.025"/></feComponentTransfer>'
            '<feDropShadow dx="16" dy="22" stdDeviation="11" flood-color="#0d1724" flood-opacity="0.34"/>'
            '</filter></defs>'
        )
        return f'{defs}<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
    if sid == STYLE_US_STORYBOOK:
        defs = (
            f'<defs><filter id="{uid}_fx" x="-25%" y="-20%" width="155%" height="155%" '
            'color-interpolation-filters="sRGB">'
            '<feColorMatrix type="saturate" values="0.90"/>'
            '<feComponentTransfer><feFuncR type="linear" slope="0.97" intercept="0.035"/>'
            '<feFuncG type="linear" slope="0.96" intercept="0.025"/>'
            '<feFuncB type="linear" slope="0.93" intercept="0.035"/></feComponentTransfer>'
            '<feDropShadow dx="9" dy="16" stdDeviation="13" flood-color="#6e5362" flood-opacity="0.20"/>'
            '</filter></defs>'
        )
        return f'{defs}<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
    if sid == STYLE_US_EDITORIAL:
        defs = (
            f'<defs><filter id="{uid}_fx" x="-20%" y="-15%" width="145%" height="145%" '
            'color-interpolation-filters="sRGB"><feColorMatrix type="saturate" values="0.98"/>'
            '<feDropShadow dx="7" dy="12" stdDeviation="7" flood-color="#1a2028" flood-opacity="0.18"/>'
            '</filter></defs>'
        )
        return f'{defs}<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
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
    sid = resolve_style(style_id)
    uid = f"jps{next(_UID)}"
    if sid in _CINEMATIC_SCENE_STYLES:
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
    if sid in _SOFT_SCENE_STYLES:
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
    if sid in _DARK_SCENE_STYLES:
        return (
            f'<defs><filter id="{uid}_fx" color-interpolation-filters="sRGB">'
            '<feColorMatrix type="saturate" values="0.68"/>'
            '<feComponentTransfer><feFuncR type="linear" slope="0.82" intercept="-0.025"/>'
            '<feFuncG type="linear" slope="0.86" intercept="-0.02"/>'
            '<feFuncB type="linear" slope="0.98" intercept="0.015"/></feComponentTransfer></filter></defs>'
            f'<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
            f'<rect width="{width}" height="{height}" fill="#07111f" opacity="0.10"/>'
        )
    if sid in _MYSTIC_SCENE_STYLES:
        return (
            f'<defs><filter id="{uid}_fx" color-interpolation-filters="sRGB">'
            '<feColorMatrix type="saturate" values="1.10"/>'
            '<feComponentTransfer><feFuncR type="linear" slope="0.96" intercept="0.02"/>'
            '<feFuncG type="linear" slope="1.02" intercept="0.015"/>'
            '<feFuncB type="linear" slope="1.12" intercept="0.03"/></feComponentTransfer></filter></defs>'
            f'<g data-style-id="{sid}" filter="url(#{uid}_fx)">{inner}</g>'
            f'<ellipse cx="{width * .72:.0f}" cy="{height * .24:.0f}" rx="{width * .30:.0f}" ry="{height * .36:.0f}" fill="#b7ddff" opacity="0.10"/>'
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
    "STYLE_US_EDITORIAL", "STYLE_US_CINEMATIC", "STYLE_US_STORYBOOK", "DEFAULT_US_STYLE",
    "STYLE_CN_WUXIA", "STYLE_CN_XIANXIA", "STYLE_CN_ROMANCE", "STYLE_EU_FANTASY",
    "STYLE_EU_HORROR", "STYLE_KO_DRAMA", "STYLE_VI_DRAMA",
    "JP_STYLE_PACKS", "US_STYLE_PACKS", "REGIONAL_SCENE_STYLE_PACKS", "REGIONAL_STYLE_PACKS",
    "STYLE_PACKS", "resolve_jp_style", "resolve_style",
    "list_jp_styles", "list_styles", "wrap_character", "wrap_scene",
]
