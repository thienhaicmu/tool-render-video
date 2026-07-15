"""
look_spec.py — CharacterLook: the visual IDENTITY of one character (GĐ2).

A look is everything that makes two characters distinguishable on screen: skin /
hair colour + style / eye colour / outfit + its palette / age build / accessories.
``derive_look(seed=...)`` fills every unset field DETERMINISTICALLY from a seed, so
the same character id always yields the same figure (identity stability — the GĐ3
identity-lock stores exactly this dict).

Pure + defensive: no I/O; every helper tolerates junk and falls back to defaults.
"""
from __future__ import annotations

import hashlib
import random
from dataclasses import asdict, dataclass, field

# ── Curated palettes (flat-anime friendly) ────────────────────────────────────
SKIN_TONES = ("#ffe3c9", "#f8d5b0", "#edbf98", "#d9a06f", "#b97d4e")
HAIR_COLORS = (
    "#26221f", "#3a2c24", "#4a352a", "#6b4a33", "#8a5a3a",   # black → chestnut
    "#d9b26a", "#e8dcc0",                                     # blonde / platinum
    "#9a9a9a", "#e8e6e2",                                     # gray / white (elder)
    "#a34029", "#7e3b2a",                                     # red / auburn
    "#3a5a8c", "#2e7d74", "#d97ba6", "#6a4a8c", "#4a7c4e",   # anime blue/teal/pink/violet/green
)
EYE_COLORS = ("#4a3524", "#2e2620", "#3a5a8c", "#2e7d5a", "#6a4a8c", "#8c5a2e", "#708090", "#a34029")

HAIR_BACK = ("short", "bob", "long", "ponytail", "twin_tails", "bun", "topknot")
HAIR_FRONT = ("flat", "side", "curtain", "spiky", "wavy")
OUTFITS = ("school_uniform", "office_suit", "doctor_coat", "police_uniform",
           "engineer_workwear", "tee_casual", "hoodie", "dress", "hanfu_robe",
           "kimono", "armor_light", "coat_long", "apron_staff")
AGES = ("child", "adult", "elder")
GENDERS = ("male", "female")
ACCESSORIES = ("glasses", "beard", "hairband", "earrings")

# Outfit → sensible primary/secondary palettes (seeded pick keeps combos coherent).
_OUTFIT_PALETTES: "dict[str, tuple]" = {
    "school_uniform": (("#2e3a55", "#f4f4f6"), ("#3a2e4a", "#eef0f4"), ("#20303e", "#f6f2e8")),
    "office_suit":    (("#2f3b52", "#bcd0e6"), ("#3a3d44", "#e8e8ea"), ("#4a3a3a", "#e6dfd4")),
    "doctor_coat":    (("#f2f5f7", "#5c9cac"), ("#eef2f4", "#77a9a0"), ("#f6f3ee", "#7192b2")),
    "police_uniform": (("#243b5a", "#dce6f0"), ("#283747", "#e5e8ec"), ("#304861", "#d7e1e9")),
    "engineer_workwear": (("#335b72", "#e68a32"), ("#475d4d", "#e6c74a"), ("#5b626b", "#66a8c7")),
    "tee_casual":     (("#c0563a", "#3a4256"), ("#3a7c6a", "#2a3040"), ("#d9a23a", "#33415c")),
    "hoodie":         (("#5a6a78", "#2a3040"), ("#7a4a5a", "#2e2633"), ("#3d5a4a", "#242e28")),
    "dress":          (("#d4607a", "#f2d9df"), ("#5a7ab5", "#dfe8f4"), ("#7a5aa0", "#e8dff2")),
    "hanfu_robe":     (("#eef0f4", "#4a7c9c"), ("#a6301f", "#e8c53a"), ("#2a3a5c", "#c9d6e8")),
    "kimono":         (("#c62b5a", "#e8c53a"), ("#3a5a8c", "#e8e0d0"), ("#4a6741", "#e8d9b0")),
    "armor_light":    (("#8f96a3", "#5a616e"), ("#7a6a4a", "#4a4032"), ("#6e7a8f", "#3d4552")),
    "coat_long":      (("#4a4038", "#2e2620"), ("#3a4250", "#252a33"), ("#5c4a3a", "#332a22")),
    "apron_staff":    (("#f3ead6", "#9c6b3f"), ("#eef0f4", "#5a7a6a"), ("#f6e8d9", "#8a4a3a")),
}


@dataclass
class CharacterLook:
    gender: str = "female"          # ∈ GENDERS
    age: str = "adult"              # ∈ AGES
    skin: str = ""
    hair_color: str = ""
    eye_color: str = ""
    hair_back: str = ""             # ∈ HAIR_BACK
    hair_front: str = ""            # ∈ HAIR_FRONT
    outfit: str = ""                # ∈ OUTFITS
    outfit_primary: str = ""
    outfit_secondary: str = ""
    accent: str = ""                # small pops: tie / ribbon / trim
    accessories: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _pick(rng: random.Random, seq):
    return seq[rng.randrange(len(seq))]


def _norm(v: str, allowed, default: str) -> str:
    v = (v or "").strip().lower()
    return v if v in allowed else default


def stable_seed(text: str) -> int:
    try:
        return int(hashlib.sha1((text or "").encode("utf-8", "ignore")).hexdigest()[:8], 16)
    except Exception:
        return 0


def derive_look(seed: "int | str" = 0, *, gender: str = "", age: str = "",
                outfit: str = "", base: "dict | None" = None) -> CharacterLook:
    """Deterministically fill a full CharacterLook from ``seed``. Explicit args and
    any fields already set in ``base`` WIN over the seeded picks (so a stored /
    user-edited look is never overridden). Never raises."""
    try:
        s = stable_seed(seed) if isinstance(seed, str) else int(seed or 0)
        rng = random.Random(s)
        b = dict(base or {})
        g = _norm(gender or b.get("gender", ""), GENDERS, _pick(rng, GENDERS))
        a = _norm(age or b.get("age", ""), AGES, "adult")
        look = CharacterLook(gender=g, age=a)
        look.skin = b.get("skin") or _pick(rng, SKIN_TONES[:4] if a != "elder" else SKIN_TONES[1:4])
        if a == "elder":
            look.hair_color = b.get("hair_color") or _pick(rng, ("#9a9a9a", "#e8e6e2", "#c9c4bd"))
        else:
            look.hair_color = b.get("hair_color") or _pick(rng, HAIR_COLORS)
        look.eye_color = b.get("eye_color") or _pick(rng, EYE_COLORS)
        if g == "female":
            look.hair_back = _norm(b.get("hair_back", ""), HAIR_BACK,
                                   _pick(rng, ("bob", "long", "ponytail", "twin_tails", "bun", "long")))
            look.hair_front = _norm(b.get("hair_front", ""), HAIR_FRONT,
                                    _pick(rng, ("flat", "side", "curtain", "wavy")))
        else:
            look.hair_back = _norm(b.get("hair_back", ""), HAIR_BACK,
                                   _pick(rng, ("short", "short", "topknot", "ponytail", "bob")))
            look.hair_front = _norm(b.get("hair_front", ""), HAIR_FRONT,
                                    _pick(rng, ("flat", "side", "spiky", "curtain")))
        look.outfit = _norm(outfit or b.get("outfit", ""), OUTFITS, _pick(rng, OUTFITS[:5]))
        pal = _OUTFIT_PALETTES.get(look.outfit, (("#5a6a78", "#2a3040"),))
        p1, p2 = _pick(rng, pal)
        look.outfit_primary = b.get("outfit_primary") or p1
        look.outfit_secondary = b.get("outfit_secondary") or p2
        look.accent = b.get("accent") or _pick(rng, ("#c0392b", "#e8c53a", "#3a7c6a", "#5a7ab5", "#d4607a"))
        acc = list(b.get("accessories") or [])
        if a == "elder" and g == "male" and "beard" not in acc:
            acc.append("beard")
        if not acc and rng.random() < 0.22:
            pool = ("glasses", "hairband", "earrings") if g == "female" else ("glasses",)
            acc.append(_pick(rng, pool))
        look.accessories = [x for x in acc if x in ACCESSORIES]
        return look
    except Exception:
        return CharacterLook(skin=SKIN_TONES[1], hair_color=HAIR_COLORS[0], eye_color=EYE_COLORS[0],
                             hair_back="short", hair_front="flat", outfit="tee_casual",
                             outfit_primary="#c0563a", outfit_secondary="#3a4256", accent="#e8c53a")


def shade(hex_color: str, f: float = 0.78) -> str:
    """Darken (f<1) / lighten (f>1) a #rrggbb colour. Defensive."""
    try:
        h = (hex_color or "").lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        if f <= 1:
            r, g, b = int(r * f), int(g * f), int(b * f)
        else:
            r = min(255, int(r + (255 - r) * (f - 1)))
            g = min(255, int(g + (255 - g) * (f - 1)))
            b = min(255, int(b + (255 - b) * (f - 1)))
        return f"#{r:02x}{g:02x}{b:02x}"
    except Exception:
        return hex_color or "#888888"


__all__ = ["CharacterLook", "derive_look", "shade", "stable_seed",
           "SKIN_TONES", "HAIR_COLORS", "EYE_COLORS", "HAIR_BACK", "HAIR_FRONT",
           "OUTFITS", "AGES", "GENDERS", "ACCESSORIES"]
