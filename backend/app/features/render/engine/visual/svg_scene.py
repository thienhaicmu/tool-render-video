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


def _temple(**k):
    return (_grad("tm", "#f0d8b0", "#c99a6a")
            + '<path d="M120 200 L768 70 L1416 200 Z" fill="#a6301f"/>'
            + '<path d="M300 200 L768 110 L1236 200 Z" fill="#8a2418"/>'
            + '<rect x="120" y="200" width="1296" height="26" fill="#6a1f16"/>'
            + "".join(f'<rect x="{x-26}" y="380" width="52" height="380" fill="#b23a2a"/>' for x in (320, 560, 976, 1216))
            + '<rect x="628" y="430" width="280" height="330" fill="#7a1f16"/>' + _floor(760, "#c9a878", "#a6835a"))


def _shrine(**k):
    return (_grad("sh", "#f4c9b0", "#d98a7a")
            + '<g fill="#c62b2b"><rect x="356" y="200" width="42" height="560"/><rect x="1138" y="200" width="42" height="560"/>'
            '<rect x="300" y="196" width="936" height="46"/><rect x="322" y="292" width="892" height="30"/></g>'
            + "".join(f'<ellipse cx="{x}" cy="430" rx="30" ry="40" fill="#e8443a"/><rect x="{x-4}" y="322" width="8" height="70" fill="#3a2418"/>'
                      for x in (520, 1016)) + _floor(760, "#b9846a", "#96634a"))


def _inn(**k):
    return (_grad("in", "#6a4a34", "#3f2c20")
            + "".join(f'<ellipse cx="{x}" cy="250" rx="40" ry="52" fill="#e8443a"/><rect x="{x-4}" y="120" width="8" height="80" fill="#2a1a12"/>'
                      for x in (300, 620, 916, 1236))
            + '<rect x="120" y="600" width="360" height="120" rx="10" fill="#8a5a3a"/><rect x="1056" y="600" width="360" height="120" rx="10" fill="#8a5a3a"/>'
            + _floor(740, "#7a5238", "#553726"))


def _market(**k):
    inner = _grad("mk", "#f4dcb0", "#d9b884")
    for i, x in enumerate((120, 460, 800, 1140)):
        c = ("#c0392b", "#2e7d6b", "#2e5aa8", "#c98a2a")[i % 4]
        inner += (f'<path d="M{x} 320 L{x+280} 320 L{x+240} 400 L{x+40} 400 Z" fill="{c}"/>'
                  f'<rect x="{x+30}" y="400" width="220" height="300" fill="#8a6a44"/>')
    return inner + _floor(700, "#c9a878", "#a6835a")


def _library(**k):
    inner = _grad("lb", "#e8d8bc", "#c4a878")
    for x in (100, 420, 740, 1060):
        inner += f'<rect x="{x}" y="140" width="300" height="620" fill="#6a4a30"/>'
        inner += "".join(f'<rect x="{x+16}" y="{y}" width="268" height="26" fill="#{c}"/>'
                          for y, c in zip(range(170, 760, 40), ("a03a2a", "2e5aa8", "2e7d4a", "c98a2a", "7a3a6a") * 4))
    return inner + _floor(780, "#a6835a", "#7a5c3a")


def _battlefield(genre="", **k):
    top = "#5a3a3a" if genre in ("horror",) else "#8a7a6a"
    inner = _grad("bt", top, "#3a2e28")
    for x, h in ((240, 300), (620, 380), (1000, 260), (1300, 340)):
        inner += f'<rect x="{x-8}" y="{760-h}" width="16" height="{h}" fill="#3a2a1a"/><path d="M{x} {760-h} L{x+120} {760-h+30} L{x} {760-h+70} Z" fill="#a6301f"/>'
    inner += "".join(f'<ellipse cx="{c}" cy="640" rx="120" ry="46" fill="#2a1e18" opacity="0.5"/>' for c in (400, 900, 1300))
    return inner + _floor(760, "#4a3a2a", "#2a2018")


def _cave(**k):
    inner = _grad("cv", "#2a2a34", "#0e0e16")
    inner += '<path d="M0 0 L1536 0 L1536 260 Q1180 120 768 200 Q356 120 0 260 Z" fill="#141420"/>'
    inner += "".join(f'<path d="M{x} 0 L{x+40} 200 L{x-40} 200 Z" fill="#1a1a26"/>' for x in range(160, 1500, 260))
    return inner + _floor(800, "#20202c", "#101018")


def _beach(**k):
    return (_grad("bc", "#8fd6ea", "#cfeaf4")
            + '<circle cx="1220" cy="220" r="90" fill="#fff2c8" opacity="0.9"/>'
            + '<rect y="520" width="1536" height="200" fill="#3a9ad6"/><rect y="510" width="1536" height="14" fill="#bfe6f4"/>'
            + _floor(720, "#f0dca8", "#d9bd84"))


def _snow(**k):
    return (_grad("sn", "#cfe0ee", "#eef4fa")
            + '<path d="M0 700 Q384 560 768 680 Q1152 560 1536 700 L1536 1024 L0 1024 Z" fill="#f4f8fc"/>'
            + "".join(f'<path d="M{x} 700 L{x+70} 480 L{x+140} 700 Z" fill="#3a5c46"/><path d="M{x+18} 620 L{x+70} 470 L{x+122} 620 Z" fill="#4a7c5a"/>'
                      for x in (180, 620, 1080)) + _floor(720, "#e6eef6", "#cdd8e2"))


def _desert(**k):
    return (_grad("ds", "#f4d9a0", "#e8b878")
            + '<circle cx="400" cy="240" r="100" fill="#fff0c0" opacity="0.85"/>'
            + '<path d="M0 640 Q400 560 820 640 Q1180 700 1536 620 L1536 1024 L0 1024 Z" fill="#e0b06a"/>'
            + '<path d="M0 780 Q500 700 1080 790 Q1300 820 1536 760 L1536 1024 L0 1024 Z" fill="#cd9a54"/>')


def _rooftop(**k):
    inner = _grad("rt", "#1a2246", "#3a2a52")
    inner += '<circle cx="1250" cy="200" r="70" fill="#f3ead0" opacity="0.9"/>'
    inner += "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{760-y}" fill="#0e1428"/>' + "".join(
        f'<rect x="{x+8+dx}" y="{y+12+dy}" width="14" height="18" fill="#f2c94a" opacity="0.7"/>'
        for dx in range(0, w - 20, 34) for dy in range(0, 760 - y - 30, 46))
        for x, y, w in ((0, 420, 200), (300, 300, 150), (620, 480, 170), (900, 360, 190), (1240, 440, 160)))
    return inner + '<rect y="760" width="1536" height="20" fill="#2a2a3a"/>' + _floor(800, "#20202e", "#12121c")


def _office(**k):
    inner = _grad("of", "#dfe8ef", "#b8c6d2")
    inner += '<rect x="60" y="100" width="1416" height="440" fill="#aecfe0" opacity="0.7"/>'
    inner += "".join(f'<rect x="{x}" y="100" width="10" height="440" fill="#8aa0b0"/>' for x in range(200, 1476, 260))
    inner += '<rect x="120" y="620" width="480" height="120" rx="8" fill="#5a6a78"/><rect x="940" y="620" width="480" height="120" rx="8" fill="#5a6a78"/>'
    return inner + _floor(740, "#c4ccd2", "#9aa4ac")


def _hospital(**k):
    inner = _grad("hp", "#eef4f2", "#cfe0da")
    inner += '<rect x="1060" y="120" width="400" height="320" fill="#c4e0ea"/>'
    inner += '<rect x="120" y="540" width="520" height="200" rx="16" fill="#e8eef0"/><rect x="120" y="540" width="520" height="60" rx="16" fill="#8fbfd0"/>'
    inner += '<rect x="760" y="160" width="16" height="580" fill="#b0bcc2"/><path d="M776 200 L960 200 L960 520 L776 520" fill="none" stroke="#cdd8dc" stroke-width="10"/>'
    return inner + _floor(760, "#d9e2e0", "#b6c4c0")


def _graveyard(**k):
    inner = _grad("gv", "#2a2e40", "#0e1018")
    inner += '<circle cx="1200" cy="200" r="80" fill="#c8ccd8" opacity="0.7"/>'
    inner += '<path d="M240 760 Q300 400 260 200 Q360 380 420 300 Q400 560 460 760 Z" fill="#0a0c12"/>'
    inner += "".join(f'<rect x="{x-40}" y="{600-h}" width="80" height="{h}" rx="30" fill="#3a3e4a"/>'
                     for x, h in ((560, 180), (760, 140), (980, 200), (1200, 150)))
    return inner + _floor(680, "#1a1e2a", "#0c0e16")


def _ruins(genre="", **k):
    top = "#4a4258" if genre in ("horror",) else "#bfd0d6"
    inner = _grad("ru", top, "#6a5a5a")
    for x, h in ((180, 500), (420, 360), (1020, 420), (1320, 300)):
        inner += f'<rect x="{x-34}" y="{760-h}" width="68" height="{h}" fill="#9a8f86"/><rect x="{x-44}" y="{760-h-20}" width="88" height="24" fill="#8a7f76"/>'
    inner += '<rect x="140" y="360" width="360" height="24" fill="#8a7f76"/>'
    return inner + _floor(760, "#7a7068", "#524a44")


def _water(**k):
    return (_grad("wt", "#bfe6ea", "#7fc6d6")
            + '<path d="M700 120 L740 120 L760 560 L680 560 Z" fill="#eaf6fa"/>'
            + '<ellipse cx="720" cy="600" rx="180" ry="40" fill="#dff2f6"/>'
            + '<rect y="640" width="1536" height="384" fill="#5aaec6"/><rect y="632" width="1536" height="12" fill="#cdeef4"/>'
            + "".join(f'<ellipse cx="{x}" cy="{y}" rx="60" ry="10" fill="#eaf6fa" opacity="0.5"/>'
                      for x, y in ((300, 720), (900, 800), (1250, 700))))


def _courtyard(**k):
    inner = _grad("cy", "#f0e0bc", "#d9c090")
    inner += '<rect x="60" y="180" width="1416" height="220" fill="#b23a2a"/><rect x="60" y="180" width="1416" height="30" fill="#e8c53a"/>'
    inner += "".join(f'<rect x="{x-20}" y="400" width="40" height="300" fill="#8a2418"/>' for x in range(200, 1400, 240))
    inner += '<rect y="700" width="1536" height="324" fill="#c9b088"/>'
    inner += "".join(f'<rect x="{x}" y="700" width="6" height="324" fill="#a68f66"/>' for x in range(0, 1536, 160))
    return inner


def _station(**k):
    # Rainy commuter-station front: platform canopy, a train car, platform edge, drizzle.
    inner = _grad("stn", "#39435c", "#20283a")
    inner += '<rect x="0" y="170" width="1536" height="54" fill="#2a3346"/>'                        # canopy
    inner += "".join(f'<rect x="{x-12}" y="224" width="24" height="470" fill="#333d52"/>' for x in range(200, 1500, 320))
    inner += '<rect x="120" y="470" width="1000" height="230" rx="20" fill="#6b7788"/>'              # train car
    inner += '<rect x="150" y="500" width="940" height="86" rx="10" fill="#a9cbe0" opacity="0.7"/>'  # window band
    inner += "".join(f'<rect x="{x}" y="600" width="120" height="80" fill="#39435c"/>' for x in range(190, 1050, 210))
    inner += '<rect y="700" width="1536" height="324" fill="#454d5e"/>'                              # platform
    inner += '<rect y="700" width="1536" height="14" fill="#f2c94a" opacity="0.55"/>'               # edge line
    inner += "".join(f'<line x1="{x}" y1="200" x2="{x-40}" y2="700" stroke="#aeb8cc" stroke-width="2" opacity="0.22"/>' for x in range(60, 1536, 90))  # rain
    return inner


def _pachinko(**k):
    # Pachinko-parlor interior: dark hall, rows of glowing machines, a neon strip.
    inner = _grad("pk", "#2a1836", "#140b1e")
    inner += '<rect x="0" y="90" width="1536" height="40" fill="#f24a7a" opacity="0.5"/>'           # neon strip
    cols = ((120, "#f24a7a"), (360, "#4ad0f2"), (600, "#f2c94a"), (840, "#7af24a"), (1080, "#f28a4a"), (1300, "#c06af2"))
    inner += "".join(
        f'<rect x="{x}" y="{y}" width="150" height="210" rx="8" fill="#3a2450"/>'
        f'<rect x="{x+22}" y="{y+26}" width="106" height="96" rx="6" fill="{c}" opacity="0.9"/>'
        for y in (170, 430) for x, c in cols)
    return inner + _floor(720, "#2a2038", "#160e22")


def _hotel(**k):
    # Upscale hotel lobby / ballroom: marble, gold-capped columns, chandelier, reception.
    inner = _grad("htl", "#efe6d2", "#cdbfa0")
    inner += "".join(f'<rect x="{x-26}" y="110" width="52" height="640" fill="#e7dcc2"/>'
                     f'<rect x="{x-34}" y="110" width="68" height="26" fill="#c9a24a"/>' for x in (240, 560, 976, 1296))
    inner += '<ellipse cx="768" cy="150" rx="130" ry="36" fill="#f4dc90" opacity="0.85"/>'          # chandelier glow
    inner += '<rect x="560" y="560" width="416" height="190" rx="10" fill="#b89a5a"/>'              # reception desk
    inner += '<rect x="60" y="300" width="300" height="240" fill="#dcccaa" opacity="0.6"/>'         # wall art / window
    return inner + _floor(760, "#d8c9a8", "#b09868")


_SCENES = {
    "cafe": _cafe, "coffee_shop": _cafe, "classroom": _classroom, "school": _classroom,
    # modern-drama scenes (offline procedural) — add new scene_kind tokens here
    "station": _station, "train_station": _station,
    "pachinko": _pachinko, "arcade": _pachinko, "game_center": _pachinko,
    "hotel": _hotel, "hotel_lobby": _hotel, "lobby": _hotel, "ballroom": _hotel,
    "forest": _forest, "bamboo_forest": _forest, "woods": _forest, "mountain": _mountain,
    "peak": _mountain, "cliff": _mountain, "throne_room": _throne, "palace": _throne,
    "imperial_hall": _throne, "bedroom": _bedroom, "living_room": _living, "home": _living,
    "kitchen": _kitchen, "garden": _garden, "yard": _garden, "park": _garden,
    "street": _street, "city": _street, "alley": _street, "castle_hall": _castle,
    "castle": _castle, "hall": _castle,
    # added scene templates (Task: richer backgrounds)
    "temple": _temple, "pagoda": _temple, "shrine": _shrine, "torii": _shrine,
    "inn": _inn, "tavern": _inn, "market": _market, "bazaar": _market,
    "library": _library, "study": _library, "battlefield": _battlefield, "war": _battlefield,
    "cave": _cave, "dungeon": _cave, "beach": _beach, "ocean": _beach, "seaside": _beach,
    "snow": _snow, "snowfield": _snow, "winter": _snow, "desert": _desert, "dunes": _desert,
    "rooftop": _rooftop, "skyline": _rooftop, "office": _office, "hospital": _hospital,
    "clinic": _hospital, "graveyard": _graveyard, "cemetery": _graveyard, "ruins": _ruins,
    "waterfall": _water, "lake": _water, "river": _water, "courtyard": _courtyard,
    "palace_courtyard": _courtyard,
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
