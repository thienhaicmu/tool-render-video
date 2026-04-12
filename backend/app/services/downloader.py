import logging
import os
import re
from pathlib import Path

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.services.bin_paths import ensure_ffmpeg_available

logger = logging.getLogger(__name__)


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "video"


def check_youtube_download_health(url: str) -> dict:
    """
    Probe a YouTube URL without downloading to check availability and max resolution.
    Tries each player client in order and returns info from the first that works.
    """
    ffmpeg_bin = ensure_ffmpeg_available()
    ffmpeg_dir = str(Path(ffmpeg_bin).parent)
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    # tv_embedded first — only client giving DASH without PO Token (tested 2026-04-09)
    clients = [
        ("tv_embedded", {"extractor_args": {"youtube": {"player_client": ["tv_embedded"]}}}),
        ("android",     {"extractor_args": {"youtube": {"player_client": ["android"]}}}),
        ("web",         {"extractor_args": {"youtube": {"player_client": ["web"]}}}),
        ("ios",         {"extractor_args": {"youtube": {"player_client": ["ios"]}}}),
        ("auto",        {}),
    ]

    last_payload: dict = {}
    for client_name, client_kwargs in clients:
        opts = {
            "skip_download": True,
            "quiet": True,
            "noplaylist": True,
            "retries": 2,
            "fragment_retries": 2,
            "extractor_retries": 2,
            **client_kwargs,
        }
        cookiefile = (os.getenv("YTDLP_COOKIEFILE", "") or "").strip()
        if cookiefile:
            p = Path(cookiefile).expanduser()
            if p.is_file():
                opts["cookiefile"] = str(p)
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
            formats = info.get("formats") or []
            video_streams = [
                f for f in formats
                if isinstance(f, dict)
                and str(f.get("vcodec") or "none").lower() != "none"
                and (f.get("url") or f.get("manifest_url"))
            ]
            if video_streams:
                best_h = max(int(float(f.get("height") or 0)) for f in video_streams)
                best_fps = max(int(float(f.get("fps") or 0)) for f in video_streams)
                return {
                    "ok": True,
                    "client": client_name,
                    "title": info.get("title") or "",
                    "best_height": best_h,
                    "best_fps": best_fps,
                    "video_stream_count": len(video_streams),
                }
            last_payload = {
                "ok": False,
                "client": client_name,
                "reason": "no_streams",
                "message": "No downloadable video streams for this client.",
            }
        except Exception as exc:
            last_payload = {
                "ok": False,
                "client": client_name,
                "reason": "error",
                "message": str(exc),
            }

    return last_payload


def download_youtube(url: str, temp_dir: Path) -> dict:
    """
    Download a YouTube video at the highest available resolution.

    Priority order:
      1. android client  → bestvideo+bestaudio  (1080p60, very reliable, no PO token)
      2. web client      → bestvideo+bestaudio  (up to 4K, may 403 sometimes)
      3. ios client      → bestvideo+bestaudio  (up to 1440p, good fallback)
      4. tv_embedded     → bestvideo+bestaudio  (lower quality cap, no bot check)
      5. android         → mp4-only combined    (single file, no merge needed)
      6. auto            → best                 (absolute last resort)

    All DASH splits are remuxed to mp4 via ffmpeg.
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = ensure_ffmpeg_available()
    ffmpeg_dir = str(Path(ffmpeg_bin).parent)
    os.environ["PATH"] = ffmpeg_dir + os.pathsep + os.environ.get("PATH", "")

    # ── Attempt order ─────────────────────────────────────────────────────────
    # [acodec=none]  → video-only DASH stream  (never combined/muxed 360p)
    # [vcodec=none]  → audio-only DASH stream
    #
    # TESTED 2026-04-09: tv_embedded is the ONLY client that returns DASH
    # streams (up to 2160p/4K) without GVS PO Token or cookies.
    # web/ios/mweb/android all require PO Token → skip HTTPS DASH → fall to 360p.
    # tv_embedded bị YouTube chặn từ 2026-04 — không dùng nữa
    _ANDROID = {"extractor_args": {"youtube": {"player_client": ["android"]}}}
    _IOS = {"extractor_args": {"youtube": {"player_client": ["ios"]}}}

    attempts = [
        # 1. android best mp4 ≤1080p (combined, không cần merge, ổn định nhất)
        (_ANDROID, "best[ext=mp4][height<=1080]/best[ext=mp4]"),
        # 2. ios best mp4 ≤1080p
        (_IOS, "best[ext=mp4][height<=1080]/best[ext=mp4]"),
        # 3. android best bất kỳ format ≤1080p
        (_ANDROID, "best[height<=1080]/best"),
        # 4. ios best bất kỳ format ≤1080p
        (_IOS, "best[height<=1080]/best"),
        # 5. auto client — để yt-dlp tự chọn (cần PO token hoặc cookie để lấy DASH)
        ({}, "best[height<=1080]/best"),
        # 6. fallback tuyệt đối — bất kỳ chất lượng nào
        ({}, "best"),
    ]

    common = {
        "outtmpl": str(temp_dir / "source.%(ext)s"),
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_bin,
        "prefer_ffmpeg": True,
        # merge adaptive video+audio streams into a single mp4
        "merge_output_format": "mp4",
        # prefer DASH (https direct) over HLS (m3u8) — HLS fragments often return empty
        "format_sort": ["proto:https", "proto:http"],
        # faster fragment downloads for DASH (1080p+ is always DASH on YouTube)
        "concurrent_fragment_downloads": 4,
        "retries": 10,
        "fragment_retries": 10,
        "extractor_retries": 5,
        "file_access_retries": 5,
        "skip_unavailable_fragments": False,
        # suppress noisy output; errors surfaced via exceptions
        "quiet": True,
        "no_warnings": False,
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }

    # Optional cookie file for unlocking higher-quality formats
    cookiefile = (os.getenv("YTDLP_COOKIEFILE", "") or "").strip()
    if cookiefile:
        p = Path(cookiefile).expanduser()
        if p.is_file():
            common["cookiefile"] = str(p)

    def _try_download(opts: dict) -> dict:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)

        title = info.get("title") or "video"
        duration = int(info.get("duration") or 0)

        # Resolve output file path
        requested = info.get("requested_downloads") or []
        filepath = requested[0].get("filepath") or "" if requested else ""
        if not filepath:
            with YoutubeDL({"quiet": True}) as ydl2:
                filepath = ydl2.prepare_filename(info)
        file_path = Path(filepath)

        # Glob fallback in case yt-dlp renamed the file
        if not file_path.exists() or file_path.stat().st_size == 0:
            candidates = sorted(
                [p for p in temp_dir.glob("source.*") if p.is_file()],
                key=lambda p: p.stat().st_size,
                reverse=True,
            )
            if candidates:
                file_path = candidates[0]

        if not file_path.exists() or file_path.stat().st_size == 0:
            raise RuntimeError(
                f"Downloaded file missing or empty (format={opts.get('format')})"
            )

        # Extract actual resolution/fps that was downloaded
        height, fps = 0, 0
        fmt_id = ""
        if isinstance(requested, list) and requested:
            for item in requested:
                if not isinstance(item, dict):
                    continue
                try:
                    height = max(height, int(float(item.get("height") or 0)))
                except Exception:
                    pass
                try:
                    fps = max(fps, int(float(item.get("fps") or 0)))
                except Exception:
                    pass
                fid = str(item.get("format_id") or "").strip()
                if fid:
                    fmt_id = fid
        if not height:
            try:
                height = int(float(info.get("height") or 0))
            except Exception:
                pass
        if not fps:
            try:
                fps = int(float(info.get("fps") or 0))
            except Exception:
                pass

        # Reject silently-low-quality results so the next attempt can try
        if height and height < 480:
            raise RuntimeError(
                f"Got only {height}p — rejecting, trying next strategy"
            )

        return {
            "title": title,
            "slug": slugify(title),
            "duration": duration,
            "filepath": str(file_path),
            "thumbnail": info.get("thumbnail"),
            "selected_height": height,
            "selected_fps": fps,
            "selected_format": fmt_id,
        }

    def _cleanup_partial():
        for p in temp_dir.glob("source*"):
            try:
                if p.is_file() and p.stat().st_size == 0:
                    p.unlink(missing_ok=True)
            except Exception:
                pass

    last_err: Exception | None = None

    for client_kwargs, fmt in attempts:
        opts = {**common, **client_kwargs, "format": fmt}
        client_name = (
            (client_kwargs.get("extractor_args") or {})
            .get("youtube", {})
            .get("player_client", ["auto"])[0]
        )
        try:
            result = _try_download(opts)
            h = result.get("selected_height", 0)
            fps_val = result.get("selected_fps", 0)
            logger.info(
                "Download OK | client=%s | format=%s | %dp%s",
                client_name, fmt[:60], h, f"@{fps_val}fps" if fps_val else "",
            )
            return result
        except Exception as exc:
            logger.warning(
                "Download attempt failed | client=%s | format=%s | %s",
                client_name, fmt[:60], exc,
            )
            last_err = exc
            _cleanup_partial()

    if isinstance(last_err, DownloadError):
        raise RuntimeError(str(last_err)) from last_err
    if last_err:
        raise RuntimeError(
            f"Download failed after all fallback strategies: {last_err}"
        ) from last_err
    raise RuntimeError("Download failed with unknown error")
