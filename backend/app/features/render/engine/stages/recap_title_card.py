"""Recap act title card (Phase R2).

Generates a short chapter/act title card for a recap video: a frame from the
act's opening scene, blurred, with the act title drawn on top, held for a few
seconds. CPU libx264 encode (no NVENC — a one-off card must not contend for GPU
encoder sessions). Output spec (WxH/fps/codec/sample-rate) is forced to match
the rendered scenes so the assembler can concat without re-encoding.

Sacred Contract #3 spirit: returns False on any failure (never raises) — the
caller drops the card and concatenates scenes directly.
"""
from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.encoder.encoder_helpers import (
    detect_windows_fontfile,
    safe_filter_path,
)

logger = logging.getLogger("app.render.recap_title_card")

_FFMPEG_TIMEOUT_SEC: int = max(120, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800")))
_CARD_DURATION_SEC: float = max(1.0, min(6.0, float(os.getenv("RECAP_ACT_CARD_SEC", "2.5"))))
_BLUR_SIGMA: int = int(os.getenv("RECAP_ACT_CARD_BLUR", "20"))


def _escape_drawtext(text: str) -> str:
    s = (text or "").strip()
    s = s.replace("\\", "\\\\").replace(":", "\\:").replace("'", "’").replace("%", "\\%")
    return s


def make_act_title_card(
    *,
    source_video: str,
    at_sec: float,
    title_text: str,
    out_path: str,
    width: int,
    height: int,
    fps: float = 30.0,
    duration_sec: float | None = None,
    sample_rate: int = 48000,
) -> bool:
    """Render one act title card → out_path. Returns True on success.

    A blurred still from ``source_video`` at ``at_sec`` is held for
    ``duration_sec`` with ``title_text`` centred, plus a matching silent audio
    track so the assembler's concat sees uniform A/V streams.
    """
    src = Path(source_video)
    out = Path(out_path)
    if not src.exists() or src.stat().st_size <= 0:
        return False
    dur = _CARD_DURATION_SEC if duration_sec is None else max(1.0, min(6.0, float(duration_sec)))
    try:
        w, h = int(width), int(height)
        # Pull a 1-frame still at at_sec, scale+pad to target, blur, hold dur,
        # draw the act title. Silent stereo audio at the scene sample rate.
        vf = (
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"boxblur={_BLUR_SIGMA}:1,setsar=1,fps={fps:.3f},tpad=stop_mode=clone:stop_duration={dur:.3f}"
        )
        fontfile = detect_windows_fontfile()
        cap = _escape_drawtext(title_text)
        if cap and fontfile:
            _ff = safe_filter_path(fontfile)
            vf += (
                f",drawtext=fontfile='{_ff}':text='{cap}'"
                f":fontcolor=white:fontsize=h/12:box=1:boxcolor=black@0.5:boxborderw=32"
                f":x=(w-text_w)/2:y=(h-text_h)/2"
            )
        cmd = [
            get_ffmpeg_bin(), "-y",
            "-ss", f"{max(0.0, float(at_sec)):.3f}", "-i", str(src),
            "-f", "lavfi", "-t", f"{dur:.3f}", "-i", f"anullsrc=channel_layout=stereo:sample_rate={sample_rate}",
            "-map", "0:v:0", "-map", "1:a:0",
            "-vf", vf,
            "-frames:v", str(int(dur * fps) + 1),
            "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
            "-r", f"{fps:.3f}",
            "-c:a", "aac", "-b:a", "192k", "-ar", str(sample_rate),
            "-t", f"{dur:.3f}",
            str(out),
        ]
        subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8",
            check=True, timeout=_FFMPEG_TIMEOUT_SEC,
        )
        return out.exists() and out.stat().st_size > 0
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.warning("recap_title_card: ffmpeg failed (non-fatal): %s", detail[:400] or exc)
        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return False
    except Exception as exc:
        logger.warning("recap_title_card: unexpected error (non-fatal): %s", exc)
        return False
