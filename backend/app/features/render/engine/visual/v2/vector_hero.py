"""
vector_hero.py — "Vector Hero" CHARACTER style (GĐ2 — flagship, user-reference match).

Reference: premium stylized vector game-avatar — semi-chibi ≈1:3.5, UNIFORM very
thick near-black outlines on every shape, vertical GRADIENTS for volume (garments /
hair / skin), ornate costume layers (belt + gold buckle, trims, cuff stripes,
collars), hair as OVERLAPPING pointED locks, an optional head ornament and a held
PROP (sword / staff / bag) by outfit, chunky laced boots, mitten hands with thumb.

Same contract as every style (styles.py):
    vector_hero_inner(look, emotion, pose, facing) -> svg inner (1024×1536)
Gradient/clip ids are namespaced per instance. Pure; never raises.
"""
from __future__ import annotations

import itertools

from app.features.render.engine.visual.v2.look_spec import (
    CharacterLook, derive_look, shade,
)

W, H = 1024, 1536
CX = 512
_INK = "#101014"
GOLD = "#c9a24a"
GOLD_D = "#8a6a26"

EMOTIONS = ("neutral", "happy", "joy", "angry", "sad", "cry",
            "surprised", "fear", "stern", "shy")
POSES = ("stand", "wave", "point", "cheer", "hands_hips", "cross_arms", "think",
         "bow", "fight", "hold", "run", "sit", "kneel")

_INST = itertools.count(1)

# geometry
HCY = 370                  # skull centre
HRX, HRY = 205, 215
CHIN = 596
EY = 420                   # eye line
MY = 508                   # mouth line
SH_Y = 640                 # shoulder line
BELT_Y = 880
HEM = 1240                 # robe/coat hem
BOOT_TOP = 1210
FOOT_Y = 1408


class _Ids:
    def __init__(self) -> None:
        self.p = f"vh{next(_INST)}"
        self.n = itertools.count(1)

    def new(self) -> str:
        return f"{self.p}_{next(self.n)}"


def _o(w: float = 12) -> str:
    return f' stroke="{_INK}" stroke-width="{w}" stroke-linejoin="round"'


def _lg(ids: _Ids, top: str, bot: str, x1="0", y1="0", x2="0", y2="1") -> "tuple[str, str]":
    gid = ids.new()
    return (f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">'
            f'<stop offset="0" stop-color="{top}"/><stop offset="1" stop-color="{bot}"/>'
            f'</linearGradient>', f"url(#{gid})")


def _rg(ids: _Ids, inner: str, outer: str, cx=".5", cy=".42", r=".75") -> "tuple[str, str]":
    gid = ids.new()
    return (f'<radialGradient id="{gid}" cx="{cx}" cy="{cy}" r="{r}">'
            f'<stop offset="0" stop-color="{inner}"/><stop offset="1" stop-color="{outer}"/>'
            f'</radialGradient>', f"url(#{gid})")


def _soft(ids: _Ids, cx: float, cy: float, rx: float, ry: float, op: float = 0.30) -> str:
    gid = ids.new()
    return (f'<defs><radialGradient id="{gid}"><stop offset="0" stop-color="#0c0814" '
            f'stop-opacity="{op}"/><stop offset="1" stop-color="#0c0814" stop-opacity="0"/>'
            f'</radialGradient></defs>'
            f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{rx:.0f}" ry="{ry:.0f}" fill="url(#{gid})"/>')


# ── poses: sleeve-arm angle (0 = hang, +cw → screen-left) ─────────────────────
_POSES: dict = {
    "stand":      dict(aL=8, aR=-8, legs="stand"),
    "wave":       dict(aL=8, aR=-148, legs="stand"),
    "point":      dict(aL=10, aR=-78, legs="stand"),
    "cheer":      dict(aL=146, aR=-146, legs="wide"),
    "hands_hips": dict(aL=46, aR=-46, legs="wide", short=True),
    "cross_arms": dict(aL=24, aR=-24, legs="stand", cross=True),
    "think":      dict(aL=8, aR=-126, legs="stand", short_r=True),
    "bow":        dict(aL=6, aR=-6, legs="stand", bow=24),
    "fight":      dict(aL=112, aR=-112, legs="wide", short=True),
    "hold":       dict(aL=8, aR=-58, legs="stand", prop_up=True),
    "run":        dict(aL=42, aR=-104, legs="run", lean=-7),
    "sit":        dict(aL=24, aR=-24, legs="sit", dy=140),
    "kneel":      dict(aL=10, aR=-10, legs="kneel", dy=110),
}
_LEGS: dict = {
    "stand": ((CX - 92, 0), (CX + 92, 0)),
    "wide":  ((CX - 118, 4), (CX + 118, -4)),
    "run":   ((CX - 104, -26), (CX + 104, 30)),
    "sit":   ((CX - 108, 54), (CX + 108, -54)),
    "kneel": ((CX - 100, 8), (CX + 100, -64)),
}


# ── face ──────────────────────────────────────────────────────────────────────
def _eye_closed(ex: int, up: bool) -> str:
    dy = -22 if up else 18
    return (f'<path d="M {ex - 36} {EY} Q {ex} {EY + dy} {ex + 36} {EY}" fill="none" '
            f'stroke="{_INK}" stroke-width="10" stroke-linecap="round"/>'
            f'<path d="M {ex + 30} {EY - 2} L {ex + 42} {EY - 8}" stroke="{_INK}" '
            f'stroke-width="7" stroke-linecap="round"/>')


def _eye_open(ids: _Ids, ex: int, iris: str, *, big: bool = False, dx: int = 0) -> str:
    rx, ry = (30, 26) if big else (28, 22)
    d = (f"M {ex - rx} {EY + 2} Q {ex - rx * 0.8:.0f} {EY - ry} {ex} {EY - ry - 2} "
         f"Q {ex + rx * 0.8:.0f} {EY - ry} {ex + rx} {EY + 2} "
         f"Q {ex + rx * 0.7:.0f} {EY + ry * 0.7:.0f} {ex} {EY + ry * 0.8:.0f} "
         f"Q {ex - rx * 0.7:.0f} {EY + ry * 0.7:.0f} {ex - rx} {EY + 2} Z")
    dfs, fill = _lg(ids, shade(iris, 0.5), shade(iris, 1.35))
    ir = 15 if big else 13
    return (f"<defs>{dfs}</defs>"
            f'<path d="{d}" fill="#ffffff"{_o(7)}/>'
            f'<circle cx="{ex + dx}" cy="{EY}" r="{ir}" fill="{fill}" stroke="{_INK}" stroke-width="4"/>'
            f'<circle cx="{ex + dx}" cy="{EY + 1}" r="{ir * 0.42:.0f}" fill="{_INK}"/>'
            f'<circle cx="{ex + dx - 5}" cy="{EY - 6}" r="4.5" fill="#ffffff"/>'
            f'<path d="M {ex - rx} {EY - 2} Q {ex} {EY - ry - 6} {ex + rx} {EY - 2}" fill="none" '
            f'stroke="{_INK}" stroke-width="9" stroke-linecap="round"/>')


def _brow(ex: int, sgn: int, dy_out: float, dy_in: float) -> str:
    y = EY - 54
    x0, x1 = ex - sgn * 34, ex + sgn * 30
    return (f'<path d="M {x0} {y + dy_out:.0f} Q {ex - sgn * 4} {y - 8 + min(dy_out, dy_in):.0f} '
            f'{x1} {y + dy_in:.0f}" fill="none" stroke="{_INK}" stroke-width="9" stroke-linecap="round"/>')


_MOUTHS = {
    "neutral":     lambda: f'<path d="M {CX - 26} {MY} Q {CX} {MY + 16} {CX + 26} {MY}" stroke="{_INK}" stroke-width="8" fill="none" stroke-linecap="round"/>',
    "smile":       lambda: (f'<path d="M {CX - 34} {MY - 6} Q {CX} {MY + 24} {CX + 34} {MY - 6}" stroke="{_INK}" stroke-width="9" fill="none" stroke-linecap="round"/>'
                            f'<path d="M {CX - 30} {MY - 4} Q {CX} {MY + 20} {CX + 30} {MY - 4} Q {CX} {MY + 30} {CX - 30} {MY - 4} Z" fill="#7c3a38" opacity="0.55"/>'),
    "open_smile":  lambda: (f'<path d="M {CX - 32} {MY - 8} Q {CX} {MY + 44} {CX + 32} {MY - 8} '
                            f'Q {CX} {MY + 6} {CX - 32} {MY - 8} Z" fill="#7c2f2d"{_o(7)}/>'
                            f'<path d="M {CX - 14} {MY + 20} Q {CX} {MY + 30} {CX + 14} {MY + 20} Q {CX} {MY + 26} {CX - 14} {MY + 20} Z" fill="#d97a70"/>'),
    "grit":        lambda: (f'<path d="M {CX - 28} {MY - 6} L {CX + 28} {MY - 6} L {CX + 20} {MY + 16} '
                            f'L {CX - 20} {MY + 16} Z" fill="#7c2f2d"{_o(6)}/>'
                            f'<path d="M {CX - 20} {MY + 2} L {CX + 20} {MY + 2}" stroke="#f4efe4" stroke-width="6"/>'),
    "frown":       lambda: f'<path d="M {CX - 24} {MY + 10} Q {CX} {MY - 10} {CX + 24} {MY + 10}" stroke="{_INK}" stroke-width="8" fill="none" stroke-linecap="round"/>',
    "wail":        lambda: (f'<path d="M {CX - 26} {MY + 4} Q {CX} {MY - 18} {CX + 26} {MY + 4} '
                            f'Q {CX} {MY + 30} {CX - 26} {MY + 4} Z" fill="#7c2f2d"{_o(6)}/>'),
    "o":           lambda: f'<ellipse cx="{CX}" cy="{MY + 2}" rx="14" ry="18" fill="#7c2f2d"{_o(6)}/>',
    "wavy":        lambda: (f'<path d="M {CX - 26} {MY + 2} Q {CX - 13} {MY - 10} {CX} {MY + 2} '
                            f'Q {CX + 13} {MY + 14} {CX + 26} {MY + 2}" stroke="{_INK}" stroke-width="8" fill="none" stroke-linecap="round"/>'),
    "line":        lambda: f'<path d="M {CX - 22} {MY + 2} L {CX + 22} {MY + 2}" stroke="{_INK}" stroke-width="9" stroke-linecap="round"/>',
    "small_smile": lambda: f'<path d="M {CX - 16} {MY} Q {CX} {MY + 12} {CX + 16} {MY}" stroke="{_INK}" stroke-width="7" fill="none" stroke-linecap="round"/>',
}

# emotion → (eyes, brow(dy_out,dy_in), mouth, blush, extra)
_EMO: dict = {
    "neutral":   ("closed_calm", (0, 0), "neutral", 0.0, ""),
    "happy":     ("closed_calm", (0, -3), "smile", 0.25, ""),
    "joy":       ("closed_up", (-4, -6), "open_smile", 0.3, ""),
    "angry":     ("open", (-8, 16), "grit", 0.0, ""),
    "sad":       ("closed_down", (4, -12), "frown", 0.0, ""),
    "cry":       ("closed_down", (4, -12), "wail", 0.0, "tears"),
    "surprised": ("open_big", (-16, -16), "o", 0.0, ""),
    "fear":      ("open_big", (4, -14), "wavy", 0.0, "sweat"),
    "stern":     ("closed_calm", (6, 10), "line", 0.0, ""),
    "shy":       ("closed_up", (0, -3), "small_smile", 0.6, ""),
}


def _face(ids: _Ids, look: CharacterLook, emotion: str, dx: int) -> str:
    eyes, (bo, bi), mouth, blush, extra = _EMO.get(emotion, _EMO["neutral"])
    exl, exr = CX - 96, CX + 96
    parts = []
    if eyes == "closed_calm":
        parts += [_eye_closed(exl, False), _eye_closed(exr, False)]
    elif eyes == "closed_up":
        parts += [_eye_closed(exl, True), _eye_closed(exr, True)]
    elif eyes == "closed_down":
        dyl = (f'<path d="M {exl - 34} {EY - 6} Q {exl} {EY + 16} {exl + 34} {EY - 6}" fill="none" '
               f'stroke="{_INK}" stroke-width="10" stroke-linecap="round"/>')
        parts += [dyl, dyl.replace(str(exl - 34), str(exr - 34)).replace(f"M {exl - 34}", f"M {exr - 34}")
                  .replace(f"Q {exl}", f"Q {exr}").replace(f"{exl + 34}", f"{exr + 34}")]
    else:
        parts += [_eye_open(ids, exl, look.eye_color, big=(eyes == "open_big"), dx=dx // 2),
                  _eye_open(ids, exr, look.eye_color, big=(eyes == "open_big"), dx=dx // 2)]
    parts += [_brow(exl, 1, bo, bi), _brow(exr, -1, bo, bi)]
    # nose + gold accent dot (reference detail)
    parts.append(f'<path d="M {CX - 6} 462 Q {CX + 6} 470 {CX - 2} 480" stroke="{shade(look.skin, 0.6)}" '
                 f'stroke-width="6" fill="none" stroke-linecap="round"/>')
    parts.append(f'<circle cx="{CX + 118}" cy="{EY + 18}" r="9" fill="{GOLD}" stroke="{GOLD_D}" stroke-width="3"/>')
    parts.append(_MOUTHS.get(mouth, _MOUTHS["neutral"])())
    if blush > 0:
        parts.append(f'<ellipse cx="{CX - 120}" cy="{MY - 26}" rx="34" ry="16" fill="#d97a70" opacity="{blush}"/>'
                     f'<ellipse cx="{CX + 120}" cy="{MY - 26}" rx="34" ry="16" fill="#d97a70" opacity="{blush}"/>')
    if extra == "tears":
        for tx in (exl, exr):
            parts.append(f'<path d="M {tx} {EY + 16} Q {tx + 5} {EY + 70} {tx + 2} {EY + 120}" '
                         f'stroke="#9fd4ec" stroke-width="10" fill="none" opacity="0.9" stroke-linecap="round"/>')
    elif extra == "sweat":
        parts.append(f'<path d="M {CX + 168} {EY - 64} q 16 24 0 36 q -16 -12 0 -36 Z" fill="#9fd4ec"{_o(5)}/>')
    return f'<g transform="translate({dx},0)">' + "".join(parts) + "</g>"


def _head(ids: _Ids, look: CharacterLook, emotion: str, facing: str) -> str:
    dfs, skin_fill = _rg(ids, shade(look.skin, 1.06), shade(look.skin, 0.82))
    d = (f"M {CX - HRX} {HCY} Q {CX - HRX - 6} {HCY - HRY} {CX} {HCY - HRY - 8} "
         f"Q {CX + HRX + 6} {HCY - HRY} {CX + HRX} {HCY} "
         f"Q {CX + HRX - 4} {HCY + 130} {CX + 96} {CHIN - 30} "
         f"Q {CX + 40} {CHIN + 10} {CX} {CHIN + 12} Q {CX - 40} {CHIN + 10} {CX - 96} {CHIN - 30} "
         f"Q {CX - HRX + 4} {HCY + 130} {CX - HRX} {HCY} Z")
    jaw = (f'<path d="M {CX - 96} {CHIN - 30} Q {CX} {CHIN + 26} {CX + 96} {CHIN - 30} '
           f'L {CX + 70} {CHIN - 6} Q {CX} {CHIN + 34} {CX - 70} {CHIN - 6} Z" '
           f'fill="{shade(look.skin, 0.72)}" opacity="0.55"/>')
    ear = (f'<path d="M {CX + HRX - 10} {HCY + 60} q 40 -6 36 36 q -8 32 -42 24 Z" '
           f'fill="{look.skin}"{_o(9)}/>')
    dx = 20 if facing in ("left", "right") else 0
    return f"<defs>{dfs}</defs>" + ear + f'<path d="{d}" fill="{skin_fill}"{_o(12)}/>' + jaw \
        + _face(ids, look, emotion, dx)


# ── hair: overlapping pointed locks + head ornament ───────────────────────────
def _lock(ids: _Ids, x0: float, y0: float, x1: float, y1: float, w: float,
          fill: str, bend: float = 0.0) -> str:
    """One pointed hair lock from (x0,y0) → tip (x1,y1)."""
    mx = (x0 + x1) / 2 + bend
    my = (y0 + y1) / 2
    return (f'<path d="M {x0 - w:.0f} {y0:.0f} Q {mx - w:.0f} {my:.0f} {x1:.0f} {y1:.0f} '
            f'Q {mx + w:.0f} {my:.0f} {x0 + w:.0f} {y0:.0f} '
            f'Q {x0:.0f} {y0 - w * 0.8:.0f} {x0 - w:.0f} {y0:.0f} Z" fill="{fill}"{_o(10)}/>')


def _hair(ids: _Ids, look: CharacterLook) -> "tuple[str, str]":
    """(back_layer, front_layer) — back renders behind the body, front over the face."""
    c = look.hair_color
    dfs1, g_dark = _lg(ids, shade(c, 1.15), shade(c, 0.6))
    dfs2, g_mid = _lg(ids, shade(c, 1.05), shade(c, 0.72))
    long_hair = look.hair_back in ("long", "ponytail", "twin_tails")
    back = f"<defs>{dfs1}{dfs2}</defs>"
    # back mass behind the head/shoulders
    if long_hair:
        back += (f'<path d="M {CX - HRX - 26} {HCY - 40} Q {CX - HRX - 60} {HCY + 420} {CX - HRX + 10} {HCY + 640} '
                 f'L {CX - HRX + 90} {HCY + 560} L {CX - HRX + 40} {HCY + 60} Z" fill="{g_dark}"{_o(10)}/>'
                 f'<path d="M {CX + HRX + 26} {HCY - 40} Q {CX + HRX + 60} {HCY + 420} {CX + HRX - 10} {HCY + 640} '
                 f'L {CX + HRX - 90} {HCY + 560} L {CX + HRX - 40} {HCY + 60} Z" fill="{g_dark}"{_o(10)}/>'
                 f'<path d="M {CX - 60} {HCY - HRY + 10} Q {CX + HRX + 80} {HCY + 40} {CX + HRX + 40} {HCY + 320} '
                 f'L {CX + HRX - 30} {HCY + 240} L {CX + 60} {HCY - HRY + 60} Z" fill="{g_mid}"{_o(10)}/>')
    else:
        back += (f'<path d="M {CX - HRX - 16} {HCY + 10} Q {CX - HRX - 24} {HCY + 170} {CX - HRX + 46} {HCY + 230} '
                 f'L {CX - HRX + 80} {HCY + 120} Z" fill="{g_dark}"{_o(10)}/>'
                 f'<path d="M {CX + HRX + 16} {HCY + 10} Q {CX + HRX + 24} {HCY + 170} {CX + HRX - 46} {HCY + 230} '
                 f'L {CX + HRX - 80} {HCY + 120} Z" fill="{g_dark}"{_o(10)}/>')
    # crown + swooping bangs (front)
    crown = (f'<path d="M {CX - HRX - 14} {HCY + 24} Q {CX - HRX - 22} {HCY - HRY - 18} {CX} {HCY - HRY - 30} '
             f'Q {CX + HRX + 22} {HCY - HRY - 18} {CX + HRX + 14} {HCY + 24} '
             f'L {CX + HRX - 26} {HCY + 96} Q {CX + HRX - 40} {HCY - 60} {CX + 60} {HCY - 78} '
             f'L {CX - 80} {HCY - 66} Q {CX - HRX + 34} {HCY - 40} {CX - HRX + 22} {HCY + 90} Z" '
             f'fill="{g_mid}"{_o(11)}/>')
    locks = (
        _lock(ids, CX - 90, HCY - 70, CX - 150, HCY + 150, 42, g_mid, bend=-16)
        + _lock(ids, CX - 20, HCY - 82, CX - 44, HCY + 128, 44, g_dark, bend=-6)
        + _lock(ids, CX + 60, HCY - 78, CX + 34, HCY + 110, 40, g_mid, bend=8)
        + _lock(ids, CX + 120, HCY - 60, CX + 160, HCY + 140, 38, g_dark, bend=14)
    )
    female = look.gender == "female"
    if female or long_hair:
        locks += (_lock(ids, CX - HRX + 30, HCY + 40, CX - HRX - 10, HCY + 330, 34, g_dark, bend=-10)
                  + _lock(ids, CX + HRX - 30, HCY + 40, CX + HRX + 10, HCY + 330, 34, g_dark, bend=10))
    # head ornament: gold diadem + accent gem (reference)
    orn = ""
    if look.outfit in ("hanfu_robe", "kimono", "armor_light", "dress") or "hairband" in look.accessories:
        gx, gy = CX, HCY - HRY - 6
        orn = (f'<path d="M {gx - 64} {gy + 22} L {gx - 40} {gy - 26} L {gx + 40} {gy - 26} '
               f'L {gx + 64} {gy + 22} L {gx + 34} {gy + 44} L {gx - 34} {gy + 44} Z" '
               f'fill="{GOLD}"{_o(9)}/>'
               f'<path d="M {gx - 30} {gy + 14} L {gx - 16} {gy - 8} L {gx + 16} {gy - 8} '
               f'L {gx + 30} {gy + 14} L {gx} {gy + 30} Z" fill="{look.accent}" stroke="{GOLD_D}" stroke-width="5"/>')
    return back, crown + locks + orn


# ── outfit ────────────────────────────────────────────────────────────────────
def _cloak_d(sw: float, hw: float, hem: float = HEM) -> str:
    return (f"M {CX - sw} {SH_Y} Q {CX - sw - 34} {SH_Y + 60} {CX - sw - 30} {SH_Y + 200} "
            f"L {CX - hw} {hem} Q {CX} {hem + 34} {CX + hw} {hem} "
            f"L {CX + sw + 30} {SH_Y + 200} Q {CX + sw + 34} {SH_Y + 60} {CX + sw} {SH_Y} "
            f"Q {CX} {SH_Y - 56} {CX - sw} {SH_Y} Z")


def _belt(w: float, acc: str) -> str:
    return (f'<path d="M {CX - w} {BELT_Y - 34} L {CX + w} {BELT_Y - 34} L {CX + w - 8} {BELT_Y + 36} '
            f'L {CX - w + 8} {BELT_Y + 36} Z" fill="#3a2c1c"{_o(10)}/>'
            f'<rect x="{CX - 52}" y="{BELT_Y - 40}" width="104" height="82" rx="18" fill="{GOLD}"{_o(9)}/>'
            f'<rect x="{CX - 34}" y="{BELT_Y - 24}" width="68" height="50" rx="10" fill="none" '
            f'stroke="{GOLD_D}" stroke-width="6"/>'
            f'<path d="M {CX} {BELT_Y - 14} l -16 15 l 16 15 l 16 -15 Z" fill="none" stroke="{GOLD_D}" stroke-width="6"/>')


def _cuff(w: float, ln: float, c: str) -> str:
    y = ln - 58
    return "".join(f'<path d="M {-w / 2 - 6:.0f} {y + i * 18} L {w / 2 + 6:.0f} {y + i * 18}" '
                   f'stroke="{c}" stroke-width="9"/>' for i in range(3))


def _outfit(ids: _Ids, look: CharacterLook) -> dict:
    p1, p2, acc = look.outfit_primary, look.outfit_secondary, look.accent
    kind = look.outfit
    dfs_c, g_cloak = _lg(ids, shade(p1, 1.18), shade(p1, 0.55))
    dfs_p, g_panel = _lg(ids, shade(p2, 1.1), shade(p2, 0.5))
    o = dict(defs=f"<defs>{dfs_c}{dfs_p}</defs>", body="", sleeve=g_cloak,
             sleeve_solid=p1, boot=shade(p1, 0.5), prop="", cuff_c=shade(GOLD, 0.9))
    sw, hw = 190, 300
    cloak = f'<path d="{_cloak_d(sw, hw)}" fill="{g_cloak}"{_o(13)}/>'
    # inner panel (front robe) with collar V
    panel = (f'<path d="M {CX - 96} {SH_Y - 24} L {CX} {SH_Y + 70} L {CX + 96} {SH_Y - 24} '
             f'L {CX + 74} {HEM - 12} Q {CX} {HEM + 20} {CX - 74} {HEM - 12} Z" fill="{g_panel}"{_o(10)}/>')
    collar = (f'<path d="M {CX - 96} {SH_Y - 24} L {CX} {SH_Y + 70} L {CX - 44} {SH_Y - 44} Z" fill="{p2}"{_o(8)}/>'
              f'<path d="M {CX + 96} {SH_Y - 24} L {CX} {SH_Y + 70} L {CX + 44} {SH_Y - 44} Z" '
              f'fill="{shade(p2, 0.8)}"{_o(8)}/>')
    if kind in ("hanfu_robe", "kimono", "armor_light", "coat_long"):
        # split hem tails (reference silhouette) + trim
        tails = (f'<path d="M {CX - 74} {BELT_Y + 40} L {CX - 20} {HEM + 60} L {CX + 8} {HEM - 40} '
                 f'L {CX - 6} {BELT_Y + 44} Z" fill="{g_panel}"{_o(9)}/>'
                 f'<path d="M {CX + 74} {BELT_Y + 40} L {CX + 20} {HEM + 60} L {CX - 8} {HEM - 40} '
                 f'L {CX + 6} {BELT_Y + 44} Z" fill="{shade(p2, 0.75)}"{_o(9)}/>')
        o["body"] = cloak + panel + collar + tails + _belt(sw - 26, acc)
        if kind == "armor_light":
            o["body"] += (f'<path d="M {CX - 120} {SH_Y + 10} Q {CX} {SH_Y - 30} {CX + 120} {SH_Y + 10} '
                          f'L {CX + 104} {SH_Y + 120} Q {CX} {SH_Y + 160} {CX - 104} {SH_Y + 120} Z" '
                          f'fill="{shade(p1, 1.3)}"{_o(10)}/>'
                          f'<path d="M {CX - 60} {SH_Y + 40} L {CX + 60} {SH_Y + 40}" stroke="{GOLD}" stroke-width="7"/>')
        o["prop"] = "sword"
    elif kind == "office_suit":
        o["body"] = (cloak + panel + collar
                     + f'<path d="M {CX} {SH_Y + 66} l -15 18 l 15 130 l 15 -130 Z" fill="{acc}"{_o(7)}/>'
                     + _belt(sw - 26, acc))
        o["prop"] = "bag"
    elif kind == "school_uniform":
        o["body"] = (cloak + panel
                     + f'<path d="M {CX - 110} {SH_Y - 20} L {CX} {SH_Y + 84} L {CX + 110} {SH_Y - 20} '
                       f'L {CX + 140} {SH_Y + 16} L {CX} {SH_Y + 140} L {CX - 140} {SH_Y + 16} Z" fill="{p2}"{_o(9)}/>'
                     + f'<path d="M {CX} {SH_Y + 116} l -20 24 l 20 32 l 20 -32 Z" fill="{acc}"{_o(7)}/>')
    elif kind == "hoodie":
        o["body"] = (cloak
                     + f'<path d="M {CX - 130} {SH_Y + 16} Q {CX} {SH_Y + 110} {CX + 130} {SH_Y + 16} '
                       f'L {CX + 100} {SH_Y - 40} Q {CX} {SH_Y + 40} {CX - 100} {SH_Y - 40} Z" '
                       f'fill="{shade(p1, 0.75)}"{_o(10)}/>'
                     + f'<path d="M {CX - 64} {HEM - 200} L {CX + 64} {HEM - 200} L {CX + 50} {HEM - 90} '
                       f'L {CX - 50} {HEM - 90} Z" fill="{shade(p1, 0.85)}"{_o(9)}/>'
                     + panel.replace(g_panel, "none").replace(_o(10), ' stroke="none"'))
    else:  # tee_casual / dress / apron_staff — simpler front
        o["body"] = cloak + panel + collar + (_belt(sw - 26, acc) if kind != "tee_casual" else "")
        if kind == "apron_staff":
            o["prop"] = "bag"
    return o


def _boot(x: float, ang: float, boot_c: str, dirx: int) -> str:
    return (f'<g transform="translate({x:.0f},{BOOT_TOP}) rotate({ang:.1f})">'
            f'<path d="M -52 -8 Q -58 90 -46 150 Q -20 178 {dirx * 84} 172 '
            f'Q {dirx * 108} 156 {dirx * 88} 128 Q {dirx * 40} 120 44 120 L 52 -8 Z" '
            f'fill="{boot_c}"{_o(11)}/>'
            f'<path d="M -34 30 L 34 58 M -34 58 L 34 30 M -34 86 L 34 114 M -34 114 L 34 86" '
            f'stroke="{shade(boot_c, 1.5)}" stroke-width="7"/></g>')


def _sleeve(ids: _Ids, x: float, ang: float, fill: str, skin: str, cuff_c: str,
            ln: float = 300, w: float = 96) -> str:
    h = w / 2
    d = (f"M {-h} -16 Q {-h - 14} {ln * 0.5:.0f} {-h - 4} {ln:.0f} "
         f"L {h + 4} {ln:.0f} Q {h + 14} {ln * 0.5:.0f} {h} -16 Q 0 {-16 - h * 0.5:.0f} {-h} -16 Z")
    hand = (f'<path d="M -26 {ln - 6:.0f} Q -34 {ln + 30:.0f} -14 {ln + 44:.0f} '
            f'Q 8 {ln + 52:.0f} 24 {ln + 36:.0f} Q 36 {ln + 18:.0f} 26 {ln - 6:.0f} Z" '
            f'fill="{skin}"{_o(9)}/>'
            f'<path d="M -28 {ln + 10:.0f} q -14 6 -8 22 q 12 8 20 -4 Z" fill="{skin}"{_o(7)}/>')
    return (f'<g transform="translate({x:.0f},{SH_Y + 20}) rotate({ang:.1f})">'
            f'<path d="{d}" fill="{fill}"{_o(11)}/>' + _cuff(w, ln, cuff_c) + hand + "</g>")


def _prop(ids: _Ids, kind: str, look: CharacterLook) -> str:
    """Held prop anchored near the right hand (hang pose): sword / staff / bag."""
    if kind == "sword":
        x, y = CX + 268, SH_Y + 330
        blade_dfs, blade = _lg(ids, "#e8ecf0", "#8a97a5")
        return (f"<defs>{blade_dfs}</defs><g transform='rotate(14 {x} {y})'>"
                f'<rect x="{x - 11}" y="{y - 40}" width="22" height="330" rx="8" fill="{blade}"{_o(8)}/>'
                f'<path d="M {x - 11} {y + 260} L {x} {y + 306} L {x + 11} {y + 260} Z" fill="{blade}"{_o(7)}/>'
                f'<rect x="{x - 42}" y="{y - 66}" width="84" height="30" rx="10" fill="{GOLD}"{_o(8)}/>'
                f'<rect x="{x - 14}" y="{y - 130}" width="28" height="70" rx="10" fill="{shade(look.accent, 0.8)}"{_o(8)}/>'
                f'<path d="M {x} {y + 306} l -14 40 l 14 34 l 14 -34 Z" fill="{look.accent}" stroke="{GOLD_D}" stroke-width="6"/>'
                "</g>")
    if kind == "bag":
        x, y = CX + 286, SH_Y + 430
        return (f'<path d="M {x - 60} {y} L {x + 60} {y} L {x + 52} {y + 96} L {x - 52} {y + 96} Z" '
                f'fill="{shade("#7a5636", 0.9)}"{_o(9)}/>'
                f'<path d="M {x - 30} {y} Q {x} {y - 44} {x + 30} {y}" fill="none" stroke="{_INK}" stroke-width="9"/>'
                f'<rect x="{x - 14}" y="{y + 34}" width="28" height="20" rx="6" fill="{GOLD}"{_o(6)}/>')
    return ""


# ── assembly ──────────────────────────────────────────────────────────────────
def vector_hero_inner(look, emotion: str = "neutral", pose: str = "stand",
                      facing: str = "front") -> str:
    """Vector-hero figure CONTENT on the 1024×1536 frame. Never raises."""
    try:
        ids = _Ids()
        lk = look if isinstance(look, CharacterLook) else derive_look(0, base=dict(look or {}))
        p = _POSES.get((pose or "stand").strip().lower(), _POSES["stand"])
        emotion = (emotion or "neutral").strip().lower()
        o = _outfit(ids, lk)

        (lx, la), (rx, ra) = _LEGS.get(p.get("legs", "stand"), _LEGS["stand"])
        boots = _boot(lx, la, o["boot"], -1) + _boot(rx, ra, o["boot"], 1)

        ln = 240 if p.get("short") else 300
        arms_back, arms_front = "", ""
        for x, ang, ln_i in ((CX - 236, p["aL"], ln),
                             (CX + 236, p["aR"], 220 if p.get("short_r") else ln)):
            s = _sleeve(ids, x, ang, o["sleeve"], lk.skin, o["cuff_c"], ln=ln_i)
            if abs(ang) > 95:
                arms_front += s
            else:
                arms_back += s
        if p.get("cross"):
            arms_back += (f'<path d="M {CX - 170} {SH_Y + 160} Q {CX} {SH_Y + 110} {CX + 170} {SH_Y + 160} '
                          f'L {CX + 156} {SH_Y + 236} Q {CX} {SH_Y + 190} {CX - 156} {SH_Y + 236} Z" '
                          f'fill="{o["sleeve"]}"{_o(11)}/>')

        prop = ""
        if o.get("prop") and pose in ("stand", "hold", "point", "stern", "bow"):
            prop = _prop(ids, o["prop"], lk)

        hair_back, hair_front = _hair(ids, lk)
        head = _head(ids, lk, emotion, facing) + hair_front
        if "glasses" in lk.accessories:
            head += (f'<g stroke="{_INK}" stroke-width="7" fill="none">'
                     f'<circle cx="{CX - 96}" cy="{EY}" r="44"/><circle cx="{CX + 96}" cy="{EY}" r="44"/>'
                     f'<path d="M {CX - 52} {EY} Q {CX} {EY - 12} {CX + 52} {EY}"/></g>')
        if "beard" in lk.accessories:
            c = lk.hair_color
            head += (f'<path d="M {CX - 84} {MY - 30} Q {CX - 60} {MY + 90} {CX} {MY + 104} '
                     f'Q {CX + 60} {MY + 90} {CX + 84} {MY - 30} Q {CX + 40} {MY + 24} {CX} {MY + 26} '
                     f'Q {CX - 40} {MY + 24} {CX - 84} {MY - 30} Z" fill="{shade(c, 0.9)}"{_o(9)}/>')

        upper = o["defs"] + hair_back + o["body"] + arms_back + prop + head + arms_front
        bow = p.get("bow", 0) + (6 if lk.age == "elder" else 0)
        if bow:
            upper = f'<g transform="rotate({bow} {CX} {BELT_Y})">{upper}</g>'

        ground = _soft(ids, CX, 1424, 230, 30, 0.30)
        body = ground + boots + upper
        if p.get("dy"):
            body = f'<g transform="translate(0,{p["dy"]})">{body}</g>'
        if p.get("lean"):
            body = f'<g transform="rotate({p["lean"]} {CX} 1400)">{body}</g>'
        s = 0.78 if lk.age == "child" else 1.0
        if s != 1.0:
            body = (f'<g transform="translate({CX * (1 - s):.1f},{1420 * (1 - s):.1f}) scale({s})">'
                    f"{body}</g>")
        if facing == "left":
            body = f'<g transform="translate({W},0) scale(-1,1)">{body}</g>'
        return body
    except Exception:
        return ""


def build_vector_hero(look, emotion: str = "neutral", pose: str = "stand",
                      facing: str = "front") -> str:
    inner = vector_hero_inner(look, emotion, pose, facing)
    if not inner:
        return ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{inner}</svg>')


__all__ = ["vector_hero_inner", "build_vector_hero", "EMOTIONS", "POSES"]
