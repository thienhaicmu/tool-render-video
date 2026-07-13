"""
story_poster.py — procedural SVG cover/poster for a Story video (thumbnail).

Composes a designed cover for the finished video: the hero key-visual (the first
hook beat's visual, else the first visual) rendered as a procedural SVG (offline, $0),
with the story TOPIC burned across the lower third via the shared FFmpeg drawtext font
pipeline (Vietnamese/Unicode-safe). Used as the History thumbnail + saved beside the
video. Best-effort — returns None on any failure so finalize falls back to a frame grab.
"""
from __future__ import annotations

import hashlib
import logging
import subprocess
from pathlib import Path
from typing import Optional

from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.encoder.encoder_helpers import safe_filter_path
from app.features.render.engine.overlay.text_overlay import (
    _fontfile_for_family, _wrap_text_for_drawtext, get_text_overlay_temp_dir,
)

logger = logging.getLogger("app.render.story")


def _hero_visual(plan):
    """The visual to feature on the cover: the first HOOK beat's visual, else the first
    visual. None when the plan has no visuals."""
    for b in getattr(plan, "timeline", []):
        if getattr(b, "hook", False) and getattr(b, "visual_id", ""):
            v = plan.visual(b.visual_id)
            if v is not None:
                return v
    vis = getattr(plan, "visuals", None) or []
    return vis[0] if vis else None


def _title_drawtext(title: str, width: int, height: int) -> str:
    """Build ONE drawtext filter that burns the title across the lower third (via a
    textfile so Vietnamese / quotes never need inline escaping). "" on failure."""
    try:
        t = (title or "").strip()
        if not t:
            return ""
        fs = max(28, int(height * 0.075))
        wrapped = _wrap_text_for_drawtext(t, fs, width * 0.86)
        digest = hashlib.sha1(wrapped.encode("utf-8", errors="replace")).hexdigest()[:12]
        tfile = get_text_overlay_temp_dir() / f"story_poster_{digest}.txt"
        tfile.write_text(wrapped, encoding="utf-8", newline="\n")
        opts = [f"textfile='{safe_filter_path(str(tfile))}'"]
        font = _fontfile_for_family("Anton", bold=True)
        if font:
            opts.append(f"fontfile='{safe_filter_path(font)}'")
        opts += [
            "fontcolor=white", f"fontsize={fs}",
            "box=1", "boxcolor=black@0.55", f"boxborderw={max(10, int(fs * 0.35))}",
            "borderw=2", "bordercolor=black@0.9", "line_spacing=8",
            "x=(w-text_w)/2", "y=h*0.76",
        ]
        return "drawtext=" + ":".join(opts)
    except Exception as exc:
        logger.info("story_poster: title drawtext failed %s", exc)
        return ""


def compose_story_poster(plan, out_path: str, width: int = 1280, height: int = 720) -> Optional[str]:
    """Compose the SVG cover → a JPEG at ``out_path``. Returns the path or None. Never
    raises. The hero visual is composed WITH characters (a richer cover than the
    background-only key-visual), then the topic is burned across the lower third."""
    try:
        hero = _hero_visual(plan)
        if hero is None:
            return None
        from app.features.render.engine.visual.svg_compose import compose_visual
        from app.features.render.engine.visual.svg_raster import render_svg
        svg = compose_visual(plan, hero, width, height, chars=True)
        png = render_svg(svg, width, height, opaque_bg="#101820") if svg else None
        if not png:
            return None
        base = Path(str(out_path) + ".base.png")
        base.write_bytes(png)
        vf = f"scale={width}:{height}"
        dt = _title_drawtext(getattr(plan, "topic", "") or "", width, height)
        if dt:
            vf += "," + dt
        cmd = [get_ffmpeg_bin(), "-y", "-i", str(base), "-vf", vf,
               "-frames:v", "1", "-q:v", "3", str(out_path)]
        r = subprocess.run(cmd, capture_output=True, timeout=60)
        try:
            base.unlink()
        except Exception:
            pass
        p = Path(out_path)
        if r.returncode == 0 and p.exists() and p.stat().st_size > 0:
            return str(out_path)
        logger.info("story_poster: ffmpeg burn failed rc=%s", r.returncode)
        return None
    except subprocess.TimeoutExpired:
        logger.info("story_poster: ffmpeg timeout")
        return None
    except Exception as exc:
        logger.info("story_poster: compose failed %s", exc)
        return None


__all__ = ["compose_story_poster"]
