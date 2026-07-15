"""
anime_char.py — cel-shaded anime CHARACTER builder (GĐ2 Visual Foundation, v2.1).

v2.1 rebuild (user review: "nhân vật xấu, không chi tiết"): every major shape is now
CEL-SHADED — a clipPath per silhouette carries shadow + highlight layers that hug the
form (light from upper-left), plus thin line-art outlines, layered anime eyes
(lash band / iris gradient / crease / lower lash), hair with gloss band + strand
accents + under-fringe shadow, tapered limbs with proper hands, garment folds/seams/
cuffs, and a soft ground-contact shadow.

All gradient/clip ids are NAMESPACED PER INSTANCE (several characters compose into
one SVG; resvg resolves duplicate ids to the last definition).

Canvas 1024×1536. Pure str → str; never raises; unknown tokens fall back safely.
NOT wired into the render pipeline yet (GĐ2 DoD: contact-sheet approval first).
"""
from __future__ import annotations

import itertools

from app.features.render.engine.visual.v2.look_spec import (
    CharacterLook, derive_look, shade,
)

W, H = 1024, 1536
CX = 512
_LINE = "#26201c"          # lash / brow / line-art ink

EMOTIONS = ("neutral", "happy", "joy", "angry", "sad", "cry",
            "surprised", "fear", "stern", "shy")
POSES = ("stand", "wave", "point", "cheer", "hands_hips", "cross_arms", "think",
         "bow", "fight", "hold", "run", "sit", "kneel")
FACINGS = ("front", "left", "right")

_INST = itertools.count(1)


class _Ids:
    """Per-instance unique id factory (clip/gradient ids must never collide when
    several characters are embedded in one SVG)."""

    def __init__(self) -> None:
        self.p = f"ch{next(_INST)}"
        self.n = itertools.count(1)

    def new(self) -> str:
        return f"{self.p}_{next(self.n)}"


# ── cel-shade toolkit ─────────────────────────────────────────────────────────
def _cel(ids: _Ids, d: str, fill: str, *, shadow: str = "", light: str = "",
         outline: bool = True, sw: float = 3.0) -> str:
    """Base shape + clipped shadow/highlight layers + line-art outline."""
    stroke = f' stroke="{shade(fill, 0.5)}" stroke-width="{sw}"' if outline else ""
    out = f'<path d="{d}" fill="{fill}"{stroke}/>'
    if shadow or light:
        cid = ids.new()
        out = (f'<defs><clipPath id="{cid}"><path d="{d}"/></clipPath></defs>'
               + out + f'<g clip-path="url(#{cid})">{shadow}{light}</g>')
    return out


def _sh(d: str, op: float = 0.16) -> str:
    return f'<path d="{d}" fill="#1a1024" opacity="{op}"/>'


def _hl(d: str, op: float = 0.22) -> str:
    return f'<path d="{d}" fill="#ffffff" opacity="{op}"/>'


def _soft_shadow(ids: _Ids, cx: float, cy: float, rx: float, ry: float, op: float = 0.30) -> str:
    gid = ids.new()
    return (f'<defs><radialGradient id="{gid}"><stop offset="0" stop-color="#0c0814" '
            f'stop-opacity="{op}"/><stop offset="1" stop-color="#0c0814" stop-opacity="0"/>'
            f'</radialGradient></defs>'
            f'<ellipse cx="{cx:.0f}" cy="{cy:.0f}" rx="{rx:.0f}" ry="{ry:.0f}" fill="url(#{gid})"/>')


# ── geometry per build ────────────────────────────────────────────────────────
def _geom(look: CharacterLook) -> dict:
    g = {
        "neck_top": 376, "sh_y": 462, "waist_y": 700, "hip_y": 792,
        "sh_w": 150, "waist_w": 88, "hip_w": 104, "hip_dx": 52,
        "arm_l1": 195, "arm_l2": 180, "arm_w1": 54, "arm_w2": 40,
        "leg_l1": 300, "leg_l2": 296, "leg_w1": 76, "leg_w2": 52,
        "scale": 1.0, "head_scale": 1.06, "stoop": 0,
    }
    if look.gender == "female":
        g.update(sh_w=126, waist_w=74, hip_w=118, hip_dx=50,
                 arm_w1=44, arm_w2=32, leg_w1=66, leg_w2=44)
    if look.age == "child":
        g.update(scale=0.72, head_scale=1.24, sh_w=g["sh_w"] * 0.82,
                 hip_w=g["hip_w"] * 0.85)
    elif look.age == "elder":
        g.update(stoop=7)
    return g


# ── limbs (tapered two segments + shaded) ─────────────────────────────────────
def _taper_d(l: float, w0: float, w1: float, top: float = -14) -> str:
    """Tapered limb segment silhouette: wider at the joint, slimmer at the end,
    with a slight outer-curve so it reads as flesh, not a capsule."""
    h0, h1 = w0 / 2, w1 / 2
    return (f"M {-h0:.0f} {top} Q {-h0 - 3:.0f} {l * 0.45:.0f} {-h1:.0f} {l:.0f} "
            f"Q 0 {l + h1 * 0.9:.0f} {h1:.0f} {l:.0f} "
            f"Q {h0 + 3:.0f} {l * 0.45:.0f} {h0:.0f} {top} "
            f"Q 0 {top - h0 * 0.7:.0f} {-h0:.0f} {top} Z")


def _seg_shade(l: float, w0: float, w1: float) -> str:
    """Right-side core shadow strip inside a tapered segment (light = upper-left)."""
    h0, h1 = w0 / 2, w1 / 2
    return _sh(f"M {h0 * 0.25:.0f} -10 Q {h0 * 0.45:.0f} {l * 0.5:.0f} {h1 * 0.3:.0f} {l:.0f} "
               f"L {h1:.0f} {l:.0f} Q {h0 + 3:.0f} {l * 0.45:.0f} {h0:.0f} -14 Z", 0.14)


def _hand(ids: _Ids, skin: str, l2: float) -> str:
    d = (f"M -18 {l2 - 26:.0f} Q -24 {l2 - 2:.0f} -12 {l2 + 8:.0f} "
         f"Q 0 {l2 + 16:.0f} 12 {l2 + 8:.0f} Q 24 {l2 - 2:.0f} 18 {l2 - 26:.0f} Z")
    thumb = (f'<ellipse cx="-17" cy="{l2 - 16:.0f}" rx="8" ry="14" fill="{skin}" '
             f'stroke="{shade(skin, 0.62)}" stroke-width="2.5" transform="rotate(18 -17 {l2 - 16:.0f})"/>')
    return _cel(ids, d, skin, shadow=_sh(f"M 4 {l2 - 26:.0f} L 20 {l2 - 26:.0f} "
                                         f"Q 24 {l2 - 2:.0f} 12 {l2 + 8:.0f} Z", 0.12), sw=2.5) + thumb


def _shoe(ids: _Ids, color: str, l2: float, dirx: int) -> str:
    d = (f"M {-30 * dirx} {l2 - 14:.0f} Q {-38 * dirx} {l2 + 12:.0f} {-20 * dirx} {l2 + 18:.0f} "
         f"L {52 * dirx} {l2 + 18:.0f} Q {66 * dirx} {l2 + 12:.0f} {58 * dirx} {l2 - 2:.0f} "
         f"Q {40 * dirx} {l2 - 16:.0f} {12 * dirx} {l2 - 16:.0f} Z")
    return _cel(ids, d, color,
                shadow=_sh(f"M {-30 * dirx} {l2 + 8:.0f} L {62 * dirx} {l2 + 8:.0f} "
                           f"L {60 * dirx} {l2 + 18:.0f} L {-24 * dirx} {l2 + 18:.0f} Z", 0.22),
                light=_hl(f"M {-8 * dirx} {l2 - 12:.0f} Q {28 * dirx} {l2 - 14:.0f} "
                          f"{46 * dirx} {l2 - 4:.0f} L {40 * dirx} {l2:.0f} "
                          f"Q {16 * dirx} {l2 - 8:.0f} {-6 * dirx} {l2 - 6:.0f} Z", 0.18), sw=2.5)


def _limb(ids: _Ids, x: float, y: float, a1: float, a2: float, l1: float, l2: float,
          w1: float, w2: float, c1: str, c2: str, end: str = "", cuff: str = "") -> str:
    d1 = _taper_d(l1, w1, w1 * 0.82)
    d2 = _taper_d(l2, w1 * 0.8, w2, top=-12)
    seg2 = _cel(ids, d2, c2, shadow=_seg_shade(l2, w1 * 0.8, w2), sw=2.8)
    return (
        f'<g transform="translate({x:.0f},{y:.0f}) rotate({a1:.1f})">'
        + _cel(ids, d1, c1, shadow=_seg_shade(l1, w1, w1 * 0.82), sw=2.8)
        + f'<g transform="translate(0,{l1 - 8:.0f}) rotate({a2:.1f})">'
        + seg2 + cuff + end + "</g></g>"
    )


# ── poses (unchanged vocabulary) ─────────────────────────────────────────────
_POSES: dict = {
    "stand":      dict(aL=(8, 3), aR=(-8, -3), legs="stand"),
    "wave":       dict(aL=(8, 3), aR=(-162, -24), legs="stand"),
    "point":      dict(aL=(10, 4), aR=(-62, -10), legs="stand"),
    "cheer":      dict(aL=(158, 16), aR=(-158, -16), legs="wide"),
    "hands_hips": dict(aL=(32, -122), aR=(-32, 122), legs="wide"),
    "cross_arms": dict(aL=(20, 0), aR=(-20, 0), legs="stand", cross=True),
    "think":      dict(aL=(8, 3), aR=(-22, -122), legs="stand"),
    "bow":        dict(aL=(6, 2), aR=(-6, -2), legs="stand", bow=36),
    "fight":      dict(aL=(26, 116), aR=(-26, -116), legs="wide", lean=-3),
    "hold":       dict(aL=(10, 4), aR=(-48, -76), legs="stand"),
    "run":        dict(aL=(38, 96), aR=(-38, -96), legs="run", lean=-7),
    "sit":        dict(aL=(22, 8), aR=(-22, -8), legs="sit", dy=212),
    "kneel":      dict(aL=(10, 4), aR=(-10, -4), legs="kneel", dy=150),
}
_LEGS: dict = {
    "stand": ((3, -1), (-3, 1)),
    "wide":  ((14, -5), (-14, 5)),
    "walk":  ((-15, 6), (13, -17)),
    "run":   ((-30, 24), (30, -58)),
    "sit":   ((10, -102), (-10, 102)),
    "kneel": ((-80, 84), (4, -102)),
}


# ── outfits ───────────────────────────────────────────────────────────────────
def _torso_d(shw: float, ww: float, hw: float) -> str:
    return (f"M {CX - shw:.0f} 480 Q {CX - shw - 5:.0f} 590 {CX - ww:.0f} 700 "
            f"L {CX - hw:.0f} 796 L {CX + hw:.0f} 796 L {CX + ww:.0f} 700 "
            f"Q {CX + shw + 5:.0f} 590 {CX + shw:.0f} 480 Q {CX:.0f} 452 {CX - shw:.0f} 480 Z")


def _torso_shade(shw: float, ww: float, hw: float) -> str:
    """Right-side form shadow + under-chest AO + left highlight."""
    return (_sh(f"M {CX + shw * 0.35:.0f} 462 Q {CX + shw * 0.5:.0f} 600 {CX + ww * 0.45:.0f} 700 "
                f"L {CX + hw:.0f} 796 L {CX + ww:.0f} 700 Q {CX + shw + 5:.0f} 590 {CX + shw:.0f} 480 Z", 0.13)
            + _sh(f"M {CX - ww:.0f} 690 L {CX + ww:.0f} 690 L {CX + hw:.0f} 796 L {CX - hw:.0f} 796 Z", 0.06)
            + _hl(f"M {CX - shw * 0.72:.0f} 470 Q {CX - shw * 0.8:.0f} 580 {CX - ww * 0.8:.0f} 690 "
                  f"L {CX - ww * 0.55:.0f} 690 Q {CX - shw * 0.5:.0f} 570 {CX - shw * 0.45:.0f} 466 Z", 0.10))


def _folds(pts: "list[tuple]", color: str, w: float = 3.5, op: float = 0.45) -> str:
    """Cloth fold accents: short curved strokes."""
    out = ""
    for (x0, y0, x1, y1, bend) in pts:
        mx, my = (x0 + x1) / 2 + bend, (y0 + y1) / 2
        out += (f'<path d="M {x0} {y0} Q {mx:.0f} {my:.0f} {x1} {y1}" stroke="{color}" '
                f'stroke-width="{w}" fill="none" stroke-linecap="round" opacity="{op}"/>')
    return out


def _skirt(ids: _Ids, hw: float, kw: float, y0: int, y1: int, color: str, pleat: bool = True) -> str:
    d = (f"M {CX - hw:.0f} {y0} L {CX - kw:.0f} {y1} Q {CX:.0f} {y1 + 14} {CX + kw:.0f} {y1} "
         f"L {CX + hw:.0f} {y0} Z")
    n = 6
    pleats = ""
    if pleat:
        for i in range(1, n):
            x0 = CX - hw + (2 * hw) * i / n
            x1 = CX - kw + (2 * kw) * i / n
            pleats += (f'<path d="M {x0:.0f} {y0 + 6} L {x1:.0f} {y1 - 2}" '
                       f'stroke="{shade(color, 0.72)}" stroke-width="3.5" opacity="0.7"/>')
            if i % 2 == 0:
                pleats += (f'<path d="M {x0 + 3:.0f} {y0 + 6} L {x1 + 3:.0f} {y1 - 2}" '
                           f'stroke="{shade(color, 1.2)}" stroke-width="2" opacity="0.5"/>')
    swing = _sh(f"M {CX + hw * 0.25:.0f} {y0} L {CX + hw:.0f} {y0} L {CX + kw:.0f} {y1} "
                f"L {CX + kw * 0.4:.0f} {y1} Z", 0.13)
    hem = f'<path d="M {CX - kw:.0f} {y1} Q {CX:.0f} {y1 + 14} {CX + kw:.0f} {y1}" stroke="{shade(color, 0.6)}" stroke-width="4" fill="none"/>'
    return _cel(ids, d, color, shadow=swing) + pleats + hem


def _outfit(ids: _Ids, look: CharacterLook, g: dict) -> dict:
    p1, p2, acc = look.outfit_primary, look.outfit_secondary, look.accent
    skin = look.skin
    shw, ww, hw = g["sh_w"], g["waist_w"], g["hip_w"]
    base = _torso_d(shw, ww, hw)
    tshade = _torso_shade(shw, ww, hw)
    o = dict(torso="", over="", skirt="", sleeve_c1=p1, sleeve_c2=p1,
             hand_skin=skin, legs_color=shade(p1, 0.55), shoe="#3a3a42")
    f = look.gender == "female"
    kind = look.outfit
    dk = shade(p1, 0.7)

    if kind == "school_uniform":
        if f:
            o["torso"] = (_cel(ids, base, p2, shadow=tshade)
                          + _folds([(CX - 40, 600, CX - 30, 680, -8), (CX + 44, 590, CX + 36, 670, 10)], shade(p2, 0.7))
                          + _cel(ids, f"M {CX - 62} 460 L {CX} 546 L {CX + 62} 460 L {CX + 112} 488 "
                                      f"L {CX} 596 L {CX - 112} 488 Z", p1,
                                 shadow=_sh(f"M {CX} 546 L {CX + 62} 460 L {CX + 112} 488 L {CX} 596 Z", 0.15))
                          + f'<path d="M {CX - 96} 480 L {CX} 576 M {CX + 96} 480 L {CX} 576" stroke="{p2}" stroke-width="4" fill="none" opacity="0.8"/>'
                          + f'<path d="M {CX} 566 l -22 26 l 22 34 l 22 -34 Z" fill="{acc}" stroke="{shade(acc, 0.6)}" stroke-width="2.5"/>'
                          + f'<circle cx="{CX}" cy="576" r="7" fill="{shade(acc, 1.25)}"/>')
            o.update(skirt=_skirt(ids, hw + 6, hw + 46, 780, 1010, p1), legs_color=skin,
                     sleeve_c1=p2, sleeve_c2=p2, shoe="#2e2a2a")
        else:
            o["torso"] = (_cel(ids, base, p1, shadow=tshade)
                          + f'<path d="M {CX - 3} 474 L {CX + 3} 474 L {CX + 3} 786 L {CX - 3} 786 Z" fill="{dk}"/>'
                          + "".join(f'<circle cx="{CX}" cy="{y}" r="7" fill="{acc}" stroke="{shade(acc, 0.55)}" stroke-width="2"/>'
                                    f'<circle cx="{CX - 2}" cy="{y - 2}" r="2" fill="#fff" opacity="0.7"/>'
                                    for y in (540, 620, 700))
                          + _cel(ids, f"M {CX - 54} 448 L {CX + 54} 448 L {CX + 50} 478 L {CX - 50} 478 Z",
                                 shade(p1, 0.85))
                          + _folds([(CX - ww + 10, 640, CX - ww + 26, 700, -6),
                                    (CX + ww - 10, 640, CX + ww - 26, 700, 6)], dk))
    elif kind == "office_suit":
        lapelL = (f"M {CX - 56} 458 L {CX - 6} 560 L {CX - 34} 596 L {CX - 66} 500 Z")
        lapelR = (f"M {CX + 56} 458 L {CX + 6} 560 L {CX + 34} 596 L {CX + 66} 500 Z")
        shirt = _cel(ids, f"M {CX - 50} 460 L {CX} 600 L {CX + 50} 460 Z", p2,
                     shadow=_sh(f"M {CX} 600 L {CX + 50} 460 L {CX + 22} 460 Z", 0.12), sw=2)
        tie = ""
        if not f:
            tie = (f'<path d="M {CX} 466 l -13 15 l 13 116 l 13 -116 Z" fill="{acc}" '
                   f'stroke="{shade(acc, 0.6)}" stroke-width="2"/>'
                   + _sh(f"M {CX} 481 l 13 0 l 0 100 Z", 0.2)
                   + f'<path d="M {CX - 8} 470 h 16 l -4 12 h -8 Z" fill="{shade(acc, 0.8)}"/>')
        o["torso"] = (_cel(ids, base, p1, shadow=tshade) + shirt + tie
                      + _cel(ids, lapelL, shade(p1, 0.9), sw=2.5) + _cel(ids, lapelR, shade(p1, 0.86), sw=2.5)
                      + f'<circle cx="{CX - 20}" cy="640" r="5" fill="{dk}"/>'
                      + _folds([(CX - ww + 12, 620, CX - ww + 30, 690, -8),
                                (CX + ww - 12, 620, CX + ww - 30, 690, 8)], dk)
                      + f'<path d="M {CX - shw + 18} 700 L {CX - 30} 700 M {CX + shw - 18} 700 L {CX + 30} 700" stroke="{dk}" stroke-width="3" opacity="0.5"/>')
        if f:
            o.update(skirt=_skirt(ids, hw + 4, hw + 12, 780, 1060, shade(p1, 0.92), pleat=False), legs_color=skin)
        o["shoe"] = "#221e1e"
    elif kind == "doctor_coat":
        coat = (_cel(ids, base, p1, shadow=tshade)
                + _cel(ids, f"M {CX - 50} 458 L {CX} 610 L {CX + 50} 458 L {CX + 34} 744 "
                            f"L {CX - 34} 744 Z", p2, sw=2)
                + f'<path d="M {CX} 560 L {CX} 790" stroke="{shade(p1, 0.72)}" stroke-width="4"/>'
                + f'<rect x="{CX - ww + 10}" y="650" width="62" height="82" rx="6" fill="{shade(p1, 0.96)}" stroke="{shade(p1, 0.72)}" stroke-width="2"/>'
                + f'<rect x="{CX + ww - 72}" y="650" width="62" height="82" rx="6" fill="{shade(p1, 0.96)}" stroke="{shade(p1, 0.72)}" stroke-width="2"/>'
                + f'<path d="M {CX - 38} 488 Q {CX - 80} 548 {CX - 42} 604 M {CX + 38} 488 Q {CX + 80} 548 {CX + 42} 604" stroke="#354b5b" stroke-width="7" fill="none"/>'
                + f'<circle cx="{CX + 45}" cy="610" r="15" fill="none" stroke="#354b5b" stroke-width="6"/>'
                + _folds([(CX - ww + 12, 600, CX - ww + 30, 690, -8),
                          (CX + ww - 12, 600, CX + ww - 30, 690, 8)], shade(p1, 0.72)))
        o["torso"] = coat
        o.update(sleeve_c1=p1, sleeve_c2=p1, legs_color="#4f6f78", shoe="#e8ecee")
    elif kind == "police_uniform":
        o["torso"] = (_cel(ids, base, p1, shadow=tshade)
                      + _cel(ids, f"M {CX - 42} 452 L {CX} 520 L {CX + 42} 452 L {CX + 28} 472 "
                                  f"L {CX} 542 L {CX - 28} 472 Z", p2, sw=2)
                      + f'<path d="M {CX} 520 l -13 18 l 13 116 l 13 -116 Z" fill="{acc}" stroke="{shade(acc, 0.6)}" stroke-width="2"/>'
                      + f'<path d="M {CX - ww - 4} 686 H {CX + ww + 4}" stroke="#171d27" stroke-width="28"/>'
                      + f'<rect x="{CX - 18}" y="671" width="36" height="30" rx="4" fill="#d8b44a" stroke="#765b20" stroke-width="3"/>'
                      + f'<path d="M {CX + 54} 542 l 20 10 l -4 24 l -16 9 l -16 -9 l -4 -24 Z" fill="#d8b44a" stroke="#765b20" stroke-width="3"/>'
                      + f'<rect x="{CX - ww + 12}" y="590" width="54" height="58" rx="5" fill="{shade(p1, 0.9)}" stroke="{shade(p1, 0.65)}" stroke-width="2"/>'
                      + _folds([(CX - ww + 10, 620, CX - ww + 28, 700, -8)], dk))
        o.update(legs_color=shade(p1, 0.76), shoe="#151a22")
    elif kind == "engineer_workwear":
        o["torso"] = (_cel(ids, base, p1, shadow=tshade)
                      + f'<path d="M {CX} 472 V 790" stroke="{shade(p1, 0.62)}" stroke-width="5"/>'
                      + f'<rect x="{CX - ww + 12}" y="566" width="70" height="78" rx="7" fill="{shade(p1, 0.9)}" stroke="{shade(p1, 0.62)}" stroke-width="3"/>'
                      + f'<rect x="{CX + ww - 82}" y="566" width="70" height="78" rx="7" fill="{shade(p1, 0.9)}" stroke="{shade(p1, 0.62)}" stroke-width="3"/>'
                      + f'<path d="M {CX - shw + 8} 670 H {CX + shw - 8}" stroke="{p2}" stroke-width="18" opacity="0.95"/>'
                      + f'<path d="M {CX - shw + 8} 676 H {CX + shw - 8}" stroke="#f7f0be" stroke-width="4" opacity="0.8"/>'
                      + f'<circle cx="{CX + 48}" cy="522" r="13" fill="{acc}" stroke="{shade(acc, 0.6)}" stroke-width="3"/>'
                      + _folds([(CX - 40, 620, CX - 30, 714, -8), (CX + 42, 620, CX + 32, 714, 8)], dk))
        o.update(legs_color=shade(p1, 0.82), shoe="#2b3238")
    elif kind == "tee_casual":
        o["torso"] = (_cel(ids, base, p1, shadow=tshade)
                      + _cel(ids, f"M {CX - 42} 452 Q {CX} 488 {CX + 42} 452 L {CX + 36} 472 "
                                  f"Q {CX} 506 {CX - 36} 472 Z", shade(p1, 0.8), sw=2)
                      + _folds([(CX - 30, 560, CX + 10, 600, 12), (CX - ww + 12, 660, CX - ww + 34, 706, -8)], dk)
                      + f'<path d="M {CX - ww + 4} 770 L {CX + ww - 4} 770" stroke="{dk}" stroke-width="4" opacity="0.5"/>')
        o.update(sleeve_c2=skin, legs_color="#3a4c66", shoe="#e8e6e0")
    elif kind == "hoodie":
        hood = _cel(ids, f"M {CX - 98} 474 Q {CX} 568 {CX + 98} 474 L {CX + 78} 432 "
                         f"Q {CX} 506 {CX - 78} 432 Z", shade(p1, 0.78), sw=2.5)
        o["torso"] = (_cel(ids, base, p1, shadow=tshade) + hood
                      + _cel(ids, f"M {CX - 68} 636 L {CX + 68} 636 L {CX + 58} 762 L {CX - 58} 762 Z",
                             shade(p1, 0.88),
                             shadow=_sh(f"M {CX - 68} 636 L {CX + 68} 636 L {CX + 64} 660 L {CX - 64} 660 Z", 0.12))
                      + f'<path d="M {CX - 26} 502 Q {CX - 24} 560 {CX - 28} 592 M {CX + 26} 502 Q {CX + 24} 560 {CX + 28} 592" stroke="{p2}" stroke-width="6" fill="none" stroke-linecap="round"/>'
                      + f'<circle cx="{CX - 28}" cy="596" r="5" fill="{p2}"/><circle cx="{CX + 28}" cy="596" r="5" fill="{p2}"/>'
                      + _folds([(CX - ww + 10, 600, CX - ww + 28, 660, -8), (CX + ww - 10, 600, CX + ww - 28, 660, 8)], dk))
        o.update(legs_color=p2, shoe="#d9d5cd")
    elif kind == "dress":
        o["torso"] = (_cel(ids, base, p1, shadow=tshade)
                      + _cel(ids, f"M {CX - 46} 452 Q {CX} 494 {CX + 46} 452 L {CX + 38} 476 "
                                  f"Q {CX} 518 {CX - 38} 476 Z", p2, sw=2)
                      + f'<rect x="{CX - ww - 2}" y="672" width="{2 * ww + 4}" height="24" rx="10" fill="{acc}" stroke="{shade(acc, 0.6)}" stroke-width="2.5"/>'
                      + f'<path d="M {CX - 10} 678 l 10 -8 l 10 8 l -10 8 Z" fill="{shade(acc, 1.3)}"/>')
        o.update(skirt=_skirt(ids, hw + 8, hw + 98, 776, 1180, p1, pleat=False)
                 + _folds([(CX - 50, 820, CX - 66, 1120, -14), (CX + 44, 820, CX + 60, 1120, 14),
                           (CX - 4, 830, CX - 6, 1100, 6)], shade(p1, 0.72), 4, 0.5),
                 legs_color=skin, sleeve_c2=skin, shoe="#8a5a5a")
    elif kind in ("hanfu_robe", "kimono"):
        o["torso"] = (_cel(ids, base, p1, shadow=tshade)
                      + _cel(ids, f"M {CX - shw} 480 L {CX + 34} 646 L {CX + 22} 796 L {CX - hw} 796 Z", p1,
                             shadow=_sh(f"M {CX - 20} 560 L {CX + 34} 646 L {CX + 22} 796 L {CX - 30} 796 Z", 0.10))
                      + _cel(ids, f"M {CX - shw + 8} 472 L {CX + 28} 636 L {CX + 46} 620 L {CX - shw + 38} 458 Z", p2, sw=2)
                      + _cel(ids, f"M {CX + shw - 8} 472 L {CX + 6} 570 L {CX + 22} 584 L {CX + shw - 30} 462 Z",
                             shade(p2, 0.9), sw=2)
                      + _folds([(CX - 40, 620, CX - 52, 700, -10), (CX + 8, 680, CX + 2, 760, 6)], dk))
        obi_h = 68 if kind == "kimono" else 42
        o["over"] = (f'<rect x="{CX - ww - 16}" y="656" width="{2 * (ww + 16)}" height="{obi_h}" rx="6" '
                     f'fill="{p2}" stroke="{shade(p2, 0.6)}" stroke-width="3"/>'
                     + _sh(f"M {CX - ww - 16} {656 + obi_h - 12} h {2 * (ww + 16)} v 12 h {-2 * (ww + 16)} Z", 0.18)
                     + (f'<rect x="{CX - 22}" y="662" width="44" height="{obi_h - 12}" rx="4" fill="{shade(p2, 0.82)}"/>'
                        if kind == "kimono" else
                        f'<path d="M {CX - 30} {656 + obi_h // 2} h 60" stroke="{shade(p2, 0.7)}" stroke-width="5"/>'))
        o["skirt"] = (_cel(ids, f"M {CX - hw - 8} 780 L {CX - hw - (36 if kind == 'kimono' else 122)} 1392 "
                              f"Q {CX:.0f} 1414 {CX + hw + (36 if kind == 'kimono' else 122)} 1392 "
                              f"L {CX + hw + 8} 780 Z", p1,
                           shadow=_sh(f"M {CX + 10} 780 L {CX + hw + 8} 780 "
                                      f"L {CX + hw + (36 if kind == 'kimono' else 122)} 1392 "
                                      f"L {CX + 40} 1400 Z", 0.12))
                      + _folds([(CX - 60, 860, CX - 80, 1330, -16), (CX + 54, 860, CX + 74, 1330, 16),
                                (CX - 6, 880, CX - 10, 1320, 8)], dk, 4, 0.45))
        o.update(legs_color=skin, shoe="#4a3a30", wide_cuff=True)
    elif kind == "armor_light":
        plate = (f"M {CX - shw + 14} 492 Q {CX} 460 {CX + shw - 14} 492 L {CX + ww + 10} 664 "
                 f"Q {CX} 702 {CX - ww - 10} 664 Z")
        o["torso"] = (_cel(ids, base, p2, shadow=tshade)
                      + _cel(ids, plate, p1,
                             shadow=_sh(f"M {CX + 20} 470 L {CX + shw - 14} 492 L {CX + ww + 10} 664 "
                                        f"Q {CX + 30} 690 {CX + 10} 692 Z", 0.16),
                             light=_hl(f"M {CX - shw + 24} 500 Q {CX - 40} 474 {CX - 20} 478 "
                                       f"L {CX - 26} 540 Q {CX - 70} 540 {CX - shw + 20} 560 Z", 0.16))
                      + f'<path d="M {CX} 500 L {CX} 690" stroke="{shade(p1, 0.6)}" stroke-width="5"/>'
                      + f'<path d="M {CX - ww} 588 Q {CX} 620 {CX + ww} 588" stroke="{shade(p1, 0.65)}" stroke-width="4" fill="none"/>'
                      + f'<circle cx="{CX - 34}" cy="530" r="6" fill="{shade(p1, 0.55)}"/><circle cx="{CX + 34}" cy="530" r="6" fill="{shade(p1, 0.55)}"/>'
                      + _cel(ids, f"M {CX - ww - 6} 700 L {CX - hw - 10} 802 L {CX + hw + 10} 802 L {CX + ww + 6} 700 Z",
                             shade(p1, 0.82),
                             shadow=_sh(f"M {CX} 700 L {CX + ww + 6} 700 L {CX + hw + 10} 802 L {CX + 10} 802 Z", 0.14))
                      + f'<path d="M {CX - ww} 750 L {CX + ww} 750" stroke="{shade(p1, 0.6)}" stroke-width="3" opacity="0.6"/>')
        pd = "M -46 -6 Q 0 -34 46 -6 Q 40 34 0 44 Q -40 34 -46 -6 Z"
        o["over"] = "".join(
            f'<g transform="translate({x},486)">'
            + _cel(ids, pd, shade(p1, 1.1), shadow=_sh("M 8 -22 Q 40 -16 44 0 Q 40 30 6 42 Z", 0.16),
                   light=_hl("M -38 -8 Q -20 -26 0 -26 L -4 -12 Q -22 -10 -32 2 Z", 0.2))
            + "</g>" for x in (CX - g["sh_w"] - 14, CX + g["sh_w"] + 14))
        o.update(legs_color=shade(p2, 0.8), shoe="#3d4552")
    elif kind == "coat_long":
        o["torso"] = (_cel(ids, base, p1, shadow=tshade)
                      + _cel(ids, f"M {CX - 42} 458 L {CX} 636 L {CX + 42} 458 Z", p2, sw=2)
                      + _cel(ids, f"M {CX - 56} 456 L {CX - 4} 560 L {CX - 30} 600 L {CX - 62} 500 Z", shade(p1, 0.88), sw=2.5)
                      + _cel(ids, f"M {CX + 56} 456 L {CX + 4} 560 L {CX + 30} 600 L {CX + 62} 500 Z", shade(p1, 0.84), sw=2.5)
                      + f'<circle cx="{CX - 16}" cy="628" r="5" fill="{dk}"/><circle cx="{CX + 16}" cy="628" r="5" fill="{dk}"/>'
                      + f'<path d="M {CX - ww - 2} 706 L {CX - 34} 706 M {CX + ww + 2} 706 L {CX + 34} 706" stroke="{dk}" stroke-width="4" opacity="0.6"/>')
        o["skirt"] = (_cel(ids, f"M {CX - hw - 6} 792 L {CX - hw - 38} 1134 L {CX - 22} 1134 L {CX - 10} 792 Z", p1,
                           shadow=_sh(f"M {CX - 40} 792 L {CX - 30} 1134 L {CX - 22} 1134 L {CX - 10} 792 Z", 0.14))
                      + _cel(ids, f"M {CX + hw + 6} 792 L {CX + hw + 38} 1134 L {CX + 22} 1134 L {CX + 10} 792 Z",
                             shade(p1, 0.86),
                             shadow=_sh(f"M {CX + hw - 10} 792 L {CX + hw + 38} 1134 L {CX + 24} 1134 Z", 0.12))
                      + _folds([(CX - hw - 10, 860, CX - hw - 24, 1090, -8),
                                (CX + hw + 10, 860, CX + hw + 24, 1090, 8)], dk, 3.5, 0.5))
        o.update(legs_color="#2e3038", shoe="#221e1e")
    else:  # apron_staff
        apron = (_cel(ids, f"M {CX - 46} 500 L {CX + 46} 500 L {CX + 46} 560 "
                          f"L {CX + 74} 582 L {CX + 90} {1000 if f else 800} "
                          f"Q {CX:.0f} {1016 if f else 812} {CX - 90} {1000 if f else 800} "
                          f"L {CX - 74} 582 L {CX - 46} 560 Z", p1,
                       shadow=_sh(f"M {CX + 10} 500 L {CX + 46} 500 L {CX + 46} 560 L {CX + 74} 582 "
                                  f"L {CX + 90} {1000 if f else 800} L {CX + 30} {1008 if f else 806} Z", 0.10))
                 + f'<path d="M {CX - 72} 646 L {CX + 72} 646" stroke="{shade(p1, 0.75)}" stroke-width="5" opacity="0.7"/>'
                 + f'<rect x="{CX - 32}" y="700" width="64" height="50" rx="8" fill="{shade(p1, 0.9)}" stroke="{shade(p1, 0.65)}" stroke-width="2.5"/>'
                 + _folds([(CX - 50, 720, CX - 58, 900, -8), (CX + 46, 720, CX + 54, 900, 8)], shade(p1, 0.7)))
        o["torso"] = _cel(ids, base, p2, shadow=tshade)
        o["over"] = apron
        o.update(sleeve_c1=p2, sleeve_c2=skin, legs_color=(skin if f else "#5a5248"),
                 shoe="#4a3a30")
    return o


# ── head + face ───────────────────────────────────────────────────────────────
def _face_d() -> str:
    return (f"M {CX - 92} 262 Q {CX - 94} 174 {CX} 166 Q {CX + 94} 174 {CX + 92} 262 "
            f"Q {CX + 92} 330 {CX + 54} 370 Q {CX + 24} 398 {CX} 400 Q {CX - 24} 398 {CX - 54} 370 "
            f"Q {CX - 92} 330 {CX - 92} 262 Z")


def _head_base(ids: _Ids, skin: str) -> str:
    ear = lambda ex, flip: (
        _cel(ids, f"M {ex - 14} 282 Q {ex - 20} 300 {ex - 12} 318 Q {ex - 2} 330 {ex + 8} 316 "
                  f"L {ex + 6} 286 Z", skin, sw=2.5)
        + f'<path d="M {ex - 8} 294 Q {ex - 10} 306 {ex - 2} 312" stroke="{shade(skin, 0.72)}" '
          f'stroke-width="3" fill="none"/>')
    face = _cel(ids, _face_d(), skin,
                shadow=_sh(f"M {CX + 40} 190 Q {CX + 92} 240 {CX + 88} 300 Q {CX + 80} 348 {CX + 50} 374 "
                           f"L {CX + 38} 360 Q {CX + 64} 320 {CX + 62} 260 Q {CX + 58} 214 {CX + 34} 194 Z", 0.10),
                sw=3)
    jaw_ao = _sh(f"M {CX - 30} 396 Q {CX} 410 {CX + 30} 396 L {CX + 22} 386 Q {CX} 396 {CX - 22} 386 Z", 0.10)
    return ear(CX - 94, -1) + ear(CX + 94, 1) + face + jaw_ao


def _eye(ids: _Ids, cx: int, cy: int, iris: str, *, mode: str = "open", dx: int = 0,
         female: bool = False) -> str:
    if mode == "closed_happy":
        return (f'<path d="M {cx - 26} {cy + 6} Q {cx} {cy - 20} {cx + 26} {cy + 6}" '
                f'stroke="{_LINE}" stroke-width="8" fill="none" stroke-linecap="round"/>'
                f'<path d="M {cx - 20} {cy + 14} Q {cx} {cy + 4} {cx + 20} {cy + 14}" '
                f'stroke="{shade("#e8b4a4", 0.9)}" stroke-width="3" fill="none" opacity="0.6"/>')
    if mode == "closed_sad":
        return (f'<path d="M {cx - 26} {cy - 4} Q {cx} {cy + 18} {cx + 26} {cy - 4}" '
                f'stroke="{_LINE}" stroke-width="8" fill="none" stroke-linecap="round"/>')
    wide = mode == "wide"
    half = mode == "half"
    ir = 15 if wide else 19
    ry = 32 if wide else 26
    gid = ids.new()
    iris_grad = (f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
                 f'<stop offset="0" stop-color="{shade(iris, 0.45)}"/>'
                 f'<stop offset="0.55" stop-color="{iris}"/>'
                 f'<stop offset="1" stop-color="{shade(iris, 1.45)}"/></linearGradient></defs>')
    if half:
        sclera_d = (f"M {cx - 30} {cy - 4} L {cx + 30} {cy - 4} Q {cx + 25} {cy + 19} {cx} {cy + 21} "
                    f"Q {cx - 25} {cy + 19} {cx - 30} {cy - 4} Z")
    else:
        sclera_d = (f"M {cx - 33} {cy + 3} Q {cx - 28} {cy - ry + 3} {cx} {cy - ry} "
                    f"Q {cx + 28} {cy - ry + 3} {cx + 33} {cy + 3} Q {cx + 26} {cy + 19} {cx} {cy + 21} "
                    f"Q {cx - 26} {cy + 19} {cx - 33} {cy + 3} Z")
    scid = ids.new()
    sclera = (f'<defs><clipPath id="{scid}"><path d="{sclera_d}"/></clipPath></defs>'
              f'<path d="{sclera_d}" fill="#ffffff"/>'
              f'<g clip-path="url(#{scid})">'
              f'<circle cx="{cx + dx}" cy="{cy + 1}" r="{ir}" fill="url(#{gid})"/>'
              f'<circle cx="{cx + dx}" cy="{cy + 2}" r="{ir * 0.46:.0f}" fill="#16100c"/>'
              f'<circle cx="{cx + dx}" cy="{cy + ir * 0.55:.0f}" r="{ir * 0.5:.0f}" fill="{shade(iris, 1.6)}" opacity="0.4"/>'
              f'<circle cx="{cx + dx - 7}" cy="{cy - 8}" r="6" fill="#ffffff"/>'
              f'<circle cx="{cx + dx + 7}" cy="{cy + 8}" r="3" fill="#ffffff" opacity="0.9"/>'
              + (f'<rect x="{cx - 34}" y="{cy - ry}" width="68" height="9" fill="#8fa0b8" opacity="0.5"/>'
                 if not half else "")
              + "</g>")
    if half:
        lash = (f'<path d="M {cx - 31} {cy - 5} L {cx + 31} {cy - 5} L {cx + 31} {cy - 11} '
                f'L {cx - 31} {cy - 11} Z" fill="{_LINE}"/>')
    else:
        lash = (f'<path d="M {cx - 33} {cy + 1} Q {cx - 26} {cy - ry - 1} {cx} {cy - ry - 2} '
                f'Q {cx + 26} {cy - ry} {cx + 33} {cy - 1} '
                + (f'L {cx + 42} {cy - 9} ' if female else f'L {cx + 35} {cy - 6} ')
                + f'Q {cx + 27} {cy - ry - 7} {cx} {cy - ry - 8} '
                f'Q {cx - 27} {cy - ry - 7} {cx - 33} {cy - 5} Z" fill="{_LINE}"/>')
    crease = (f'<path d="M {cx - 24} {cy - ry - 12} Q {cx} {cy - ry - 18} {cx + 24} {cy - ry - 12}" '
              f'stroke="{shade("#d9a08a", 0.85)}" stroke-width="3" fill="none" opacity="0.55"/>') if not half else ""
    lower = (f'<path d="M {cx - 22} {cy + 20} Q {cx} {cy + 25} {cx + 22} {cy + 20}" '
             f'stroke="{_LINE}" stroke-width="3" fill="none" opacity="0.35"/>')
    return iris_grad + sclera + lash + crease + lower


def _brow(x0: int, x1: int, y0: float, y1: float) -> str:
    ym = min(y0, y1) - 6
    return (f'<path d="M {x0} {y0:.0f} Q {(x0 + x1) // 2} {ym:.0f} {x1} {y1:.0f} '
            f'L {x1} {y1 + 6:.0f} Q {(x0 + x1) // 2} {ym + 7:.0f} {x0} {y0 + 5:.0f} Z" fill="{_LINE}"/>')


_MOUTHS = {
    "neutral":     lambda: (f'<path d="M {CX - 14} 372 Q {CX} 379 {CX + 14} 372" stroke="#9a4a3a" stroke-width="6" fill="none" stroke-linecap="round"/>'
                            f'<path d="M {CX - 8} 384 Q {CX} 388 {CX + 8} 384" stroke="#d9a08a" stroke-width="3" fill="none" opacity="0.5"/>'),
    "smile":       lambda: (f'<path d="M {CX - 22} 365 Q {CX} 388 {CX + 22} 365" stroke="#9a4a3a" stroke-width="7" fill="none" stroke-linecap="round"/>'
                            f'<path d="M {CX - 10} 386 Q {CX} 391 {CX + 10} 386" stroke="#d9a08a" stroke-width="3" fill="none" opacity="0.5"/>'),
    "open_smile":  lambda: (f'<path d="M {CX - 25} 361 Q {CX} 404 {CX + 25} 361 Q {CX} 374 {CX - 25} 361 Z" fill="#7a2f2a" stroke="#5f241f" stroke-width="2"/>'
                            f'<path d="M {CX - 18} 364 Q {CX} 372 {CX + 18} 364 L {CX + 14} 370 Q {CX} 377 {CX - 14} 370 Z" fill="#ffffff"/>'
                            f'<path d="M {CX - 11} 386 Q {CX} 396 {CX + 11} 386 Q {CX} 391 {CX - 11} 386 Z" fill="#e2726a"/>'),
    "grit":        lambda: (f'<path d="M {CX - 21} 362 Q {CX} 380 {CX + 21} 362 L {CX + 17} 379 Q {CX} 391 {CX - 17} 379 Z" fill="#6f2320" stroke="#571b18" stroke-width="2"/>'
                            f'<path d="M {CX - 16} 367 L {CX + 16} 367 L {CX + 14} 374 L {CX - 14} 374 Z" fill="#f4efe4"/>'),
    "frown":       lambda: f'<path d="M {CX - 16} 377 Q {CX} 362 {CX + 16} 377" stroke="#9a4a3a" stroke-width="6" fill="none" stroke-linecap="round"/>',
    "wail":        lambda: (f'<path d="M {CX - 18} 378 Q {CX} 354 {CX + 18} 378 Q {CX} 398 {CX - 18} 378 Z" fill="#7a2f2a" stroke="#5f241f" stroke-width="2"/>'
                            f'<path d="M {CX - 9} 385 Q {CX} 392 {CX + 9} 385 Q {CX} 389 {CX - 9} 385 Z" fill="#e2726a"/>'),
    "o":           lambda: (f'<ellipse cx="{CX}" cy="372" rx="12" ry="16" fill="#7a2f2a" stroke="#5f241f" stroke-width="2"/>'
                            f'<ellipse cx="{CX}" cy="378" rx="6" ry="7" fill="#e2726a"/>'),
    "wavy":        lambda: (f'<path d="M {CX - 20} 372 Q {CX - 10} 363 {CX} 372 Q {CX + 10} 381 {CX + 20} 372" '
                            f'stroke="#7a2f2a" stroke-width="6" fill="none" stroke-linecap="round"/>'),
    "line":        lambda: f'<rect x="{CX - 16}" y="368" width="32" height="6" rx="3" fill="#9a4a3a"/>',
    "small_smile": lambda: f'<path d="M {CX - 12} 370 Q {CX} 380 {CX + 12} 370" stroke="#9a4a3a" stroke-width="5" fill="none" stroke-linecap="round"/>',
}

_EMOTIONS: dict = {
    "neutral":   ("open", (0, 0), "neutral", 0.0, 0, ""),
    "happy":     ("open", (0, -2), "smile", 0.3, 0, ""),
    "joy":       ("closed_happy", (-4, -4), "open_smile", 0.35, 0, ""),
    "angry":     ("open", (-6, 14), "grit", 0.0, 0, ""),
    "sad":       ("open", (2, -10), "frown", 0.0, 0, ""),
    "cry":       ("closed_sad", (2, -10), "wail", 0.0, 0, "tears"),
    "surprised": ("wide", (-14, -14), "o", 0.0, 0, ""),
    "fear":      ("wide", (2, -12), "wavy", 0.0, 0, "sweat"),
    "stern":     ("half", (4, 8), "line", 0.0, 0, ""),
    "shy":       ("open", (0, -2), "small_smile", 0.7, 9, ""),
}


def _face(ids: _Ids, look: CharacterLook, emotion: str, face_dx: int) -> str:
    eye_mode, (b_out, b_in), mouth, blush, idx, extra = _EMOTIONS.get(emotion, _EMOTIONS["neutral"])
    f = look.gender == "female"
    exl, exr, ey, by = CX - 58, CX + 58, 302, 258
    skin_sh = shade(look.skin, 0.78)
    parts = [
        # under-fringe soft shadow on the forehead
        _sh(f"M {CX - 80} 236 Q {CX} 262 {CX + 80} 236 L {CX + 78} 252 Q {CX} 278 {CX - 78} 252 Z", 0.08),
        _eye(ids, exl, ey, look.eye_color, mode=eye_mode, dx=idx + face_dx // 3, female=f),
        _eye(ids, exr, ey, look.eye_color, mode=eye_mode, dx=idx + face_dx // 3, female=f),
        _brow(exl - 26, exl + 26, by + b_out, by + b_in),
        _brow(exr + 26, exr - 26, by + b_out, by + b_in),
        # nose: side shade + tip highlight
        f'<path d="M {CX + 2} 334 Q {CX + 9} 344 {CX + 2} 352" stroke="{skin_sh}" stroke-width="4.5" fill="none" stroke-linecap="round"/>',
        f'<circle cx="{CX - 2}" cy="349" r="2.5" fill="#ffffff" opacity="0.5"/>',
        _MOUTHS.get(mouth, _MOUTHS["neutral"])(),
    ]
    if blush > 0:
        parts.append(
            f'<g opacity="{blush}">'
            f'<ellipse cx="{CX - 64}" cy="342" rx="24" ry="12" fill="#f0867c"/>'
            f'<ellipse cx="{CX + 64}" cy="342" rx="24" ry="12" fill="#f0867c"/>'
            + "".join(f'<path d="M {bx - 10} 334 L {bx - 2} 350 M {bx} 332 L {bx + 8} 348 M {bx + 10} 334 L {bx + 18} 350" '
                      f'stroke="#e06a60" stroke-width="2.5" opacity="0.6"/>' for bx in (CX - 64, CX + 64))
            + "</g>")
    if extra == "tears":
        for tx, sgn in ((CX - 60, -1), (CX + 60, 1)):
            parts.append(
                f'<path d="M {tx} 320 Q {tx + sgn * 5} 372 {tx + sgn * 2} 424" stroke="#a8dcf0" '
                f'stroke-width="9" fill="none" opacity="0.85" stroke-linecap="round"/>'
                f'<path d="M {tx - 2} 322 Q {tx} 360 {tx - 1} 400" stroke="#e8f6fc" '
                f'stroke-width="3" fill="none" opacity="0.8"/>')
    elif extra == "sweat":
        parts.append(f'<path d="M {CX + 98} 228 q 15 22 0 33 q -15 -11 0 -33 Z" fill="#a8dcf0" '
                     f'stroke="#7ec4e0" stroke-width="2"/>'
                     f'<circle cx="{CX + 95}" cy="248" r="3" fill="#ffffff" opacity="0.8"/>')
    return f'<g transform="translate({face_dx},0)">' + "".join(parts) + "</g>"


# ── hair ──────────────────────────────────────────────────────────────────────
def _gloss(c: str, y: int = 196, spread: int = 74) -> str:
    """Anime zig-zag shine band across the crown."""
    pts = []
    for i, x in enumerate(range(-spread, spread + 1, spread // 3)):
        pts.append(f"{'L' if i else 'M'} {CX + x} {y + (10 if i % 2 else -6)}")
    top = " ".join(pts)
    pts_b = []
    for i, x in enumerate(range(spread, -spread - 1, -spread // 3)):
        pts_b.append(f"L {CX + x} {y + 18 + (8 if i % 2 else -4)}")
    return (f'<path d="{top} {" ".join(pts_b)} Z" fill="{shade(c, 1.45)}" opacity="0.45"/>')


def _strands(c: str, xs: "tuple", y0: int, y1: int) -> str:
    return "".join(f'<path d="M {CX + x} {y0} Q {CX + x + 6} {(y0 + y1) // 2} {CX + x - 4} {y1}" '
                   f'stroke="{shade(c, 0.7)}" stroke-width="3.5" fill="none" opacity="0.55"/>' for x in xs)


def _hair_front(ids: _Ids, style: str, c: str, female: bool = False) -> str:
    sh = shade(c, 0.72)
    cap = f'M {CX - 98} 300 Q {CX - 106} 148 {CX} 140 Q {CX + 106} 148 {CX + 98} 300 '
    locks = ""
    if female:
        for sgn in (-1, 1):
            lx = CX + sgn * 92
            locks += _cel(ids, f"M {lx - sgn * 8} 262 Q {lx + sgn * 12} 330 {lx - sgn * 2} 392 "
                               f"Q {lx - sgn * 6} 400 {lx - sgn * 16} 392 "
                               f"Q {lx - sgn * 12} 320 {lx - sgn * 20} 264 Z", c,
                          shadow=_sh(f"M {lx - sgn * 2} 300 Q {lx + sgn * 4} 350 {lx - sgn * 4} 388 "
                                     f"L {lx - sgn * 10} 384 Q {lx - sgn * 4} 330 {lx - sgn * 10} 300 Z", 0.2),
                          sw=2.5)
    if style == "side":
        body_d = (f"{cap}L {CX + 90} 306 Q {CX + 96} 262 {CX + 78} 236 "
                  f"Q {CX + 30} 258 {CX - 30} 252 Q {CX - 74} 246 {CX - 88} 220 "
                  f"Q {CX - 96} 252 {CX - 98} 300 Z")
        detail = (_strands(c, (-50, -8, 34), 232, 254)
                  + _sh(f"M {CX - 88} 220 Q {CX - 20} 252 {CX + 52} 240 L {CX + 46} 252 "
                        f"Q {CX - 24} 260 {CX - 84} 234 Z", 0.18))
    elif style == "curtain":
        body_d = (f"{cap}L {CX + 92} 308 Q {CX + 90} 240 {CX + 64} 218 L {CX + 26} 280 "
                  f"L {CX + 14} 224 L {CX - 14} 224 L {CX - 26} 280 L {CX - 64} 218 "
                  f"Q {CX - 90} 240 {CX - 92} 308 Z")
        detail = (_strands(c, (-46, 44), 236, 268)
                  + _sh(f"M {CX + 26} 280 L {CX + 64} 218 L {CX + 72} 226 L {CX + 34} 278 Z", 0.16))
    elif style == "spiky":
        xs = list(range(-88, 89, 22))
        pts = "".join(f"L {CX + x} {300 if i % 2 == 0 else 224} " for i, x in enumerate(xs))
        body_d = f"{cap}{pts}Z"
        detail = _strands(c, (-66, -22, 22, 66), 210, 250)
    elif style == "wavy":
        body_d = (f"{cap}L {CX + 92} 304 Q {CX + 72} 276 {CX + 70} 244 Q {CX + 44} 286 {CX + 20} 250 "
                  f"Q {CX} 292 {CX - 22} 248 Q {CX - 44} 288 {CX - 68} 242 Q {CX - 72} 278 {CX - 92} 304 Z")
        detail = _strands(c, (-56, -10, 36), 238, 276)
    else:  # flat
        body_d = (f"{cap}L {CX + 92} 300 Q {CX + 86} 258 {CX + 62} 252 Q {CX + 48} 274 {CX + 32} 254 "
                  f"Q {CX + 14} 276 {CX} 256 Q {CX - 14} 276 {CX - 32} 254 Q {CX - 48} 274 {CX - 62} 252 "
                  f"Q {CX - 86} 258 {CX - 92} 300 Z")
        detail = _strands(c, (-46, 0, 46), 236, 268)
    body = _cel(ids, body_d, c,
                shadow=_sh(f"M {CX + 30} 150 Q {CX + 100} 170 {CX + 96} 290 L {CX + 74} 286 "
                           f"Q {CX + 80} 190 {CX + 22} 160 Z", 0.16),
                sw=3)
    return locks + body + detail + _gloss(c)


def _hair_back(ids: _Ids, style: str, c: str, female: bool) -> str:
    sh = shade(c, 0.66)
    base_d = (f"M {CX - 100} 300 Q {CX - 108} 150 {CX} 140 Q {CX + 108} 150 {CX + 100} 300 "
              f"L {CX + 96} 396 Q {CX + 70} 430 {CX + 40} 420 L {CX - 40} 420 Q {CX - 70} 430 {CX - 96} 396 Z")
    base = _cel(ids, base_d, shade(c, 0.88), shadow=_sh(
        f"M {CX - 96} 360 L {CX + 96} 360 L {CX + 80} 424 L {CX - 80} 424 Z", 0.22), sw=3)
    if style == "bob":
        d = (f"M {CX - 106} 300 Q {CX - 114} 146 {CX} 136 Q {CX + 114} 146 {CX + 106} 300 "
             f"Q {CX + 112} 470 {CX + 72} 524 Q {CX + 54} 500 {CX + 42} 470 L {CX - 42} 470 "
             f"Q {CX - 54} 500 {CX - 72} 524 Q {CX - 112} 470 {CX - 106} 300 Z")
        return _cel(ids, d, shade(c, 0.9),
                    shadow=_sh(f"M {CX + 40} 300 Q {CX + 70} 420 {CX + 66} 512 Q {CX + 96} 460 "
                               f"{CX + 92} 330 Z", 0.2), sw=3) \
            + f'<path d="M {CX - 70} 480 Q {CX - 60} 440 {CX - 64} 400 M {CX + 70} 480 Q {CX + 60} 440 {CX + 64} 400" stroke="{sh}" stroke-width="3.5" fill="none" opacity="0.5"/>'
    if style == "long":
        d = (f"M {CX - 102} 300 Q {CX - 112} 148 {CX} 138 Q {CX + 112} 148 {CX + 102} 300 "
             f"L {CX + 114} 560 Q {CX + 124} 860 {CX + 86} 1034 Q {CX + 70} 1000 {CX + 74} 900 "
             f"Q {CX + 70} 700 {CX + 74} 560 L {CX + 70} 430 L {CX - 70} 430 L {CX - 74} 560 "
             f"Q {CX - 70} 700 {CX - 74} 900 Q {CX - 70} 1000 {CX - 86} 1034 "
             f"Q {CX - 124} 860 {CX - 114} 560 Z")
        return _cel(ids, d, c,
                    shadow=_sh(f"M {CX + 74} 560 Q {CX + 72} 840 {CX + 84} 1020 Q {CX + 104} 880 "
                               f"{CX + 98} 600 L {CX + 92} 440 L {CX + 70} 434 Z", 0.18),
                    light=_hl(f"M {CX - 96} 480 Q {CX - 102} 700 {CX - 92} 900 L {CX - 84} 896 "
                              f"Q {CX - 92} 700 {CX - 86} 484 Z", 0.14), sw=3) \
            + f'<path d="M {CX - 90} 560 Q {CX - 84} 800 {CX - 88} 960 M {CX + 90} 560 Q {CX + 84} 800 {CX + 88} 960" stroke="{sh}" stroke-width="3.5" fill="none" opacity="0.45"/>'
    if style == "ponytail":
        tail_d = (f"M {CX + 58} 188 Q {CX + 196} 300 {CX + 156} 640 Q {CX + 140} 780 {CX + 96} 838 "
                  f"Q {CX + 82} 800 {CX + 84} 760 Q {CX + 112} 640 {CX + 92} 400 "
                  f"Q {CX + 78} 262 {CX + 28} 198 Z")
        tail = _cel(ids, tail_d, c,
                    shadow=_sh(f"M {CX + 120} 300 Q {CX + 150} 500 {CX + 128} 700 L {CX + 108} 690 "
                               f"Q {CX + 128} 500 {CX + 102} 320 Z", 0.18), sw=3)
        band = (f'<ellipse cx="{CX + 58}" cy="206" rx="17" ry="13" fill="{shade(c, 0.6)}"/>'
                f'<ellipse cx="{CX + 55}" cy="203" rx="6" ry="4" fill="{shade(c, 1.3)}" opacity="0.7"/>')
        return base + tail + band
    if style == "twin_tails":
        out = base
        for sgn in (-1, 1):
            tx = CX + sgn * 108
            d = (f"M {tx} 280 Q {tx + sgn * 100} 420 {tx + sgn * 62} 760 Q {tx + sgn * 52} 880 "
                 f"{tx + sgn * 12} 946 Q {tx - sgn * 2} 900 {tx + sgn * 2} 850 "
                 f"Q {tx + sgn * 26} 700 {tx + sgn * 12} 460 Q {tx + sgn * 6} 340 {tx - sgn * 22} 280 Z")
            out += _cel(ids, d, c,
                        shadow=_sh(f"M {tx + sgn * 40} 400 Q {tx + sgn * 66} 600 {tx + sgn * 44} 800 "
                                   f"L {tx + sgn * 28} 790 Q {tx + sgn * 48} 600 {tx + sgn * 24} 420 Z", 0.18),
                        sw=3)
            out += (f'<ellipse cx="{tx - sgn * 6}" cy="292" rx="15" ry="12" fill="{shade(c, 0.6)}"/>'
                    f'<circle cx="{tx - sgn * 9}" cy="288" r="4" fill="{shade(c, 1.3)}" opacity="0.7"/>')
        return out
    if style == "bun":
        bun = _cel(ids, f"M {CX - 52} 152 Q {CX - 44} 100 {CX} 96 Q {CX + 44} 100 {CX + 52} 152 "
                        f"Q {CX + 40} 196 {CX} 200 Q {CX - 40} 196 {CX - 52} 152 Z", c,
                   shadow=_sh(f"M {CX + 6} 100 Q {CX + 48} 110 {CX + 50} 152 Q {CX + 40} 192 "
                              f"{CX + 8} 198 Z", 0.2), sw=3)
        wrap = f'<path d="M {CX - 34} 168 Q {CX} 184 {CX + 34} 168" stroke="{shade(c, 0.6)}" stroke-width="5" fill="none"/>'
        return bun + wrap + base
    if style == "topknot":
        knot = _cel(ids, f"M {CX - 30} 128 Q {CX - 24} 92 {CX} 90 Q {CX + 24} 92 {CX + 30} 128 "
                         f"Q {CX + 20} 152 {CX} 154 Q {CX - 20} 152 {CX - 30} 128 Z", c, sw=3)
        tie = (f'<rect x="{CX - 22}" y="150" width="44" height="13" rx="6" fill="#8a2a2a"/>'
               f'<rect x="{CX - 22}" y="152" width="44" height="4" rx="2" fill="#b04040"/>')
        return knot + tie + base
    return base  # short


# ── accessories ───────────────────────────────────────────────────────────────
def _accessories(look: CharacterLook) -> str:
    out = []
    if "glasses" in look.accessories:
        out.append(f'<g stroke="#2a2a33" stroke-width="4.5" fill="none">'
                   f'<rect x="{CX - 88}" y="284" width="58" height="40" rx="12"/>'
                   f'<rect x="{CX + 30}" y="284" width="58" height="40" rx="12"/>'
                   f'<line x1="{CX - 30}" y1="298" x2="{CX + 30}" y2="298"/></g>'
                   f'<path d="M {CX - 82} 292 L {CX - 44} 288" stroke="#ffffff" stroke-width="3" opacity="0.4"/>')
    if "beard" in look.accessories:
        c = look.hair_color
        out.append(f'<path d="M {CX - 52} 356 Q {CX - 42} 448 {CX} 464 Q {CX + 42} 448 {CX + 52} 356 '
                   f'Q {CX + 30} 396 {CX} 400 Q {CX - 30} 396 {CX - 52} 356 Z" fill="{c}" '
                   f'stroke="{shade(c, 0.6)}" stroke-width="2.5"/>'
                   f'<path d="M {CX - 20} 420 Q {CX} 434 {CX + 20} 420" stroke="{shade(c, 0.7)}" '
                   f'stroke-width="3" fill="none" opacity="0.6"/>')
    if "hairband" in look.accessories:
        out.append(f'<path d="M {CX - 92} 234 Q {CX} 172 {CX + 92} 234 L {CX + 84} 252 Q {CX} 194 '
                   f'{CX - 84} 252 Z" fill="{look.accent}" stroke="{shade(look.accent, 0.6)}" stroke-width="2.5"/>'
                   f'<path d="M {CX - 60} 214 Q {CX} 186 {CX + 20} 200" stroke="#ffffff" stroke-width="3" opacity="0.4" fill="none"/>')
    if "earrings" in look.accessories:
        out.append(f'<circle cx="{CX - 96}" cy="326" r="6" fill="{look.accent}" stroke="{shade(look.accent, 0.6)}" stroke-width="2"/>'
                   f'<circle cx="{CX + 96}" cy="326" r="6" fill="{look.accent}" stroke="{shade(look.accent, 0.6)}" stroke-width="2"/>'
                   f'<circle cx="{CX - 98}" cy="324" r="2" fill="#fff" opacity="0.8"/>')
    return "".join(out)


# ── assembly ──────────────────────────────────────────────────────────────────
def anime_char_inner(look, emotion: str = "neutral", pose: str = "stand",
                     facing: str = "front", style_id: str | None = None) -> str:
    """Figure CONTENT on the 1024×1536 frame (no <svg> wrapper). Never raises."""
    try:
        ids = _Ids()
        lk = look if isinstance(look, CharacterLook) else derive_look(0, base=dict(look or {}))
        g = _geom(lk)
        p = _POSES.get((pose or "stand").strip().lower(), _POSES["stand"])
        emotion = (emotion or "neutral").strip().lower()
        o = _outfit(ids, lk, g)
        skin = lk.skin

        legs_key = p.get("legs", "stand")
        if lk.outfit in ("hanfu_robe", "kimono", "dress") and legs_key in ("kneel", "walk", "run"):
            legs_key = "sit" if legs_key == "kneel" else "stand"
        legs_mode = _LEGS.get(legs_key, _LEGS["stand"])
        hipL, hipR = CX - g["hip_dx"], CX + g["hip_dx"]
        legs = ""
        for (a1, a2), hx, dirx in ((legs_mode[0], hipL, -1), (legs_mode[1], hipR, 1)):
            legs += _limb(ids, hx, g["hip_y"] - 12, a1, a2, g["leg_l1"], g["leg_l2"],
                          g["leg_w1"], g["leg_w2"], o["legs_color"],
                          o["legs_color"] if o["legs_color"] != skin else skin,
                          end=_shoe(ids, o["shoe"], g["leg_l2"], dirx))

        shx = g["sh_w"] + 6
        cuff = ""
        if o.get("wide_cuff"):
            cd = (f"M -32 56 Q -58 {g['arm_l2'] * 0.6:.0f} -68 {g['arm_l2'] - 4:.0f} "
                  f"L 68 {g['arm_l2'] - 4:.0f} Q 58 {g['arm_l2'] * 0.6:.0f} 32 56 Z")
            cuff = _cel(ids, cd, o["sleeve_c1"],
                        shadow=_sh(f"M 10 56 L 32 56 Q 58 {g['arm_l2'] * 0.6:.0f} 68 {g['arm_l2'] - 4:.0f} "
                                   f"L 30 {g['arm_l2'] - 4:.0f} Z", 0.14), sw=2.5)
        if p.get("cross"):
            arms = (_limb(ids, CX - shx, g["sh_y"] + 16, p["aL"][0], 0, 150, 0, g["arm_w1"], 0,
                          o["sleeve_c1"], o["sleeve_c1"])
                    + _limb(ids, CX + shx, g["sh_y"] + 16, p["aR"][0], 0, 150, 0, g["arm_w1"], 0,
                            o["sleeve_c1"], o["sleeve_c1"])
                    + f'<g transform="translate({CX},616)">'
                    + _cel(ids, "M -120 -12 Q -60 -34 120 -14 L 116 18 Q -50 4 -114 20 Z",
                           o["sleeve_c2"], shadow=_sh("M -20 -22 L 120 -14 L 116 18 L -16 6 Z", 0.12), sw=2.8)
                    + _cel(ids, "M -120 -14 Q 50 -36 118 -16 L 122 14 Q 60 -4 -114 18 Z",
                           o["sleeve_c1"], shadow=_sh("M 30 -24 L 118 -16 L 122 14 L 40 -2 Z", 0.12), sw=2.8)
                    + f'<ellipse cx="-106" cy="-14" rx="19" ry="23" fill="{o["hand_skin"]}" stroke="{shade(o["hand_skin"], 0.62)}" stroke-width="2.5"/>'
                    + f'<ellipse cx="106" cy="-16" rx="19" ry="23" fill="{o["hand_skin"]}" stroke="{shade(o["hand_skin"], 0.62)}" stroke-width="2.5"/>'
                    + "</g>")
        else:
            arms = (
                _limb(ids, CX - shx, g["sh_y"] + 16, p["aL"][0], p["aL"][1], g["arm_l1"], g["arm_l2"],
                      g["arm_w1"], g["arm_w2"], o["sleeve_c1"], o["sleeve_c2"],
                      end=_hand(ids, o["hand_skin"], g["arm_l2"]), cuff=cuff)
                + _limb(ids, CX + shx, g["sh_y"] + 16, p["aR"][0], p["aR"][1], g["arm_l1"], g["arm_l2"],
                        g["arm_w1"], g["arm_w2"], o["sleeve_c1"], o["sleeve_c2"],
                        end=_hand(ids, o["hand_skin"], g["arm_l2"]), cuff=cuff))
        cap_r = g["arm_w1"] / 2 + 5
        shoulder_caps = "".join(
            _cel(ids, f"M {x - cap_r:.0f} {g['sh_y'] + 12} a {cap_r:.0f} {cap_r:.0f} 0 1 1 {2 * cap_r:.0f} 0 "
                      f"a {cap_r:.0f} {cap_r:.0f} 0 1 1 {-2 * cap_r:.0f} 0 Z", o["sleeve_c1"],
                 light=_hl(f"M {x - cap_r * 0.7:.0f} {g['sh_y'] + 2} q {cap_r * 0.6:.0f} -10 {cap_r * 1.2:.0f} 0 "
                           f"l -4 8 q {-cap_r * 0.5:.0f} -7 {-cap_r:.0f} 0 Z", 0.2), sw=2.8)
            for x in (CX - shx, CX + shx))

        neck = (f'<path d="M {CX - 24} {g["neck_top"]} h 48 v 82 q -24 14 -48 0 Z" fill="{skin}" '
                f'stroke="{shade(skin, 0.62)}" stroke-width="2.5"/>'
                + _sh(f"M {CX - 24} {g['neck_top']} h 48 v 26 q -24 10 -48 0 Z", 0.16))

        face_dx = 16 if facing in ("left", "right") else 0
        _head_tf = (f'translate({CX * (1 - g["head_scale"]):.1f},{300 * (1 - g["head_scale"]):.1f}) '
                    f'scale({g["head_scale"]})')
        hair_back_layer = (f'<g transform="{_head_tf}">'
                           + _hair_back(ids, lk.hair_back, lk.hair_color, lk.gender == "female")
                           + "</g>")
        headg = (
            f'<g transform="{_head_tf}">'
            + _head_base(ids, skin)
            + _face(ids, lk, emotion, face_dx)
            + _hair_front(ids, lk.hair_front, lk.hair_color, lk.gender == "female")
            + _accessories(lk)
            + "</g>"
        )

        upper = hair_back_layer + neck + o["torso"] + shoulder_caps + arms + o.get("over", "") + headg
        bow = p.get("bow", 0) + g.get("stoop", 0)
        if bow:
            upper = f'<g transform="rotate({bow} {CX} {g["hip_y"]})">{upper}</g>'

        ground = _soft_shadow(ids, CX, 1424, 190 if legs_key in ("wide", "run") else 150, 26, 0.30)
        body = ground + legs + o.get("skirt", "") + upper
        if p.get("dy"):
            body = f'<g transform="translate(0,{p["dy"]})">{body}</g>'
        if p.get("lean"):
            body = f'<g transform="rotate({p["lean"]} {CX} 1400)">{body}</g>'
        s = g["scale"]
        if s != 1.0:
            body = (f'<g transform="translate({CX * (1 - s):.1f},{1408 * (1 - s):.1f}) scale({s})">'
                    f"{body}</g>")
        if facing == "left":
            body = f'<g transform="translate({W},0) scale(-1,1)">{body}</g>'
        if style_id:
            from app.features.render.engine.visual.v2.theme_pack import wrap_character
            body = wrap_character(body, style_id)
        return body
    except Exception:
        return ""


def build_anime_char(look, emotion: str = "neutral", pose: str = "stand",
                     facing: str = "front", style_id: str | None = None) -> str:
    """Standalone transparent SVG (1024×1536). Never raises ('' on failure)."""
    inner = anime_char_inner(look, emotion, pose, facing, style_id)
    if not inner:
        return ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{inner}</svg>')


__all__ = ["build_anime_char", "anime_char_inner", "EMOTIONS", "POSES", "FACINGS"]
