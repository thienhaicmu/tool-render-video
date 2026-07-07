"""
context.py — ContentRenderContext + shared helpers for the Content-Mode render
stages (CM-6 decomposition of content_pipeline.run_content).

``ContentRenderContext`` gathers the render-invariant parameters (paths, canvas,
voice, subtitle policy, cancel probe) so the per-scene / assembly / finalize
stage functions take a single ``ctx`` instead of ~15 closure-captured locals.
Pure data + two pure helpers — no I/O, no import of content_pipeline (so the
stage modules import from here without a cycle).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

_FS_ILLEGAL_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def stable_seed(key: str) -> int:
    """CU-11 — a stable 31-bit seed from a key (character id / style) so the same
    subject reproduces a consistent look across scenes. 0 for an empty key."""
    key = (key or "").strip().lower()
    if not key:
        return 0
    return int(hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:8], 16) & 0x7FFFFFFF


def safe_filename(name: str, max_len: int = 120) -> str:
    """Make an AI-authored title/topic safe to use as a filename stem. Strips
    illegal chars, collapses whitespace, trims trailing dots/spaces (Windows),
    caps length. Returns '' if nothing usable survives. Never raises."""
    try:
        s = _FS_ILLEGAL_RE.sub(" ", str(name or ""))
        s = re.sub(r"\s+", " ", s).strip().strip(".").strip()
        if len(s) > max_len:
            s = s[:max_len].rsplit(" ", 1)[0].strip() or s[:max_len].strip()
        return s
    except Exception:
        return ""


@dataclass
class ContentRenderContext:
    """Render-invariant parameters shared by the Content-Mode stage functions.

    Carries the "how / where" of the render; the "what" (the ContentPlan and the
    per-scene provider choice) is passed to the stage functions separately."""
    job_id: str
    effective_channel: str
    scenes_dir: Path
    width: int
    height: int
    fps: float
    sample_rate: int
    language: str
    gender: str
    voice_id: Optional[str]
    tts_engine: str
    add_subtitle: bool
    word_by_word: bool
    visual_provider: str
    bg_kind: str
    bg_value: str
    imagen_tier: str
    subtitle_pick: str            # payload.subtitle_style — the user's UI choice
    cancel_cb: Callable[[], bool]
