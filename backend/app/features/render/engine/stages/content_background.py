"""
content_background.py — Build a VIDEO-ONLY background clip for Content Mode
(render_format="content").

Content Mode has no source footage, so every scene is composited over a
user-chosen background: a solid COLOR, a still IMAGE (held for the scene), or a
looping VIDEO. This module produces just that background clip at the target
canvas size / fps / duration; ``content_scene_render`` then burns the subtitle
and muxes the TTS narration on top.

CPU libx264 encode only — a background must never contend for an NVENC hardware
session (mirrors the recap act-title-card policy). No audio track: the scene
renderer supplies the audio from the narration.

Sacred Contract #3 spirit: every entry point returns ``False`` on any failure
(never raises) so the pipeline can skip the scene / fail the job cleanly.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.encoder.encoder_helpers import safe_filter_path

logger = logging.getLogger("app.render.content_background")

_FFMPEG_TIMEOUT_SEC: int = max(120, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800")))

# Background kinds (case-insensitive). "color" is the safest default — it needs
# no external asset and can never fail on a missing file.
KIND_COLOR = "color"
KIND_IMAGE = "image"
KIND_VIDEO = "video"
_VALID_KINDS = (KIND_COLOR, KIND_IMAGE, KIND_VIDEO)

_DEFAULT_COLOR = "#000000"


def _normalize_color(value: str) -> str:
    """Map a user color string to an ffmpeg-accepted token. ``#RRGGBB`` →
    ``0xRRGGBB``; named colors (``black``, ``white`` …) pass through. Falls back
    to opaque black on anything unusable."""
    v = (value or "").strip()
    if not v:
        return "0x000000"
    if v.startswith("#"):
        hexpart = v[1:]
        if len(hexpart) in (6, 8) and all(c in "0123456789abcdefABCDEF" for c in hexpart):
            return "0x" + hexpart
        return "0x000000"
    # named color or already an ffmpeg token (e.g. "black", "0x1e90ff")
    return v


def _scale_crop_vf(width: int, height: int, fps: float) -> str:
    """Cover-fit an input frame to WxH (crop overflow), square pixels, at fps."""
    return (
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},setsar=1,fps={fps:.3f}"
    )


def _ken_burns_vf(width: int, height: int, fps: float, frames: int) -> str:
    """CS-E — a slow Ken Burns zoom on a still image. Upscales the source 2× and
    cover-crops (so zoompan samples a clean, aspect-correct frame) then zooms
    from 1.0 → 1.30 across ``frames`` output frames. zoompan generates the frames
    from a SINGLE input frame — the caller must NOT use ``-loop`` for this path."""
    w2, h2 = int(width) * 2, int(height) * 2
    return (
        f"scale={w2}:{h2}:force_original_aspect_ratio=increase,crop={w2}:{h2},"
        f"zoompan=z='min(zoom+0.0006,1.30)':d={max(1, int(frames))}:s={width}x{height}:"
        f"fps={fps:.3f}:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',setsar=1"
    )


def build_background_clip(
    *,
    kind: str,
    value: str,
    width: int,
    height: int,
    fps: float,
    duration_sec: float,
    out_path: str,
    ken_burns: bool = False,
) -> bool:
    """Render a video-only background clip → ``out_path``. Returns True on success.

    kind:
      "color" — solid color (``value`` = "#RRGGBB" / named color). No asset needed.
      "image" — still image at ``value`` (path), scaled+cropped to WxH, held for
                the whole scene. When ``ken_burns`` is True, a slow zoom/pan is
                applied instead of a static hold (CS-E).
      "video" — looping video at ``value`` (path), scaled+cropped to WxH, cut to
                the scene duration.

    On a missing image/video asset, or any ffmpeg error, returns False (never
    raises). The output carries NO audio track (``-an``)."""
    try:
        w, h = int(width), int(height)
        dur = max(0.1, float(duration_sec))
        r = float(fps) if fps and fps > 0 else 30.0
        k = (kind or KIND_COLOR).strip().lower()
        if k not in _VALID_KINDS:
            logger.warning("content_background: unknown kind=%r → falling back to color", kind)
            k = KIND_COLOR
        out = Path(out_path)

        common_tail = [
            "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p",
            # No B-frames: DTS==PTS keeps the concat-demuxer boundary monotonic
            # when scenes are joined (mirrors recap_title_card).
            "-bf", "0",
            "-r", f"{r:.3f}",
            "-an",
            "-t", f"{dur:.3f}",
            str(out),
        ]

        if k == KIND_COLOR:
            color = _normalize_color(value)
            cmd = [
                get_ffmpeg_bin(), "-y",
                "-f", "lavfi",
                "-i", f"color=c={color}:s={w}x{h}:r={r:.3f}:d={dur:.3f}",
                "-vf", "setsar=1",
                *common_tail,
            ]
        elif k == KIND_IMAGE:
            src = Path(value or "")
            if not src.exists() or src.stat().st_size <= 0:
                logger.warning("content_background: image not found: %r", value)
                return False
            if ken_burns:
                # zoompan generates the frames from ONE input frame — no -loop.
                frames = int(dur * r) + 1
                cmd = [
                    get_ffmpeg_bin(), "-y",
                    "-i", str(src),
                    "-vf", _ken_burns_vf(w, h, r, frames),
                    *common_tail,
                ]
            else:
                cmd = [
                    get_ffmpeg_bin(), "-y",
                    "-loop", "1", "-i", str(src),
                    "-vf", _scale_crop_vf(w, h, r),
                    *common_tail,
                ]
        else:  # KIND_VIDEO
            src = Path(value or "")
            if not src.exists() or src.stat().st_size <= 0:
                logger.warning("content_background: video not found: %r", value)
                return False
            cmd = [
                get_ffmpeg_bin(), "-y",
                "-stream_loop", "-1", "-i", str(src),
                "-vf", _scale_crop_vf(w, h, r),
                *common_tail,
            ]

        subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            check=True, timeout=_FFMPEG_TIMEOUT_SEC,
        )
        ok = out.exists() and out.stat().st_size > 0
        if not ok:
            logger.warning("content_background: output missing/empty after ffmpeg")
        return ok
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.warning("content_background: ffmpeg failed (non-fatal): %s", detail[:400] or exc)
        _cleanup(out_path)
        return False
    except Exception as exc:
        logger.warning("content_background: unexpected error (non-fatal): %s", exc)
        _cleanup(out_path)
        return False


def _cleanup(path: str) -> None:
    try:
        p = Path(path)
        if p.exists():
            p.unlink()
    except Exception:
        pass


# ``safe_filter_path`` is imported so callers that build filter args around a
# background asset share the same escaping; re-exported for convenience.
__all__ = ["build_background_clip", "KIND_COLOR", "KIND_IMAGE", "KIND_VIDEO", "safe_filter_path"]
