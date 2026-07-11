"""
svg_scene.py — procedural flat SCENE (background) SVG builder (Phase B3).

Python port of the offline flat-scene generators (gradient + silhouette), keyed by a
scene_kind token (AI-plan SettingDef.scene_kind) + a time-of-day tint. Wide 16:9
(1536×1024), opaque. Pure str → str, never raises. Unknown scene_kind → a genre-tinted
gradient fallback so there is ALWAYS a background.

``scene_inner(kind, region, genre, tod) -> str``  (content only, for the compositor)
``build_scene(...) -> str``                        (standalone <svg>)
"""
from __future__ import annotations

W, H = 1536, 1024


def _grad(gid, a, b):
    return (f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/></linearGradient></defs>'
            f'<rect width="{W}" height="{H}" fill="url(#{gid})"/>')


def _floor(y, c, c2):
    return f'<rect y="{y}" width="{W}" height="{H-y}" fill="{c}"/><rect y="{y-10}" width="{W}" height="12" fill="{c2}"/>'


# ── scene templates (return inner SVG, opaque, 1536×1024) ─────────────────────
def _cafe(**k):
    return (_grad("cf", "#5a4232", "#3a2a20")
            + '<rect x="120" y="120" width="520" height="420" rx="12" fill="#a9c8d6"/>'
            + '<g stroke="#5a4232" stroke-width="10"><path d="M380 120 L380 540 M120 330 L640 330"/></g>'
            + "".join(f'<rect x="{x-4}" y="120" width="8" height="150" fill="#2a1e16"/><ellipse cx="{x}" cy="285" rx="34" ry="26" fill="#f2c14a"/>'
                      for x in (820, 1020, 1220, 1420))
            + _floor(720, "#6b4a34", "#4a3122")
            + '<rect x="900" y="620" width="560" height="110" rx="10" fill="#7a5640"/>')


def _classroom(**k):
    return (_grad("cl", "#f4d9a8", "#e8b98a")
            + '<rect x="820" y="120" width="640" height="460" fill="#ffe6b0"/>'
            + '<g stroke="#c98a4a" stroke-width="10"><path d="M1140 120 L1140 580 M820 350 L1460 350"/></g>'
            + '<rect x="80" y="220" width="360" height="220" fill="#3a5a4a"/>'
            + _floor(620, "#c99a6a", "#a6763a")
            + "".join(f'<rect x="{x-60}" y="{y}" width="120" height="20" rx="6" fill="#e0c090"/>'
                      for x in (220, 420, 620, 820, 1020, 1240) for y in (680, 820)))


def _forest(genre="", **k):
    dark = genre in ("horror", "fantasy")
    top, bot = ("#123a3a", "#0a2230") if genre == "fantasy" else ("#cfe6cf", "#7fae8f")
    inner = _grad("bf", top, bot)
    for i in range(22):
        x = 40 + i * 70 + ((i * 53) % 40)
        w = 14 + ((i * 31) % 16)
        col = "#0c2a26" if dark else "#4a7c5a"
        inner += f'<rect x="{x}" y="-40" width="{w}" height="1100" fill="{col}" opacity="{0.35 + (i % 4) * 0.12:.2f}"/>'
    inner += _floor(960, "#3a5c46", "#243a30")
    return inner


def _mountain(**k):
    return (_grad("mp", "#ffe6c9", "#b98a9a")
            + '<circle cx="1050" cy="360" r="120" fill="#fff2df" opacity="0.9"/>'
            + '<path d="M0 800 L280 420 L520 800 Z" fill="#6a5a78"/><path d="M360 800 L768 300 L1180 800 Z" fill="#54465f"/>'
            + '<path d="M980 800 L1280 480 L1536 800 Z" fill="#6a5a78"/>' + _floor(900, "#efe0e6", "#cdbcc6"))


def _throne(**k):
    return (_grad("ih", "#7a2020", "#4a1414")
            + "".join(f'<rect x="{x-24}" y="120" width="48" height="700" fill="#a6301f"/>' for x in (300, 560, 976, 1236))
            + '<path d="M120 120 L1416 120 L1416 150 L120 150 Z" fill="#e8c53a"/>'
            + '<rect x="628" y="360" width="280" height="300" fill="#c9a24a"/>' + _floor(760, "#5a1818", "#3a1010"))


def _bedroom(**k):
    return (_grad("bd", "#e6dce6", "#b89ac0")
            + '<rect x="980" y="160" width="440" height="340" rx="10" fill="#a9cfe0"/>'
            + '<rect x="140" y="560" width="620" height="200" rx="20" fill="#7a6a9a"/><rect x="160" y="600" width="580" height="120" rx="16" fill="#f2eef6"/>'
            + _floor(760, "#b89ac0", "#9a7aa6"))


def _living(**k):
    return (_grad("lr", "#e8dcc8", "#c9a878")
            + '<rect x="120" y="160" width="440" height="360" rx="10" fill="#a9cfe0"/>'
            + '<rect x="820" y="360" width="560" height="220" rx="24" fill="#7a5a8a"/>' + _floor(700, "#c9a878", "#a6835a"))


def _kitchen(**k):
    return (_grad("kt", "#eef0ea", "#c9cdb0")
            + '<rect x="80" y="120" width="1376" height="200" fill="#d9d0b8"/>'
            + '<rect x="80" y="560" width="1376" height="200" fill="#b0a488"/><rect x="80" y="540" width="1376" height="24" fill="#e0dcc8"/>'
            + _floor(760, "#c9cdb0", "#a6ab8c"))


def _garden(**k):
    return (_grad("gy", "#bfe6f4", "#dff2e0")
            + '<circle cx="1240" cy="200" r="90" fill="#fff6d8" opacity="0.85"/>'
            + '<rect x="200" y="380" width="44" height="300" fill="#7a5636"/><ellipse cx="222" cy="350" rx="150" ry="120" fill="#5aa05a"/>'
            + _floor(640, "#7ac06a", "#5a9a4a"))


def _street(genre="", **k):
    return (_grad("st", "#161a3a", "#3a2a4a")
            + '<circle cx="1230" cy="200" r="70" fill="#f3ead0" opacity="0.9"/>'
            + "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{H-y}" fill="#0e1424"/>'
                      for x, y, w in ((0, 560, 180), (330, 600, 130), (630, 430, 150), (920, 500, 160), (1230, 470, 150)))
            + '<rect x="0" y="980" width="1536" height="44" fill="#0a0e1a"/>')


def _castle(**k):
    return (_grad("ch", "#4a4258", "#2a2438")
            + "".join(f'<rect x="{x-30}" y="120" width="60" height="760" fill="#3a3450"/>' for x in (190, 470, 1066, 1346))
            + "".join(f'<rect x="{x-70}" y="180" width="140" height="420" rx="70" fill="#7a6a3a" opacity="0.55"/>' for x in (320, 768, 1216))
            + _floor(820, "#231e30", "#151022"))


_SCENES = {
    "cafe": _cafe, "coffee_shop": _cafe, "classroom": _classroom, "school": _classroom,
    "forest": _forest, "bamboo_forest": _forest, "woods": _forest, "mountain": _mountain,
    "peak": _mountain, "cliff": _mountain, "throne_room": _throne, "palace": _throne,
    "imperial_hall": _throne, "bedroom": _bedroom, "living_room": _living, "home": _living,
    "kitchen": _kitchen, "garden": _garden, "yard": _garden, "park": _garden,
    "street": _street, "city": _street, "alley": _street, "castle_hall": _castle,
    "castle": _castle, "hall": _castle,
}

# genre → fallback palette (top, bottom, floor, floor2)
_GENRE_PAL = {
    "wuxia": ("#cfe0e6", "#8fa6ae", "#5a6a6a", "#3a4a4a"),
    "ngontinh": ("#ffe0e8", "#f6c6d0", "#d9a2b0", "#b98a98"),
    "horror": ("#1a2030", "#0c1018", "#08100c", "#040804"),
    "fantasy": ("#bfe6d8", "#8fc6a8", "#5a8a6a", "#3a6a4a"),
    "codai": ("#e6d3a8", "#cdbf9a", "#a89a70", "#8a7c54"),
    "hiendai": ("#cfe0ee", "#aec4d6", "#8a9aa8", "#6a7a88"),
}


def _night_overlay():
    stars = "".join(f'<circle cx="{(i*181+30) % W}" cy="{(i*97) % 520}" r="{1+(i%3)}" fill="#fff" opacity="{0.4+(i%4)*0.15:.2f}"/>'
                    for i in range(60))
    return ('<rect width="1536" height="1024" fill="#0e1636" opacity="0.55"/>'
            '<rect width="1536" height="1024" fill="#1a1030" opacity="0.18"/>'
            '<circle cx="1300" cy="180" r="74" fill="#f4f0d0" opacity="0.9"/>'
            '<circle cx="1272" cy="164" r="74" fill="#0e1636" opacity="0.55"/>' + stars)


def scene_inner(kind: str, region: str = "", genre: str = "", tod: str = "") -> str:
    """Inner SVG for a scene (opaque, fills 1536×1024). Unknown kind → genre gradient.
    tod='night' overlays a night tint. Never raises."""
    try:
        k = (kind or "").strip().lower().replace(" ", "_").replace("-", "_")
        fn = _SCENES.get(k)
        if fn:
            inner = fn(genre=(genre or "").strip().lower())
        else:
            pal = _GENRE_PAL.get((genre or "").strip().lower(), ("#cfe0ee", "#aec4d6", "#8a9aa8", "#6a7a88"))
            inner = _grad("fb", pal[0], pal[1]) + _floor(720, pal[2], pal[3])
        if (tod or "").strip().lower() == "night":
            inner += _night_overlay()
        return inner
    except Exception:
        return _grad("fb", "#cfe0ee", "#aec4d6")


def build_scene(kind: str, region: str = "", genre: str = "", tod: str = "") -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
            + scene_inner(kind, region, genre, tod) + "</svg>")


__all__ = ["scene_inner", "build_scene"]
