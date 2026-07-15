"""
anime_scene.py — layered flat-anime SCENE builder (GĐ2 Visual Foundation).

A scene = SKY (time-of-day aware) + FAR (desaturated silhouettes) + MID (the place)
+ NEAR (ground + foreground framing) + LIGHT (tod tint / glow / vignette). Depth
comes from the layer palette shifting lighter/cooler with distance; time-of-day
("day" / "sunset" / "night") re-lights the SAME geometry — one recipe, three moods.

Canvas 1536×1024 (same frame as svg_scene so later wiring is drop-in).
Pure str → str; never raises; unknown kind → a lit gradient stage.
NOT wired into the render pipeline yet (GĐ2 DoD: contact-sheet approval first).
"""
from __future__ import annotations

import itertools

from app.features.render.engine.visual.v2.look_spec import shade

W, H = 1536, 1024

# Gradient ids must be UNIQUE per scene instance: contact sheets / composed frames
# embed several scenes in ONE svg, and resvg resolves duplicate ids to the last
# definition (a night sky turned sunset). A per-call counter namespaces them.
_UID = itertools.count(1)
_cur_uid = "0"

SCENES = ("street", "classroom", "office", "cafe", "bedroom", "forest",
          "shrine", "castle_hall", "rooftop", "beach", "hospital",
          "police_office", "laboratory", "living_room", "executive_office",
          "train_station", "convenience_store", "traditional_house", "courtyard",
          "market", "library", "cave", "ruins", "waterfall", "desert", "graveyard",
          "park", "garden", "snow", "temple", "battlefield", "inn")
TODS = ("day", "sunset", "night")

# tod → (sky_top, sky_bottom, sun/moon, far_mul, tint, tint_op, window_glow)
_TOD = {
    "day":    ("#8ec9ea", "#d8ecf4", "#fff6d8", 1.00, "#ffffff", 0.0, "#bfe0ee"),
    "sunset": ("#f4a25a", "#f8d8a0", "#ffdca0", 0.88, "#c85a2a", 0.14, "#ffd9a0"),
    "night":  ("#141c3a", "#2a3556", "#f0ead0", 0.55, "#0e1636", 0.30, "#f2c94a"),
}


def _grad(gid: str, a: str, b: str, y0: int = 0, h: int = H) -> str:
    gid = f"{gid}_{_cur_uid}"
    return (f'<defs><linearGradient id="{gid}" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{a}"/><stop offset="1" stop-color="{b}"/>'
            f'</linearGradient></defs><rect y="{y0}" width="{W}" height="{h}" fill="url(#{gid})"/>')


def _sky(tod: str, indoor: bool = False) -> str:
    top, bot, orb, _, _, _, _ = _TOD.get(tod, _TOD["day"])
    if indoor:
        return ""
    sky = _grad("skyg", top, bot, 0, 760)
    if tod == "night":
        stars = "".join(f'<circle cx="{(i * 197 + 60) % W}" cy="{(i * 83) % 420}" '
                        f'r="{1.5 + (i % 3)}" fill="#fff" opacity="{0.35 + (i % 4) * 0.15:.2f}"/>'
                        for i in range(56))
        moon = (f'<circle cx="1240" cy="170" r="66" fill="{orb}" opacity="0.95"/>'
                f'<circle cx="1214" cy="156" r="66" fill="{top}" opacity="0.9"/>')
        return sky + stars + moon
    sun = f'<circle cx="{1220 if tod == "day" else 380}" cy="{170 if tod == "day" else 560}" r="82" fill="{orb}" opacity="0.9"/>'
    clouds = "".join(
        f'<g fill="#ffffff" opacity="{0.5 if tod == "day" else 0.32}">'
        f'<ellipse cx="{x}" cy="{y}" rx="120" ry="30"/><ellipse cx="{x + 70}" cy="{y - 18}" rx="80" ry="26"/></g>'
        for x, y in ((260, 180), (760, 120), (1120, 260)))
    return sky + sun + clouds


def _win(tod: str, x: int, y: int, w: int, h: int) -> str:
    """A window pane — sky-lit by day, warm-lit at night."""
    glow = _TOD.get(tod, _TOD["day"])[6]
    op = 0.9 if tod == "night" else 0.75
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="6" fill="{glow}" opacity="{op}"/>'


def _f(c: str, tod: str) -> str:
    """FAR-layer tone: fades toward the sky with distance + dims by tod."""
    return shade(c, _TOD.get(tod, _TOD["day"])[3])


def _light(tod: str, indoor: bool = False) -> str:
    _, _, _, _, tint, op, _ = _TOD.get(tod, _TOD["day"])
    out = ""
    if op > 0:
        out += f'<rect width="{W}" height="{H}" fill="{tint}" opacity="{op * (0.75 if indoor else 1):.2f}"/>'
    vid = f"vig_{_cur_uid}"
    out += (f'<defs><radialGradient id="{vid}" cx="0.5" cy="0.42" r="0.85">'
            f'<stop offset="0.62" stop-color="#000" stop-opacity="0"/>'
            f'<stop offset="1" stop-color="#000" stop-opacity="0.22"/></radialGradient></defs>'
            f'<rect width="{W}" height="{H}" fill="url(#{vid})"/>')
    return out


# ── recipes ───────────────────────────────────────────────────────────────────
def _street(tod: str) -> str:
    far = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{700 - y}" fill="{_f("#8a95a8", tod)}"/>'
                  for x, y, w in ((30, 300, 130), (200, 360, 100), (1240, 330, 120), (1400, 380, 110)))
    mid = ""
    for x, y, w, c in ((300, 260, 220, "#b0876a"), (560, 320, 200, "#9aa3b5"), (1000, 280, 230, "#a8927e")):
        mid += f'<rect x="{x}" y="{y}" width="{w}" height="{700 - y}" fill="{shade(c, _TOD[tod][3])}"/>'
        mid += "".join(_win(tod, x + 24 + dx, y + 36 + dy, 40, 52)
                       for dx in range(0, w - 60, 72) for dy in range(0, 700 - y - 90, 110))
        mid += f'<rect x="{x - 8}" y="{y - 18}" width="{w + 16}" height="22" fill="{shade(c, 0.7)}"/>'
    road = (f'<path d="M 0 1024 L 560 700 L 976 700 L 1536 1024 Z" fill="#4a4d58"/>'
            f'<path d="M 745 700 L 700 1024 L 836 1024 L 791 700 Z" fill="#e8e2cf" opacity="0.7"/>'
            f'<rect y="690" width="{W}" height="14" fill="#6a6d78"/>')
    lamps = ""
    for lx in (240, 1296):
        lamps += (f'<rect x="{lx - 7}" y="430" width="14" height="280" fill="#3a3d46"/>'
                  f'<circle cx="{lx}" cy="420" r="26" fill="{"#f2c94a" if tod != "day" else "#d8dce2"}"'
                  f' opacity="{0.95 if tod != "day" else 0.8}"/>')
        if tod != "day":
            lamps += f'<circle cx="{lx}" cy="420" r="60" fill="#f2c94a" opacity="0.18"/>'
    ground = f'<rect y="700" width="{W}" height="{H - 700}" fill="#585c66"/>'
    return _sky(tod) + far + ground + road + mid + lamps


def _classroom(tod: str) -> str:
    wall = _grad("clw", "#f2e6c8", "#e6d4ac")
    windows = ""
    for wx in (90, 470, 850):
        windows += (f'<rect x="{wx}" y="150" width="320" height="330" rx="8" fill="#7a6a4a"/>'
                    + _win(tod, wx + 12, 162, 142, 146) + _win(tod, wx + 166, 162, 142, 146)
                    + _win(tod, wx + 12, 322, 142, 146) + _win(tod, wx + 166, 322, 142, 146))
    board = (f'<rect x="1250" y="170" width="260" height="300" rx="8" fill="#2e5a4a"/>'
             f'<rect x="1240" y="160" width="280" height="12" fill="#8a6a44"/>'
             f'<line x1="1280" y1="240" x2="1420" y2="240" stroke="#e8e2cf" stroke-width="6" opacity="0.7"/>'
             f'<line x1="1280" y1="290" x2="1380" y2="290" stroke="#e8e2cf" stroke-width="6" opacity="0.5"/>')
    floor = (f'<path d="M 0 640 L 1536 640 L 1536 1024 L 0 1024 Z" fill="#c9a06a"/>'
             + "".join(f'<line x1="{i * 200 - 120}" y1="640" x2="{i * 260 - 340}" y2="1024" '
                       f'stroke="#b08a54" stroke-width="5"/>' for i in range(1, 9)))
    desks = ""
    for r, (y, s) in enumerate(((700, 0.85), (820, 1.0))):
        for i in range(3):
            dx = 150 + i * 480 + r * 90
            dw, dh = int(300 * s), int(26 * s)
            desks += (f'<rect x="{dx}" y="{y}" width="{dw}" height="{dh}" rx="8" fill="#8a6a44"/>'
                      f'<rect x="{dx + 16}" y="{y + dh}" width="16" height="{int(120 * s)}" fill="#6a4f30"/>'
                      f'<rect x="{dx + dw - 32}" y="{y + dh}" width="16" height="{int(120 * s)}" fill="#6a4f30"/>')
    return wall + windows + board + floor + desks


def _office(tod: str) -> str:
    wall = _grad("ofw", "#dfe6ee", "#c2ccd8")
    glass = (f'<rect x="60" y="120" width="1416" height="380" fill="{_f("#9fc4dd", tod)}" opacity="0.85"/>'
             + "".join(f'<rect x="{x}" y="120" width="10" height="380" fill="#8aa0b0"/>'
                       for x in range(60, 1480, 236)))
    skyline = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{500 - y}" fill="{_f("#6a7a95", tod)}" opacity="0.8"/>'
                      for x, y, w in ((120, 300, 90), (260, 260, 70), (420, 330, 100), (700, 280, 80),
                                      (900, 320, 110), (1120, 270, 90), (1300, 340, 100)))
    floor = f'<rect y="640" width="{W}" height="{H - 640}" fill="#aeb6c2"/><rect y="632" width="{W}" height="12" fill="#8a93a2"/>'
    desks = ""
    for dx in (140, 900):
        desks += (f'<rect x="{dx}" y="700" width="520" height="30" rx="10" fill="#e8e2d8"/>'
                  f'<rect x="{dx + 30}" y="730" width="22" height="150" fill="#9aa0aa"/>'
                  f'<rect x="{dx + 468}" y="730" width="22" height="150" fill="#9aa0aa"/>'
                  f'<rect x="{dx + 150}" y="600" width="180" height="104" rx="8" fill="#2a3040"/>'
                  f'<rect x="{dx + 158}" y="608" width="164" height="80" rx="4" fill="{_f("#6a9ac4", tod)}"/>'
                  f'<rect x="{dx + 230}" y="704" width="20" height="10" fill="#3a4048"/>')
    plant = (f'<rect x="762" y="800" width="60" height="70" rx="8" fill="#8a5a3a"/>'
             f'<ellipse cx="792" cy="760" rx="80" ry="70" fill="#3e6e4a"/>')
    return wall + glass + skyline + floor + desks + plant + (
        f'<rect y="96" width="{W}" height="10" fill="#f2f4f6" opacity="0.8"/>')


def _cafe(tod: str) -> str:
    wall = _grad("cfw", "#6a4c38", "#4a3324")
    win = (f'<rect x="110" y="150" width="470" height="400" rx="14" fill="#3a2a1e"/>'
           + _win(tod, 126, 166, 210, 368) + _win(tod, 348, 166, 216, 368))
    shelf = "".join(f'<rect x="{860 + i * 150}" y="200" width="110" height="16" fill="#8a6244"/>'
                    + "".join(f'<rect x="{866 + i * 150 + j * 34}" y="{160}" width="24" height="40" rx="4" '
                              f'fill="{c}"/>' for j, c in enumerate(("#c0563a", "#3a7c6a", "#d9a23a")))
                    for i in range(4))
    lamp = "".join(f'<rect x="{x - 3}" y="0" width="6" height="150" fill="#2a1e14"/>'
                   f'<path d="M {x - 44} 190 L {x + 44} 190 L {x + 26} 140 L {x - 26} 140 Z" fill="#c98a3a"/>'
                   f'<circle cx="{x}" cy="196" r="16" fill="#f2c94a" opacity="0.95"/>'
                   + (f'<circle cx="{x}" cy="210" r="52" fill="#f2c94a" opacity="0.16"/>' if tod != "day" else "")
                   for x in (760, 1060, 1360))
    floor = (f'<rect y="660" width="{W}" height="{H - 660}" fill="#7a5136"/>'
             + "".join(f'<rect x="0" y="{y}" width="{W}" height="6" fill="#6a442c"/>' for y in range(700, 1024, 74)))
    counter = (f'<rect x="820" y="560" width="640" height="150" rx="12" fill="#8a5e40"/>'
               f'<rect x="820" y="548" width="640" height="24" rx="10" fill="#a8764e"/>'
               f'<rect x="880" y="480" width="90" height="68" rx="8" fill="#c8c2b4"/>')
    table = (f'<ellipse cx="330" cy="760" rx="150" ry="34" fill="#a8764e"/>'
             f'<rect x="316" y="770" width="28" height="180" fill="#6a442c"/>'
             f'<ellipse cx="330" cy="742" rx="20" ry="8" fill="#f4efe4"/>')
    return wall + win + shelf + lamp + floor + counter + table


def _bedroom(tod: str) -> str:
    wall = _grad("bdw", "#ece2ee", "#cbb4d4")
    win = (f'<rect x="1020" y="140" width="400" height="330" rx="10" fill="#8a7a9a"/>'
           + _win(tod, 1036, 156, 180, 298) + _win(tod, 1228, 156, 176, 298)
           + f'<rect x="990" y="130" width="20" height="360" fill="#d4c4dc"/>'
           + f'<rect x="1430" y="130" width="20" height="360" fill="#d4c4dc"/>')
    floor = f'<rect y="680" width="{W}" height="{H - 680}" fill="#b89ac0"/><rect y="672" width="{W}" height="10" fill="#9a7aa6"/>'
    bed = (f'<rect x="120" y="600" width="620" height="200" rx="26" fill="#7a6a9a"/>'
           f'<rect x="140" y="560" width="580" height="130" rx="20" fill="#f2eef6"/>'
           f'<rect x="150" y="520" width="180" height="80" rx="18" fill="#e0d4ea"/>'
           f'<rect x="120" y="770" width="620" height="40" rx="12" fill="#5c4a78"/>')
    desk = (f'<rect x="1080" y="640" width="330" height="24" rx="8" fill="#a8845c"/>'
            f'<rect x="1100" y="664" width="18" height="130" fill="#7a5e40"/>'
            f'<rect x="1372" y="664" width="18" height="130" fill="#7a5e40"/>'
            f'<rect x="1180" y="560" width="120" height="80" rx="6" fill="#2a3040"/>')
    lamp = (f'<rect x="880" y="560" width="12" height="120" fill="#4a4048"/>'
            f'<path d="M 850 560 L 934 560 L 916 512 L 868 512 Z" fill="#e8c53a"/>'
            + (f'<circle cx="892" cy="565" r="46" fill="#f2c94a" opacity="0.2"/>' if tod != "day" else ""))
    rug = f'<ellipse cx="700" cy="900" rx="260" ry="60" fill="#d4a6b8" opacity="0.8"/>'
    return wall + win + floor + rug + bed + desk + lamp


def _forest(tod: str) -> str:
    far = "".join(f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{int(r * 1.3)}" fill="{_f("#7fae8f", tod)}" opacity="0.7"/>'
                  for x, y, r in ((160, 360, 120), (420, 300, 150), (760, 340, 130), (1080, 300, 150), (1380, 360, 120)))
    trunks = ""
    for i, x in enumerate((90, 340, 620, 940, 1230, 1460)):
        w = 46 + (i * 17) % 26
        c = shade("#5a4030", 0.9 + (i % 3) * 0.08)
        trunks += f'<rect x="{x}" y="0" width="{w}" height="880" rx="14" fill="{c}"/>'
        trunks += f'<path d="M {x} 200 q {w // 2} 30 {w} 0 l 0 26 q -{w // 2} 26 -{w} 0 Z" fill="{shade(c, 0.8)}"/>'
    canopy = "".join(f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{int(r * 0.62)}" fill="{shade("#3e6e4a", 0.9 + (i % 3) * 0.12)}"/>'
                     for i, (x, y, r) in enumerate(((180, 90, 260), (560, 60, 300), (980, 80, 300), (1360, 100, 260))))
    beams = ""
    if tod == "day":
        beams = "".join(f'<path d="M {x} 0 L {x + 130} 0 L {x + 40} 700 L {x - 30} 700 Z" '
                        f'fill="#fff6d8" opacity="0.16"/>' for x in (420, 820, 1180))
    ground = (f'<rect y="820" width="{W}" height="{H - 820}" fill="{shade("#3a5c46", _TOD[tod][3])}"/>'
              + "".join(f'<ellipse cx="{(i * 260 + 120) % W}" cy="{870 + (i % 3) * 40}" rx="90" ry="16" '
                        f'fill="{shade("#4a7c5a", 0.9)}" opacity="0.5"/>' for i in range(8)))
    return _sky(tod) + far + canopy + trunks + beams + ground


def _shrine(tod: str) -> str:
    far = f'<path d="M 0 560 L 300 300 L 620 560 Z" fill="{_f("#7a8a9a", tod)}" opacity="0.7"/>' \
          f'<path d="M 900 560 L 1220 260 L 1536 560 Z" fill="{_f("#68788a", tod)}" opacity="0.7"/>'
    torii = (f'<g fill="#c62b2b">'
             f'<rect x="420" y="180" width="46" height="560"/><rect x="1070" y="180" width="46" height="560"/>'
             f'<rect x="330" y="150" width="876" height="50" rx="10"/>'
             f'<rect x="360" y="250" width="816" height="34"/></g>'
             f'<rect x="330" y="140" width="876" height="18" rx="8" fill="#8a1f16"/>')
    hall = (f'<rect x="620" y="430" width="300" height="240" fill="#8a4a3a"/>'
            f'<path d="M 560 440 L 768 340 L 976 440 Z" fill="#5a3028"/>'
            f'<rect x="700" y="520" width="140" height="150" fill="#4a2a20"/>'
            + (_win(tod, 720, 540, 100, 90) if tod == "night" else ""))
    lanterns = "".join(
        f'<rect x="{x - 5}" y="600" width="10" height="130" fill="#3a2418"/>'
        f'<ellipse cx="{x}" cy="580" rx="30" ry="40" fill="{"#f2c94a" if tod != "day" else "#e8443a"}" '
        f'opacity="0.95"/>' + (f'<ellipse cx="{x}" cy="580" rx="58" ry="66" fill="#f2c94a" opacity="0.16"/>'
                               if tod != "day" else "")
        for x in (300, 1240))
    steps = "".join(f'<rect x="{560 - i * 40}" y="{700 + i * 44}" width="{416 + i * 80}" height="44" '
                    f'fill="{shade("#b9a68a", 1 - i * 0.06)}"/>' for i in range(5))
    trees = (f'<ellipse cx="140" cy="480" rx="130" ry="160" fill="{shade("#4a7c5a", _TOD[tod][3])}"/>'
             f'<rect x="120" y="560" width="40" height="180" fill="#5a4030"/>'
             f'<ellipse cx="1420" cy="470" rx="120" ry="150" fill="{shade("#e58aa0", _TOD[tod][3])}"/>'
             f'<rect x="1402" y="560" width="36" height="180" fill="#5a4030"/>')
    return _sky(tod) + far + trees + steps + hall + torii + lanterns


def _castle_hall(tod: str) -> str:
    wall = _grad("chw", "#4a4258", "#2c2638")
    cols = "".join(f'<rect x="{x}" y="80" width="70" height="760" fill="#3a3450"/>'
                   f'<rect x="{x - 10}" y="80" width="90" height="26" fill="#5a5274"/>'
                   f'<rect x="{x - 10}" y="816" width="90" height="26" fill="#5a5274"/>'
                   for x in (150, 430, 1036, 1316))
    windows = "".join(f'<path d="M {x} 420 L {x} 220 Q {x + 60} 150 {x + 120} 220 L {x + 120} 420 Z" '
                      f'fill="{_TOD[tod][6] if tod == "night" else _f("#9fc4dd", tod)}" opacity="0.85"/>'
                      for x in (300, 708, 1120))
    banners = "".join(f'<path d="M {x} 120 L {x + 120} 120 L {x + 120} 420 L {x + 60} 470 L {x} 420 Z" '
                      f'fill="#7a1f2a"/><rect x="{x}" y="120" width="120" height="26" fill="#c9a24a"/>'
                      for x in (560, 856))
    torch = "".join(f'<rect x="{x - 6}" y="480" width="12" height="80" fill="#5a4030"/>'
                    f'<ellipse cx="{x}" cy="466" rx="18" ry="26" fill="#f2913a"/>'
                    f'<ellipse cx="{x}" cy="470" rx="42" ry="52" fill="#f2913a" opacity="0.2"/>'
                    for x in (240, 1296))
    floor = (f'<rect y="840" width="{W}" height="{H - 840}" fill="#231e30"/>'
             + "".join(f'<line x1="{i * 160}" y1="840" x2="{i * 200 - 240}" y2="1024" stroke="#312a44" '
                       f'stroke-width="6"/>' for i in range(1, 10))
             + f'<path d="M 560 840 L 460 1024 L 1076 1024 L 976 840 Z" fill="#6a1f2a"/>'
               f'<path d="M 700 840 L 660 1024 L 876 1024 L 836 840 Z" fill="#8a2f3a"/>')
    return wall + cols + windows + banners + torch + floor


def _rooftop(tod: str) -> str:
    sky = _sky(tod)
    skyline_far = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{620 - y}" '
                          f'fill="{_f("#5a6a88", tod)}" opacity="0.75"/>'
                          for x, y, w in ((0, 300, 150), (170, 340, 110), (320, 280, 140), (500, 360, 100),
                                          (640, 300, 130), (820, 340, 110), (980, 260, 150), (1180, 330, 120),
                                          (1340, 290, 140)))
    win_glow = ""
    if tod != "day":
        win_glow = "".join(f'<rect x="{(i * 73 + 20) % 1500}" y="{300 + (i * 41) % 280}" width="10" height="14" '
                           f'fill="#f2c94a" opacity="{0.5 + (i % 3) * 0.2:.1f}"/>' for i in range(60))
    deck = (f'<rect y="620" width="{W}" height="{H - 620}" fill="#7a8290"/>'
            f'<rect y="612" width="{W}" height="14" fill="#a8b0bc"/>'
            + "".join(f'<line x1="{x}" y1="620" x2="{x - 60}" y2="1024" stroke="#6a7280" stroke-width="5"/>'
                      for x in range(200, 1500, 260)))
    fence = ("".join(f'<rect x="{x}" y="470" width="8" height="150" fill="#9aa4b2"/>' for x in range(30, 1520, 56))
             + f'<rect x="20" y="470" width="1500" height="10" fill="#b8c0cc"/>'
               f'<rect x="20" y="540" width="1500" height="8" fill="#b8c0cc"/>')
    ac = (f'<rect x="1180" y="520" width="220" height="100" rx="10" fill="#c2c8d2"/>'
          f'<circle cx="1240" cy="570" r="34" fill="#8a929e"/><circle cx="1340" cy="570" r="34" fill="#8a929e"/>')
    door = (f'<rect x="80" y="380" width="200" height="240" rx="8" fill="#8a929e"/>'
            f'<rect x="150" y="430" width="80" height="190" fill="#5a626e"/>')
    return sky + skyline_far + win_glow + fence + deck + ac + door


def _beach(tod: str) -> str:
    sea = (f'<rect y="520" width="{W}" height="240" fill="{shade("#3a9ad6", _TOD[tod][3])}"/>'
           f'<rect y="514" width="{W}" height="12" fill="#cfeaf4" opacity="0.8"/>'
           + "".join(f'<ellipse cx="{(i * 320 + 140) % W}" cy="{560 + (i % 3) * 50}" rx="110" ry="8" '
                     f'fill="#eaf6fa" opacity="0.5"/>' for i in range(7)))
    sand = (f'<path d="M 0 760 Q 400 700 800 748 Q 1200 790 1536 740 L 1536 1024 L 0 1024 Z" '
            f'fill="{shade("#f0dca8", _TOD[tod][3])}"/>'
            + f'<path d="M 0 760 Q 400 700 800 748 Q 1200 790 1536 740 L 1536 760 Q 1200 810 800 768 '
              f'Q 400 720 0 780 Z" fill="#fdf2d0" opacity="0.7"/>')
    palm = (f'<path d="M 1210 460 Q 1240 640 1220 800 L 1260 800 Q 1268 640 1252 470 Z" fill="#7a5636"/>'
            + "".join(f'<path d="M 1235 470 Q {1235 + dx} {470 + dy} {1235 + dx * 2} {470 + dy2} '
                      f'Q {1235 + dx} {480 + dy} 1235 486 Z" fill="#3e7e4a"/>'
                      for dx, dy, dy2 in ((90, -40, 10), (-96, -36, 16), (70, -70, -60), (-64, -74, -66), (8, -90, -80))))
    rock = f'<ellipse cx="240" cy="770" rx="120" ry="46" fill="#8a8378"/><ellipse cx="330" cy="790" rx="70" ry="30" fill="#736c62"/>'
    return _sky(tod) + sea + sand + palm + rock


def _hospital(tod: str) -> str:
    wall = _grad("hpw", "#edf5f5", "#d8e7e8")
    window = (f'<rect x="70" y="130" width="520" height="340" rx="14" fill="#7c96a5"/>'
              + _win(tod, 86, 146, 238, 308) + _win(tod, 336, 146, 238, 308)
              + '<path d="M330 146 V454" stroke="#e8f0f2" stroke-width="12"/>')
    floor = (f'<rect y="650" width="{W}" height="{H - 650}" fill="#b9d1d2"/>'
             + ''.join(f'<path d="M{x} 650 L{x - 90} 1024" stroke="#a6c2c4" stroke-width="4"/>'
                       for x in range(120, 1540, 190)))
    bed = ('<ellipse cx="955" cy="902" rx="410" ry="42" fill="#405868" opacity="0.22"/>'
           '<rect x="650" y="600" width="600" height="230" rx="28" fill="#dbe9ec" stroke="#7894a0" stroke-width="8"/>'
           '<path d="M670 626 Q900 568 1230 630 V720 H670 Z" fill="#f7fbfc"/>'
           '<rect x="690" y="586" width="180" height="78" rx="28" fill="#ffffff" stroke="#c5d7dc" stroke-width="5"/>'
           '<path d="M690 770 H1220" stroke="#6d8792" stroke-width="14"/><circle cx="730" cy="842" r="28" fill="#49606c"/><circle cx="1180" cy="842" r="28" fill="#49606c"/>')
    monitor = ('<rect x="1280" y="420" width="190" height="150" rx="14" fill="#263746" stroke="#7894a0" stroke-width="8"/>'
               '<path d="M1305 500 h28 l18 -46 l32 92 l24 -58 h36" fill="none" stroke="#62d7a1" stroke-width="8"/>'
               '<rect x="1364" y="570" width="20" height="170" fill="#718992"/><rect x="1308" y="738" width="132" height="18" rx="8" fill="#718992"/>')
    iv = ('<rect x="600" y="350" width="12" height="390" rx="6" fill="#80949d"/><path d="M606 360 h70" stroke="#80949d" stroke-width="10"/>'
          '<rect x="642" y="390" width="52" height="100" rx="12" fill="#dff5f4" stroke="#75929b" stroke-width="4" opacity="0.9"/>'
          '<path d="M668 490 Q690 560 650 650" fill="none" stroke="#7894a0" stroke-width="4"/>')
    ceiling = ''.join(f'<rect x="{x}" y="50" width="280" height="34" rx="15" fill="#ffffff" opacity="0.9"/>' for x in (140, 620, 1100))
    return wall + window + ceiling + floor + bed + monitor + iv


def _police_office(tod: str) -> str:
    wall = _grad("pow", "#d9e2e9", "#b9c8d3")
    board = ('<rect x="70" y="130" width="460" height="320" rx="12" fill="#48677b" stroke="#f1f4f6" stroke-width="10"/>'
             + ''.join(f'<rect x="{105 + (i % 4) * 98}" y="{165 + (i // 4) * 112}" width="72" height="86" rx="4" fill="{("#f5efe0", "#dceaf0", "#eedbd9")[i % 3]}" transform="rotate({(i % 3) - 1} {140 + (i % 4) * 98} {208 + (i // 4) * 112})"/>' for i in range(8)))
    lockers = ''.join(f'<rect x="{1130 + i * 120}" y="110" width="106" height="470" rx="6" fill="#6d7f8b" stroke="#4c5d68" stroke-width="5"/>'
                      f'<path d="M{1152 + i * 120} 175 H{1215 + i * 120}" stroke="#aebbc3" stroke-width="8"/>'
                      for i in range(3))
    floor = f'<rect y="650" width="{W}" height="{H - 650}" fill="#9daab4"/><path d="M0 650 H{W}" stroke="#71808c" stroke-width="14"/>'
    desks = ''.join(f'<g transform="translate({x},0)"><ellipse cx="260" cy="895" rx="250" ry="30" fill="#344650" opacity="0.2"/>'
                    '<rect x="70" y="680" width="380" height="35" rx="9" fill="#8e745a"/><rect x="90" y="715" width="25" height="170" fill="#5d6670"/><rect x="405" y="715" width="25" height="170" fill="#5d6670"/>'
                    '<rect x="180" y="570" width="170" height="110" rx="9" fill="#273744"/><rect x="192" y="582" width="146" height="78" rx="4" fill="#6f9eb5"/>'
                    '<rect x="100" y="640" width="70" height="28" rx="5" fill="#e9edf0"/></g>' for x in (30, 720))
    emblem = '<circle cx="790" cy="270" r="96" fill="#2e5672" opacity="0.95"/><path d="M790 192 l24 52 l56 6 l-42 38 l12 56 l-50 -28 l-50 28 l12 -56 l-42 -38 l56 -6 Z" fill="#d4b453"/>'
    return wall + board + lockers + emblem + floor + desks


def _laboratory(tod: str) -> str:
    wall = _grad("lbw", "#e5eef2", "#c4d3dc")
    cabinets = ''.join(f'<rect x="{80 + i * 230}" y="110" width="200" height="360" rx="10" fill="#dce7eb" stroke="#8299a5" stroke-width="6"/>'
                       f'<rect x="{100 + i * 230}" y="145" width="160" height="120" rx="5" fill="#9fc3d0" opacity="0.75"/>'
                       for i in range(4))
    pipes = '<path d="M80 75 H1450 V310 H1380" fill="none" stroke="#73909d" stroke-width="20"/><circle cx="1450" cy="75" r="26" fill="#d6a64b"/>'
    floor = f'<rect y="670" width="{W}" height="{H - 670}" fill="#a9bdc5"/>'
    bench = ('<ellipse cx="760" cy="920" rx="620" ry="42" fill="#3d5663" opacity="0.22"/>'
             '<rect x="160" y="650" width="1210" height="55" rx="15" fill="#eef4f5" stroke="#7d939d" stroke-width="7"/>'
             '<rect x="210" y="705" width="35" height="200" fill="#6d818b"/><rect x="1285" y="705" width="35" height="200" fill="#6d818b"/>')
    gear = ('<rect x="260" y="510" width="210" height="140" rx="16" fill="#536d79"/><circle cx="365" cy="580" r="45" fill="#a9d4df" stroke="#293e48" stroke-width="8"/>'
            '<path d="M650 650 v-90 q0 -80 85 -80 q85 0 85 80 v90" fill="none" stroke="#5089a5" stroke-width="28"/>'
            '<rect x="940" y="535" width="250" height="115" rx="12" fill="#253944"/><path d="M965 605 q38 -70 72 0 t72 0 h50" fill="none" stroke="#74e1b5" stroke-width="7"/>'
            + ''.join(f'<path d="M{560 + i * 58} 610 v40" stroke="{c}" stroke-width="18"/><circle cx="{560 + i * 58}" cy="590" r="22" fill="{c}" opacity="0.8"/>' for i, c in enumerate(("#df6b66", "#e7c95e", "#63b5c8", "#9875c0"))))
    return wall + cabinets + pipes + floor + bench + gear


def _living_room(tod: str) -> str:
    wall = _grad("lrw", "#eee4d5", "#d7c4ae")
    win = '<rect x="90" y="120" width="460" height="350" rx="14" fill="#756454"/>' + _win(tod, 108, 138, 205, 314) + _win(tod, 327, 138, 205, 314)
    floor = f'<rect y="680" width="{W}" height="{H - 680}" fill="#b98e64"/>'
    sofa = ('<ellipse cx="775" cy="922" rx="500" ry="45" fill="#49372c" opacity="0.22"/>'
            '<rect x="400" y="570" width="720" height="270" rx="55" fill="#8898a0" stroke="#5f6e75" stroke-width="8"/>'
            '<rect x="450" y="610" width="300" height="180" rx="32" fill="#9daab0"/><rect x="770" y="610" width="300" height="180" rx="32" fill="#9daab0"/>'
            '<rect x="365" y="610" width="100" height="220" rx="38" fill="#718188"/><rect x="1055" y="610" width="100" height="220" rx="38" fill="#718188"/>')
    table = '<ellipse cx="770" cy="900" rx="250" ry="48" fill="#8b6848"/><rect x="752" y="900" width="36" height="110" fill="#654a34"/>'
    tv = '<rect x="1190" y="260" width="280" height="190" rx="14" fill="#202a32" stroke="#5a646c" stroke-width="8"/><rect x="1210" y="280" width="240" height="150" rx="6" fill="#678da1"/><rect x="1314" y="450" width="28" height="120" fill="#5b5149"/>'
    decor = '<rect x="650" y="145" width="260" height="200" rx="8" fill="#705c4b"/><rect x="668" y="163" width="224" height="164" fill="#b8c8a2"/><ellipse cx="1390" cy="660" rx="85" ry="130" fill="#527954"/><rect x="1350" y="755" width="80" height="90" rx="12" fill="#8c5f3d"/>'
    return wall + win + floor + decor + sofa + table + tv


def _executive_office(tod: str) -> str:
    base = _office(tod)
    overlay = ('<rect x="65" y="505" width="1410" height="135" fill="#354451" opacity="0.18"/>'
               '<ellipse cx="790" cy="935" rx="620" ry="55" fill="#1b2830" opacity="0.26"/>'
               '<rect x="360" y="700" width="820" height="70" rx="14" fill="#604a38" stroke="#382c24" stroke-width="8"/>'
               '<rect x="405" y="770" width="58" height="175" fill="#3f342e"/><rect x="1075" y="770" width="58" height="175" fill="#3f342e"/>'
               '<path d="M690 700 V560 Q770 500 850 560 V700" fill="#35414b" stroke="#1f2930" stroke-width="9"/>'
               '<rect x="630" y="625" width="280" height="62" rx="10" fill="#222e36"/><rect x="651" y="637" width="238" height="36" rx="5" fill="#648ea3"/>'
               '<rect x="95" y="525" width="230" height="320" rx="12" fill="#58483d"/>'
               + ''.join(f'<path d="M115 {580 + i * 62} H305" stroke="#91745a" stroke-width="8"/>' for i in range(4)))
    return base + overlay


def _train_station(tod: str) -> str:
    sky = _sky(tod)
    roof = '<path d="M0 0 H1536 V150 H0 Z" fill="#465965"/><path d="M0 150 H1536" stroke="#718792" stroke-width="24"/>'
    platform = f'<path d="M0 520 H{W} V840 H0 Z" fill="#a8afb2"/><path d="M0 780 H{W}" stroke="#e2c64f" stroke-width="30"/>'
    tracks = ('<rect y="840" width="1536" height="184" fill="#4a5052"/>'
              + ''.join(f'<rect x="{x}" y="850" width="90" height="174" fill="#676d6e" transform="skewX(-16)"/>' for x in range(-100, 1700, 170))
              + '<path d="M0 900 H1536 M0 990 H1536" stroke="#bcc3c4" stroke-width="18"/>')
    cols = ''.join(f'<rect x="{x}" y="130" width="32" height="650" fill="#52656f"/><rect x="{x - 20}" y="500" width="72" height="18" fill="#40535d"/>' for x in (150, 620, 1090, 1450))
    bench = '<rect x="320" y="600" width="420" height="38" rx="12" fill="#53798c"/><rect x="350" y="638" width="25" height="120" fill="#44545c"/><rect x="685" y="638" width="25" height="120" fill="#44545c"/>'
    vending = '<rect x="1220" y="330" width="210" height="440" rx="18" fill="#e9ecec" stroke="#6f8088" stroke-width="8"/><rect x="1250" y="370" width="150" height="240" rx="9" fill="#7fb0c4"/>' + ''.join(f'<circle cx="{1280 + (i % 3) * 48}" cy="{410 + (i // 3) * 55}" r="15" fill="{("#e46b5a", "#62a36e", "#e1c450")[i % 3]}"/>' for i in range(12)) + '<rect x="1280" y="660" width="90" height="42" rx="6" fill="#46535a"/>'
    return sky + roof + platform + cols + bench + vending + tracks


def _convenience_store(tod: str) -> str:
    wall = _grad("cvw", "#eef2f2", "#d7e0e1")
    lights = ''.join(f'<rect x="{x}" y="55" width="300" height="35" rx="16" fill="#ffffff" opacity="0.95"/>' for x in (90, 610, 1130))
    floor = f'<rect y="700" width="{W}" height="{H - 700}" fill="#bec7c9"/>'
    fridges = ''.join(f'<rect x="{70 + i * 235}" y="170" width="215" height="460" rx="10" fill="#c9dce1" stroke="#6e858e" stroke-width="7"/>'
                      f'<rect x="{88 + i * 235}" y="195" width="179" height="385" fill="#87adba" opacity="0.75"/>'
                      + ''.join(f'<path d="M{95 + i * 235} {270 + j * 90} H{255 + i * 235}" stroke="#e8f0f2" stroke-width="10"/>' for j in range(4))
                      for i in range(4))
    shelf = ('<rect x="1030" y="300" width="410" height="390" rx="10" fill="#e8e4da" stroke="#7b827f" stroke-width="7"/>'
             + ''.join(f'<path d="M1050 {365 + j * 92} H1420" stroke="#86908d" stroke-width="12"/>' for j in range(4))
             + ''.join(f'<rect x="{1070 + (i % 6) * 55}" y="{320 + (i // 6) * 92}" width="34" height="52" rx="5" fill="{("#d76655", "#e0b54b", "#5b9f75", "#648eb4")[i % 4]}"/>' for i in range(24)))
    counter = '<ellipse cx="650" cy="920" rx="390" ry="38" fill="#46555c" opacity="0.2"/><rect x="330" y="690" width="650" height="210" rx="16" fill="#e4e7e5" stroke="#798582" stroke-width="7"/><rect x="330" y="680" width="650" height="34" rx="12" fill="#5b9b78"/><rect x="720" y="590" width="190" height="90" rx="8" fill="#263740"/><rect x="745" y="610" width="140" height="50" fill="#78a2af"/>'
    return wall + lights + fridges + shelf + floor + counter


def _traditional_house(tod: str) -> str:
    wall = _grad("thw", "#e7ddc7", "#cbbd9f")
    shoji = ''.join(f'<g transform="translate({x},0)"><rect x="0" y="120" width="310" height="470" fill="#f1ead8" stroke="#6d5137" stroke-width="14"/>'
                    + ''.join(f'<path d="M{v} 120 V590" stroke="#8b6c4c" stroke-width="7"/>' for v in (62, 124, 186, 248))
                    + ''.join(f'<path d="M0 {y} H310" stroke="#8b6c4c" stroke-width="7"/>' for y in (214, 308, 402, 496)) + '</g>' for x in (80, 400, 720))
    alcove = '<rect x="1080" y="115" width="360" height="520" fill="#b79b73"/><rect x="1130" y="175" width="260" height="300" rx="5" fill="#e9e1d0"/><path d="M1260 210 q-100 120 0 220 q100 -100 0 -220" fill="none" stroke="#4f6c56" stroke-width="13"/><rect x="1200" y="520" width="120" height="90" rx="10" fill="#735037"/><path d="M1260 520 q-45 -75 0 -120 q45 45 0 120" fill="#708c61"/>'
    tatami = f'<rect y="650" width="{W}" height="{H - 650}" fill="#b7ad72"/>' + ''.join(f'<rect x="{x}" y="680" width="330" height="290" fill="none" stroke="#7f794f" stroke-width="10"/>' for x in (30, 390, 750, 1110))
    table = '<ellipse cx="740" cy="895" rx="310" ry="50" fill="#60442f" opacity="0.25"/><rect x="500" y="760" width="480" height="70" rx="18" fill="#765137"/><rect x="540" y="830" width="35" height="120" fill="#533a29"/><rect x="905" y="830" width="35" height="120" fill="#533a29"/><ellipse cx="740" cy="750" rx="55" ry="18" fill="#d2c6a8"/><path d="M720 742 q20 -50 40 0" fill="none" stroke="#8b6d4d" stroke-width="8"/>'
    beams = f'<rect y="90" width="{W}" height="35" fill="#61452f"/><rect y="620" width="{W}" height="30" fill="#61452f"/>'
    return wall + shoji + alcove + tatami + table + beams


def _courtyard(tod: str) -> str:
    wall = _grad("cwy", "#d8e5e8", "#aab8b2")
    sky = _sky(tod)
    gate = ('<path d="M480 660 V270 Q768 90 1056 270 V660" fill="#8a4a3a" stroke="#5c3029" stroke-width="18"/>'
            '<path d="M430 270 Q768 40 1106 270" fill="none" stroke="#6e3b30" stroke-width="46"/>'
            '<rect x="620" y="360" width="296" height="300" fill="#4b3330"/>')
    trees = ''.join(f'<rect x="{x}" y="390" width="42" height="300" fill="#654532"/>'
                    f'<ellipse cx="{x + 20}" cy="340" rx="150" ry="120" fill="{shade("#4f7e59", 0.84 + i * .06)}"/>'
                    for i, x in enumerate((90, 1280)))
    floor = '<rect y="660" width="1536" height="364" fill="#b1a177"/><path d="M0 1024 L540 660 H996 L1536 1024" fill="#c5b88b" opacity="0.85"/>'
    stones = ''.join(f'<ellipse cx="{x}" cy="{y}" rx="42" ry="16" fill="#7f846f" opacity="0.8"/>' for x, y in ((240, 820), (360, 900), (1210, 820), (1330, 910)))
    return sky + wall + trees + gate + floor + stones


def _market(tod: str) -> str:
    sky = _sky(tod)
    ground = '<rect y="650" width="1536" height="374" fill="#8f735d"/><path d="M0 1024 L580 650 H960 L1536 1024" fill="#b28c69"/>'
    stalls = []
    for i, x in enumerate((80, 500, 920, 1340)):
        color = ("#c95745", "#3d7180", "#d7a33c", "#7a4f82")[i]
        stalls.append(f'<rect x="{x}" y="330" width="300" height="330" fill="#8b5a3b" stroke="#513528" stroke-width="10"/>'
                      f'<path d="M{x - 24} 330 Q{x + 150} 215 {x + 324} 330 Z" fill="{color}" stroke="#513528" stroke-width="10"/>'
                      f'<rect x="{x + 22}" y="480" width="256" height="80" rx="12" fill="#d6b27a"/>'
                      f'<circle cx="{x + 80}" cy="520" r="26" fill="#e2b84f"/><circle cx="{x + 150}" cy="520" r="26" fill="#78a764"/><circle cx="{x + 220}" cy="520" r="26" fill="#bf6650"/>')
    lanterns = ''.join(f'<path d="M{x} 0 V170" stroke="#45352f" stroke-width="8"/><path d="M{x - 34} 190 H{x + 34} L{x + 22} 250 H{x - 22} Z" fill="#e6b64d"/>' for x in (210, 760, 1310))
    return sky + ground + ''.join(stalls) + lanterns


def _library(tod: str) -> str:
    wall = _grad("liw", "#d7d4c7", "#9c8c78")
    shelves = ''.join(f'<rect x="{x}" y="150" width="250" height="480" fill="#684b37" stroke="#392d25" stroke-width="12"/>'
                      f'<path d="M{x + 24} {260 + j * 92} H{x + 226}" stroke="#b28b59" stroke-width="16"/>'
                      for x in (90, 390, 690, 990, 1290) for j in range(4))
    books = ''.join(f'<rect x="{x + 32 + (j % 5) * 38}" y="{260 + (j // 5) * 92}" width="25" height="58" fill="{c}"/>'
                    for x in (90, 390, 690, 990, 1290) for j, c in enumerate(("#b85b4a", "#668e8e", "#d1a34d", "#7b6a9b", "#8b5f43") * 4))
    table = '<rect y="710" width="1536" height="314" fill="#8e7358"/><ellipse cx="768" cy="790" rx="320" ry="48" fill="#654732"/><rect x="744" y="800" width="48" height="180" fill="#543a2b"/><circle cx="768" cy="746" r="24" fill="#e7ca83"/>'
    return wall + shelves + books + table


def _cave(tod: str) -> str:
    wall = _grad("cav", "#263346", "#10141f")
    rocks = '<path d="M0 0 L240 0 L390 190 L290 460 L0 560 Z" fill="#394456"/><path d="M1536 0 L1290 0 L1150 200 L1240 500 L1536 580 Z" fill="#2e394d"/>'
    opening = '<path d="M410 1024 Q420 280 768 160 Q1116 280 1126 1024 Z" fill="#080d17" stroke="#53647a" stroke-width="18"/>'
    crystals = ''.join(f'<path d="M{x} 860 L{x + 30} {y} L{x + 65} 860 Z" fill="{c}" opacity="0.82"/>' for x, y, c in ((500, 620, "#6fc4d1"), (610, 720, "#91a9e8"), (920, 650, "#bd83df"), (1010, 760, "#6fc4d1")))
    ground = '<path d="M0 1024 L0 850 Q420 780 768 890 Q1110 780 1536 850 V1024 Z" fill="#2b3442"/>'
    return wall + rocks + opening + crystals + ground


def _ruins(tod: str) -> str:
    sky = _sky(tod)
    ground = '<rect y="700" width="1536" height="324" fill="#776c5d"/><path d="M0 1024 L420 700 H1110 L1536 1024" fill="#91806a"/>'
    columns = ''.join(f'<path d="M{x} 180 L{x + 70} 210 V720 H{x - 4} Z" fill="#827c73" stroke="#4f504f" stroke-width="12"/>' for x in (180, 480, 1040, 1320))
    arch = '<path d="M300 460 Q768 20 1236 460" fill="none" stroke="#696860" stroke-width="70"/><path d="M310 460 Q768 80 1226 460" fill="none" stroke="#a59a87" stroke-width="20"/>'
    rubble = ''.join(f'<path d="M{x} {y} l60 -35 l55 40 l-68 42 Z" fill="#5f5b53"/>' for x, y in ((90, 820), (300, 900), (1140, 840), (1380, 920)))
    return sky + ground + arch + columns + rubble


def _waterfall(tod: str) -> str:
    sky = _sky(tod)
    trees = ''.join(f'<ellipse cx="{x}" cy="{y}" rx="{r}" ry="{int(r * .72)}" fill="{shade("#3e6e4a", 0.88 + i * .05)}"/>' for i, (x, y, r) in enumerate(((130, 250, 220), (380, 220, 240), (1170, 230, 250), (1430, 270, 190))))
    cliff = '<path d="M0 590 L430 500 L600 560 V860 H0 Z" fill="#6f7c6c"/><path d="M1536 590 L1110 500 L940 560 V860 H1536 Z" fill="#637463"/>'
    fall = '<path d="M650 90 Q768 40 886 90 L850 720 Q768 800 686 720 Z" fill="#b8e6ee" opacity="0.82"/><path d="M720 120 Q768 80 816 120 L800 690 Q768 730 736 690 Z" fill="#e3f6f3" opacity="0.5"/>'
    pool = '<ellipse cx="768" cy="850" rx="450" ry="110" fill="#518ca0"/><ellipse cx="768" cy="830" rx="260" ry="45" fill="#9bdae0" opacity="0.5"/>'
    return sky + trees + cliff + fall + pool


def _desert(tod: str) -> str:
    sky = _sky(tod)
    dunes = '<path d="M0 690 Q330 510 680 700 Q1050 470 1536 690 V1024 H0 Z" fill="#c99557"/><path d="M0 780 Q420 620 800 800 Q1140 650 1536 800 V1024 H0 Z" fill="#e0b46d"/>'
    ruins = '<path d="M560 690 V410 H640 V690 M900 690 V350 H980 V690" stroke="#75523a" stroke-width="60"/><path d="M500 430 H1040" stroke="#75523a" stroke-width="50"/>'
    return sky + dunes + ruins


def _graveyard(tod: str) -> str:
    sky = _sky(tod)
    hill = '<path d="M0 650 Q360 430 720 650 Q1100 390 1536 650 V1024 H0 Z" fill="#4b5b59"/>'
    stones = ''.join(f'<path d="M{x} 790 V{y} Q{x + 42} {y - 44} {x + 84} {y} V790 Z" fill="#a8aaa0" stroke="#4a514e" stroke-width="8"/>' for x, y in ((140, 560), (380, 610), (680, 500), (980, 600), (1250, 530)))
    trees = '<path d="M90 820 V350 M90 480 L0 390 M90 560 L190 440 M1400 820 V300 M1400 470 L1300 370 M1400 560 L1500 440" stroke="#292f2d" stroke-width="44"/>'
    return sky + hill + trees + stones


def _park(tod: str) -> str:
    sky = _sky(tod)
    lawn = '<rect y="650" width="1536" height="374" fill="#72a46c"/><path d="M650 1024 Q690 780 768 650 Q846 780 886 1024" fill="#d7bd8f"/>'
    trees = ''.join(f'<rect x="{x}" y="{y}" width="35" height="260" fill="#694a34"/><ellipse cx="{x + 18}" cy="{y - 20}" rx="130" ry="100" fill="#4f895a"/>' for x, y in ((140, 430), (1230, 400)))
    bench = '<rect x="570" y="790" width="390" height="28" rx="8" fill="#765037"/><rect x="600" y="820" width="24" height="120" fill="#5a3e2e"/><rect x="906" y="820" width="24" height="120" fill="#5a3e2e"/>'
    return sky + lawn + trees + bench


def _garden(tod: str) -> str:
    sky = _sky(tod)
    lawn = '<rect y="650" width="1536" height="374" fill="#78a36e"/><ellipse cx="760" cy="850" rx="340" ry="110" fill="#4f8b9c"/><ellipse cx="760" cy="830" rx="230" ry="45" fill="#8ec9c4" opacity="0.55"/>'
    trees = ''.join(f'<path d="M{x} 740 V380" stroke="#654832" stroke-width="38"/><ellipse cx="{x}" cy="330" rx="150" ry="115" fill="#4d8858"/>' for x in (150, 1370))
    flowers = ''.join(f'<circle cx="{x}" cy="{y}" r="10" fill="{c}"/>' for x, y, c in ((280, 760, "#e26d6d"), (360, 820, "#e7c34f"), (1120, 770, "#d77ab0"), (1230, 840, "#f1d05b")))
    return sky + lawn + trees + flowers


def _snow(tod: str) -> str:
    sky = _sky(tod)
    ground = '<path d="M0 650 Q360 560 720 680 Q1110 540 1536 660 V1024 H0 Z" fill="#e8f0f2"/>'
    pines = ''.join(f'<path d="M{x} 700 L{x + 90} 250 L{x + 180} 700 Z" fill="#3d5f62"/><path d="M{x + 40} 560 L{x + 90} 380 L{x + 140} 560 Z" fill="#f1f5f4"/>' for x in (80, 330, 1120, 1370))
    cabin = '<path d="M590 690 V470 L770 330 L950 470 V690 Z" fill="#85563e" stroke="#50382d" stroke-width="12"/><path d="M540 470 L770 270 L1000 470" fill="none" stroke="#dce8e8" stroke-width="48"/><rect x="720" y="540" width="100" height="150" fill="#50382d"/><rect x="620" y="500" width="80" height="70" fill="#f2c94a"/>'
    return sky + ground + pines + cabin


def _temple(tod: str) -> str:
    sky = _sky(tod)
    ground = '<rect y="690" width="1536" height="334" fill="#9c8264"/><path d="M0 1024 L520 690 H1016 L1536 1024" fill="#c0a07a"/>'
    hall = ('<rect x="480" y="390" width="576" height="330" fill="#b84e36" stroke="#5b3028" stroke-width="14"/>'
            '<path d="M390 400 Q768 210 1146 400 L1090 450 Q768 320 446 450 Z" fill="#304a63" stroke="#1d2c42" stroke-width="14"/>'
            '<path d="M330 340 Q768 120 1206 340 L1146 385 Q768 240 390 385 Z" fill="#3b5d78" stroke="#1d2c42" stroke-width="14"/>'
            '<rect x="700" y="505" width="136" height="215" fill="#49322b"/>'
            '<rect x="560" y="500" width="82" height="100" fill="#e9b85b"/><rect x="894" y="500" width="82" height="100" fill="#e9b85b"/>')
    lanterns = ''.join(f'<path d="M{x} 120 V300" stroke="#402c29" stroke-width="8"/><path d="M{x - 30} 310 H{x + 30} L{x + 18} 380 H{x - 18} Z" fill="#d66b43"/>' for x in (240, 1296))
    steps = '<rect x="420" y="720" width="696" height="32" fill="#6f5544"/><rect x="360" y="752" width="816" height="32" fill="#775a47"/><rect x="300" y="784" width="936" height="32" fill="#85644d"/>'
    return sky + ground + hall + lanterns + steps


def _battlefield(tod: str) -> str:
    sky = _sky(tod)
    hills = '<path d="M0 620 Q240 420 480 620 Q780 380 1080 620 Q1320 450 1536 620 V1024 H0 Z" fill="#65735f"/>'
    ground = '<path d="M0 760 Q400 650 780 770 Q1140 640 1536 760 V1024 H0 Z" fill="#75614d"/>'
    flags = ''.join(f'<path d="M{x} 230 V850" stroke="#3f3937" stroke-width="14"/><path d="M{x} 250 L{x + 170} 300 L{x} 360 Z" fill="{c}"/>' for x, c in ((260, "#b7473b"), (560, "#4c6f8f"), (1030, "#c49342"), (1320, "#8c4f71")))
    rocks = ''.join(f'<path d="M{x} 850 l55 -90 l70 90 Z" fill="#4e4e4a"/>' for x in (120, 720, 1260))
    return sky + hills + ground + flags + rocks


def _inn(tod: str) -> str:
    wall = _grad("inw", "#77513d", "#3b2a25")
    beams = '<rect y="90" width="1536" height="42" fill="#32251f"/><rect x="100" y="130" width="38" height="540" fill="#432e26"/><rect x="1398" y="130" width="38" height="540" fill="#432e26"/>'
    tables = ''.join(f'<ellipse cx="{x}" cy="{y}" rx="180" ry="36" fill="#9d6d43"/><rect x="{x - 14}" y="{y}" width="28" height="170" fill="#553a2c"/>' for x, y in ((300, 760), (760, 850), (1230, 740)))
    shelves = '<rect x="930" y="220" width="430" height="370" fill="#5a3c2f" stroke="#2e211e" stroke-width="12"/>' + ''.join(f'<rect x="{970 + i * 90}" y="{290 + (i % 2) * 120}" width="55" height="75" rx="8" fill="{c}"/>' for i, c in enumerate(("#c95b43", "#d4aa4e", "#638e78", "#7d6ca0", "#b86e48", "#6e8ba1")))
    lamps = ''.join(f'<path d="M{x} 0 V170" stroke="#271d1a" stroke-width="8"/><path d="M{x - 42} 190 H{x + 42} L{x + 24} 250 H{x - 24} Z" fill="#d79f4c"/>' for x in (320, 780, 1240))
    return wall + beams + shelves + tables + lamps


_RECIPES = {
    "street": _street, "classroom": _classroom, "office": _office, "cafe": _cafe,
    "bedroom": _bedroom, "forest": _forest, "shrine": _shrine,
    "castle_hall": _castle_hall, "rooftop": _rooftop, "beach": _beach,
    "hospital": _hospital, "police_office": _police_office, "laboratory": _laboratory,
    "living_room": _living_room, "executive_office": _executive_office,
    "train_station": _train_station, "convenience_store": _convenience_store,
    "traditional_house": _traditional_house, "courtyard": _courtyard, "market": _market,
    "library": _library, "cave": _cave, "ruins": _ruins, "waterfall": _waterfall,
    "desert": _desert, "graveyard": _graveyard, "park": _park, "garden": _garden,
    "snow": _snow, "temple": _temple, "battlefield": _battlefield, "inn": _inn,
}
_INDOOR = {"classroom", "office", "cafe", "bedroom", "castle_hall", "hospital",
           "police_office", "laboratory", "living_room", "executive_office",
    "convenience_store", "traditional_house", "courtyard", "market", "library", "cave",
    "ruins", "waterfall", "desert", "graveyard", "park", "garden", "snow",
    "temple", "battlefield", "inn"}

# aliases → recipe (mirrors svg_scene token families)
_ALIASES = {
    "city": "street", "alley": "street", "town": "street",
    "school": "classroom", "lecture_hall": "classroom",
    "workplace": "office", "meeting_room": "office",
    "hospital_room": "hospital", "clinic": "hospital", "doctor_office": "hospital",
    "police_station": "police_office", "kobан": "police_office", "koban": "police_office",
    "lab": "laboratory", "engineering_lab": "laboratory", "workshop": "laboratory",
    "family_home": "living_room", "apartment": "living_room",
    "ceo_office": "executive_office", "director_office": "executive_office",
    "station": "train_station", "metro_station": "train_station",
    "konbini": "convenience_store", "shop": "convenience_store",
    "washitsu": "traditional_house", "ryokan": "traditional_house",
    "coffee_shop": "cafe", "restaurant": "cafe", "tavern": "cafe", "inn": "cafe",
    "home": "bedroom", "living_room": "bedroom", "room": "bedroom",
    "woods": "forest", "bamboo_forest": "forest", "jungle": "forest", "mountain": "forest",
    "temple": "shrine", "torii": "shrine", "pagoda": "shrine",
    "palace": "castle_hall", "throne_room": "castle_hall", "castle": "castle_hall",
    "hall": "castle_hall", "imperial_hall": "castle_hall",
    "skyline": "rooftop", "balcony": "rooftop",
    "ocean": "beach", "seaside": "beach", "coast": "beach", "lake": "beach",
}


def anime_scene_inner(kind: str, tod: str = "day", style_id: str | None = None) -> str:
    """Scene CONTENT (opaque, fills 1536×1024). Unknown kind → lit gradient stage.
    Never raises."""
    global _cur_uid
    try:
        _cur_uid = str(next(_UID))
        k = (kind or "").strip().lower().replace(" ", "_").replace("-", "_")
        k = _ALIASES.get(k, k)
        t = (tod or "day").strip().lower()
        if t not in TODS:
            t = "day"
        fn = _RECIPES.get(k)
        if fn is None:
            top, bot, *_ = _TOD[t]
            body = _grad("fbg", shade(top, 0.9), shade(bot, 0.9)) + \
                f'<rect y="720" width="{W}" height="{H - 720}" fill="{shade(bot, 0.6)}"/>'
        else:
            body = fn(t)
        body = body + _light(t, k in _INDOOR)
        if style_id:
            from app.features.render.engine.visual.v2.theme_pack import wrap_scene
            body = wrap_scene(body, style_id, W, H)
        return body
    except Exception:
        return _grad("fbe", "#cfe0ee", "#aec4d6")


def build_anime_scene(kind: str, tod: str = "day", style_id: str | None = None) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
            f'viewBox="0 0 {W} {H}">{anime_scene_inner(kind, tod, style_id)}</svg>')


__all__ = ["build_anime_scene", "anime_scene_inner", "SCENES", "TODS"]
