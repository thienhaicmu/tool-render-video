"""
story_reference_sheet.py — procedural SVG character master (SVG-only Story Mode).

Story Mode is SVG-only: a character's overlay "master" (cutout-ready, transparent
full-body figure) is composed procedurally from its archetype/gender via the chibi
builder — offline, $0, deterministic. This replaces the former gpt-image-1 reference
sheet / environment sheet / transparent master (all removed with the paid image path).

Content-addressed + cached in the durable asset store (never pruned) so an identical
character reuses its master across the whole video / series. Best-effort: None on any
failure — never raises (Sacred Contract #3 spirit).
"""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from app.core.config import APP_DATA_DIR
from app.features.render.engine.visual.svg_char import build_char
from app.features.render.engine.visual.svg_presets import preset
from app.features.render.engine.visual.svg_raster import save_svg_png

logger = logging.getLogger("app.render.visual.story_ref_sheet")

# Durable asset store (shared with Content's pinned assets — never pruned).
_ASSETS_DIR = Path(APP_DATA_DIR) / "content_assets"

# Poses a "regenerate" (variant>0) rotates through so the user gets a different look.
_VARIANT_POSES = ("stand", "wave", "cheer", "point", "hip")


def _safe_cid(character) -> str:
    cid = (getattr(character, "id", "") or getattr(character, "name", "") or "char").strip().lower()
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in cid)[:40] or "char"


def generate_character_master(
    character,
    art_style: str = "",
    width: int = 1024,
    height: int = 1536,
    variant: int = 0,
    *,
    region: str = "",
    genre: str = "",
) -> Optional[str]:
    """Compose a cutout-ready transparent CHARACTER MASTER (procedural chibi SVG) →
    a durable PNG-with-alpha path, or None on failure. Never raises.

    Derives the look from the character's ``archetype`` + gender (+ optional
    ``region``/``genre`` for a market-appropriate palette). Portrait 1024x1536 gives
    head-to-toe headroom. Content-addressed with a ``master|`` namespace so ONE master
    per character (variant/pose) is reused across renders. ``variant`` (A5 approval/lock):
    0 = the canonical stand pose; >0 rotates the pose so a Review "regenerate" yields a
    different look for the user to pick/lock. ``art_style`` is accepted for call-site
    compatibility but unused (the chibi style is fixed)."""
    try:
        arch = (getattr(character, "archetype", "") or "").strip()
        gender = (getattr(character, "gender", "") or getattr(character, "voice_gender", "") or "").strip()
        name = (getattr(character, "name", "") or "").strip()
        subject = arch or name or (getattr(character, "id", "") or "").strip()
        if not subject:
            return None
        _v = int(variant or 0)
        pose = _VARIANT_POSES[_v % len(_VARIANT_POSES)] if _v > 0 else "stand"
        _key = hashlib.sha1(
            f"master|{arch}|{gender}|{region}|{genre}|{name}|{pose}".encode("utf-8", "ignore")
        ).hexdigest()[:12]
        _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        dst = _ASSETS_DIR / f"master_{_safe_cid(character)}_{_key}.png"
        if dst.exists() and dst.stat().st_size > 0:
            return str(dst)                     # cache hit — no recompute
        opts = preset(arch, region, genre, gender)
        opts["pose"] = pose
        path = save_svg_png(build_char(opts), str(dst), width, height)  # transparent (no opaque_bg)
        if not path or not (dst.exists() and dst.stat().st_size > 0):
            return None
        return str(dst)
    except Exception as exc:
        logger.info("story_ref_sheet: SVG master generation error %s", exc)
        return None


__all__ = ["generate_character_master"]
