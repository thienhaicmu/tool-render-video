from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Callable

from app.services.bin_paths import ensure_ffmpeg_available
from .platform_detect import detect_platform
from .file_naming import build_output_filename, resolve_unique_path
from .tiktok_handler import get_tiktok_opts

logger = logging.getLogger("app.downloader")


def _ensure_ffmpeg_on_path() -> str:
    ffmpeg_bin = ensure_ffmpeg_available()
    ffmpeg_dir = str(Path(ffmpeg_bin).parent)
    current = os.environ.get("PATH", "")
    if ffmpeg_dir not in current.split(os.pathsep):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current
    return ffmpeg_bin


def _base_opts(output_dir: Path, job_id: str, ffmpeg_bin: str) -> dict:
    return {
        "format": (
            "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]"
            "/bestvideo[height<=1080]+bestaudio"
            "/best[height<=1080]/best"
        ),
        # Temp name uses job_id only — no dates
        "outtmpl": str(output_dir / f"_dl_{job_id}.%(ext)s"),
        "noplaylist": True,
        "merge_output_format": "mp4",
        "ffmpeg_location": ffmpeg_bin,
        "prefer_ffmpeg": True,
        "quiet": True,
        "no_warnings": True,
        "socket_timeout": 60,
        "retries": 3,
        "fragment_retries": 3,
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
        ],
    }


def get_video_info(url: str) -> dict:
    """Extract metadata without downloading. Returns title, duration, formats."""
    try:
        import yt_dlp
        ffmpeg_bin = _ensure_ffmpeg_on_path()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ffmpeg_location": ffmpeg_bin,
        }
        platform = detect_platform(url)
        if platform == "tiktok":
            opts.update(get_tiktok_opts())
            opts["skip_download"] = True

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = []
        for f in (info.get("formats") or []):
            h = f.get("height") or 0
            if h >= 360:
                formats.append({
                    "height": h,
                    "fps": round(f.get("fps") or 0),
                    "ext": f.get("ext"),
                    "filesize": f.get("filesize") or f.get("filesize_approx") or 0,
                })
        # Deduplicate by height
        seen: set[int] = set()
        unique_formats = []
        for f in sorted(formats, key=lambda x: x["height"], reverse=True):
            if f["height"] not in seen:
                seen.add(f["height"])
                unique_formats.append(f)

        return {
            "title": info.get("title") or "",
            "platform": platform,
            "duration": info.get("duration") or 0,
            "thumbnail": info.get("thumbnail") or "",
            "formats": unique_formats[:6],
        }
    except Exception as exc:
        logger.warning("get_video_info failed: %s", exc)
        return {"title": "", "platform": detect_platform(url), "duration": 0, "formats": []}


def download_video(
    job_id: str,
    url: str,
    output_dir: Path,
    on_progress: Callable[[int, str, str], None] | None = None,
) -> dict:
    """
    Download video to output_dir.
    Filename: {original_title}_{height}p{fps}fps.mp4
    Returns dict with title, platform, output_path, filename, height, fps, duration, filesize.
    """
    import yt_dlp

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = _ensure_ffmpeg_on_path()
    platform = detect_platform(url)

    opts = _base_opts(output_dir, job_id, ffmpeg_bin)
    if platform == "tiktok":
        tiktok_opts = get_tiktok_opts()
        opts["format"] = tiktok_opts["format"]
        opts["extractor_args"] = tiktok_opts["extractor_args"]

    def _hook(data: dict):
        if not on_progress:
            return
        status = str(data.get("status") or "")
        if status == "downloading":
            total = float(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            downloaded = float(data.get("downloaded_bytes") or 0)
            pct = int(downloaded / total * 100) if total > 0 else 0
            speed = str(data.get("_speed_str") or "").strip()
            eta = str(data.get("_eta_str") or "").strip()
            on_progress(min(99, max(1, pct)), speed, eta)
        elif status == "finished":
            on_progress(99, "", "")

    opts["progress_hooks"] = [_hook]

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)

    # Find the temp file (_dl_{job_id}.mp4)
    temp_candidates = sorted(
        [p for p in output_dir.glob(f"_dl_{job_id}.*") if p.is_file()],
        key=lambda p: p.stat().st_size,
        reverse=True,
    )
    if not temp_candidates:
        raise RuntimeError("Downloaded file not found after yt-dlp completed")

    temp_file = temp_candidates[0]

    # Build final filename
    filename = build_output_filename(info)
    final_path = resolve_unique_path(output_dir, filename)
    temp_file.rename(final_path)

    return {
        "title": info.get("title") or final_path.stem,
        "platform": platform,
        "output_path": str(final_path),
        "filename": final_path.name,
        "height": int(info.get("height") or 0),
        "fps": float(info.get("fps") or 0),
        "duration": float(info.get("duration") or 0),
        "filesize": final_path.stat().st_size,
    }
