"""
enrichment.py — post-download asset enrichment pipeline.

Phase C — Asset Library. Runs in a background thread after a download
completes. Never raises — all exceptions are caught and logged.

Pipeline steps:
  1. ffprobe metadata (duration, width, height, fps, file_size_bytes)
  2. Whisper-tiny language detection (first 30s only, optional — skipped
     gracefully when the Whisper dependency is absent)
  3. Heuristic content_type classification based on duration
  4. Thumbnail extraction via FFmpeg at the 10% mark

Results are written back to the `assets` table via update_asset_enrichment().
If any individual step fails, the others still run and partial results
are still persisted.
"""
from __future__ import annotations

import logging
import os
import subprocess
import uuid
from pathlib import Path
from typing import Optional

logger = logging.getLogger("app.download.enrichment")


def enrich_asset(asset_id: str, file_path: str) -> None:
    """Enrich the asset row with ffprobe metadata, language, and thumbnail.

    Never raises. Designed to run in a background ThreadPoolExecutor thread
    so it does not block the download response.
    """
    try:
        _do_enrich(asset_id, file_path)
    except Exception:
        logger.warning(
            "enrichment: unexpected error asset_id=%s file=%s",
            asset_id, file_path, exc_info=True,
        )


def _do_enrich(asset_id: str, file_path: str) -> None:
    path = Path(file_path)
    if not path.is_file():
        logger.warning("enrichment: file not found asset_id=%s path=%s", asset_id, file_path)
        return

    probe = _ffprobe_metadata(file_path)
    language = _detect_language(file_path, probe.get("duration") or 0.0)
    content_type = _heuristic_content_type(probe.get("duration") or 0.0)
    thumbnail_path = _extract_thumbnail(file_path, probe.get("duration") or 0.0)
    file_size_bytes = _file_size(path)

    from app.db.assets_repo import update_asset_enrichment
    update_asset_enrichment(
        asset_id=asset_id,
        duration_sec=probe.get("duration") or 0.0,
        width=probe.get("width") or 0,
        height=probe.get("height") or 0,
        fps=probe.get("fps") or 0.0,
        file_size_bytes=file_size_bytes,
        language=language,
        content_type=content_type,
        thumbnail_path=thumbnail_path,
    )
    logger.info(
        "enrichment: done asset_id=%s dur=%.1fs lang=%s ctype=%s thumb=%s",
        asset_id, probe.get("duration") or 0.0, language, content_type, thumbnail_path,
    )


# ── Step 1: ffprobe metadata ──────────────────────────────────────────────────

def _ffprobe_metadata(file_path: str) -> dict:
    """Run ffprobe and return {duration, width, height, fps}. Returns empty dict on error."""
    try:
        from app.services.bin_paths import get_ffprobe_bin
        import json

        cmd = [
            get_ffprobe_bin(), "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,avg_frame_rate,r_frame_rate,width,height",
            "-of", "json", str(file_path),
        ]
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=30)
        if r.returncode != 0:
            logger.warning("enrichment: ffprobe failed for %s: %s", file_path, r.stderr[:200])
            return {}

        data = json.loads(r.stdout or "{}")
        result: dict = {"duration": None, "width": 0, "height": 0, "fps": 0.0}

        fmt = data.get("format", {})
        try:
            raw_dur = fmt.get("duration")
            if raw_dur:
                result["duration"] = float(raw_dur)
        except (ValueError, TypeError):
            pass

        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video":
                try:
                    result["width"] = int(stream.get("width") or 0)
                    result["height"] = int(stream.get("height") or 0)
                except (ValueError, TypeError):
                    pass
                fps_str = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or ""
                if "/" in fps_str:
                    n, d = fps_str.split("/", 1)
                    try:
                        result["fps"] = round(float(n) / float(d), 3) if float(d) else 0.0
                    except (ValueError, ZeroDivisionError):
                        pass
                break

        return result
    except Exception:
        logger.warning("enrichment: _ffprobe_metadata error for %s", file_path, exc_info=True)
        return {}


# ── Step 2: language detection ────────────────────────────────────────────────

def _detect_language(file_path: str, duration_sec: float) -> str:
    """Detect spoken language from first 30s using Whisper tiny. Returns '' on failure."""
    if duration_sec <= 0:
        return ""
    try:
        import whisper as _whisper  # type: ignore[import]
        model = _whisper.load_model("tiny")
        result = model.transcribe(file_path, language=None, task="detect", duration=30.0)
        lang = (result.get("language") or "").strip().lower()
        logger.info("enrichment: language=%r for %s", lang, file_path)
        return lang
    except ImportError:
        return ""
    except Exception:
        logger.warning("enrichment: language detection error for %s", file_path, exc_info=True)
        return ""


# ── Step 3: heuristic content_type ───────────────────────────────────────────

def _heuristic_content_type(duration_sec: float) -> str:
    """Simple duration-based content_type estimate. Override with AI in future sprints."""
    if duration_sec <= 0:
        return ""
    if duration_sec < 90:
        return "short_clip"
    if duration_sec < 600:
        return "vlog"
    return "long_form"


# ── Step 4: thumbnail extraction ──────────────────────────────────────────────

def _extract_thumbnail(file_path: str, duration_sec: float) -> Optional[str]:
    """Extract a thumbnail at the 10% mark. Returns the thumbnail path or None."""
    try:
        from app.services.bin_paths import get_ffmpeg_bin
        from app.core.config import CACHE_DIR

        thumb_dir = CACHE_DIR / "asset_thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)
        thumb_path = thumb_dir / f"{uuid.uuid4().hex}.jpg"

        seek = max(0.0, (duration_sec or 10.0) * 0.10)
        cmd = [
            get_ffmpeg_bin(),
            "-ss", str(round(seek, 2)),
            "-i", str(file_path),
            "-frames:v", "1",
            "-q:v", "4",
            "-vf", "scale=320:-2",
            "-y", str(thumb_path),
        ]
        r = subprocess.run(cmd, capture_output=True, timeout=20)
        if r.returncode == 0 and thumb_path.is_file():
            return str(thumb_path)
        logger.warning("enrichment: thumbnail extraction failed for %s", file_path)
        return None
    except Exception:
        logger.warning("enrichment: _extract_thumbnail error for %s", file_path, exc_info=True)
        return None


# ── Utility ───────────────────────────────────────────────────────────────────

def _file_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except Exception:
        return 0
