"""
story_reference_sheet.py — Character Reference Sheet generation (P3).

Generates a canonical "reference sheet" image for a Story Bible character ONCE
(front view + neutral background) from its canonical description. The result is
pinned as a durable asset (APP_DATA_DIR/content_assets, never pruned) and its path
is stored on the character (characters.reference_image_path) so EVERY later shot
feeds it to gpt-image-1's image-edit endpoint → the character looks the same
across the whole video / series.

Reuses story_image.generate_image_bytes. Opt-in + graceful: None on no key / no
SDK / error. Never raises (Sacred Contract #3 spirit).
"""
from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from typing import Optional

from app.core.config import APP_DATA_DIR
from app.features.render.engine.visual.story_image import generate_image_bytes

logger = logging.getLogger("app.render.visual.story_ref_sheet")

# Durable asset store (shared with Content's pinned assets — never pruned).
_ASSETS_DIR = Path(APP_DATA_DIR) / "content_assets"

# gpt-image-1 quality tiers a reference sheet may use.
_REFSHEET_TIERS = ("low", "medium", "high", "auto")


def _refsheet_quality() -> str:
    """gpt-image-1 quality tier for reference sheets (C3 cost knob). Reference sheets
    are INTERNAL conditioning images (fed to image-edit), not final output, so their
    tier is env-tunable via ``STORY_REFSHEET_QUALITY``. Default ``high`` preserves the
    historical behaviour (and the byte-identical cache key). Never raises."""
    q = (os.getenv("STORY_REFSHEET_QUALITY", "high") or "high").strip().lower()
    return q if q in _REFSHEET_TIERS else "high"


def _safe_cid(character) -> str:
    cid = (getattr(character, "id", "") or getattr(character, "name", "") or "char").strip().lower()
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in cid)[:40] or "char"


def generate_character_reference_sheet(
    character,
    art_style: str = "",
    width: int = 1024,
    height: int = 1024,
) -> Optional[str]:
    """Generate a reference sheet for a character → a durable PNG path, or None on no
    key / no usable description / error. Never raises.

    Accepts BOTH the v1 StoryCharacter (``.description``) and the v2 CharacterDef
    (``.canonical_desc``). Content-addressed: the file name hashes (subject, style,
    size), so an identical character across renders REUSES the sheet (no re-gen, no
    extra gpt-image-1 cost). The prompt asks for a neutral, well-lit character study."""
    try:
        desc = (getattr(character, "description", "") or getattr(character, "canonical_desc", "") or "").strip()
        name = (getattr(character, "name", "") or "").strip()
        subject = desc or name
        if not subject:
            return None
        style = (art_style or "").strip() or "cinematic"
        quality = _refsheet_quality()
        # Non-default tiers namespace the cache so a cheaper sheet never masquerades as
        # a "high" one; the default "high" keeps the historical key (no regen, no cost).
        _qtag = "" if quality == "high" else f"|{quality}"
        # Content-addressed cache: same subject+style+size(+tier) → same file → generate once.
        _key = hashlib.sha1(f"{subject}|{style}|{width}x{height}{_qtag}".encode("utf-8", "ignore")).hexdigest()[:12]
        _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        dst = _ASSETS_DIR / f"refsheet_{_safe_cid(character)}_{_key}.png"
        if dst.exists() and dst.stat().st_size > 0:
            return str(dst)                     # cache hit — no API call
        prompt = (
            f"Character reference sheet of {subject}. "
            f"Front-facing full-body view and a face close-up, neutral grey studio "
            f"background, even lighting, consistent design, {style} style. "
            f"Clean reference art, no text, no watermark."
        )
        data = generate_image_bytes(prompt, width, height, quality=quality)
        if not data:
            return None
        dst.write_bytes(data)
        if not (dst.exists() and dst.stat().st_size > 0):
            return None
        return str(dst)
    except Exception as exc:
        logger.info("story_ref_sheet: generation error %s", exc)
        return None


def generate_environment_reference_sheet(
    setting,
    art_style: str = "",
    width: int = 1536,
    height: int = 1024,
) -> Optional[str]:
    """Generate a canonical ESTABLISHING reference view of a setting/location → a
    durable PNG path, or None on no key / no description / error. Never raises (G6).

    Accepts the v2 SettingDef (``.canonical_desc``/``.name``). Content-addressed
    (subject, style, size, tier) with an ``env|`` namespace so it never collides with
    a character sheet — an identical location across renders REUSES the sheet. The
    prompt asks for a wide, people-free establishing shot so later scenes can condition
    on it for a consistent location. Tier follows the STORY_REFSHEET_QUALITY knob."""
    try:
        desc = (getattr(setting, "canonical_desc", "") or getattr(setting, "description", "") or "").strip()
        name = (getattr(setting, "name", "") or "").strip()
        subject = desc or name
        if not subject:
            return None
        style = (art_style or "").strip() or "cinematic"
        quality = _refsheet_quality()
        _qtag = "" if quality == "high" else f"|{quality}"
        _key = hashlib.sha1(
            f"env|{subject}|{style}|{width}x{height}{_qtag}".encode("utf-8", "ignore")).hexdigest()[:12]
        _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        dst = _ASSETS_DIR / f"envsheet_{_safe_cid(setting)}_{_key}.png"
        if dst.exists() and dst.stat().st_size > 0:
            return str(dst)                     # cache hit — no API call
        prompt = (
            f"Establishing reference view of the location: {subject}. "
            f"Wide cinematic establishing shot, no people, consistent architecture and "
            f"mood, {style} style. Clean reference art, no text, no watermark."
        )
        data = generate_image_bytes(prompt, width, height, quality=quality)
        if not data:
            return None
        dst.write_bytes(data)
        if not (dst.exists() and dst.stat().st_size > 0):
            return None
        return str(dst)
    except Exception as exc:
        logger.info("story_ref_sheet: env generation error %s", exc)
        return None


__all__ = ["generate_character_reference_sheet", "generate_environment_reference_sheet"]
