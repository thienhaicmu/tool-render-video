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

import logging
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import APP_DATA_DIR
from app.features.render.engine.visual.story_image import generate_image_bytes

logger = logging.getLogger("app.render.visual.story_ref_sheet")

# Durable asset store (shared with Content's pinned assets — never pruned).
_ASSETS_DIR = Path(APP_DATA_DIR) / "content_assets"


def generate_character_reference_sheet(
    character,
    art_style: str = "",
    width: int = 1024,
    height: int = 1024,
) -> Optional[str]:
    """Generate a reference sheet for a StoryCharacter → a durable PNG path, or
    None on no key / no usable description / error. Never raises.

    The prompt asks for a neutral, well-lit character study so the sheet is a clean
    reference for later image-edit conditioning."""
    try:
        desc = (getattr(character, "description", "") or "").strip()
        name = (getattr(character, "name", "") or "").strip()
        subject = desc or name
        if not subject:
            return None
        style = (art_style or "").strip() or "cinematic"
        prompt = (
            f"Character reference sheet of {subject}. "
            f"Front-facing full-body view and a face close-up, neutral grey studio "
            f"background, even lighting, consistent design, {style} style. "
            f"Clean reference art, no text, no watermark."
        )
        data = generate_image_bytes(prompt, width, height, quality="high")
        if not data:
            return None
        _ASSETS_DIR.mkdir(parents=True, exist_ok=True)
        cid = (getattr(character, "id", "") or getattr(character, "name", "") or "char").strip().lower()
        cid = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in cid)[:40] or "char"
        dst = _ASSETS_DIR / f"refsheet_{cid}_{uuid.uuid4().hex[:8]}.png"
        dst.write_bytes(data)
        if not (dst.exists() and dst.stat().st_size > 0):
            return None
        return str(dst)
    except Exception as exc:
        logger.info("story_ref_sheet: generation error %s", exc)
        return None


__all__ = ["generate_character_reference_sheet"]
