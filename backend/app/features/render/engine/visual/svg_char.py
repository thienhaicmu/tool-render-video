"""
svg_char.py — procedural CHIBI character SVG builder (Phase B2).

Faithful Python port of the offline chibi builder used to author the asset library
(same shapes → same look). Pure str → str, never raises. Big head, short chubby body,
big cute eyes; supports outfit kinds (shirt/dress/robe/gown), emotion
(smile/open/angry/sad/stern), pose (stand/wave/cheer/point/hip), hat + props.

Canvas 1024×1536, transparent. ``build_char(opts) -> svg_string``; rasterise via
svg_raster.save_svg_png(..., 1024, 1536).  See svg_presets.py for archetype→opts.
"""
from __future__ import annotations

# ── front hair (drawn over the big head) ─────────────────────────────────────
_HAIR = {
 "short": lambda c: f'<path d="M262 430 Q250 168 512 158 Q774 168 762 430 Q740 300 660 286 Q612 360 512 360 Q412 360 364 286 Q284 300 262 430 Z" fill="{c}"/>',
 "bob": lambda c: f'<path d="M256 560 Q244 168 512 158 Q780 168 768 560 L742 560 Q744 360 700 300 Q640 350 512 350 Q384 350 324 300 Q280 360 282 560 Z" fill="{c}"/>',
 "long": lambda c: f'<path d="M262 430 Q250 168 512 158 Q774 168 762 430 Q744 320 700 300 Q640 350 512 350 Q384 350 324 300 Q280 320 262 430 Z" fill="{c}"/>',
 "twin": lambda c: f'<path d="M262 430 Q250 168 512 158 Q774 168 762 430 Q740 300 660 288 Q612 356 512 356 Q412 356 364 288 Q284 300 262 430 Z" fill="{c}"/><circle cx="250" cy="470" r="86" fill="{c}"/><circle cx="774" cy="470" r="86" fill="{c}"/>',
 "pony": lambda c: f'<path d="M262 430 Q250 168 512 158 Q774 168 762 430 Q740 300 660 288 Q612 356 512 356 Q412 356 364 288 Q284 300 262 430 Z" fill="{c}"/><path d="M760 300 Q900 380 862 640 Q844 690 800 668 Q846 460 720 360 Z" fill="{c}"/>',
 "bun": lambda c: f'<circle cx="512" cy="176" r="70" fill="{c}"/><path d="M270 420 Q262 200 512 190 Q762 200 754 420 Q730 300 660 290 Q612 356 512 356 Q412 356 364 290 Q294 300 270 420 Z" fill="{c}"/>',
 "spiky": lambda c: f'<path d="M262 420 L300 250 L356 360 L404 210 L452 350 L512 200 L572 350 L620 210 L668 360 L724 250 L762 420 Q660 300 512 300 Q364 300 262 420 Z" fill="{c}"/>',
 "topknot": lambda c: f'<circle cx="512" cy="180" r="44" fill="{c}"/><path d="M280 420 Q272 210 512 202 Q752 210 744 420 Q724 306 660 296 Q612 356 512 356 Q412 356 364 296 Q300 306 280 420 Z" fill="{c}"/>',
 "curly": lambda c: f'<g fill="{c}"><circle cx="330" cy="300" r="70"/><circle cx="430" cy="240" r="76"/><circle cx="540" cy="230" r="80"/><circle cx="650" cy="250" r="74"/><circle cx="720" cy="330" r="66"/><path d="M290 440 Q300 320 512 314 Q724 320 734 440 Q700 360 512 360 Q324 360 290 440 Z"/></g>',
}
_BACK = {
 "long": lambda c: f'<path d="M250 380 Q250 170 512 160 Q774 170 774 380 L806 1040 Q800 1090 740 1078 L716 470 L308 470 L284 1078 Q224 1090 218 1040 Z" fill="{c}"/>',
 "twin": lambda c: f'<circle cx="236" cy="470" r="86" fill="{c}"/><path d="M180 520 Q150 820 220 1020 Q250 1070 300 1044 Q236 780 300 540 Z" fill="{c}"/><circle cx="788" cy="470" r="86" fill="{c}"/><path d="M844 520 Q874 820 804 1020 Q774 1070 724 1044 Q788 780 724 540 Z" fill="{c}"/>',
 "curly": lambda c: f'<g fill="{c}"><circle cx="300" cy="480" r="60"/><circle cx="724" cy="480" r="60"/><circle cx="300" cy="600" r="54"/><circle cx="724" cy="600" r="54"/></g>',
}

# ── HATs (optional) ──────────────────────────────────────────────────────────
_HAT = {
 "witch": lambda c="#3a2a4a": f'<path d="M512 40 L640 300 L384 300 Z" fill="{c}"/><ellipse cx="512" cy="300" rx="210" ry="40" fill="{c}"/><rect x="384" y="272" width="256" height="30" fill="#c9a227" opacity="0.8"/>',
 "crown": lambda g="#f2d24a": f'<path d="M396 210 L430 120 L478 190 L512 100 L546 190 L594 120 L628 210 Z" fill="{g}"/><rect x="396" y="200" width="232" height="26" fill="{g}"/><circle cx="512" cy="150" r="12" fill="#e0403a"/>',
 "straw": lambda c="#d9b96a": f'<ellipse cx="512" cy="250" rx="260" ry="44" fill="{c}"/><path d="M372 250 Q380 120 512 118 Q644 120 652 250 Z" fill="{c}"/><rect x="372" y="228" width="280" height="24" fill="#b23a3a" opacity="0.7"/>',
}


def _eyes(col="#4a3728", expr="smile"):
    if expr == "closed":
        return ('<path d="M388 486 Q430 452 472 486" stroke="#3a2c22" stroke-width="9" fill="none" stroke-linecap="round"/>'
                '<path d="M552 486 Q594 452 636 486" stroke="#3a2c22" stroke-width="9" fill="none" stroke-linecap="round"/>')
    def E(cx):
        return (f'<ellipse cx="{cx}" cy="486" rx="46" ry="58" fill="#ffffff"/><circle cx="{cx}" cy="492" r="40" fill="{col}"/>'
                f'<circle cx="{cx}" cy="496" r="24" fill="#241c18"/><circle cx="{cx-12}" cy="478" r="14" fill="#fff"/>'
                f'<circle cx="{cx+10}" cy="506" r="7" fill="#fff" opacity="0.8"/>')
    return E(430) + E(594)


def _face(expr, brow, skin):
    if expr in ("open", "surprised"):
        mouth = '<ellipse cx="512" cy="588" rx="30" ry="22" fill="#9a3a3a"/><ellipse cx="512" cy="598" rx="18" ry="11" fill="#e2726a"/>'
    elif expr == "angry":
        mouth = '<path d="M476 606 Q512 578 548 606" stroke="#8a2a2a" stroke-width="10" fill="none" stroke-linecap="round"/><path d="M488 592 L536 592" stroke="#8a2a2a" stroke-width="6"/>'
    elif expr == "sad":
        mouth = '<path d="M486 600 Q512 582 538 600" stroke="#a5563f" stroke-width="8" fill="none" stroke-linecap="round"/>'
    elif expr == "stern":
        mouth = '<rect x="490" y="590" width="44" height="9" rx="4" fill="#a5563f"/>'
    else:  # smile
        mouth = '<path d="M470 578 Q512 622 554 578" stroke="#a5563f" stroke-width="9" fill="none" stroke-linecap="round"/>'
    if expr == "angry":
        b = (f'<g fill="{brow}"><rect x="388" y="400" width="78" height="14" rx="7" transform="rotate(20 427 407)"/>'
             f'<rect x="558" y="400" width="78" height="14" rx="7" transform="rotate(-20 597 407)"/></g>')
    elif expr == "sad":
        b = (f'<g fill="{brow}"><rect x="392" y="408" width="72" height="12" rx="6" transform="rotate(-13 428 414)"/>'
             f'<rect x="560" y="408" width="72" height="12" rx="6" transform="rotate(13 596 414)"/></g>')
    else:
        b = f'<rect x="392" y="410" width="70" height="12" rx="6" fill="{brow}"/><rect x="562" y="410" width="70" height="12" rx="6" fill="{brow}"/>'
    nose = '<ellipse cx="512" cy="548" rx="8" ry="6" fill="#e0a884" opacity="0.7"/>'
    bl = "#f28a5a" if expr == "angry" else "#f6a6a0"
    blush = f'<ellipse cx="360" cy="556" rx="42" ry="26" fill="{bl}" opacity="0.55"/><ellipse cx="664" cy="556" rx="42" ry="26" fill="{bl}" opacity="0.55"/>'
    tear = '<ellipse cx="452" cy="548" rx="12" ry="20" fill="#8fd0ea" opacity="0.8"/>' if expr == "sad" else ""
    return b + nose + _eyes(brow or "#4a3728", expr) + mouth + blush + tear


def _arm(px, py, ang, c, skin, ln=214):
    return (f'<g transform="translate({px},{py}) rotate({ang})"><rect x="-34" y="-14" width="68" height="{ln}" rx="34" fill="{c}"/>'
            f'<circle cx="0" cy="{ln-16}" r="44" fill="{skin}"/></g>')


def _pose_arms(pose, c, skin):
    L, R = (350, 756), (674, 756)
    if pose == "wave":
        return _arm(*L, 7, c, skin) + _arm(*R, 205, c, skin, 202)
    if pose == "cheer":
        return _arm(*L, 154, c, skin, 202) + _arm(*R, 206, c, skin, 202)
    if pose == "point":
        return _arm(*L, 7, c, skin) + _arm(*R, 262, c, skin, 210)
    if pose == "hip":
        return _arm(*L, 52, c, skin, 150) + _arm(*R, -52, c, skin, 150)
    return _arm(*L, 7, c, skin) + _arm(*R, -7, c, skin)


def _body_deco(o):
    collar = f'<path d="M446 690 L512 742 L578 690 L556 686 L512 720 L468 686 Z" fill="{o["collar"]}"/>' if o.get("collar") else ""
    tie = (f'<path d="M512 726 l-14 16 l14 22 l14 -22 Z" fill="{o["tie"]}"/><rect x="504" y="762" width="16" height="120" fill="{o["tie"]}"/>'
           if o.get("tie") else "")
    apron = (f'<path d="M420 760 L604 760 L620 1080 Q512 1108 404 1080 Z" fill="{o["apron"]}"/><rect x="470" y="740" width="84" height="40" rx="10" fill="{o["apron"]}"/>'
             if o.get("apron") else "")
    buttons = (f'<circle cx="512" cy="820" r="10" fill="{o["buttons"]}"/><circle cx="512" cy="900" r="10" fill="{o["buttons"]}"/><circle cx="512" cy="980" r="10" fill="{o["buttons"]}"/>'
               if o.get("buttons") else "")
    return apron + collar + tie + buttons


def _body(o):
    top = o.get("top") or "#5a8fd6"
    skin = o["skin"]
    shoes = o.get("shoes") or "#3a3a42"
    bottom = o.get("bottom") or {"kind": "shorts", "color": "#3a4256"}
    kind = bottom.get("kind", "shorts")
    col = bottom.get("color") or top
    arm_c = o.get("sleeve") or o.get("top") or col or "#7a8fae"
    arms = _pose_arms(o.get("pose"), arm_c, skin)
    if kind in ("dress", "gown"):
        skirt = f'<path d="M372 706 Q512 686 652 706 L742 1252 L282 1252 Z" fill="{col}"/>'
        waist = (f'<rect x="360" y="980" width="304" height="34" rx="14" fill="{o["sash"]}"/><rect x="360" y="980" width="304" height="34" rx="14" fill="#00000010"/>'
                 if o.get("sash") else "")
        feet = (f'<ellipse cx="454" cy="1290" rx="52" ry="30" fill="{skin}"/><ellipse cx="570" cy="1290" rx="52" ry="30" fill="{skin}"/>'
                f'<ellipse cx="454" cy="1318" rx="52" ry="24" fill="{shoes}"/><ellipse cx="570" cy="1318" rx="52" ry="24" fill="{shoes}"/>')
        return feet + skirt + arms + waist + _body_deco(o)
    if kind == "robe":
        robe = (f'<path d="M356 700 Q512 680 668 700 L740 1250 L284 1250 Z" fill="{col}"/>'
                '<path d="M486 704 L512 800 L538 704 Z" fill="#00000010"/>')
        sash = f'<rect x="330" y="980" width="364" height="46" rx="10" fill="{o["sash"]}"/>' if o.get("sash") else ""
        feet = f'<ellipse cx="452" cy="1268" rx="54" ry="26" fill="{shoes}"/><ellipse cx="572" cy="1268" rx="54" ry="26" fill="{shoes}"/>'
        return feet + robe + arms + sash
    # round torso + legs (shirt + pants)
    torso = (f'<path d="M512 662 C 360 662 330 770 336 900 C 342 1030 420 1120 512 1120 '
             f'C 604 1120 682 1030 688 900 C 694 770 664 662 512 662 Z" fill="{top}"/>')
    legs = (f'<rect x="430" y="1090" width="76" height="170" rx="36" fill="{col}"/><rect x="518" y="1090" width="76" height="170" rx="36" fill="{col}"/>'
            f'<ellipse cx="454" cy="1300" rx="60" ry="36" fill="{shoes}"/><ellipse cx="570" cy="1300" rx="60" ry="36" fill="{shoes}"/>')
    return legs + torso + arms + _body_deco(o)


def char_inner(opts: dict) -> str:
    """Chibi character CONTENT (no <svg> wrapper), on the 1024×1536 coordinate frame —
    for the compositor to place inside a wider scene. Never raises."""
    try:
        o = dict(opts or {})
        skin = o.get("skin") or "#f6cda6"
        hair = o.get("hair") or "#3a2a20"
        brow = o.get("brow") or hair
        style = o.get("hair_style") or o.get("hairStyle") or "short"
        back = _BACK.get(style, lambda c: "")(hair)
        hat = o.get("hat") or ""
        if hat and hat in _HAT:
            hat = _HAT[hat]()
        return (
            back
            + _body({**o, "skin": skin})
            + f'<ellipse cx="272" cy="430" rx="30" ry="40" fill="{skin}"/><ellipse cx="752" cy="430" rx="30" ry="40" fill="{skin}"/>'
            + f'<ellipse cx="512" cy="410" rx="250" ry="258" fill="{skin}"/>'
            + _face(o.get("expr") or "smile", brow, skin)
            + _HAIR.get(style, _HAIR["short"])(hair)
            + hat + (o.get("props") or "")
        )
    except Exception:
        return ""


def build_char(opts: dict) -> str:
    """Return the chibi character as a standalone SVG string (1024×1536, transparent).
    Never raises. opts keys: skin, hair, hair_style|hairStyle, eye, brow, top, collar, tie,
    apron, buttons, sleeve, bottom{kind,color}, sash, shoes, expr, pose, hat(str key or raw
    svg), props(raw svg)."""
    inner = char_inner(opts)
    if not inner:
        return ""
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="1024" height="1536" viewBox="0 0 1024 1536">'
            + inner + "</svg>")


# emotion (StoryPlan beat.emotion) → builder expr
_EMOTION = {"normal": "smile", "happy": "smile", "smile": "smile", "angry": "angry",
            "sad": "sad", "surprised": "open", "open": "open", "stern": "stern",
            "serious": "stern", "calm": "smile"}


def emotion_expr(emotion: str) -> str:
    return _EMOTION.get((emotion or "").strip().lower(), "smile")


__all__ = ["build_char", "char_inner", "emotion_expr"]
