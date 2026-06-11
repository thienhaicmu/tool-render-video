"""acquire.py — unified asset acquisition entry point.

Owns the adapter chain. Dispatches downloads to the correct platform adapter,
then normalises the raw adapter result into the standard dict expected by the
service layer:

    {title, platform, output_path, filename, height, fps, duration, filesize}

Also exposes get_video_info() (yt-dlp metadata probe, no download).
"""
from __future__ import annotations

import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger("app.downloader")


# ── Adapter registry ─────────────────────────────────────────────────────────

def _build_chain():
    from app.features.download.adapters.youtube import YouTubeAdapter
    from app.features.download.adapters.tiktok import TikTokAdapter
    from app.features.download.adapters.instagram import InstagramAdapter
    from app.features.download.adapters.facebook import FacebookAdapter
    from app.features.download.adapters.douyin import DouyinAdapter
    from app.features.download.adapters.generic import GenericAdapter
    return [
        YouTubeAdapter(),
        TikTokAdapter(),
        InstagramAdapter(),
        FacebookAdapter(),
        DouyinAdapter(),
        GenericAdapter(),
    ]


_ADAPTER_CHAIN = None
_CHAIN_LOCK = threading.Lock()


def _get_chain() -> list:
    global _ADAPTER_CHAIN
    if _ADAPTER_CHAIN is None:
        with _CHAIN_LOCK:
            if _ADAPTER_CHAIN is None:
                _ADAPTER_CHAIN = _build_chain()
    return _ADAPTER_CHAIN


def get_adapter(url: str):
    """Return the first adapter that supports the given URL."""
    for adapter in _get_chain():
        if adapter.supports(url):
            logger.debug("acquire: adapter_selected platform=%s url=%s", adapter.platform_name, url[:80])
            return adapter
    return _get_chain()[-1]  # GenericAdapter always matches


# ── Main acquisition function ─────────────────────────────────────────────────

def acquire(
    job_id: str,
    url: str,
    output_dir: Path,
    *,
    quality: str = "best",
    platform: str = "",
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[[int, str, str], None]] = None,
) -> dict:
    """Download a video via the adapter chain.

    Returns a normalised result dict:
        title, platform, output_path, filename, height, fps, duration, filesize

    Raises RuntimeError on failure (propagated from adapter).
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    adapter = get_adapter(url)
    _platform = platform or adapter.platform_name

    logger.info(
        "acquire.start  job=%s  platform=%s  quality=%s  url=%s",
        job_id, _platform, quality, url,
    )

    try:
        raw = adapter.download(
            url, output_dir,
            quality=quality,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
            context=job_id,
        )
    except Exception:
        # Cleanup any partial temp files from this job
        for _p in output_dir.glob(f"_dl_{job_id}.*"):
            try:
                _p.unlink(missing_ok=True)
            except Exception:
                pass
        raise

    return _normalise(raw, output_dir, _platform)


# ── Output normalisation ──────────────────────────────────────────────────────

def _normalise(raw: dict, output_dir: Path, platform: str) -> dict:
    """Map adapter result to the standard dict expected by the service layer."""
    filepath = Path(raw.get("filepath") or raw.get("output_path") or "")
    if not filepath.is_file():
        raise RuntimeError(f"Adapter returned missing or invalid filepath: {filepath!r}")

    title = raw.get("title") or filepath.stem
    # downloader.py uses selected_height / selected_fps; engine.py used height / fps
    height = int(raw.get("selected_height") or raw.get("height") or 0)
    fps = float(raw.get("selected_fps") or raw.get("fps") or 0)
    duration = float(raw.get("duration") or 0)

    # Build final filename from slug + resolution tags
    slug = raw.get("slug") or _slugify(title)
    res_tag = f"_{height}p" if height else ""
    fps_tag = f"_{int(fps)}fps" if fps > 0 else ""
    final_name = f"{slug[:80]}{res_tag}{fps_tag}.mp4"
    final_path = _resolve_unique(output_dir, final_name)

    if filepath.resolve() != final_path.resolve():
        filepath.rename(final_path)

    filesize = final_path.stat().st_size

    return {
        "title":       title,
        "platform":    raw.get("platform") or raw.get("source") or platform,
        "output_path": str(final_path),
        "filename":    final_path.name,
        "height":      height,
        "fps":         fps,
        "duration":    duration,
        "filesize":    filesize,
    }


def _slugify(text: str) -> str:
    try:
        from app.core.naming import slugify
        return slugify(text) or "video"
    except Exception:
        import re
        return re.sub(r"[^\w-]", "_", text.lower())[:80] or "video"


def _resolve_unique(directory: Path, filename: str) -> Path:
    try:
        from app.features.download.engine.file_naming import resolve_unique_path
        return resolve_unique_path(directory, filename)
    except Exception:
        candidate = directory / filename
        if not candidate.exists():
            return candidate
        stem = candidate.stem
        suffix = candidate.suffix
        for i in range(1, 1000):
            alt = directory / f"{stem}_{i}{suffix}"
            if not alt.exists():
                return alt
        return candidate


# ── Metadata probe ────────────────────────────────────────────────────────────

def get_video_info(url: str) -> dict:
    """Probe video metadata without downloading (yt-dlp extract_info, skip_download=True)."""
    try:
        import yt_dlp
        from app.features.download.engine.platform_detect import detect_platform
        from app.services.bin_paths import ensure_ffmpeg_available
        from app.features.download.engine.tiktok_handler import get_tiktok_opts

        ffmpeg_bin = ensure_ffmpeg_available()
        ffmpeg_dir = str(Path(ffmpeg_bin).parent)
        if ffmpeg_dir not in os.environ.get("PATH", "").split(os.pathsep):
            os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

        opts: dict = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "ffmpeg_location": ffmpeg_bin,
        }

        # Cookie auth (same priority chain as engine.py)
        cookiefile = (os.getenv("YTDLP_COOKIEFILE", "") or "").strip()
        if cookiefile and Path(cookiefile).expanduser().is_file():
            opts["cookiefile"] = str(Path(cookiefile).expanduser())
        else:
            try:
                from app.core.config import COOKIES_DIR
                auto = COOKIES_DIR / "youtube_cookies.txt"
                if auto.is_file():
                    opts["cookiefile"] = str(auto)
            except Exception:
                pass

        platform = detect_platform(url)
        if platform == "tiktok":
            opts.update(get_tiktok_opts())
            opts["skip_download"] = True
        elif platform == "youtube":
            opts["extractor_args"] = {"youtube": {"player_client": ["ios"]}}

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
        try:
            from app.features.download.engine.platform_detect import detect_platform
            _plat = detect_platform(url)
        except Exception:
            _plat = "unknown"
        return {"title": "", "platform": _plat, "duration": 0, "formats": []}
