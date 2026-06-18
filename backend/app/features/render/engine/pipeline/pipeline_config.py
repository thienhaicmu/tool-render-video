"""pipeline_config.py — Profile resolution, path helpers, and video probing.

Extracted from render_pipeline.py (lines 985–1117) as part of C-1 decomposition.
All logic is identical — this is a mechanical lift, not a rewrite.
"""

import logging
import re
import subprocess
from pathlib import Path

from app.models.schemas import RenderRequest
from app.core.config import CHANNELS_DIR
from app.services.bin_paths import get_ffprobe_bin

logger = logging.getLogger("app.render")


def _resolve_profile(payload: RenderRequest):
    profile = (payload.render_profile or "quality").lower()
    defaults = {
        # fast: quick turnaround, acceptable quality — base keeps CPU transcription fast
        "fast":     {"video_preset": "veryfast", "video_crf": 23, "whisper_model": "base",     "transition_sec": 0.05},
        # balanced: good quality/speed — small keeps CPU latency acceptable (~30s vs 90-120s for large-v3)
        "balanced": {"video_preset": "medium",   "video_crf": 18, "whisper_model": "small",    "transition_sec": 0.06},
        # quality: high quality — large-v3 gives near-perfect transcript accuracy
        "quality":  {"video_preset": "slow",     "video_crf": 15, "whisper_model": "large-v3", "transition_sec": 0.06},
        # best: maximum quality — large-v3 is the ceiling for open-weight ASR
        "best":     {"video_preset": "slower",   "video_crf": 13, "whisper_model": "large-v3", "transition_sec": 0.08},
    }
    picked = defaults.get(profile, defaults["quality"])
    if payload.video_preset:
        logger.info("profile_override_used: video_preset=%s (profile=%s default=%s)", payload.video_preset, profile, picked["video_preset"])
    if payload.video_crf is not None:
        logger.info("profile_override_used: video_crf=%s (profile=%s default=%s)", payload.video_crf, profile, picked["video_crf"])
    whisper_model = payload.whisper_model
    if (whisper_model or "auto").lower() == "auto":
        whisper_model = picked["whisper_model"]
    return {
        "video_preset": payload.video_preset or picked["video_preset"],
        "video_crf": max(12, min(32, int(payload.video_crf or picked["video_crf"]))),
        "whisper_model": whisper_model,
        "transition_sec": max(0.0, min(1.5, float(payload.transition_sec if payload.transition_sec is not None else picked["transition_sec"]))),
    }


def _probe_video_duration(video_path: Path) -> int:
    cmd = [
        get_ffprobe_bin(),
        "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", check=True, timeout=30)
        return max(0, int(float((r.stdout or "0").strip() or 0)))
    except Exception:
        return 0


def extract_text_from_srt(srt_path: str) -> str:
    try:
        text_lines = []
        with open(srt_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                if re.match(r"^\d+$", line):
                    continue
                if "-->" in line:
                    continue
                text_lines.append(line)
        text = " ".join(text_lines)
        text = re.sub(r" {2,}", " ", text).strip()
        if text and text[-1] not in ".!?":
            text += "."
        return text
    except Exception:
        return ""


def _reserve_source_path_in_dir(source_dir: Path, slug: str, ext: str = ".mp4") -> Path:
    source_dir.mkdir(parents=True, exist_ok=True)
    base = source_dir / f"{slug}{ext}"
    if not base.exists():
        return base
    idx = 1
    while True:
        candidate = source_dir / f"{slug}_{idx}{ext}"
        if not candidate.exists():
            return candidate
        idx += 1


def _reserve_source_path(channel_code: str, slug: str, ext: str = ".mp4") -> Path:
    return _reserve_source_path_in_dir(CHANNELS_DIR / channel_code / "upload" / "source", slug, ext=ext)


def _sanitize_channel_subdir(value: str | None) -> str:
    raw = (value or "Video").strip().replace("\\", "/")
    raw = raw.strip("/")
    if not raw:
        return "Video"
    parts = [p for p in raw.split("/") if p not in ("", ".", "..")]
    safe = "/".join(parts).strip()
    return safe or "Video"


def _resolve_output_dir(channel_code: str, raw_output_dir: str, render_output_subdir: str | None = None) -> Path:
    raw = (raw_output_dir or "").strip()
    channel_base = (CHANNELS_DIR / channel_code).resolve()
    fallback = channel_base / _sanitize_channel_subdir(render_output_subdir)
    if not raw:
        return fallback

    norm = raw.replace("\\", "/")
    legacy_prefix = f"/data/channels/{channel_code}/"
    legacy_prefix_no_slash = f"data/channels/{channel_code}/"
    if norm.startswith(legacy_prefix):
        rel = norm[len(legacy_prefix):]
        return (channel_base / rel).resolve()
    if norm.startswith(legacy_prefix_no_slash):
        rel = norm[len(legacy_prefix_no_slash):]
        return (channel_base / rel).resolve()
    if norm.startswith("/data/channels/"):
        return fallback

    p = Path(raw)
    if p.is_absolute():
        return p
    return (Path.cwd() / p).resolve()
