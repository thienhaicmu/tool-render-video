"""
pipeline_subtitle_utils.py — Subtitle and SRT file operations.

Extracted from pipeline_helpers.py. All functions operate on .srt / .ass files
or subtitle-related configuration. No pipeline state dependencies.
"""

import logging
import re as _re
from pathlib import Path

from app.services.subtitle_engine import parse_srt_blocks, write_srt_blocks

logger = logging.getLogger("app.render")

# Mapping from aspect_ratio string → ASS PlayResY value.
_PLAY_RES_Y_MAP: dict[str, int] = {
    "9:16": 1920, "1:1": 1080, "3:4": 1440, "4:5": 1440, "16:9": 1080,
}


def _aspect_play_res_y(aspect_ratio: str) -> int:
    ar = (aspect_ratio or "").strip()
    val = _PLAY_RES_Y_MAP.get(ar)
    if val is None:
        logger.warning("_aspect_play_res_y: unrecognised aspect_ratio=%r, defaulting to 1440", ar)
        return 1440
    return val


def _read_srt_meta(srt_path: str) -> dict:
    """Read timing metadata from an existing per-part SRT — mirrors slice_srt_by_time return shape.

    Used on the resume path (needs_srt=False) so CTA and logging have correct timestamps.
    """
    try:
        blocks = parse_srt_blocks(srt_path)
        if not blocks:
            return {"subtitle_count": 0, "first_start": None, "first_end": None,
                    "last_start": None, "last_end": None}
        return {
            "subtitle_count": len(blocks),
            "first_start": blocks[0]["start"],
            "first_end":   blocks[0]["end"],
            "last_start":  blocks[-1]["start"],
            "last_end":    blocks[-1]["end"],
        }
    except Exception:
        return {}


def _append_cta_block_to_srt(
    srt_path: str, cta_text: str, after_sec: float, clip_end_sec: float
) -> bool:
    """Append a CTA subtitle block to an existing SRT file. Returns True on success."""
    try:
        blocks = parse_srt_blocks(srt_path)
        if not blocks:
            return False
        cta_start = max(float(after_sec) + 0.3, float(clip_end_sec) - 3.0)
        cta_end = min(cta_start + 2.5, float(clip_end_sec) - 0.1)
        if cta_end <= cta_start or cta_start >= float(clip_end_sec):
            return False
        blocks.append({"start": cta_start, "end": cta_end, "text": cta_text})
        write_srt_blocks(blocks, srt_path)
        return True
    except Exception:
        return False


def _apply_subtitle_edits_to_srt(srt_path: str, edits: list) -> None:
    """Patch specific SRT blocks in-place with user-supplied text.

    Matches by index (0-based segment position in file).  For each edit,
    verifies that the block's start-time is within 0.5 s of the stored value
    to guard against offset drift.  On any mismatch or error the edit is
    silently skipped and the original block is preserved.
    """
    if not edits:
        return
    edit_map = {}
    for e in edits:
        try:
            edit_map[int(e['index'])] = e
        except (KeyError, TypeError, ValueError):
            pass
    if not edit_map:
        return

    _srt_ts_re = _re.compile(
        r'(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})'
    )

    def _ts_to_sec(h, m, s, ms):
        return int(h)*3600 + int(m)*60 + int(s) + int(ms)/1000.0

    try:
        raw = Path(srt_path).read_text(encoding='utf-8', errors='replace')
    except Exception:
        return

    blocks = _re.split(r'\n{2,}', raw.strip())
    changed = False
    out_blocks = []
    for blk_idx, blk in enumerate(blocks):
        lines = blk.strip().splitlines()
        if blk_idx in edit_map and len(lines) >= 3:
            edit = edit_map[blk_idx]
            ts_match = _srt_ts_re.search(blk)
            if ts_match:
                blk_start = _ts_to_sec(*ts_match.groups()[:4])
                try:
                    expected_start = float(edit.get('start', blk_start))
                except (TypeError, ValueError):
                    expected_start = blk_start
                if abs(blk_start - expected_start) <= 0.5:
                    seq_line = lines[0]
                    ts_line  = lines[1]
                    new_blk  = f"{seq_line}\n{ts_line}\n{str(edit['text']).strip()}"
                    out_blocks.append(new_blk)
                    changed = True
                    continue
        out_blocks.append(blk)

    if changed:
        try:
            Path(srt_path).write_text('\n\n'.join(out_blocks) + '\n', encoding='utf-8')
        except Exception as exc:
            logger.warning("subtitle_edits: failed to write patched SRT (%s): %s", srt_path, exc)
