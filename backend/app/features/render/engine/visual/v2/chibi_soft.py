"""
chibi_soft.py — "Chibi mềm" CHARACTER style (GĐ2, user-reference match).

Reference: soft fan-art chibi — HUGE round head (≈½ figure), thick warm-dark
outlines on every shape, simple curved closed-happy eyes, big blush, tiny open
mouth, stubby single-segment limbs with mitten hands, flat muted colours with at
most one shade tone. Charm over realism.

Same contract as every style in styles.py:
    chibi_soft_inner(look, emotion, pose, facing) -> svg inner (1024×1536)
Identity comes from the SAME CharacterLook (hair/eye/outfit palette), so switching
styles re-skins a story without touching the plan. Pure; never raises.
"""
from __future__ import annotations

from app.features.render.engine.visual.v2.anime_char import _Ids, _soft_shadow
from app.features.render.engine.visual.v2.look_spec import (
    CharacterLook, derive_look, shade,
)

W, H = 1024, 1536
CX = 512
_INK = "#3a342c"           # warm hand-drawn ink

# head geometry
HCY, HRX, HRY = 470, 298, 282
EY = 566                    # eye line
MY = 668                    # mouth line
BODY_TOP = 730
HEM = 1156                  # tunic hem
LEG_TOP = 1120
FOOT_Y = 1372


def _o(width: float = 10) -> str:
    return f' stroke="{_INK}" stroke-width="{width}" stroke-linejoin="round"'


# ── poses: single-segment stub arms (angle°; 0 = down, +cw) + leg mode ────────
_POSES: dict = {
    "stand":      dict(aL=18, aR=-18, legs="stand"),
    "wave":       dict(aL=18, aR=-152, legs="hop"),
    "point":      dict(aL=20, aR=-84, legs="stand"),
    "cheer":      dict(aL=152, aR=-152, legs="hop"),
    "hands_hips": dict(aL=52, aR=-52, legs="stand", short=True),
    "cross_arms": dict(aL=30, aR=-30, legs="stand", cross=True),
    "think":      dict(aL=18, aR=-132, legs="stand", short_r=True),
    "bow":        dict(aL=10, aR=-10, legs="stand", bow=26),
    "fight":      dict(aL=118, aR=-118, legs="wide", short=True),
    "hold":       dict(aL=18, aR=-66, legs="stand"),
    "run":        dict(aL=48, aR=-120, legs="run", lean=-8),
    "sit":        dict(aL=30, aR=-30, legs="sit", dy=150),
    "kneel":      dict(aL=14, aR=-14, legs="kneel", dy=120),
}


def _arm(ids: _Ids, x: float, y: float, ang: float, c: str, skin: str,
         ln: float = 178, w: float = 64) -> str:
    h = w / 2
    d = (f"M {-h:.0f} -12 Q {-h - 8:.0f} {ln * 0.5:.0f} {-h * 0.72:.0f} {ln:.0f} "
         f"Q 0 {ln + 20:.0f} {h * 0.72:.0f} {ln:.0f} Q {h + 8:.0f} {ln * 0.5:.0f} {h:.0f} -12 "
         f"Q 0 {-12 - h * 0.6:.0f} {-h:.0f} -12 Z")
    hand = (f'<circle cx="0" cy="{ln + 6:.0f}" r="{h * 0.86:.0f}" fill="{skin}"{_o(8)}/>')
    return (f'<g transform="translate({x:.0f},{y:.0f}) rotate({ang:.1f})">'
            f'<path d="{d}" fill="{c}"{_o(9)}/>{hand}</g>')


def _leg(x: float, ang: float, c: str, shoe: str, sock: str, ln: float = 214,
         w: float = 62, dirx: int = 1) -> str:
    h = w / 2
    return (f'<g transform="translate({x:.0f},{LEG_TOP}) rotate({ang:.1f})">'
            f'<path d="M {-h:.0f} -10 Q {-h - 4:.0f} {ln * 0.55:.0f} {-h * 0.8:.0f} {ln:.0f} '
            f'L {h * 0.8:.0f} {ln:.0f} Q {h + 4:.0f} {ln * 0.55:.0f} {h:.0f} -10 Z" fill="{c}"{_o(9)}/>'
            f'<path d="M {-h * 0.8:.0f} {ln - 34:.0f} L {h * 0.8:.0f} {ln - 34:.0f} '
            f'L {h * 0.78:.0f} {ln:.0f} L {-h * 0.78:.0f} {ln:.0f} Z" fill="{sock}"{_o(7)}/>'
            f'<path d="M {-h * 0.9:.0f} {ln - 4:.0f} Q {-h - 6:.0f} {ln + 26:.0f} {-h * 0.2:.0f} {ln + 30:.0f} '
            f'L {dirx * (h + 22):.0f} {ln + 30:.0f} Q {dirx * (h + 34):.0f} {ln + 16:.0f} '
            f'{dirx * (h + 10):.0f} {ln + 2:.0f} Z" fill="{shoe}"{_o(8)}/></g>')


_LEGS: dict = {
    "stand": ((CX - 74, 2), (CX + 74, -2)),
    "wide":  ((CX - 92, 8), (CX + 92, -8)),
    "hop":   ((CX - 74, 14), (CX + 74, -30)),
    "run":   ((CX - 80, -34), (CX + 80, 38)),
    "sit":   ((CX - 84, 62), (CX + 84, -62)),
    "kneel": ((CX - 78, 10), (CX + 78, -78)),
}


# ── face ──────────────────────────────────────────────────────────────────────
def _eye_curve(ex: int, up: bool) -> str:
    dy = -34 if up else 30
    return (f'<path d="M {ex - 44} {EY} Q {ex} {EY + dy} {ex + 44} {EY}" fill="none" '
            f'stroke="{_INK}" stroke-width="11" stroke-linecap="round"/>')


def _eye_open(ex: int, iris: str, *, big: bool = False, dx: int = 0) -> str:
    rx, ry = (26, 34) if big else (21, 28)
    return (f'<ellipse cx="{ex + dx}" cy="{EY}" rx="{rx}" ry="{ry}" fill="{_INK}"/>'
            f'<ellipse cx="{ex + dx}" cy="{EY + 4}" rx="{rx * 0.62:.0f}" ry="{ry * 0.62:.0f}" fill="{shade(iris, 1.1)}"/>'
            f'<circle cx="{ex + dx - 7}" cy="{EY - 10}" r="{8 if big else 6}" fill="#ffffff"/>'
            f'<circle cx="{ex + dx + 6}" cy="{EY + 10}" r="3" fill="#ffffff" opacity="0.9"/>')


def _eye_half(ex: int, iris: str) -> str:
    return (f'<path d="M {ex - 34} {EY - 8} L {ex + 34} {EY - 8}" stroke="{_INK}" '
            f'stroke-width="10" stroke-linecap="round"/>'
            f'<path d="M {ex - 20} {EY + 10} Q {ex} {EY + 18} {ex + 20} {EY + 10}" '
            f'stroke="{_INK}" stroke-width="7" fill="none" stroke-linecap="round"/>')


_MOUTHS = {
    "neutral":     lambda: f'<path d="M {CX - 12} {MY} Q {CX} {MY + 8} {CX + 12} {MY}" stroke="{_INK}" stroke-width="8" fill="none" stroke-linecap="round"/>',
    "smile":       lambda: f'<path d="M {CX - 20} {MY - 6} Q {CX} {MY + 16} {CX + 20} {MY - 6}" stroke="{_INK}" stroke-width="8" fill="none" stroke-linecap="round"/>',
    "open_smile":  lambda: (f'<path d="M {CX - 24} {MY - 10} Q {CX} {MY + 40} {CX + 24} {MY - 10} '
                            f'Q {CX} {MY + 2} {CX - 24} {MY - 10} Z" fill="#c0272d"{_o(7)}/>'),
    "grit":        lambda: (f'<path d="M {CX - 20} {MY - 6} L {CX + 20} {MY - 6} L {CX + 14} {MY + 12} '
                            f'L {CX - 14} {MY + 12} Z" fill="#c0272d"{_o(6)}/>'
                            f'<path d="M {CX - 14} {MY} L {CX + 14} {MY}" stroke="#fff" stroke-width="5"/>'),
    "frown":       lambda: f'<path d="M {CX - 16} {MY + 8} Q {CX} {MY - 8} {CX + 16} {MY + 8}" stroke="{_INK}" stroke-width="8" fill="none" stroke-linecap="round"/>',
    "wail":        lambda: (f'<path d="M {CX - 20} {MY + 4} Q {CX} {MY - 16} {CX + 20} {MY + 4} '
                            f'Q {CX} {MY + 26} {CX - 20} {MY + 4} Z" fill="#c0272d"{_o(6)}/>'),
    "o":           lambda: f'<ellipse cx="{CX}" cy="{MY + 2}" rx="12" ry="15" fill="#c0272d"{_o(6)}/>',
    "wavy":        lambda: (f'<path d="M {CX - 22} {MY} Q {CX - 11} {MY - 10} {CX} {MY} '
                            f'Q {CX + 11} {MY + 10} {CX + 22} {MY}" stroke="{_INK}" stroke-width="7" '
                            f'fill="none" stroke-linecap="round"/>'),
    "line":        lambda: f'<path d="M {CX - 16} {MY + 2} L {CX + 16} {MY + 2}" stroke="{_INK}" stroke-width="8" stroke-linecap="round"/>',
    "small_smile": lambda: f'<path d="M {CX - 10} {MY} Q {CX} {MY + 10} {CX + 10} {MY}" stroke="{_INK}" stroke-width="7" fill="none" stroke-linecap="round"/>',
}

# emotion → (eye kind, mouth, blush boost, extra)
_EMO: dict = {
    "neutral":   ("open", "neutral", 0.0, ""),
    "happy":     ("closed_up", "open_smile", 0.1, ""),
    "joy":       ("closed_up", "open_smile", 0.15, ""),
    "angry":     ("open", "grit", 0.0, "brow_angry"),
    "sad":       ("closed_down", "frown", 0.0, "brow_sad"),
    "cry":       ("closed_down", "wail", 0.0, "tears"),
    "surprised": ("wide", "o", 0.0, ""),
    "fear":      ("wide", "wavy", 0.0, "sweat"),
    "stern":     ("half", "line", 0.0, "brow_flat"),
    "shy":       ("closed_up", "small_smile", 0.35, ""),
}


def _face(look: CharacterLook, emotion: str, dx: int) -> str:
    kind, mouth, boost, extra = _EMO.get(emotion, _EMO["neutral"])
    exl, exr = CX - 118, CX + 118
    parts = []
    if kind == "closed_up":
        parts += [_eye_curve(exl, True), _eye_curve(exr, True)]
    elif kind == "closed_down":
        parts += [_eye_curve(exl, False), _eye_curve(exr, False)]
    elif kind == "half":
        parts += [_eye_half(exl, look.eye_color), _eye_half(exr, look.eye_color)]
    else:
        parts += [_eye_open(exl, look.eye_color, big=(kind == "wide"), dx=dx),
                  _eye_open(exr, look.eye_color, big=(kind == "wide"), dx=dx)]
    if extra == "brow_angry":
        parts += [f'<path d="M {exl - 34} {EY - 62} L {exl + 26} {EY - 44}" stroke="{_INK}" stroke-width="9" stroke-linecap="round"/>',
                  f'<path d="M {exr + 34} {EY - 62} L {exr - 26} {EY - 44}" stroke="{_INK}" stroke-width="9" stroke-linecap="round"/>']
    elif extra == "brow_sad":
        parts += [f'<path d="M {exl - 30} {EY - 46} Q {exl} {EY - 60} {exl + 28} {EY - 52}" stroke="{_INK}" stroke-width="8" fill="none" stroke-linecap="round"/>',
                  f'<path d="M {exr + 30} {EY - 46} Q {exr} {EY - 60} {exr - 28} {EY - 52}" stroke="{_INK}" stroke-width="8" fill="none" stroke-linecap="round"/>']
    elif extra == "brow_flat":
        parts += [f'<path d="M {exl - 30} {EY - 50} L {exl + 28} {EY - 50}" stroke="{_INK}" stroke-width="9" stroke-linecap="round"/>',
                  f'<path d="M {exr + 30} {EY - 50} L {exr - 28} {EY - 50}" stroke="{_INK}" stroke-width="9" stroke-linecap="round"/>']
    blush_op = 0.5 + boost
    parts.append(f'<ellipse cx="{CX - 172}" cy="{EY + 66}" rx="52" ry="26" fill="#f2989e" opacity="{blush_op}"/>')
    parts.append(f'<ellipse cx="{CX + 172}" cy="{EY + 66}" rx="52" ry="26" fill="#f2989e" opacity="{blush_op}"/>')
    parts.append(_MOUTHS.get(mouth, _MOUTHS["neutral"])())
    if extra == "tears":
        for tx in (CX - 120, CX + 120):
            parts.append(f'<path d="M {tx} {EY + 22} Q {tx + 6} {EY + 90} {tx} {EY + 150}" '
                         f'stroke="#a8dcf0" stroke-width="12" fill="none" opacity="0.85" stroke-linecap="round"/>')
    elif extra == "sweat":
        parts.append(f'<path d="M {CX + 226} {EY - 96} q 18 26 0 40 q -18 -14 0 -40 Z" '
                     f'fill="#a8dcf0"{_o(5)}/>')
    return f'<g transform="translate({dx},0)">' + "".join(parts) + "</g>"


# ── hair (big soft mass + swoopy bangs, ref-style) ────────────────────────────
def _hair(look: CharacterLook) -> str:
    c = look.hair_color
    sh = shade(c, 0.8)
    skull = (f"M {CX - HRX - 14} {HCY + 30} Q {CX - HRX - 26} {HCY - HRY - 10} {CX} {HCY - HRY - 26} "
             f"Q {CX + HRX + 26} {HCY - HRY - 10} {CX + HRX + 14} {HCY + 30} ")
    fb = look.hair_back
    female = look.gender == "female"
    # bangs sweep (right-leaning like the reference)
    bangs = (f"L {CX + HRX - 20} {HCY + 130} "
             f"Q {CX + HRX - 60} {HCY + 40} {CX + 150} {HCY + 10} "
             f"L {CX + 96} {HCY + 128} L {CX + 60} {HCY - 10} "
             f"L {CX - 20} {HCY + 118} L {CX - 78} {HCY - 20} "
             f"L {CX - 148} {HCY + 96} Q {CX - HRX + 40} {HCY + 40} {CX - HRX + 20} {HCY + 120} Z")
    mass = f'<path d="{skull}{bangs}" fill="{c}"{_o(11)}/>'
    under = (f'<path d="M {CX - 60} {HCY - 4} L {CX - 20} {HCY + 112} L {CX + 10} {HCY + 20} Z" '
             f'fill="{sh}" opacity="0.5"/>')
    back = ""
    if fb in ("long",):
        back = (f'<path d="M {CX - HRX - 10} {HCY} Q {CX - HRX - 40} {HCY + 380} {CX - HRX + 60} {HCY + 560} '
                f'L {CX - HRX + 130} {HCY + 460} L {CX - HRX + 60} {HCY + 60} Z" fill="{c}"{_o(10)}/>'
                f'<path d="M {CX + HRX + 10} {HCY} Q {CX + HRX + 40} {HCY + 380} {CX + HRX - 60} {HCY + 560} '
                f'L {CX + HRX - 130} {HCY + 460} L {CX + HRX - 60} {HCY + 60} Z" fill="{c}"{_o(10)}/>')
    elif fb in ("twin_tails",):
        for sgn in (-1, 1):
            tx = CX + sgn * (HRX + 20)
            back += (f'<path d="M {tx} {HCY - 40} Q {tx + sgn * 110} {HCY + 200} {tx + sgn * 30} {HCY + 470} '
                     f'L {tx - sgn * 40} {HCY + 380} Q {tx + sgn * 20} {HCY + 160} {tx - sgn * 40} {HCY - 10} Z" '
                     f'fill="{c}"{_o(10)}/>'
                     f'<circle cx="{tx - sgn * 16}" cy="{HCY - 16}" r="20" fill="{shade(c, 0.62)}"{_o(6)}/>')
    elif fb in ("ponytail", "topknot", "bun"):
        back = (f'<path d="M {CX + 60} {HCY - HRY - 20} Q {CX + 190} {HCY - HRY - 60} {CX + 220} {HCY - HRY + 60} '
                f'Q {CX + 150} {HCY - HRY + 40} {CX + 110} {HCY - HRY + 20} Z" fill="{c}"{_o(9)}/>')
    elif fb == "bob" or female:
        back = (f'<path d="M {CX - HRX - 12} {HCY + 10} Q {CX - HRX - 20} {HCY + 190} {CX - HRX + 70} {HCY + 240} '
                f'L {CX - HRX + 96} {HCY + 130} Z" fill="{c}"{_o(9)}/>'
                f'<path d="M {CX + HRX + 12} {HCY + 10} Q {CX + HRX + 20} {HCY + 190} {CX + HRX - 70} {HCY + 240} '
                f'L {CX + HRX - 96} {HCY + 130} Z" fill="{c}"{_o(9)}/>')
    # side spikes near the ears (reference detail)
    spikes = (f'<path d="M {CX - HRX + 16} {HCY + 116} L {CX - HRX - 26} {HCY + 176} L {CX - HRX + 52} {HCY + 150} Z" fill="{c}"{_o(8)}/>'
              f'<path d="M {CX + HRX - 16} {HCY + 116} L {CX + HRX + 26} {HCY + 176} L {CX + HRX - 52} {HCY + 150} Z" fill="{c}"{_o(8)}/>')
    return back + mass + spikes + under


# ── outfit (simplified tunic silhouettes) ─────────────────────────────────────
def _tunic_d(top_w: float, hem_w: float, hem: float = HEM) -> str:
    return (f"M {CX - top_w:.0f} {BODY_TOP} Q {CX:.0f} {BODY_TOP - 26} {CX + top_w:.0f} {BODY_TOP} "
            f"L {CX + hem_w:.0f} {hem:.0f} Q {CX:.0f} {hem + 30:.0f} {CX - hem_w:.0f} {hem:.0f} Z")


def _outfit(look: CharacterLook) -> dict:
    p1, p2, acc = look.outfit_primary, look.outfit_secondary, look.accent
    kind = look.outfit
    f = look.gender == "female"
    o = dict(body="", arm_c=p1, legs_c=look.skin, sock="#f4efe2", shoe="#c0272d",
             hem=HEM, hide_legs=False)
    flare = 250 if (f or kind in ("dress", "hanfu_robe", "kimono", "apron_staff")) else 210
    body = f'<path d="{_tunic_d(150, flare)}" fill="{p1}"{_o(10)}/>'
    if kind == "school_uniform":
        body += (f'<path d="M {CX - 110} {BODY_TOP - 6} L {CX} {BODY_TOP + 96} L {CX + 110} {BODY_TOP - 6} '
                 f'L {CX + 150} {BODY_TOP + 22} L {CX} {BODY_TOP + 150} L {CX - 150} {BODY_TOP + 22} Z" '
                 f'fill="{p2}"{_o(8)}/>'
                 f'<path d="M {CX} {BODY_TOP + 120} l -20 24 l 20 30 l 20 -30 Z" fill="{acc}"{_o(6)}/>')
    elif kind == "office_suit":
        body += (f'<path d="M {CX - 40} {BODY_TOP - 8} L {CX} {BODY_TOP + 120} L {CX + 40} {BODY_TOP - 8} Z" fill="{p2}"{_o(7)}/>'
                 + (f'<path d="M {CX} {BODY_TOP + 4} l -11 12 l 11 84 l 11 -84 Z" fill="{acc}"{_o(5)}/>' if not f else "")
                 + f'<circle cx="{CX - 14}" cy="{BODY_TOP + 190}" r="6" fill="{shade(p1, 0.6)}"/>')
        o["shoe"] = "#3a342c"
    elif kind == "hoodie":
        body += (f'<path d="M {CX - 120} {BODY_TOP + 10} Q {CX} {BODY_TOP + 110} {CX + 120} {BODY_TOP + 10} '
                 f'L {CX + 96} {BODY_TOP - 30} Q {CX} {BODY_TOP + 40} {CX - 96} {BODY_TOP - 30} Z" '
                 f'fill="{shade(p1, 0.8)}"{_o(8)}/>'
                 f'<path d="M {CX - 60} {HEM - 130} L {CX + 60} {HEM - 130} L {CX + 48} {HEM - 40} L {CX - 48} {HEM - 40} Z" fill="{shade(p1, 0.86)}"{_o(7)}/>')
        o["sock"] = p2
    elif kind in ("hanfu_robe", "kimono"):
        body = f'<path d="{_tunic_d(150, 240, 1300)}" fill="{p1}"{_o(10)}/>'
        body += (f'<path d="M {CX - 130} {BODY_TOP} L {CX + 30} {BODY_TOP + 150} L {CX + 16} {BODY_TOP + 190} '
                 f'L {CX - 150} {BODY_TOP + 30} Z" fill="{p2}"{_o(7)}/>'
                 f'<rect x="{CX - 140}" y="{BODY_TOP + 200}" width="280" height="52" rx="10" fill="{p2}"{_o(8)}/>')
        o.update(hide_legs=True, hem=1300)
    elif kind == "armor_light":
        body += (f'<path d="M {CX - 120} {BODY_TOP + 40} Q {CX} {BODY_TOP + 10} {CX + 120} {BODY_TOP + 40} '
                 f'L {CX + 130} {BODY_TOP + 170} Q {CX} {BODY_TOP + 210} {CX - 130} {BODY_TOP + 170} Z" '
                 f'fill="{shade(p1, 1.15)}"{_o(8)}/>'
                 f'<path d="M {CX} {BODY_TOP + 30} L {CX} {BODY_TOP + 190}" stroke="{shade(p1, 0.6)}" stroke-width="6"/>')
        o.update(arm_c=p2, sock=shade(p2, 0.8), shoe="#3d4552")
    elif kind == "coat_long":
        body = f'<path d="{_tunic_d(150, 230, 1280)}" fill="{p1}"{_o(10)}/>'
        body += (f'<path d="M {CX} {BODY_TOP - 10} L {CX} 1270" stroke="{shade(p1, 0.65)}" stroke-width="7"/>'
                 f'<path d="M {CX - 44} {BODY_TOP - 6} L {CX} {BODY_TOP + 96} L {CX + 44} {BODY_TOP - 6} Z" fill="{p2}"{_o(7)}/>'
                 + "".join(f'<circle cx="{CX - 20}" cy="{BODY_TOP + 150 + i * 70}" r="7" fill="{shade(p1, 0.55)}"/>' for i in range(2)))
        o.update(hide_legs=False, hem=1280, shoe="#2a2622")
    elif kind == "apron_staff":
        body += (f'<path d="M {CX - 84} {BODY_TOP + 60} L {CX + 84} {BODY_TOP + 60} L {CX + 104} {HEM - 20} '
                 f'Q {CX} {HEM + 6} {CX - 104} {HEM - 20} Z" fill="{p2}"{_o(8)}/>'
                 f'<path d="M {CX - 50} {BODY_TOP + 60} L {CX - 40} {BODY_TOP - 10} M {CX + 50} {BODY_TOP + 60} L {CX + 40} {BODY_TOP - 10}" '
                 f'stroke="{_INK}" stroke-width="7"/>')
    elif kind == "dress":
        body += (f'<path d="M {CX - 46} {BODY_TOP - 4} Q {CX} {BODY_TOP + 30} {CX + 46} {BODY_TOP - 4}" '
                 f'stroke="{_INK}" stroke-width="7" fill="none"/>'
                 f'<rect x="{CX - 130}" y="{BODY_TOP + 168}" width="260" height="26" rx="12" fill="{acc}"{_o(6)}/>'
                 f'<path d="M {CX - 60} {HEM - 60} L {CX - 70} {HEM} M {CX} {HEM - 54} L {CX} {HEM + 8} '
                 f'M {CX + 60} {HEM - 60} L {CX + 70} {HEM}" stroke="{shade(p1, 0.72)}" stroke-width="5"/>')
    else:  # tee_casual
        body += (f'<path d="M {CX - 40} {BODY_TOP - 8} Q {CX} {BODY_TOP + 24} {CX + 40} {BODY_TOP - 8}" '
                 f'stroke="{_INK}" stroke-width="7" fill="none"/>')
        o.update(legs_c="#5a7ab5", sock="#5a7ab5", shoe="#e8e6e0")
    o["body"] = body
    return o


def _accessories(look: CharacterLook) -> str:
    out = []
    if "glasses" in look.accessories:
        out.append(f'<g stroke="{_INK}" stroke-width="8" fill="none">'
                   f'<circle cx="{CX - 118}" cy="{EY}" r="52"/><circle cx="{CX + 118}" cy="{EY}" r="52"/>'
                   f'<path d="M {CX - 66} {EY} Q {CX} {EY - 14} {CX + 66} {EY}"/></g>')
    if "beard" in look.accessories:
        c = look.hair_color
        out.append(f'<path d="M {CX - 90} {MY - 10} Q {CX - 60} {MY + 90} {CX} {MY + 100} '
                   f'Q {CX + 60} {MY + 90} {CX + 90} {MY - 10} Q {CX + 40} {MY + 30} {CX} {MY + 30} '
                   f'Q {CX - 40} {MY + 30} {CX - 90} {MY - 10} Z" fill="{c}"{_o(8)}/>')
    if "hairband" in look.accessories:
        out.append(f'<path d="M {CX - 240} {HCY - 190} Q {CX} {HCY - 300} {CX + 240} {HCY - 190}" '
                   f'stroke="{look.accent}" stroke-width="26" fill="none"/>')
    if "earrings" in look.accessories:
        out.append(f'<circle cx="{CX - HRX - 4}" cy="{HCY + 130}" r="10" fill="{look.accent}"{_o(5)}/>'
                   f'<circle cx="{CX + HRX + 4}" cy="{HCY + 130}" r="10" fill="{look.accent}"{_o(5)}/>')
    return "".join(out)


# ── assembly ──────────────────────────────────────────────────────────────────
def chibi_soft_inner(look, emotion: str = "neutral", pose: str = "stand",
                     facing: str = "front") -> str:
    """Chibi-soft figure CONTENT on the 1024×1536 frame. Never raises."""
    try:
        ids = _Ids()
        lk = look if isinstance(look, CharacterLook) else derive_look(0, base=dict(look or {}))
        p = _POSES.get((pose or "stand").strip().lower(), _POSES["stand"])
        emotion = (emotion or "neutral").strip().lower()
        o = _outfit(lk)
        skin = lk.skin

        legs = ""
        if not o["hide_legs"]:
            (lx, la), (rx, ra) = _LEGS.get(p.get("legs", "stand"), _LEGS["stand"])
            legs = (_leg(lx, la, o["legs_c"], o["shoe"], o["sock"], dirx=-1)
                    + _leg(rx, ra, o["legs_c"], o["shoe"], o["sock"], dirx=1))
        else:
            legs = "".join(
                f'<path d="M {x - 34} {o["hem"] - 8} Q {x} {o["hem"] + 34} {x + 34} {o["hem"] - 8} Z" '
                f'fill="{o["shoe"]}"{_o(8)}/>' for x in (CX - 70, CX + 70))

        # Sleeve reads against a same-colour tunic only by its outline — lift it a touch.
        sleeve = shade(o["arm_c"], 1.12)
        ln = 150 if p.get("short") else 178
        # A raised arm (|angle| > 95°) must render IN FRONT of the huge head, else the
        # wave/cheer gesture disappears behind it (reference keeps raised arms visible).
        arms_back, arms_front = "", ""
        for x, ang, ln_i in ((CX - 176, p["aL"], ln),
                             (CX + 176, p["aR"], 140 if p.get("short_r") else ln)):
            svg_arm = _arm(ids, x, BODY_TOP + 30, ang, sleeve, skin, ln=ln_i)
            if abs(ang) > 95:
                arms_front += svg_arm
            else:
                arms_back += svg_arm
        if p.get("cross"):
            arms_back += (f'<path d="M {CX - 130} {BODY_TOP + 130} Q {CX} {BODY_TOP + 90} {CX + 130} {BODY_TOP + 130} '
                          f'L {CX + 120} {BODY_TOP + 186} Q {CX} {BODY_TOP + 150} {CX - 120} {BODY_TOP + 186} Z" '
                          f'fill="{sleeve}"{_o(9)}/>')

        # Ear only for hair styles that leave it uncovered (short crops).
        ear = ""
        if lk.hair_back in ("short", "topknot", "ponytail", "bun") and lk.gender != "female":
            ear = (f'<path d="M {CX + HRX - 6} {HCY + 96} q 34 -4 30 30 q -6 26 -34 20 Z" '
                   f'fill="{skin}"{_o(8)}/>')
        head = (ear
                + f'<ellipse cx="{CX}" cy="{HCY + 44}" rx="{HRX - 34}" ry="{HRY - 20}" fill="{skin}"{_o(11)}/>'
                + _face(lk, emotion, 22 if facing in ("left", "right") else 0)
                + _hair(lk)
                + _accessories(lk))

        upper = o["body"] + arms_back + head + arms_front
        if p.get("bow"):
            upper = f'<g transform="rotate({p["bow"]} {CX} {BODY_TOP + 200})">{upper}</g>'

        ground = _soft_shadow(ids, CX, 1420, 200, 30, 0.28)
        body = ground + legs + upper
        if p.get("dy"):
            body = f'<g transform="translate(0,{p["dy"]})">{body}</g>'
        if p.get("lean"):
            body = f'<g transform="rotate({p["lean"]} {CX} 1400)">{body}</g>'
        if facing == "left":
            body = f'<g transform="translate({W},0) scale(-1,1)">{body}</g>'
        return body
    except Exception:
        return ""


def build_chibi_soft(look, emotion: str = "neutral", pose: str = "stand",
                     facing: str = "front") -> str:
    inner = chibi_soft_inner(look, emotion, pose, facing)
    if not inner:
        return ""
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{inner}</svg>')


__all__ = ["chibi_soft_inner", "build_chibi_soft"]
