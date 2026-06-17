from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path
from typing import Callable

from app.services.bin_paths import ensure_ffmpeg_available
from app.features.download.engine.platform_detect import detect_platform
from app.features.download.engine.file_naming import build_output_filename, resolve_unique_path
from app.features.download.engine.tiktok_handler import get_tiktok_opts

logger = logging.getLogger("app.downloader")


# Perf-opt Phase 3 (D3) — cache /api/downloader/info responses for 5 min.
# Same URL pasted twice (preview → submit, or two preview clicks) returns
# instantly instead of re-running yt-dlp metadata extraction (1–2 s).
# Cache is in-memory + thread-safe; evicted by TTL on every read.
_INFO_CACHE: dict[str, tuple[float, dict]] = {}
_INFO_TTL_SEC: float = 300.0
_INFO_LOCK = threading.Lock()
_INFO_MAX_ENTRIES: int = 100

# iOS client kwargs — bypasses YouTube bot/login checks on most videos
_IOS = {"extractor_args": {"youtube": {"player_client": ["ios"]}}}


def _apply_cookies(opts: dict) -> dict:
    """Add cookie auth to yt-dlp opts.

    Priority:
      1. YTDLP_COOKIEFILE env var (explicit exported file)
      2. Auto-extracted Chrome cookies (data/cookies/youtube_cookies.txt)
      3. YTDLP_COOKIES_FROM_BROWSER env var (yt-dlp native, fails when Chrome running)
    """
    cookiefile = (os.getenv("YTDLP_COOKIEFILE", "") or "").strip()
    if cookiefile:
        p = Path(cookiefile).expanduser()
        if p.is_file():
            opts["cookiefile"] = str(p)
            return opts
    try:
        from app.core.config import COOKIES_DIR
        auto = COOKIES_DIR / "youtube_cookies.txt"
        if auto.is_file():
            opts["cookiefile"] = str(auto)
            return opts
    except Exception:
        pass
    browser = (os.getenv("YTDLP_COOKIES_FROM_BROWSER", "") or "").strip().lower()
    if browser:
        opts["cookiesfrombrowser"] = (browser, None, None, None)
    return opts


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
    """Extract metadata without downloading. Returns title, duration, formats.

    Perf-opt Phase 3 (D3): in-memory cache keyed on the URL with 5 min TTL.
    Repeated preview clicks against the same URL return without spawning a
    yt-dlp probe. Cache entries are pruned on read when they expire and the
    map is bounded by oldest-eviction at 100 entries.
    """
    _now = time.monotonic()
    with _INFO_LOCK:
        _cached = _INFO_CACHE.get(url)
        if _cached is not None:
            _ts, _payload = _cached
            if (_now - _ts) < _INFO_TTL_SEC:
                return _payload
            # Stale — drop it now so the cache map stays tight
            _INFO_CACHE.pop(url, None)

    try:
        import yt_dlp
        ffmpeg_bin = _ensure_ffmpeg_on_path()
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ffmpeg_location": ffmpeg_bin,
        }
        _apply_cookies(opts)
        platform = detect_platform(url)
        if platform == "tiktok":
            opts.update(get_tiktok_opts())
            opts["skip_download"] = True
        elif platform == "youtube":
            opts.update(_IOS)

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

        _result = {
            "title": info.get("title") or "",
            "platform": platform,
            "duration": info.get("duration") or 0,
            "thumbnail": info.get("thumbnail") or "",
            "formats": unique_formats[:6],
        }
        # Phase 3 D3 — write back to cache on the success path only.
        # Failure path returns a thin error payload that is NOT cached so
        # the next call retries the probe.
        with _INFO_LOCK:
            _INFO_CACHE[url] = (_now, _result)
            if len(_INFO_CACHE) > _INFO_MAX_ENTRIES:
                # Evict the oldest entry by timestamp; bounded O(N) is fine
                # at N≤100 — calls are user-triggered, not high-frequency.
                _oldest_url = min(_INFO_CACHE, key=lambda k: _INFO_CACHE[k][0])
                _INFO_CACHE.pop(_oldest_url, None)
        return _result
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
    _apply_cookies(opts)
    if platform == "tiktok":
        tiktok_opts = get_tiktok_opts()
        opts["format"] = tiktok_opts["format"]
        opts["extractor_args"] = tiktok_opts["extractor_args"]
    elif platform == "youtube":
        opts.update(_IOS)

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

    cookie_src = "file" if "cookiefile" in opts else ("browser" if "cookiesfrombrowser" in opts else "none")
    logger.info("download.start  job=%s  platform=%s  cookies=%s  url=%s", job_id, platform, cookie_src, url)

    _t_dl = time.monotonic()
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except Exception as exc:
        _elapsed_ms = int((time.monotonic() - _t_dl) * 1000)
        logger.error(
            "download.ytdlp_error  job=%s  platform=%s  cookies=%s  elapsed_ms=%d  error=%s",
            job_id, platform, cookie_src, _elapsed_ms, exc,
            exc_info=True,
        )
        raise

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

    _elapsed_ms = int((time.monotonic() - _t_dl) * 1000)
    _filesize   = final_path.stat().st_size
    _height     = int(info.get("height") or 0)
    _fps        = float(info.get("fps") or 0)
    logger.info(
        "download.done  job=%s  platform=%s  cookies=%s  elapsed_ms=%d  size_bytes=%d  res=%dp  fps=%g  file=%s",
        job_id, platform, cookie_src, _elapsed_ms, _filesize, _height, _fps, final_path.name,
    )

    return {
        "title":       info.get("title") or final_path.stem,
        "platform":    platform,
        "output_path": str(final_path),
        "filename":    final_path.name,
        "height":      _height,
        "fps":         _fps,
        "duration":    float(info.get("duration") or 0),
        "filesize":    _filesize,
    }
