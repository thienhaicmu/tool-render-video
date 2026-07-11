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
}

# gender defaults for gender-neutral archetypes (hairstyle + dress bottom for female)
_FEMALE_STYLE = {"student", "office_worker", "teacher", "nurse", "businessman", "ceo", "idol", "child"}


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
