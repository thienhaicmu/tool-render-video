from __future__ import annotations

import subprocess
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin, _summarize_ffmpeg_stderr


_DIMENSIONS_BY_ASPECT = {
    "9:16": (1080, 1920),
    "1:1": (1080, 1080),
    "3:4": (1080, 1440),
}


def _dimensions_for_aspect(aspect_ratio: str) -> tuple[int, int]:
    return _DIMENSIONS_BY_ASPECT.get((aspect_ratio or "").strip(), _DIMENSIONS_BY_ASPECT["3:4"])


def _escape_drawtext(text: str) -> str:
    return (
        str(text or "")
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def generate_hook_intro(
    output_path: str,
    *,
    aspect_ratio: str,
    duration_sec: float,
    headline_text: str | None = None,
) -> str | None:
    """Generate a tiny placeholder hook intro clip.

    RM-1 intentionally avoids a Remotion/React dependency. This validates the
    optional visual-layer seam with FFmpeg-generated media and soft fallback.
    """
    out = Path(output_path)
    duration = max(0.5, min(2.0, float(duration_sec or 1.0)))
    width, height = _dimensions_for_aspect(aspect_ratio)
    text = _escape_drawtext((headline_text or "AI HIGHLIGHT").strip() or "AI HIGHLIGHT")
    font_size = max(44, int(height * 0.075))
    fade_out_start = max(0.1, duration - 0.25)
    vf = (
        f"drawtext=text='{text}':fontcolor=white:fontsize={font_size}:"
        "x=(w-text_w)/2:y=(h-text_h)/2,"
        "fade=t=in:st=0:d=0.2,"
        f"fade=t=out:st={fade_out_start:.3f}:d=0.2"
    )
    cmd = [
        get_ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-f",
        "lavfi",
        "-i",
        f"color=c=black:s={width}x{height}:r=30:d={duration:.3f}",
        "-f",
        "lavfi",
        "-i",
        f"anullsrc=r=48000:cl=stereo:d={duration:.3f}",
        "-vf",
        vf,
        "-shortest",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(out),
    ]
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode != 0 or not out.exists() or out.stat().st_size <= 0:
            return None
        return str(out)
    except Exception:
        return None


def prepend_intro_clip(
    clip_path: str,
    intro_path: str,
    output_path: str,
    *,
    timeout_sec: int = 60,
) -> str | None:
    """Prepend intro to an existing rendered clip.

    This re-encodes through FFmpeg's concat filter for compatibility and returns
    None on any failure so the caller can preserve the original clip.
    """
    clip = Path(clip_path)
    intro = Path(intro_path)
    out = Path(output_path)
    if not clip.exists() or not intro.exists():
        return None
    filter_complex = (
        "[0:v]setsar=1,fps=30,format=yuv420p[v0];"
        "[1:v]setsar=1,fps=30,format=yuv420p[v1];"
        "[0:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a0];"
        "[1:a]aformat=sample_fmts=fltp:sample_rates=48000:channel_layouts=stereo[a1];"
        "[v0][a0][v1][a1]concat=n=2:v=1:a=1[v][a]"
    )
    cmd = [
        get_ffmpeg_bin(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(intro),
        "-i",
        str(clip),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-map",
        "[a]",
        "-c:v",
        "libx264",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        str(out),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        if proc.returncode != 0 or not out.exists() or out.stat().st_size <= 0:
            _summarize_ffmpeg_stderr(proc.stderr or "")
            return None
        return str(out)
    except Exception:
        return None
