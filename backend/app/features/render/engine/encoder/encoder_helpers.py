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
            capture_output=True, text=True, encoding="utf-8", check=True, timeout=30,
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
        proc = subprocess.run(probe_cmd, capture_output=True, text=True, encoding="utf-8")
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


@lru_cache(maxsize=2)
def qsv_runtime_ready(codec_name: str) -> bool:
    """Probe whether Intel Quick Sync (QSV) can actually open an encode session.
    Strict: only True when a tiny test encode succeeds (rc==0). Mirrors
    nvenc_runtime_ready but conservative — QSV is opt-in so a false negative
    just keeps the safe CPU path."""
    try:
        proc = subprocess.run(
            [
                get_ffmpeg_bin(), "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=256x256:d=0.1",
                "-an", "-c:v", codec_name, "-f", "null", "-",
            ],
            capture_output=True, text=True, encoding="utf-8",
        )
        return proc.returncode == 0
    except Exception:
        return False


def qsv_enabled() -> bool:
    """QSV mặc định BẬT — chuỗi resolver là card-first: NVENC → QSV → CPU
    (quyết định chủ dự án 2026-07: "mặc định dùng card, không có thì về
    CPU"). An toàn: ``qsv_runtime_ready`` probe thật trước khi chọn, máy
    không có iGPU Intel hoặc driver hỏng tự rơi về libx264. Tắt khẩn cấp
    bằng ``ENABLE_QSV=0``. Đọc tại call time để test/env toggle có hiệu lực."""
    return os.getenv("ENABLE_QSV", "1").strip() == "1"


def _maybe_qsv(c: str) -> str | None:
    """Shared QSV decision used by BOTH resolvers (encoder_helpers.resolve_encoder
    and ffmpeg_helpers._resolve_codec) so they can never diverge — see
    tests/test_nvenc_codec_resolver_parity.py. Returns the QSV codec name when
    QSV is enabled AND available for this codec, else None (caller continues to
    the CPU fallback)."""
    if not qsv_enabled():
        return None
    if c == "h265":
        return "hevc_qsv" if has_encoder("hevc_qsv") and qsv_runtime_ready("hevc_qsv") else None
    return "h264_qsv" if has_encoder("h264_qsv") and qsv_runtime_ready("h264_qsv") else None


def resolve_encoder(codec: str, encoder_mode: str = "auto") -> str:
    """Return the best available FFmpeg video encoder for the given codec/mode pair.

    Order: NVENC (if auto/nvenc) → QSV (default ON, ENABLE_QSV=0 tắt) →
    libx264/libx265 CPU fallback. Mỗi bậc đều probe runtime thật.
    """
    c = (codec or "h264").lower()
    mode = (encoder_mode or "auto").lower()
    if mode in ("auto", "nvenc"):
        if c == "h265" and has_encoder("hevc_nvenc") and nvenc_runtime_ready("hevc_nvenc"):
            return "hevc_nvenc"
        if c != "h265" and has_encoder("h264_nvenc") and nvenc_runtime_ready("h264_nvenc"):
            return "h264_nvenc"
    _qsv = _maybe_qsv(c)
    if _qsv:
        return _qsv
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
    if c in ("h264_qsv", "hevc_qsv"):
        # QSV accepts veryfast..veryslow directly; clamp ultra/superfast.
        valid = {"veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"}
        return p if p in valid else "medium"
    return p


def gpu_pacing_flags(video_codec: str, encoder_mode: str = "auto") -> list[str] | None:
    """Cờ encoder phần cứng cho pass re-encode của micro-pacing (mục tiêu
    chất lượng tương đương legacy libx264 crf17: NVENC cq 17 / QSV
    global_quality 17, preset ~ medium).

    Trả ``None`` khi máy/job resolve ra encoder CPU — caller (clip_ops)
    giữ cờ CPU legacy. Nhận cả NVENC lẫn QSV (iGPU Intel) theo luật
    card-first của resolver; QSV không cần NVENC_SEMAPHORE. Literal codec
    phần cứng sống ở file này (resolver) để clip_ops giữ đúng phân loại
    false-positive trong tests/test_nvenc_semaphore_external_acquire.py.
    """
    resolved = resolve_encoder(video_codec or "h264", encoder_mode or "auto")
    if resolved not in ("h264_nvenc", "hevc_nvenc", "h264_qsv", "hevc_qsv"):
        return None
    return [
        "-c:v", resolved,
        "-preset", map_preset_for_encoder("medium", resolved),
        *codec_extra_flags(resolved, 17, "medium"),
    ]


def codec_extra_flags(
    resolved_codec: str,
    video_crf: int,
    video_preset: str = "slow",
    maxrate_m: int = 20,
    bufsize_m: int = 40,
) -> list[str]:
    """Return the encoder-specific FFmpeg flags for the given resolved codec.

    NVENC paths include -maxrate/-bufsize for delivery-safe constrained VBR.
    CPU paths (libx264/libx265) use CRF + preset-tiered x264/x265 params.
    """
    c = (resolved_codec or "").lower()
    p = (video_preset or "slow").lower()
    if c == "hevc_nvenc":
        return [
            "-rc", "vbr_hq", "-cq", str(video_crf), "-b:v", "0",
            "-maxrate", f"{maxrate_m}M", "-bufsize", f"{bufsize_m}M",
            "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
            "-rc-lookahead", "32", "-bf", "4",
        ]
    if c == "h264_nvenc":
        return [
            "-rc", "vbr_hq", "-cq", str(video_crf), "-b:v", "0",
            "-maxrate", f"{maxrate_m}M", "-bufsize", f"{bufsize_m}M",
            "-spatial_aq", "1", "-temporal_aq", "1", "-aq-strength", "8",
            "-rc-lookahead", "32", "-bf", "3",
        ]
    if c in ("h264_qsv", "hevc_qsv"):
        # Intel QSV: ICQ (intelligent constant quality) via -global_quality,
        # mapped from the CRF target. Look-ahead improves quality at a small
        # speed cost. Constrained by the same delivery maxrate/bufsize. QSV runs
        # on the iGPU — no NVENC semaphore needed (not an NVENC codec).
        flags = [
            "-global_quality", str(video_crf),
            "-look_ahead", "1", "-look_ahead_depth", "40",
            "-maxrate", f"{maxrate_m}M", "-bufsize", f"{bufsize_m}M",
        ]
        if c == "hevc_qsv":
            flags += ["-tag:v", "hvc1"]
        return flags
    if c == "libx265":
        if p in ("veryslow", "slower"):
            x265p = "aq-mode=3:aq-strength=1.0:deblock=-1,-1:rc-lookahead=60:ref=5:bframes=4:psy-rdoq=1.0:rdoq-level=2"
        elif p == "slow":
            x265p = "aq-mode=3:aq-strength=0.8:deblock=-1,-1:rc-lookahead=40:ref=4:bframes=4"
        else:
            x265p = "aq-mode=2:rc-lookahead=20:ref=3:bframes=3"
        return [
            "-crf", str(video_crf), "-maxrate", f"{maxrate_m}M", "-bufsize", f"{bufsize_m}M",
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
        "-maxrate", f"{maxrate_m}M", "-bufsize", f"{bufsize_m}M",
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
        here.parents[4] / "fonts",
        here.parents[5] / "fonts",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None
