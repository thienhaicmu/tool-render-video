import logging
import os
import re
from pathlib import Path
from urllib.parse import urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError

from app.services.bin_paths import ensure_ffmpeg_available

logger = logging.getLogger(__name__)

SUPPORTED_PUBLIC_SOURCES = {"youtube", "facebook", "instagram"}


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")[:80] or "video"


def _ensure_ffmpeg_on_path() -> str:
    """Add ffmpeg dir to PATH once and return the binary path."""
    ffmpeg_bin = ensure_ffmpeg_available()
    ffmpeg_dir = str(Path(ffmpeg_bin).parent)
    current_path = os.environ.get("PATH", "")
    if ffmpeg_dir not in current_path.split(os.pathsep):
        os.environ["PATH"] = ffmpeg_dir + os.pathsep + current_path
    return ffmpeg_bin


def detect_public_video_source(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return "unknown"
    try:
        host = (urlparse(raw).hostname or "").lower()
    except Exception:
        return "unknown"
    host = host[4:] if host.startswith("www.") else host
    if host in {"youtube.com", "youtu.be", "m.youtube.com", "youtube-nocookie.com"} or host.endswith(".youtube.com") or host.endswith(".youtube-nocookie.com"):
        return "youtube"
    if host in {"facebook.com", "fb.watch", "m.facebook.com"} or host.endswith(".facebook.com"):
        return "facebook"
    if host in {"instagram.com", "instagr.am", "www.instagram.com"} or host.endswith(".instagram.com"):
        return "instagram"
    return "unknown"


def _resolve_download_filepath(info: dict, temp_dir: Path) -> Path:
    requested = info.get("requested_downloads") or []
    filepath = requested[0].get("filepath") or "" if requested else ""
    if not filepath:
        with YoutubeDL({"quiet": True}) as ydl2:
            filepath = ydl2.prepare_filename(info)
    file_path = Path(filepath)
    if not file_path.exists() or file_path.stat().st_size == 0:
        candidates = sorted(
            [p for p in temp_dir.glob("*") if p.is_file()],
            key=lambda p: p.stat().st_size,
            reverse=True,
        )
        if candidates:
            file_path = candidates[0]
    if not file_path.exists() or file_path.stat().st_size == 0:
        raise RuntimeError("Downloaded file missing or empty")
    return file_path


def download_public_video(url: str, temp_dir: Path, progress_callback=None) -> dict:
    source = detect_public_video_source(url)
    if source not in SUPPORTED_PUBLIC_SOURCES:
        raise RuntimeError("Unsupported link")

    temp_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = _ensure_ffmpeg_on_path()

    def _progress_hook(data: dict):
        if not progress_callback:
            return
        status = str(data.get("status") or "").lower()
        if status == "downloading":
            total = float(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
            downloaded = float(data.get("downloaded_bytes") or 0)
            pct = int((downloaded / total) * 100) if total > 0 else 0
            progress_callback(min(99, max(1, pct)), "Downloading")
        elif status == "finished":
            progress_callback(99, "Finalizing file")

    opts = {
        "outtmpl": str(temp_dir / "%(title).80s [%(id)s].%(ext)s"),
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_bin,
        "prefer_ffmpeg": True,
        "merge_output_format": "mp4",
        "format": "bv*+ba/b/best",
        "format_sort": ["proto:https", "proto:http"],
        "concurrent_fragment_downloads": 4,
        "retries": 8,
        "fragment_retries": 8,
        "extractor_retries": 4,
        "file_access_retries": 4,
        "quiet": True,
        "no_warnings": False,
        "progress_hooks": [_progress_hook],
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        },
    }

    cookiefile = (os.getenv("YTDLP_COOKIEFILE", "") or "").strip()
    if cookiefile:
        p = Path(cookiefile).expanduser()
        if p.is_file():
            opts["cookiefile"] = str(p)

    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
        file_path = _resolve_download_filepath(info, temp_dir)
        return {
            "source": source,
            "title": info.get("title") or file_path.stem,
            "slug": slugify(info.get("title") or file_path.stem),
            "duration": int(info.get("duration") or 0),
            "filepath": str(file_path),
            "thumbnail": info.get("thumbnail"),
            "extractor": str(info.get("extractor_key") or source),
            "webpage_url": str(info.get("webpage_url") or url),
        }
    except DownloadError as exc:
        raise RuntimeError(str(exc)) from exc


_IOS = {"extractor_args": {"youtube": {"player_client": ["ios"]}}}
_ANDROID = {"extractor_args": {"youtube": {"player_client": ["android"]}}}
_TV = {"extractor_args": {"youtube": {"player_client": ["tv_embedded"]}}}


def check_youtube_download_health(url: str) -> dict:
    """
    Probe a YouTube URL without downloading to check availability and max resolution.
    Uses ios client (only reliable client without PO Token as of 2026-04).
    """
    _ensure_ffmpeg_on_path()

    clients = [
        ("ios", _IOS),
        ("android", _ANDROID),
        ("tv_embedded", _TV),
        ("auto", {}),
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

    Priority order (tested 2026-04-13):
      1. ios  -> adaptive A/V with <=1080p target
      2. ios  -> adaptive A/V without cap
      3. auto -> adaptive A/V with <=1080p target
      4. auto -> adaptive A/V without cap
      5. auto -> progressive fallback
      6. auto -> best (last resort)

    All adaptive streams are merged to mp4 via ffmpeg.
    """
    temp_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg_bin = _ensure_ffmpeg_on_path()
    attempts = [
        (_IOS, "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"),
        (_IOS, "bv*+ba/b"),
        (_ANDROID, "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"),
        (_ANDROID, "bv*+ba/b"),
        (_TV, "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"),
        (_TV, "bv*+ba/b"),
        ({}, "bv*[height<=1080]+ba/b[height<=1080]/bv*+ba/b"),
        ({}, "bv*+ba/b"),
        ({}, "b[height<=1080]/b"),
        ({}, "best"),
    ]

    common = {
        "outtmpl": str(temp_dir / "source.%(ext)s"),
        "noplaylist": True,
        "ffmpeg_location": ffmpeg_bin,
        "prefer_ffmpeg": True,
        # merge adaptive video+audio streams into a single mp4
        "merge_output_format": "mp4",
        # prefer DASH (https direct) over HLS (m3u8) - HLS fragments often return empty
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
                f"Got only {height}p - rejecting, trying next strategy"
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

    def _probe_info(client_kwargs: dict) -> dict:
        probe_opts = {
            "skip_download": True,
            "quiet": True,
            "noplaylist": True,
            "extractor_retries": 2,
            **client_kwargs,
        }
        if cookiefile:
            probe_opts["cookiefile"] = common["cookiefile"]
        with YoutubeDL(probe_opts) as ydl:
            return ydl.extract_info(url, download=False)

    def _dynamic_format_candidates(info: dict) -> list[str]:
        formats = [f for f in (info.get("formats") or []) if isinstance(f, dict)]
        videos = [
            f for f in formats
            if str(f.get("vcodec") or "none").lower() != "none"
            and str(f.get("acodec") or "none").lower() == "none"
            and f.get("format_id")
        ]
        audios = [
            f for f in formats
            if str(f.get("acodec") or "none").lower() != "none"
            and str(f.get("vcodec") or "none").lower() == "none"
            and f.get("format_id")
        ]
        progressive = [
            f for f in formats
            if str(f.get("vcodec") or "none").lower() != "none"
            and str(f.get("acodec") or "none").lower() != "none"
            and f.get("format_id")
        ]
        videos = sorted(videos, key=lambda x: (int(float(x.get("height") or 0)), int(float(x.get("fps") or 0))), reverse=True)
        audios = sorted(audios, key=lambda x: int(float(x.get("abr") or 0)), reverse=True)
        progressive = sorted(progressive, key=lambda x: (int(float(x.get("height") or 0)), int(float(x.get("fps") or 0))), reverse=True)

        out: list[str] = []
        if videos and audios:
            # best adaptive
            out.append(f"{videos[0]['format_id']}+{audios[0]['format_id']}")
            # cap to <=1080 if available
            v1080 = next((v for v in videos if int(float(v.get("height") or 0)) <= 1080), None)
            if v1080:
                out.append(f"{v1080['format_id']}+{audios[0]['format_id']}")
        if progressive:
            out.append(str(progressive[0]["format_id"]))
            p1080 = next((p for p in progressive if int(float(p.get("height") or 0)) <= 1080), None)
            if p1080:
                out.append(str(p1080["format_id"]))
        # final generic fallbacks
        out.extend(["bv*+ba/b", "best"])
        # de-dup keep order
        seen = set()
        deduped: list[str] = []
        for f in out:
            if f and f not in seen:
                deduped.append(f)
                seen.add(f)
        return deduped

    def _cleanup_partial():
        """Remove ALL source* files so the next attempt starts clean."""
        for p in temp_dir.glob("source*"):
            try:
                if p.is_file():
                    p.unlink(missing_ok=True)
            except Exception:
                pass

    last_err: Exception | None = None

    unavailable_requested = False
    attempted_formats: list[str] = []

    for idx, (client_kwargs, fmt) in enumerate(attempts, start=1):
        opts = {**common, **client_kwargs}
        if fmt:
            opts["format"] = fmt
            attempted_formats.append(fmt)
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
                "Download OK | attempt=%d/%d | client=%s | format=%s | %dp%s%s",
                idx, len(attempts), client_name, fmt[:60], h, f"@{fps_val}fps" if fps_val else "",
                f" (after {idx-1} retries)" if idx > 1 else "",
            )
            return result
        except Exception as exc:
            msg = str(exc)
            if "Requested format is not available" in msg:
                unavailable_requested = True
            logger.warning(
                "Download attempt failed (will retry) | attempt=%d/%d | client=%s | format=%s | reason=%s",
                idx, len(attempts), client_name, fmt[:60], msg,
            )
            last_err = exc
            _cleanup_partial()

    # Dynamic fallback: probe available formats and retry with concrete format IDs.
    if unavailable_requested:
        dynamic_attempts: list[tuple[dict, str]] = []
        for client_kwargs in (_IOS, _ANDROID, _TV, {}):
            try:
                info = _probe_info(client_kwargs)
                for fmt in _dynamic_format_candidates(info):
                    dynamic_attempts.append((client_kwargs, fmt))
            except Exception as exc:
                logger.warning("Dynamic probe failed | client=%s | %s",
                               ((client_kwargs.get("extractor_args") or {}).get("youtube", {}).get("player_client", ["auto"])[0]),
                               exc)
        # de-dup attempts while preserving order
        seen_pairs = set()
        dynamic_unique: list[tuple[dict, str]] = []
        for ck, fmt in dynamic_attempts:
            cname = ((ck.get("extractor_args") or {}).get("youtube", {}).get("player_client", ["auto"])[0])
            key = (cname, fmt)
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            dynamic_unique.append((ck, fmt))

        for idx, (client_kwargs, fmt) in enumerate(dynamic_unique[:8], start=1):
            opts = {**common, **client_kwargs, "format": fmt}
            client_name = (
                (client_kwargs.get("extractor_args") or {})
                .get("youtube", {})
                .get("player_client", ["auto"])[0]
            )
            attempted_formats.append(fmt)
            try:
                result = _try_download(opts)
                h = result.get("selected_height", 0)
                fps_val = result.get("selected_fps", 0)
                logger.info(
                    "Dynamic download OK | attempt=%d/%d | client=%s | format=%s | %dp%s%s",
                    idx, min(8, len(dynamic_unique)), client_name, fmt[:60], h, f"@{fps_val}fps" if fps_val else "",
                    f" (after {idx-1} retries)" if idx > 1 else "",
                )
                return result
            except Exception as exc:
                logger.warning(
                    "Dynamic download failed (will retry) | attempt=%d/%d | client=%s | format=%s | reason=%s",
                    idx, min(8, len(dynamic_unique)), client_name, fmt[:60], exc,
                )
                last_err = exc
                _cleanup_partial()

    last_err_text = str(last_err or "")
    extract_fail = "Failed to extract any player response" in last_err_text
    if isinstance(last_err, DownloadError):
        if extract_fail:
            cookie_hint = (
                "Add valid cookies via YTDLP_COOKIEFILE and retry."
                if not cookiefile
                else "Verify your cookie file is valid/fresh and retry."
            )
            raise RuntimeError(
                "yt-dlp could not extract YouTube player response after trying ios/android/tv/auto clients. "
                f"{cookie_hint} Also ensure yt-dlp is up to date (`python -m pip install -U yt-dlp`). "
                f"Tried formats: {', '.join(attempted_formats[:12])}"
            ) from last_err
        raise RuntimeError(
            f"{last_err}. Tried formats: {', '.join(attempted_formats[:12])}"
        ) from last_err
    if last_err:
        raise RuntimeError(
            f"Download failed after all fallback strategies: {last_err}. Tried formats: {', '.join(attempted_formats[:12])}"
        ) from last_err
    raise RuntimeError("Download failed with unknown error")

