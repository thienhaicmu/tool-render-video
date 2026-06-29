"""Burn the spoken narration as on-screen subtitles (Phase R3b).

Recap videos show the narrator's words as captions (user-chosen default).
The narration segments produced by the ai_rewrite path ({start, end, text} in
SOURCE-clip seconds) are written to a temp SRT — timestamps mapped to the
final, speed-adjusted timeline (source/speed) — then burned with FFmpeg's
``subtitles`` filter.

Ordering note (handled by the caller): this burns the captions into the video
PIXELS right after the narration mix and BEFORE the reaction freeze post-pass,
so the freeze re-times the burned captions together with the video + audio and
everything stays in sync.

Only ``kind=="voice"`` segments with text are captioned; reaction
``kind=="original"`` windows (reactor silent, source audio plays) get no
caption. CPU libx264 (no NVENC). Sacred Contract #3 spirit: returns False on any
failure (never raises) — the caller keeps the un-captioned video.
"""
from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.encoder.encoder_helpers import (
    safe_filter_path,
    detect_windows_fonts_dir,
    get_custom_fonts_dir,
)

logger = logging.getLogger("app.render.recap_narration_subtitle")

_FFMPEG_TIMEOUT_SEC: int = max(120, int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "1800")))
# force_style override (ASS style fields). Override via RECAP_SUBTITLE_STYLE.
_FORCE_STYLE: str = os.getenv(
    "RECAP_SUBTITLE_STYLE",
    "Fontsize=18,Outline=2,Shadow=1,MarginV=40,Alignment=2,BorderStyle=1",
)


def _ts(seconds: float) -> str:
    """Seconds → SRT timestamp HH:MM:SS,mmm."""
    s = max(0.0, float(seconds))
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    ms = int(round((s - int(s)) * 1000))
    if ms == 1000:
        ms = 0
        sec += 1
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def build_narration_srt(segments: list[dict], speed: float, out_path: str) -> bool:
    """Write narration voice segments → SRT at out_path (final-timeline times).
    Returns True if at least one caption was written."""
    sp = speed if speed and speed > 0 else 1.0
    rows: list[tuple[float, float, str]] = []
    for seg in segments or []:
        if str(seg.get("kind", "voice") or "voice").strip().lower() != "voice":
            continue
        text = str(seg.get("text", "") or "").strip()
        if not text:
            continue
        try:
            s = float(seg.get("start", 0.0)) / sp
            e = float(seg.get("end", 0.0)) / sp
        except (TypeError, ValueError):
            continue
        if e <= s:
            continue
        rows.append((s, e, text))
    if not rows:
        return False
    rows.sort(key=lambda r: r[0])
    try:
        lines: list[str] = []
        for i, (s, e, text) in enumerate(rows, start=1):
            lines.append(str(i))
            lines.append(f"{_ts(s)} --> {_ts(e)}")
            lines.append(text)
            lines.append("")
        Path(out_path).write_text("\n".join(lines), encoding="utf-8")
        return True
    except Exception as exc:
        logger.warning("recap_narration_subtitle: SRT write failed: %s", exc)
        return False


def burn_narration_subtitle(
    *,
    video_path: str,
    segments: list[dict],
    out_path: str,
    speed: float = 1.0,
    video_crf: int = 18,
) -> bool:
    """Burn narration captions onto video_path → out_path. Returns True on
    success; False (and no partial output) on any failure / no captions."""
    src = Path(video_path)
    out = Path(out_path)
    if not src.exists() or src.stat().st_size <= 0:
        return False
    srt_path = None
    try:
        fd, srt_path = tempfile.mkstemp(suffix=".srt", prefix="recap_narr_")
        os.close(fd)
        if not build_narration_srt(segments, speed, srt_path):
            return False  # nothing to caption
        _srt = safe_filter_path(str(Path(srt_path).resolve()))
        fonts_dir = get_custom_fonts_dir() or detect_windows_fonts_dir()
        _vf = f"subtitles='{_srt}':force_style='{_FORCE_STYLE}'"
        if fonts_dir:
            _vf = f"subtitles='{_srt}':fontsdir='{safe_filter_path(fonts_dir)}':force_style='{_FORCE_STYLE}'"
        cmd = [
            get_ffmpeg_bin(), "-y", "-i", str(src),
            "-vf", _vf,
            "-c:v", "libx264", "-preset", "medium", "-crf", str(int(video_crf)), "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            str(out),
        ]
        subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       check=True, timeout=_FFMPEG_TIMEOUT_SEC)
        return out.exists() and out.stat().st_size > 0
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        logger.warning("recap_narration_subtitle: ffmpeg failed (non-fatal): %s", detail[:400] or exc)
        try:
            if out.exists():
                out.unlink()
        except Exception:
            pass
        return False
    except Exception as exc:
        logger.warning("recap_narration_subtitle: unexpected error (non-fatal): %s", exc)
        return False
    finally:
        if srt_path:
            try:
                os.unlink(srt_path)
            except Exception:
                pass
