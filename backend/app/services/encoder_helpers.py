"""
Shared FFmpeg encoder detection, preset mapping, and flag helpers.

render_engine.py and motion_crop.py both delegate to this module so that
encoder logic has a single source of truth.  This module imports only from
stdlib and app.services.bin_paths — no other app.services imports — so it
can be safely imported by both render_engine and motion_crop without creating
circular dependencies.
"""
from __future__ import annotations

import os
import subprocess
import logging
from functools import lru_cache
from pathlib import Path

from app.services.bin_paths import get_ffmpeg_bin

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def ffmpeg_encoders_text() -> str:
    try:
        r = subprocess.run(
            [get_ffmpeg_bin(), "-hide_banner", "-encoders"],
            capture_output=True, text=True, check=True,
        )
        return (r.stdout or "") + "\n" + (r.stderr or "")
    except Exception:
        return ""


def has_encoder(name: str) -> bool:
    return name in ffmpeg_encoders_text()


@lru_cache(maxsize=2)
def nvenc_runtime_ready(codec_name: str) -> bool:
    try:
        probe_cmd = [
            get_ffmpeg_bin(),
            "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
            "-an", "-c:v", codec_name, "-f", "null", "-",
        ]
        proc = subprocess.run(probe_cmd, capture_output=True, text=True)
        text = ((proc.stdout or "") + "\n" + (proc.stderr or "")).lower()
        if proc.returncode == 0:
            return True
        blockers = (
            "cannot load nvcuda.dll",
            "no nvenc capable devices found",
            "cannot init cuda",
            "operation not permitted",
        )
        return not any(b in text for b in blockers)
    except Exception:
        return False


def resolve_encoder(codec: str, encoder_mode: str = "auto") -> str:
    """Return the best available FFmpeg video encoder for the given codec/mode pair.

    Falls back to libx264/libx265 when NVENC is requested but unavailable.
    """
    c = (codec or "h264").lower()
    mode = (encoder_mode or "auto").lower()
    if mode in ("auto", "nvenc"):
        if c == "h265" and has_encoder("hevc_nvenc") and nvenc_runtime_ready("hevc_nvenc"):
            return "hevc_nvenc"
        if c != "h265" and has_encoder("h264_nvenc") and nvenc_runtime_ready("h264_nvenc"):
            return "h264_nvenc"
    if c == "h265":
        return "libx265"
    return "libx264"


def map_preset_for_encoder(video_preset: str, resolved_codec: str) -> str:
    c = (resolved_codec or "").lower()
    p = (video_preset or "slow").lower()
    if c in ("h264_nvenc", "hevc_nvenc"):
        mapping = {
            "ultrafast": "p2", "superfast": "p3", "veryfast": "p4",
            "faster": "p4", "fast": "p4", "medium": "p5",
            "slow": "p6", "slower": "p7", "veryslow": "p7",
        }
        return mapping.get(p, "p6")
    return p


def codec_extra_flags(resolved_codec: str, video_crf: int, video_preset: str = "slow") -> list[str]:
    """Return the encoder-specific FFmpeg flags for the given resolved codec.

    NVENC paths include -maxrate/-bufsize for delivery-safe constrained VBR.
    CPU paths (libx264/libx265) use CRF + preset-tiered x264/x265 params.
    """
    c = (resolved_codec or "").lower()
    p = (video_preset or "slow").lower()
    if c == "hevc_nvenc":
        return [
            "-rc", "vbr_hq", "-cq", str(video_crf), "-b:v", "0",
            "-maxrate", "20M", "-bufsize", "40M",
            "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
            "-rc-lookahead", "32", "-bf", "4",
        ]
    if c == "h264_nvenc":
        return [
            "-rc", "vbr_hq", "-cq", str(video_crf), "-b:v", "0",
            "-maxrate", "20M", "-bufsize", "40M",
            "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
            "-rc-lookahead", "32", "-bf", "3",
        ]
    if c == "libx265":
        if p in ("veryslow", "slower"):
            x265p = "aq-mode=3:aq-strength=1.0:deblock=-1,-1:rc-lookahead=60:ref=5:bframes=4:psy-rdoq=1.0:rdoq-level=2"
        elif p == "slow":
            x265p = "aq-mode=3:aq-strength=0.8:deblock=-1,-1:rc-lookahead=40:ref=4:bframes=4"
        else:
            x265p = "aq-mode=2:rc-lookahead=20:ref=3:bframes=3"
        return [
            "-crf", str(video_crf), "-maxrate", "20M", "-bufsize", "40M",
            "-tag:v", "hvc1", "-x265-params", x265p,
        ]
    # libx264 — tiered by preset
    if p in ("veryslow", "slower"):
        x264p = "ref=5:bframes=3:me=umh:subme=9:analyse=all:trellis=2:deblock=-1,-1:aq-mode=3:aq-strength=0.8:psy-rd=1.0:psy-rdoq=0.0"
    elif p == "slow":
        x264p = "ref=4:bframes=3:me=hex:subme=7:trellis=1:deblock=-1,-1:aq-mode=3:aq-strength=0.8:psy-rd=1.0"
    else:
        x264p = "ref=3:bframes=2:me=hex:subme=6:trellis=0:aq-mode=2"
    return [
        "-crf", str(video_crf),
        "-maxrate", "20M", "-bufsize", "40M",
        "-profile:v", "high", "-level:v", "5.1",
        "-tune", "film",
        "-x264-params", x264p,
    ]


def reup_video_filters() -> list[str]:
    return [
        "eq=contrast=1.04:saturation=1.10:brightness=0.01",
        "unsharp=5:5:0.45:3:3:0.0",
        "hqdn3d=1.2:1.2:6:6",
    ]


def reup_audio_filter() -> str:
    return (
        "highpass=f=120,"
        "lowpass=f=11000,"
        "acompressor=threshold=-16dB:ratio=2.2:attack=20:release=200:makeup=2,"
        "alimiter=limit=0.95"
    )


def safe_filter_path(path: str) -> str:
    return str(path).replace("\\", "/").replace(":", r"\:").replace("'", r"\'")


def detect_windows_fontfile() -> str | None:
    windir = os.environ.get("WINDIR")
    if not windir:
        return None
    fonts_dir = Path(windir) / "Fonts"
    for name in ("arial.ttf", "segoeui.ttf", "tahoma.ttf"):
        p = fonts_dir / name
        if p.exists():
            return str(p)
    return None


def detect_windows_fonts_dir() -> str | None:
    windir = os.environ.get("WINDIR")
    if not windir:
        return None
    p = Path(windir) / "Fonts"
    return str(p) if p.exists() else None


def get_custom_fonts_dir() -> str | None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "fonts",
        here.parents[3] / "fonts",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None
