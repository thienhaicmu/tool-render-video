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


# Maximum seconds of source video to encode for the preview.
# The preview is only used for clip-selection scrubbing; the original file is
# always used for the actual render. Capping here bounds the worst-case wait
# for long HEVC/VP9 sources that cannot be copy-remuxed.
_PREVIEW_MAX_ENCODE_SECONDS = 600  # 10 minutes


def _ensure_h264_preview(src: Path, work_dir: Path, duration_sec: int = 0) -> Path:
    """
    Return a browser-safe H.264 MP4 path for editor preview.

    Fast-path order:
      1. Return cached output if it already exists.
      2. Return src unchanged when it is already browser-safe.
      3. Copy-remux (no re-encode) when the source is H.264 in a non-MP4 container.
         This takes 3-5 seconds regardless of video duration.
      4. Re-encode with libx264 ultrafast, capped at _PREVIEW_MAX_ENCODE_SECONDS.
         Bounding the encode length prevents a 30-minute HEVC source from stalling
         the UI for 30 minutes. The original file is always used for actual rendering.

    Returns src unchanged if all attempts fail so the caller can still serve it.
    """
    out = work_dir / "preview_h264.mp4"
    if out.exists() and out.stat().st_size > 0:
        return out
    if _is_browser_safe_preview(src):
        return src

    profile = _probe_preview_profile(src)
    has_audio = bool(profile.get("audio_codec"))
    video_codec = (profile.get("video_codec") or "").lower()

    # ── Fast path: H.264 source in a non-browser-safe container ─────────────
    # Just change the container — no pixel re-encoding needed.
    # Handles the common H.264-in-MKV case in seconds at any duration.
    if video_codec in ("h264", "avc", "avc1"):
        logger.info("Copy-remuxing H.264 preview to MP4 container (src=%s)", src)
        cmd = [get_ffmpeg_bin(), "-y", "-i", str(src), "-c:v", "copy"]
        cmd += (["-c:a", "copy"] if has_audio else ["-an"])
        cmd += ["-movflags", "+faststart", str(out)]
        try:
            subprocess.run(cmd, capture_output=True, timeout=60, check=False)
            if out.exists() and out.stat().st_size > 0:
                logger.info("Copy-remux OK (output=%s)", out)
                return out
        except Exception as exc:
            logger.warning("Copy-remux failed for %s: %s — falling through to encode", src, exc)
        try:
            out.unlink(missing_ok=True)
        except Exception:
            pass

    # ── Encode path: libx264 with a hard duration cap ────────────────────────
    # ultrafast preset at reduced resolution is ~4x faster than the previous
    # veryfast + 1280px combination. The cap means a 30-min HEVC source produces
    # a 10-minute preview in ~3-5 min instead of blocking for 30 min.
    cap_sec = _PREVIEW_MAX_ENCODE_SECONDS
    timeout_sec = 600  # generous bound: ultrafast encodes 10 min well within this
    logger.info(
        "Encoding preview (format=%s video=%s audio=%s cap=%ss timeout=%ss)",
        profile.get("format_name") or "",
        video_codec,
        profile.get("audio_codec") or "",
        cap_sec,
        timeout_sec,
    )
    cmd = [
        get_ffmpeg_bin(),
        "-y",
        "-i", str(src),
        "-t", str(cap_sec),
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "32",
        "-pix_fmt", "yuv420p",
        "-vf", "scale='min(960,iw)':-2",
        "-movflags", "+faststart",
    ]
    if has_audio:
        cmd += ["-c:a", "aac", "-b:a", "96k"]
    else:
        cmd += ["-an"]
    cmd.append(str(out))

    try:
        subprocess.run(cmd, capture_output=True, timeout=timeout_sec, check=False)
        if out.exists() and out.stat().st_size > 0:
            logger.info("Preview encode OK (output=%s)", out)
            return out
    except subprocess.TimeoutExpired:
        logger.error(
            "Preview encode timed out after %ss (src=%s). Falling back to original file.",
            timeout_sec,
            src,
        )
    except Exception as exc:
        logger.warning("Preview encode failed for %s: %s", src, exc)

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
