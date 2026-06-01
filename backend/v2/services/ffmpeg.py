"""
ffmpeg.py — FFmpeg/FFprobe wrapper cho v2.

Binary discovery delegate sang v1 bin_paths (WinGet, packaged EXE, PATH) —
không duplicate logic phức tạp đó.

Public API:
    get_ffmpeg_bin()       -> str
    get_ffprobe_bin()      -> str
    safe_filter_path(path) -> str
    probe_video(path)      -> VideoProbe
    execute_ffmpeg(args)   -> None  (raise nếu rc != 0)
"""
from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from v2.core.constants import FFMPEG_TIMEOUT_SEC


# ── Binary resolution — delegate to v1 ───────────────────────────────────────

def get_ffmpeg_bin() -> str:
    """Trả về đường dẫn ffmpeg binary. Ưu tiên: env var > packaged > PATH > WinGet."""
    try:
        from app.services.bin_paths import get_ffmpeg_bin as _v1_get
        return _v1_get()
    except ImportError:
        import shutil
        return shutil.which("ffmpeg") or "ffmpeg"


def get_ffprobe_bin() -> str:
    """Trả về đường dẫn ffprobe binary."""
    try:
        from app.services.bin_paths import get_ffprobe_bin as _v1_get
        return _v1_get()
    except ImportError:
        import shutil
        return shutil.which("ffprobe") or "ffprobe"


# ── Path safety ───────────────────────────────────────────────────────────────

def safe_filter_path(path: Path) -> str:
    """Escape path để dùng an toàn trong FFmpeg filter graph argument."""
    return str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")


# ── Probe ─────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class VideoStream:
    width:     int
    height:    int
    fps:       float
    codec:     str
    duration:  float   # giây


@dataclass(frozen=True)
class AudioStream:
    codec:     str
    channels:  int
    sample_rate: int


@dataclass(frozen=True)
class VideoProbe:
    duration:     float
    video:        Optional[VideoStream]
    audio:        Optional[AudioStream]
    format_name:  str = ""

    @property
    def has_video(self) -> bool:
        return self.video is not None

    @property
    def has_audio(self) -> bool:
        return self.audio is not None


def probe_video(path: Path) -> VideoProbe:
    """
    Dùng ffprobe lấy metadata video.
    Raise RuntimeError nếu file không đọc được hoặc ffprobe thất bại.
    """
    cmd = [
        get_ffprobe_bin(),
        "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        "-show_format",
        str(path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed (rc={result.returncode}): {result.stderr[:300]}"
        )

    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    fmt = data.get("format") or {}

    # Duration: prefer format-level, fallback to video stream
    duration = float(fmt.get("duration") or 0.0)

    video_stream: Optional[VideoStream] = None
    audio_stream: Optional[AudioStream] = None

    for s in streams:
        codec_type = str(s.get("codec_type") or "").lower()

        if codec_type == "video" and video_stream is None:
            # Parse FPS từ "avg_frame_rate" = "30000/1001" hoặc "30/1"
            fps = _parse_fps(s.get("avg_frame_rate") or s.get("r_frame_rate") or "0")
            stream_dur = float(s.get("duration") or duration or 0.0)
            if not duration:
                duration = stream_dur
            video_stream = VideoStream(
                width=int(s.get("width") or 0),
                height=int(s.get("height") or 0),
                fps=fps,
                codec=str(s.get("codec_name") or ""),
                duration=stream_dur,
            )

        elif codec_type == "audio" and audio_stream is None:
            audio_stream = AudioStream(
                codec=str(s.get("codec_name") or ""),
                channels=int(s.get("channels") or 0),
                sample_rate=int(s.get("sample_rate") or 0),
            )

    return VideoProbe(
        duration=duration,
        video=video_stream,
        audio=audio_stream,
        format_name=str(fmt.get("format_name") or ""),
    )


# ── Execute ───────────────────────────────────────────────────────────────────

def execute_ffmpeg(args: list[str], timeout: int = FFMPEG_TIMEOUT_SEC) -> None:
    """
    Chạy FFmpeg với args đã build sẵn. Raise RuntimeError nếu rc != 0.
    Không pass shell=True — luôn dùng list args để tránh injection.
    """
    cmd = [get_ffmpeg_bin()] + args
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (rc={result.returncode}): {result.stderr[-500:]}"
        )


# ── Internal ──────────────────────────────────────────────────────────────────

def _parse_fps(fps_str: str) -> float:
    """Parse '30000/1001' hoặc '30' → float."""
    try:
        if "/" in fps_str:
            num, den = fps_str.split("/", 1)
            den_val = float(den)
            return float(num) / den_val if den_val else 0.0
        return float(fps_str)
    except Exception:
        return 0.0
