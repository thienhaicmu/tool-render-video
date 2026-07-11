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

# A3 character overlay — master HEIGHT as a fraction of the canvas per char_scale,
# and the entrance/motion timings (seconds).
_CHAR_SCALE_FRAC = {"small": 0.55, "medium": 0.72, "large": 0.90}
_CHAR_SLIDE_SEC = 0.5
_CHAR_FADE_SEC = 0.4


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


# s4 text_anchor → drawtext (x, y) expressions. "auto" keeps the historical upper-third
# placement (h*0.10, centered) so a pre-s4 cue is byte-identical. left/right sit mid-height
# on a side so the text clears a character overlaid on the opposite side.
def _anchor_xy(text_anchor: str) -> "tuple[str, str]":
    a = (text_anchor or "auto").strip().lower()
    if a == "top":
        return "(w-text_w)/2", "h*0.08"
    if a == "bottom":
        return "(w-text_w)/2", "h*0.82"
    if a == "left":
        return "w*0.06", "(h-text_h)/2"
    if a == "right":
        return "w-text_w-w*0.06", "(h-text_h)/2"
    return "(w-text_w)/2", "h*0.10"          # auto (default, backward-compat)


def _drawtext(text: str, width: int, height: int, *, fs: int, family: str, bold: bool,
              y: str, box_alpha: float, uniq: str = "", x: str = "(w-text_w)/2") -> str:
    """Build ONE drawtext filter for ``text`` (via a textfile so Vietnamese / quotes /
    colons never need inline escaping). ``x``/``y`` are drawtext expressions (from the
    cue's text_anchor). ``uniq`` (e.g. the cue's part_no) namespaces the textfile so two
    cues with IDENTICAL text can't race on the same file when rendered in parallel.
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
            f"x={x}", f"y={y}",
        ]
        return "drawtext=" + ":".join(opts)
    except Exception as exc:
        logger.warning("story overlay drawtext failed: %s", exc)
        return ""


def _overlay_suffix(cue, width: int, height: int, part_no: int = 0) -> str:
    """Filtergraph suffix (leading comma) that burns the cue's hook title at its
    ``text_anchor`` (s4; default auto = upper third). On-screen text is HOOK-ONLY — no
    full-video subtitle. "" when nothing to burn. ``part_no`` namespaces the drawtext
    textfiles so parallel cues never share a file."""
    try:
        parts: list[str] = []
        _u = f"{int(part_no):04d}_"
        if getattr(cue, "hook", False) and (getattr(cue, "hook_text", "") or "").strip():
            _x, _y = _anchor_xy(getattr(cue, "text_anchor", "auto"))
            parts.append(_drawtext(
                cue.hook_text, width, height, fs=max(28, int(height * 0.060)),
                family="Anton", bold=True, y=_y, x=_x, box_alpha=0.55, uniq=_u + "h"))
        parts = [p for p in parts if p]
        return ("," + ",".join(parts)) if parts else ""
    except Exception:
        return ""


def _char_overlay_parts(cue, width: int, height: int, dur: float) -> "tuple[str, str, str]":
    """(fg_chain, x_expr, y_expr) to composite a speaking character's transparent master
    over the base. Scale by char_scale (height fraction of the canvas), position by
    char_anchor, animate by char_motion. Uses overlay expression vars W/H (main), w/h
    (overlay), t (time). x/y are single-quoted at the call site so commas inside
    ``if(...)`` are safe in the filtergraph. Never raises."""
    try:
        frac = _CHAR_SCALE_FRAC.get((getattr(cue, "char_scale", "medium") or "medium"), 0.72)
        ch = max(2, int(height * frac))
        anchor = (getattr(cue, "char_anchor", "left") or "left")
        motion = (getattr(cue, "char_motion", "fade") or "fade")
        margin = width * 0.03
        if anchor == "center":
            xt = "(W-w)/2"
        elif anchor == "right":
            xt = f"W-w-{margin:.1f}"
        else:                                   # left (default)
            xt = f"{margin:.1f}"
        yt = "H-h"                              # stand on the ground (bottom-aligned)
        fg = f"scale=-1:{ch},format=rgba"
        x, y = xt, yt
        if motion == "fade":
            fo = max(0.0, dur - _CHAR_FADE_SEC)
            fg += (f",fade=t=in:st=0:d={_CHAR_FADE_SEC}:alpha=1"
                   f",fade=t=out:st={fo:.3f}:d={_CHAR_FADE_SEC}:alpha=1")
        elif motion == "slide":
            s = _CHAR_SLIDE_SEC
            if anchor == "right":
                x = f"if(lt(t,{s}),W-(W-({xt}))*t/{s},{xt})"
            else:                               # slide in from the left edge
                x = f"if(lt(t,{s}),-w+(({xt})+w)*t/{s},{xt})"
        elif motion == "float":
            amp = max(2.0, height * 0.012)
            y = f"({yt})+{amp:.1f}*sin(2*PI*t*0.5)"
        # static → xt/yt as-is
        return fg, x, y
    except Exception:
        return "scale=-1:{}".format(max(2, int(height * 0.72))) + ",format=rgba", f"{width * 0.03:.1f}", "H-h"


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

        # A2: optional LOCAL base video the story is composited over. When present, the
        # cue's base layer is a SEGMENT of that video, seeked to the cue's position in
        # the story timeline (looped by modulo when the video is shorter than the
        # narration). No Ken Burns — the video already has motion. "" → image/color path
        # (byte-identical to pre-A2).
        base_video = getattr(ctx, "base_video_path", "") or ""
        base_dur = float(getattr(ctx, "base_video_dur", 0.0) or 0.0)
        use_video = bool(base_video) and _ok_file(base_video)

        # A3: overlay the speaking character's transparent master over the base video —
        # ONLY with a base video + char_anchor set + a master available. "" → no overlay
        # (the A2 base-video / image path is byte-identical).
        overlay_master = ""
        if use_video and (getattr(cue, "char_anchor", "none") or "none") != "none":
            _m = (getattr(plan.render, "masters", None) or {}).get(getattr(cue, "speaker_id", "") or "")
            if _ok_file(_m):
                overlay_master = _m

        cmd = [get_ffmpeg_bin(), "-y"]
        if use_video:
            seek = (float(cue.start_sec) % base_dur) if base_dur > 0 else max(0.0, float(cue.start_sec))
            cmd += ["-stream_loop", "-1", "-ss", f"{seek:.3f}", "-t", f"{dur:.3f}", "-i", str(base_video)]
            vf = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                  f"crop={width}:{height},setsar=1,fps={fps:.3f},format=yuv420p")
        elif have_img:
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
        if overlay_master:                       # input [2] — a looped still so motion has frames
            cmd += ["-loop", "1", "-t", f"{dur:.3f}", "-i", str(overlay_master)]

        af = f"aformat=sample_rates={_SAMPLE_RATE}:channel_layouts=stereo,apad"
        if overlay_master:
            _fg, _x, _y = _char_overlay_parts(cue, width, height, dur)
            _fc = (f"[0:v]{vf}[bg];[2:v]{_fg}[fg];"
                   f"[bg][fg]overlay=x='{_x}':y='{_y}':format=auto[v];[1:a]{af}[a]")
        else:
            _fc = f"[0:v]{vf}[v];[1:a]{af}[a]"
        cmd += [
            "-filter_complex", _fc,
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
            return {"clip": None, "error": f"ffmpeg rc={proc.returncode}", "fallback": not (use_video or have_img)}
        return {"clip": str(out), "error": "", "fallback": not (use_video or have_img)}
    except subprocess.TimeoutExpired:
        logger.warning("story cue %s ffmpeg timeout", part_no)
        return {"clip": None, "error": "ffmpeg timeout", "fallback": False}
    except Exception as exc:
        logger.warning("story cue %s render error %s", part_no, exc)
        return {"clip": None, "error": str(exc), "fallback": False}


__all__ = ["render_one_cue"]
