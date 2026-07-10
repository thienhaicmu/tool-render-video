"""
beat_render.py — render ONE cue of a Story v2 timeline to a clip (B7).

A cue (``domain.story_plan_v2.Cue``) is the deterministic unit the render walks:
one beat's window over one wide image, with a Ken Burns move (``crop_from`` →
``crop_to``) and the beat's narration audio. This module turns a cue into a single
self-contained MP4 (video + audio) so ``assemble_shots`` can xfade them together.

Ken Burns via ``zoompan``: the wide AI image (gpt-image-1 is 3:2 / 2:3) is first
COVER-cropped to the output aspect at 2× resolution (headroom so a zoom-in stays
sharp), then panned/zoomed. ``crop_*`` rects are equal-fraction (w==h) on that
aspect-correct frame, so the pan never distorts. CPU libx264 only — a Story clip
must never contend for an NVENC session (mirrors content_background policy).

Hook-title BURN-IN (upper third) uses the shared text_overlay font pipeline
(``cue.hook`` / ``cue.hook_text``). On-screen text is HOOK-ONLY by design — there is
no full-video subtitle track.

Sacred Contract #3 spirit: never raises; returns ``{clip, error, fallback}`` so one
bad cue degrades to a skipped/failed part, never aborts the whole render.
"""
from __future__ import annotations

import hashlib
import logging
import os
import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.encoder.encoder_helpers import safe_filter_path
from app.features.render.engine.overlay.text_overlay import (
    _fontfile_for_family, _wrap_text_for_drawtext, get_text_overlay_temp_dir,
)

logger = logging.getLogger("app.render.story")

_FFMPEG_TIMEOUT_SEC: int = max(120, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800")))
_SAMPLE_RATE = 48000

# Q4 — a cue clip is an INTERMEDIATE: the assembler re-encodes it through xfade
# (which cannot stream-copy). Encode cues near-lossless + fast so that SECOND pass
# is the only quality-defining step — this removes the double-encode quality loss
# without touching the shared assembler. Env-tunable; STORY_CUE_CRF=20 +
# STORY_CUE_PRESET=medium restores the pre-Q4 behaviour.
_CUE_CRF = (os.getenv("STORY_CUE_CRF", "15").strip() or "15")
_CUE_PRESET = (os.getenv("STORY_CUE_PRESET", "veryfast").strip() or "veryfast")


def _norm_color(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return "0x101820"
    if v.startswith("#"):
        hp = v[1:]
        if len(hp) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in hp):
            return "0x" + hp
        return "0x101820"
    return v


def _ok_file(p: "str | None") -> bool:
    try:
        return bool(p) and Path(p).exists() and Path(p).stat().st_size > 0
    except Exception:
        return False


def _kenburns_vf(crop_from, crop_to, width: int, height: int, fps: float, dur: float) -> str:
    """zoompan Ken Burns from crop_from→crop_to over ``dur`` on a cover-cropped 2×
    canvas. crop rects are (x, y, w, h) fractions with w==h (aspect-preserving)."""
    T = max(1, int(round(dur * fps)))
    den = max(1, T - 1)
    xf, yf, wf, hf = (float(crop_from[0]), float(crop_from[1]), float(crop_from[2]), float(crop_from[3]))
    xt, yt, wt, ht = (float(crop_to[0]), float(crop_to[1]), float(crop_to[2]), float(crop_to[3]))
    cxf, cxt = xf + wf / 2.0, xt + wt / 2.0        # crop centre (fraction)
    cyf, cyt = yf + hf / 2.0, yt + ht / 2.0
    s_expr = f"({wf:.5f}+({(wt - wf):.5f})*on/{den})"   # crop width fraction over time
    z_expr = f"(1/{s_expr})"                            # zoom = 1/fraction (≥1)
    cx_expr = f"({cxf:.5f}+({(cxt - cxf):.5f})*on/{den})"
    cy_expr = f"({cyf:.5f}+({(cyt - cyf):.5f})*on/{den})"
    x_expr = f"max(0,min(iw-iw/zoom,(iw*{cx_expr}-(iw/zoom/2))))"
    y_expr = f"max(0,min(ih-ih/zoom,(ih*{cy_expr}-(ih/zoom/2))))"
    W2, H2 = width * 2, height * 2
    return (
        f"scale={W2}:{H2}:force_original_aspect_ratio=increase:flags=lanczos,"
        f"crop={W2}:{H2},"
        f"zoompan=z='{z_expr}':x='{x_expr}':y='{y_expr}':d={T}:s={width}x{height}:fps={fps:.3f},"
        f"setsar=1,format=yuv420p"
    )


def _drawtext(text: str, width: int, height: int, *, fs: int, family: str, bold: bool,
              y: str, box_alpha: float, uniq: str = "") -> str:
    """Build ONE drawtext filter for ``text`` (via a textfile so Vietnamese / quotes /
    colons never need inline escaping). Centered horizontally; ``y`` is a drawtext
    expression. ``uniq`` (e.g. the cue's part_no) namespaces the textfile so two cues
    with IDENTICAL text can't race on the same file when rendered in parallel.
    Returns "" on any failure (never breaks the render)."""
    try:
        t = (text or "").strip()
        if not t:
            return ""
        wrapped = _wrap_text_for_drawtext(t, fs, width * 0.86)
        digest = hashlib.sha1(wrapped.encode("utf-8", errors="replace")).hexdigest()[:16]
        tfile = get_text_overlay_temp_dir() / f"story_cue_{uniq}{digest}.txt"
        tfile.write_text(wrapped, encoding="utf-8", newline="\n")
        opts = [f"textfile='{safe_filter_path(str(tfile))}'"]
        font = _fontfile_for_family(family, bold=bold)
        if font:
            opts.append(f"fontfile='{safe_filter_path(font)}'")
        opts += [
            "fontcolor=white", f"fontsize={fs}",
            "box=1", f"boxcolor=black@{box_alpha:.2f}", f"boxborderw={max(8, int(fs * 0.35))}",
            "borderw=2", "bordercolor=black@0.9", "line_spacing=8",
            "x=(w-text_w)/2", f"y={y}",
        ]
        return "drawtext=" + ":".join(opts)
    except Exception as exc:
        logger.warning("story overlay drawtext failed: %s", exc)
        return ""


def _overlay_suffix(cue, width: int, height: int, part_no: int = 0) -> str:
    """Filtergraph suffix (leading comma) that burns the cue's hook title (upper
    third). On-screen text is HOOK-ONLY — no full-video subtitle. "" when nothing to
    burn. ``part_no`` namespaces the drawtext textfiles so parallel cues never share
    a file."""
    try:
        parts: list[str] = []
        _u = f"{int(part_no):04d}_"
        if getattr(cue, "hook", False) and (getattr(cue, "hook_text", "") or "").strip():
            parts.append(_drawtext(
                cue.hook_text, width, height, fs=max(28, int(height * 0.060)),
                family="Anton", bold=True, y="h*0.10", box_alpha=0.55, uniq=_u + "h"))
        parts = [p for p in parts if p]
        return ("," + ",".join(parts)) if parts else ""
    except Exception:
        return ""


def render_one_cue(ctx, plan, part_no: int, cue) -> dict:
    """Render one ``Cue`` → an MP4 clip. Returns ``{clip, error, fallback}``.
    ``fallback`` True when the visual image was missing and a solid background was
    used instead. Never raises."""
    try:
        width, height, fps = int(ctx.width), int(ctx.height), float(ctx.fps)
        threads = int(getattr(ctx, "ffmpeg_threads", 0) or 0)   # >0 caps libx264 threads (parallel cues)
        dur = max(0.5, float(cue.end_sec) - float(cue.start_sec))
        img = plan.render.visual_assets.get(cue.visual_id)
        have_img = _ok_file(img)
        have_audio = _ok_file(cue.audio_path)
        out = Path(ctx.shots_dir) / f"cue_{part_no:04d}.mp4"

        cmd = [get_ffmpeg_bin(), "-y"]
        if have_img:
            cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(img)]
            vf = _kenburns_vf(cue.crop_from, cue.crop_to, width, height, fps, dur)
        else:
            col = _norm_color(getattr(ctx, "bg_value", "") or "#101820")
            cmd += ["-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"color=c={col}:s={width}x{height}:r={fps:.3f}"]
            vf = f"scale={width}:{height},setsar=1,format=yuv420p,fps={fps:.3f}"
        vf += _overlay_suffix(cue, width, height, part_no)   # burn hook title (hook-only)
        if have_audio:
            cmd += ["-i", str(cue.audio_path)]
        else:
            cmd += ["-f", "lavfi", "-t", f"{dur:.3f}",
                    "-i", f"anullsrc=channel_layout=stereo:sample_rate={_SAMPLE_RATE}"]

        af = f"aformat=sample_rates={_SAMPLE_RATE}:channel_layouts=stereo,apad"
        cmd += [
            "-filter_complex", f"[0:v]{vf}[v];[1:a]{af}[a]",
            "-map", "[v]", "-map", "[a]",
            "-r", f"{fps:.3f}", "-t", f"{dur:.3f}",
            *(["-threads", str(threads)] if threads > 0 else []),
            "-c:v", "libx264", "-preset", _CUE_PRESET, "-crf", _CUE_CRF, "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(_SAMPLE_RATE), "-ac", "2",
            "-movflags", "+faststart", str(out),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=_FFMPEG_TIMEOUT_SEC)
        if proc.returncode != 0 or not _ok_file(str(out)):
            err = (proc.stderr or "")[-400:]
            logger.warning("story cue %s ffmpeg failed rc=%s: %s", part_no, proc.returncode, err)
            return {"clip": None, "error": f"ffmpeg rc={proc.returncode}", "fallback": not have_img}
        return {"clip": str(out), "error": "", "fallback": not have_img}
    except subprocess.TimeoutExpired:
        logger.warning("story cue %s ffmpeg timeout", part_no)
        return {"clip": None, "error": "ffmpeg timeout", "fallback": False}
    except Exception as exc:
        logger.warning("story cue %s render error %s", part_no, exc)
        return {"clip": None, "error": str(exc), "fallback": False}


__all__ = ["render_one_cue"]
