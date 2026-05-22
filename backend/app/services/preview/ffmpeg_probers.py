"""FFmpeg/ffprobe media inspection helpers for preview generation.

Pure probing functions — no route objects, no session state, no DB access.
All subprocess calls are self-contained.
"""

import json
import re
import subprocess
import logging
from pathlib import Path

from fastapi import HTTPException
from app.services.bin_paths import get_ffprobe_bin, get_ffmpeg_bin

logger = logging.getLogger("app.render")


def _probe_video_codec(video_path: Path) -> str:
    """Return the video codec name, e.g. 'h264', 'vp9', 'av1'."""
    cmd = [
        get_ffprobe_bin(),
        "-v", "error",
        "-select_streams", "v:0",
        "-show_entries", "stream=codec_name",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        return (r.stdout or "").strip().lower()
    except Exception:
        return ""


def _probe_preview_profile(video_path: Path) -> dict:
    """Return container/video/audio details used to decide browser preview compatibility."""
    cmd = [
        get_ffprobe_bin(),
        "-v", "error",
        "-show_entries", "format=format_name:stream=index,codec_type,codec_name",
        "-of", "json",
        str(video_path),
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
        data = json.loads(result.stdout or "{}")
        streams = data.get("streams") or []
        format_name = str((data.get("format") or {}).get("format_name") or "").lower()
        video_codec = ""
        audio_codec = ""
        for stream in streams:
            codec_type = str(stream.get("codec_type") or "").lower()
            codec_name = str(stream.get("codec_name") or "").lower()
            if codec_type == "video" and not video_codec:
                video_codec = codec_name
            elif codec_type == "audio" and not audio_codec:
                audio_codec = codec_name
        return {
            "format_name": format_name,
            "video_codec": video_codec,
            "audio_codec": audio_codec,
        }
    except Exception:
        return {
            "format_name": "",
            "video_codec": _probe_video_codec(video_path),
            "audio_codec": "",
        }


def _is_browser_safe_preview(video_path: Path) -> bool:
    """Return True when the source should play reliably in Chromium without preview transcoding."""
    profile = _probe_preview_profile(video_path)
    container = profile.get("format_name") or ""
    video_codec = profile.get("video_codec") or ""
    audio_codec = profile.get("audio_codec") or ""

    container_ok = any(name in container for name in ("mp4", "mov"))
    video_ok = video_codec in ("h264", "avc", "avc1")
    audio_ok = (not audio_codec) or audio_codec in ("aac", "mp3")
    return container_ok and video_ok and audio_ok


def _ensure_h264_preview(src: Path, work_dir: Path, duration_sec: int = 0) -> Path:
    """
    Reuse the source only when it is already browser-safe for Chromium playback.
    Otherwise generate a cached H.264 preview for the editor.

    Timeout is duration-aware: base 120s + 2s per second of video, capped at 3600s.
    Returns src unchanged when transcoding fails so the caller can still serve it.
    """
    out = work_dir / "preview_h264.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out
    if _is_browser_safe_preview(src):
        return src

    timeout_sec = min(3600, 120 + 2 * max(0, int(duration_sec)))
    profile = _probe_preview_profile(src)
    has_audio = bool(profile.get("audio_codec"))
    logger.info(
        "Transcoding preview to browser-safe H.264 (format=%s video=%s audio=%s duration=%ss timeout=%ss)",
        profile.get("format_name") or "",
        profile.get("video_codec") or "",
        profile.get("audio_codec") or "",
        duration_sec,
        timeout_sec,
    )

    cmd = [
        get_ffmpeg_bin(),
        "-y",
        "-i", str(src),
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-vf", "scale='min(1280,iw)':-2",
        "-movflags", "+faststart",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "128k"]
    else:
        cmd += ["-an"]
    cmd.append(str(out))

    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout_sec, check=False)
        if out.exists() and out.stat().st_size > 0:
            logger.info("Preview transcode OK (output=%s)", out)
            return out
    except subprocess.TimeoutExpired:
        logger.error(
            "Preview transcode timed out after %ss (src=%s duration=%ss). Falling back to original file.",
            timeout_sec,
            src,
            duration_sec,
        )
    except Exception as exc:
        logger.warning("Preview transcode failed for %s: %s", src, exc)

    try:
        out.unlink(missing_ok=True)
    except Exception:
        pass

    return src


def _run_ffmpeg_checked(cmd: list[str], fail_message: str):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        detail = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise HTTPException(status_code=500, detail=f"{fail_message}: {detail or 'unknown ffmpeg error'}")
    return proc


def _detect_leading_black_duration(input_path: Path, min_duration: float, threshold: float) -> float:
    """
    Detect black frames only at the beginning and return trim seconds (black_end).
    Returns 0.0 when no leading black intro matches criteria.
    """
    cmd = [
        get_ffmpeg_bin(),
        "-hide_banner",
        "-loglevel", "info",
        "-i", str(input_path),
        "-vf", f"blackdetect=d={min_duration:.3f}:pic_th={threshold:.3f}",
        "-an",
        "-f", "null",
        "-",
    ]
    proc = _run_ffmpeg_checked(cmd, "FFmpeg black-intro detection failed")
    output = ((proc.stderr or "") + "\n" + (proc.stdout or "")).strip()

    pattern = re.compile(r"black_start:(?P<start>\d+(\.\d+)?)\s+black_end:(?P<end>\d+(\.\d+)?)\s+black_duration:(?P<dur>\d+(\.\d+)?)")
    for match in pattern.finditer(output):
        start = float(match.group("start"))
        end = float(match.group("end"))
        dur = float(match.group("dur"))
        # Trim only if black section starts at beginning.
        if start <= 0.12 and dur >= min_duration:
            return max(0.0, end)
        break
    return 0.0
