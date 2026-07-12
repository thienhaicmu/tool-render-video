"""
svg_presets.py — archetype → chibi appearance opts for the procedural builder (Phase B2).

Maps the AI-plan CharacterDef.archetype (+ region / gender) to a set of svg_char.build_char
opts (skin/hair/outfit/colour/props). Derived from the offline chibi roster so a procedural
character matches the look of the pre-rendered library. Pure + defensive: an unknown
archetype falls back to a neutral "everyman"; nothing raises.
"""
from __future__ import annotations

# reusable props (chibi coords: chin≈y640, shoulders≈y740)
_BEARD = lambda c="#3a2c22": f'<path d="M366 556 Q512 712 658 556 Q642 636 512 656 Q382 636 366 556 Z" fill="{c}"/>'
_LBEARD = lambda c="#e2ded6": f'<path d="M384 556 Q404 812 512 852 Q620 812 640 556 Q616 652 512 672 Q408 652 384 556 Z" fill="{c}"/>'
_SWORD = ('<rect x="726" y="720" width="10" height="360" rx="5" fill="#c9ccd2"/>'
          '<rect x="714" y="720" width="34" height="26" rx="6" fill="#7a5a3a"/>')
_STAFF = ('<rect x="272" y="700" width="14" height="440" rx="7" fill="#8a6a44"/>'
          '<circle cx="279" cy="690" r="30" fill="#8fd6ea"/>')
# extra props (raw SVG, chibi coords: head centre≈512,410 top≈152; drawn over everything)
_HALO = '<ellipse cx="512" cy="118" rx="132" ry="34" fill="none" stroke="#f5e18a" stroke-width="14" opacity="0.95"/>'
_HORNS = ('<path d="M366 214 Q330 120 300 150 Q356 156 366 232 Z" fill="#6a3226"/>'
          '<path d="M658 214 Q694 120 724 150 Q668 156 658 232 Z" fill="#6a3226"/>')
_TUSKS = ('<path d="M470 604 L462 648 L486 616 Z" fill="#f4efe4"/>'
          '<path d="M554 604 L562 648 L538 616 Z" fill="#f4efe4"/>')
_BOW = ('<path d="M268 640 Q210 860 268 1080" fill="none" stroke="#7a5a3a" stroke-width="12"/>'
        '<line x1="268" y1="640" x2="268" y2="1080" stroke="#e8e2d0" stroke-width="3"/>')
_HOOD = lambda c="#2a2630": (f'<path d="M248 440 Q236 150 512 140 Q788 150 776 440 L742 440 '
                             f'Q744 260 660 250 Q690 362 512 362 Q334 362 364 250 Q280 260 282 440 Z" fill="{c}"/>')
_ANTENNA = '<rect x="506" y="88" width="12" height="62" fill="#9aa0a6"/><circle cx="512" cy="82" r="16" fill="#e0403a"/>'
_FEDORA = ('<ellipse cx="512" cy="252" rx="224" ry="34" fill="#3a2c22"/>'
           '<path d="M398 250 Q408 150 512 148 Q616 150 626 250 Z" fill="#4a3628"/>'
           '<rect x="398" y="230" width="228" height="22" fill="#241a14"/>')
_TRICORN = ('<path d="M300 236 Q512 120 724 236 Q724 274 512 274 Q300 274 300 236 Z" fill="#241a14"/>'
            '<circle cx="512" cy="168" r="18" fill="#e8c53a"/>')
_BEADS = ('<g fill="#7a4a2a">'
          '<circle cx="392" cy="726" r="9"/><circle cx="428" cy="756" r="9"/><circle cx="470" cy="776" r="9"/>'
          '<circle cx="512" cy="784" r="9"/><circle cx="554" cy="776" r="9"/><circle cx="596" cy="756" r="9"/>'
          '<circle cx="632" cy="726" r="9"/></g>')
_EYEPATCH = '<ellipse cx="594" cy="492" rx="42" ry="36" fill="#141414"/><path d="M552 470 L648 460" stroke="#141414" stroke-width="8"/>'
_LUTE = ('<ellipse cx="286" cy="900" rx="66" ry="86" fill="#a0703a"/><circle cx="286" cy="900" r="20" fill="#3a2418"/>'
         '<rect x="278" y="640" width="16" height="220" rx="6" fill="#5a3a1e"/>')

# region → default skin tone (archetype can override, e.g. ghost/vampire pale)
_REGION_SKIN = {"cn": "#f0d0ae", "jp": "#f6cda6", "ko": "#f6cda6", "vi": "#e6b58a",
                "eu": "#f0d0ae", "us": "#e6bd96"}
_EVERYMAN = {"hair": "#3a2a20", "hair_style": "short", "top": "#5a8fd6", "collar": "#fff",
             "bottom": {"kind": "shorts", "color": "#3a4256"}, "shoes": "#e8e8e8"}

# archetype → opts override (merged onto everyman). Keys are lowercase tokens the AI emits.
_ARCH: dict = {
 "office_worker": {"top": "#2f3b52", "tie": "#7a2a2a", "bottom": {"kind": "shorts", "color": "#20242e"}, "shoes": "#1c1c1e"},
 "salaryman": {"hair": "#2a2622", "top": "#6b6f73", "tie": "#3f4a55", "bottom": {"kind": "shorts", "color": "#4a4d52"}, "shoes": "#2a2622"},
 "businessman": {"hair": "#201914", "top": "#2b3a55", "collar": "#bcd0e6", "tie": "#7a2a2a", "bottom": {"kind": "shorts", "color": "#2a3346"}, "shoes": "#5a4030"},
 "ceo": {"hair": "#c4bfb8", "top": "#3a3d44", "tie": "#6a1f24", "bottom": {"kind": "shorts", "color": "#2a2c30"}, "shoes": "#1a1a1c", "expr": "stern", "props": _BEARD("#b8b3ac")},
 "cafe_staff": {"hair": "#6b4a2e", "hair_style": "bob", "top": "#f3ead6", "apron": "#9c6b3f", "bottom": {"kind": "shorts", "color": "#c8b28c"}, "shoes": "#7a5a3a", "collar": None},
 "waiter": {"top": "#f3ead6", "apron": "#9c6b3f", "bottom": {"kind": "shorts", "color": "#c8b28c"}, "shoes": "#7a5a3a"},
 "chef": {"top": "#fbfbfb", "apron": "#f0ede6", "buttons": "#cfc8bc", "bottom": {"kind": "shorts", "color": "#8a8f96"}, "shoes": "#3a3a3a"},
 "nurse": {"hair": "#2a2320", "hair_style": "bob", "top": "#8fd0d6", "collar": "#fff", "bottom": {"kind": "dress", "color": "#a9e0e4"}, "shoes": "#eee"},
 "student": {"hair": "#7a5230", "top": "#e7b7c2", "bottom": {"kind": "shorts", "color": "#41597a"}, "shoes": "#efe9df", "collar": None},
 "child": {"hair_style": "bob", "top": "#f2c94c", "bottom": {"kind": "dress", "color": "#f2c94c"}, "shoes": "#e0553a", "collar": None},
 "grandpa": {"hair": "#c9c4bd", "top": "#7a6f56", "buttons": "#5a5040", "bottom": {"kind": "shorts", "color": "#5a4d3a"}, "shoes": "#4a3a2a", "props": _BEARD("#c9c4bd"), "collar": None},
 "grandma": {"hair": "#c9c4bd", "hair_style": "bun", "top": "#b89ac0", "bottom": {"kind": "dress", "color": "#c8b6d0"}, "shoes": "#7a6a80", "collar": None},
 "teacher": {"hair": "#3a2c22", "top": "#8a9bb0", "bottom": {"kind": "shorts", "color": "#3a4150"}, "shoes": "#33291f"},
 "idol": {"hair": "#1a1a1a", "hair_style": "spiky", "top": "#2a2a30", "buttons": "#c0c0c8", "bottom": {"kind": "shorts", "color": "#1c1c22"}, "shoes": "#e0e0e0", "collar": None},
 # cổ trang / wuxia
 "swordsman": {"hair": "#1c1712", "hair_style": "topknot", "top": "#eef0f4", "bottom": {"kind": "robe", "color": "#eef0f4"}, "sash": "#4a7c9c", "shoes": "#3a352e", "expr": "stern", "props": _SWORD, "collar": None},
 "heroine": {"hair": "#1a1510", "hair_style": "long", "top": "#bcd4e6", "bottom": {"kind": "gown", "color": "#bcd4e6"}, "sash": "#7a9bbf", "shoes": "#5a6a7a", "collar": None},
 "immortal": {"hair": "#eeeae2", "hair_style": "long", "top": "#f4f2ec", "bottom": {"kind": "robe", "color": "#f4f2ec"}, "sash": "#cdbf9a", "shoes": "#8a7a5a", "props": _LBEARD() + _STAFF, "collar": None},
 "villain": {"hair": "#141014", "hair_style": "long", "eye": "#a02a2a", "top": "#2a1a24", "bottom": {"kind": "robe", "color": "#2a1a24"}, "sash": "#8a1f2a", "shoes": "#1a1016", "expr": "stern", "props": _BEARD("#141014") + _SWORD, "collar": None},
 "emperor": {"hair": "#241d18", "hair_style": "topknot", "top": "#e8c53a", "bottom": {"kind": "robe", "color": "#e8c53a"}, "sash": "#a6301f", "shoes": "#8a6a2a", "expr": "stern", "props": _BEARD("#241d18"), "hat": "crown", "collar": None},
 "king": {"hair": "#241d18", "hair_style": "topknot", "top": "#a6301f", "bottom": {"kind": "robe", "color": "#a6301f"}, "sash": "#e8c53a", "shoes": "#6a3a1e", "expr": "stern", "props": _BEARD("#241d18"), "hat": "crown", "collar": None},
 "general": {"hair": "#241d18", "hair_style": "topknot", "top": "#8a3a2a", "bottom": {"kind": "robe", "color": "#9a4a36"}, "sash": "#e8c53a", "shoes": "#4a2a1e", "expr": "stern", "props": _BEARD("#241d18") + _SWORD, "collar": None},
 "scholar": {"hair": "#241d18", "hair_style": "topknot", "top": "#2a2a30", "bottom": {"kind": "robe", "color": "#2a2a30"}, "sash": "#5a5a44", "shoes": "#1a1a20", "props": _BEARD("#8a857e"), "collar": None},
 "princess": {"hair": "#1a1510", "hair_style": "bun", "top": "#d4405a", "bottom": {"kind": "gown", "color": "#d4405a"}, "sash": "#e8c53a", "shoes": "#a62a3a", "hat": "crown", "collar": None},
 "noblewoman": {"hair": "#1a1510", "hair_style": "bun", "top": "#7fae8f", "bottom": {"kind": "gown", "color": "#e9dfe8"}, "sash": "#b25a7a", "shoes": "#8a5a6a", "collar": None},
 "samurai": {"hair": "#1c1712", "hair_style": "topknot", "top": "#3a4a3a", "bottom": {"kind": "robe", "color": "#4a5a4a"}, "sash": "#6a2a2a", "shoes": "#2a241e", "expr": "stern", "props": _SWORD, "collar": None},
 "ninja": {"hair": "#141414", "top": "#1f1f26", "bottom": {"kind": "shorts", "color": "#18181e"}, "shoes": "#0e0e12", "expr": "stern", "props": '<rect x="262" y="470" width="500" height="70" rx="10" fill="#1a1a20"/>', "collar": None},
 "geisha": {"skin": "#fbeee4", "hair": "#1a1510", "hair_style": "bun", "eye": "#3a2a2a", "top": "#c62b5a", "bottom": {"kind": "gown", "color": "#d94070"}, "sash": "#e8c53a", "shoes": "#7a3a4a", "collar": None},
 # fantasy / horror
 "knight": {"hair": "#6b4a2e", "top": "#b8bcc4", "buttons": "#8a9098", "bottom": {"kind": "shorts", "color": "#9aa0aa"}, "shoes": "#5a5e66", "expr": "stern", "props": _SWORD, "collar": None},
 "mage": {"hair": "#d8d3cb", "hair_style": "long", "top": "#2f3d7a", "bottom": {"kind": "robe", "color": "#2f3d7a"}, "sash": "#c9a227", "shoes": "#3a2a4a", "props": _LBEARD() + _STAFF, "hat": "witch", "collar": None},
 "witch": {"skin": "#e0d0c8", "hair": "#2a1a2a", "hair_style": "long", "eye": "#6a8a4a", "top": "#2a1a34", "bottom": {"kind": "gown", "color": "#2a1a34"}, "sash": "#5a3a1a", "shoes": "#1a1020", "hat": "witch", "collar": None},
 "vampire": {"skin": "#e8e2e4", "hair": "#141216", "eye": "#a02a2a", "top": "#17151a", "collar": "#7a1420", "tie": None, "bottom": {"kind": "robe", "color": "#1f1c24"}, "sash": "#3a1520", "shoes": "#0a0a0c", "expr": "stern"},
 "elf": {"skin": "#f6dcc0", "hair": "#dcdad4", "hair_style": "long", "eye": "#5a8a5a", "top": "#5a7a4a", "bottom": {"kind": "shorts", "color": "#4a5a3a"}, "shoes": "#5a4630", "collar": None},
 "dwarf": {"skin": "#e0a878", "hair": "#6a3a1a", "top": "#7a5a3a", "bottom": {"kind": "shorts", "color": "#5a4028"}, "shoes": "#3a2818", "expr": "stern", "props": _LBEARD("#a03a1a"), "collar": None},
 "ghost": {"skin": "#e6e2e4", "hair": "#dcd8da", "hair_style": "long", "eye": "#8a8a9a", "top": "#eef0f2", "bottom": {"kind": "gown", "color": "#e8eaee"}, "shoes": "#d8d8dc", "expr": "sad", "collar": None},
 # modern west
 "cowboy": {"skin": "#e6b58a", "hair": "#3a2c22", "top": "#c9b48a", "buttons": "#8a6a44", "bottom": {"kind": "shorts", "color": "#3a5a7a"}, "shoes": "#4a3320", "expr": "stern", "hat": "straw", "collar": None},
 "astronaut": {"hair": "#241d18", "top": "#eef1f4", "buttons": "#3a6ea5", "bottom": {"kind": "shorts", "color": "#e2e6ea"}, "shoes": "#9aa0a6", "collar": None},
 "soldier": {"skin": "#e6b58a", "hair": "#2a2622", "top": "#5a6a4a", "buttons": "#3a4432", "bottom": {"kind": "shorts", "color": "#4a5a3a"}, "shoes": "#2a2a20", "expr": "stern", "collar": None},
 # extra archetypes (Task: more diverse forms) — cổ trang / spiritual
 "monk": {"skin": "#e8c9a2", "hair": "#e6c6a2", "hair_style": "short", "top": "#c8772a", "bottom": {"kind": "robe", "color": "#c8772a"}, "sash": "#8a3a1a", "shoes": "#6a4a2a", "expr": "smile", "props": _BEADS, "collar": None},
 "assassin": {"hair": "#141216", "top": "#1c1c22", "bottom": {"kind": "robe", "color": "#1c1c22"}, "sash": "#3a1520", "shoes": "#0c0c10", "expr": "stern", "props": _HOOD() + _SWORD, "collar": None},
 "merchant": {"hair": "#241d18", "hair_style": "topknot", "top": "#7a5a2a", "buttons": "#c9a24a", "bottom": {"kind": "robe", "color": "#8a6a34"}, "sash": "#c9a24a", "shoes": "#4a3320", "props": _BEARD("#241d18"), "collar": None},
 "monk_warrior": {"hair": "#e6c6a2", "top": "#b8601f", "bottom": {"kind": "robe", "color": "#b8601f"}, "sash": "#5a2a12", "shoes": "#6a4a2a", "expr": "stern", "props": _BEADS + _STAFF, "collar": None},
 # fantasy / mythic
 "archer": {"hair": "#5a3a1e", "hair_style": "pony", "top": "#4a6a3a", "buttons": "#7a5a3a", "bottom": {"kind": "shorts", "color": "#3a4a2a"}, "shoes": "#4a3320", "props": _BOW, "collar": None},
 "ranger": {"hair": "#3a2c22", "top": "#3f5a3a", "buttons": "#6a5236", "bottom": {"kind": "shorts", "color": "#4a4030"}, "shoes": "#3a2a1a", "expr": "stern", "props": _BOW, "collar": None},
 "orc": {"skin": "#7fae6a", "hair": "#2a2018", "top": "#6a4a2a", "buttons": "#3a2a1a", "bottom": {"kind": "shorts", "color": "#4a3a24"}, "shoes": "#2a2018", "expr": "angry", "props": _TUSKS, "collar": None},
 "demon": {"skin": "#c05a4a", "hair": "#241014", "hair_style": "spiky", "eye": "#e8c53a", "top": "#2a1218", "bottom": {"kind": "robe", "color": "#3a1620"}, "sash": "#7a1420", "shoes": "#1a0c10", "expr": "angry", "props": _HORNS, "collar": None},
 "angel": {"skin": "#f6dcc0", "hair": "#f2e6b8", "hair_style": "long", "top": "#f4f2ec", "bottom": {"kind": "gown", "color": "#f4f2ec"}, "sash": "#e8d48a", "shoes": "#d8cf9a", "props": _HALO, "collar": None},
 "fairy": {"skin": "#f6dcc0", "hair": "#e58aa0", "hair_style": "twin", "top": "#b25a9a", "bottom": {"kind": "dress", "color": "#d47ab0"}, "sash": "#f2c94c", "shoes": "#a04a7a", "props": _HALO, "collar": None},
 "pirate": {"skin": "#e6b58a", "hair": "#241d18", "top": "#7a2a2a", "buttons": "#c9a24a", "bottom": {"kind": "shorts", "color": "#3a2a24"}, "shoes": "#3a2418", "expr": "stern", "props": _TRICORN + _EYEPATCH, "collar": None},
 "bard": {"hair": "#7a4a2a", "hair_style": "curly", "top": "#8a3a7a", "buttons": "#e8c53a", "bottom": {"kind": "shorts", "color": "#3a4a7a"}, "shoes": "#5a3a2a", "props": _LUTE, "collar": None},
 # modern professions
 "doctor": {"hair": "#2a2622", "top": "#f4f6f8", "buttons": "#b0c4d4", "bottom": {"kind": "shorts", "color": "#2a3546"}, "shoes": "#e8e8ea", "collar": "#dfe8f0"},
 "police": {"hair": "#241d18", "top": "#2a3550", "buttons": "#c9c24a", "bottom": {"kind": "shorts", "color": "#20283a"}, "shoes": "#141620", "expr": "stern", "collar": "#1a2030"},
 "firefighter": {"skin": "#e6b58a", "hair": "#2a2622", "top": "#c0392b", "buttons": "#e8c53a", "bottom": {"kind": "shorts", "color": "#8a2a20"}, "shoes": "#241010", "expr": "stern", "collar": None},
 "farmer": {"skin": "#e0b088", "hair": "#3a2c22", "top": "#7a8f5a", "bottom": {"kind": "shorts", "color": "#6a5a3a"}, "shoes": "#4a3320", "hat": "straw", "collar": None},
 "detective": {"hair": "#241d18", "top": "#3a4250", "buttons": "#2a323e", "bottom": {"kind": "shorts", "color": "#2a303a"}, "shoes": "#241a14", "expr": "stern", "props": _FEDORA, "collar": None},
 "maid": {"hair": "#3a2c22", "hair_style": "bob", "top": "#2a2a30", "apron": "#f4f4f6", "collar": "#fff", "bottom": {"kind": "dress", "color": "#2a2a30"}, "shoes": "#1a1a1e"},
 "robot": {"skin": "#c4c9d0", "hair": "#8a9098", "hair_style": "short", "eye": "#4fd8e6", "top": "#6a7078", "buttons": "#3a6ea5", "bottom": {"kind": "shorts", "color": "#5a606a"}, "shoes": "#3a3e46", "props": _ANTENNA, "collar": None},
}

# gender defaults for gender-neutral archetypes (hairstyle + dress bottom for female)
_FEMALE_STYLE = {"student", "office_worker", "teacher", "nurse", "businessman", "ceo", "idol", "child",
                 "doctor", "police", "detective", "archer", "ranger", "bard", "merchant", "farmer", "robot"}


def preset(archetype: str, region: str = "", genre: str = "", gender: str = "") -> dict:
    """Return svg_char.build_char opts for a character. Merges everyman + archetype + region
    skin + a light gender tweak. Unknown archetype → everyman. Never raises."""
    try:
        a = (archetype or "").strip().lower().replace(" ", "_").replace("-", "_")
        o = dict(_EVERYMAN)
        o["skin"] = _REGION_SKIN.get((region or "").strip().lower(), o.get("skin", "#f6cda6"))
        ov = _ARCH.get(a)
        if ov:
            for k, v in ov.items():
                if v is None:
                    o.pop(k, None)          # explicit clear (e.g. drop collar on a robe)
                else:
                    o[k] = v
        elif (gender or "").strip().lower() == "female" or a in _FEMALE_STYLE:
            pass  # fall through to gender tweak below
        # gender tweak for gender-neutral archetypes only (skip if archetype fixed a gown/robe)
        g = (gender or "").strip().lower()
        b = o.get("bottom") or {}
        if g == "female" and (not ov or a in _FEMALE_STYLE) and b.get("kind") in (None, "shorts"):
            o.setdefault("hair", "#6b4a2e")
            o["hair_style"] = "long"
            o["bottom"] = {"kind": "dress", "color": (o.get("top") or "#e7b7c2")}
            o.pop("collar", None)
        return o
    except Exception:
        return dict(_EVERYMAN)


__all__ = ["preset"]
