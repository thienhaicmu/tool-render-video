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
from pathlib import Path
from typing import Optional

from app.core.config import APP_DATA_DIR
from app.features.render.engine.visual.story_image import generate_image_bytes

logger = logging.getLogger("app.render.visual.story_ref_sheet")

# Durable asset store (shared with Content's pinned assets — never pruned).
_ASSETS_DIR = Path(APP_DATA_DIR) / "content_assets"


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
        # Content-addressed cache: same subject+style+size → same file → generate once.
        _key = hashlib.sha1(f"{subject}|{style}|{width}x{height}".encode("utf-8", "ignore")).hexdigest()[:12]
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
        data = generate_image_bytes(prompt, width, height, quality="high")
        if not data:
            return None
        dst.write_bytes(data)
        if not (dst.exists() and dst.stat().st_size > 0):
            return None
        return str(dst)
    except Exception as exc:
        logger.info("story_ref_sheet: generation error %s", exc)
        return None


__all__ = ["generate_character_reference_sheet"]
