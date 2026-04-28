from __future__ import annotations

import os
import shutil
from functools import lru_cache
from pathlib import Path


def _is_file(path: str | None) -> bool:
    return bool(path) and Path(path).is_file()


@lru_cache(maxsize=1)
def _winget_ffmpeg_bin_dir() -> str | None:
    local = os.environ.get("LOCALAPPDATA", "")
    if not local:
        return None
    root = Path(local) / "Microsoft" / "WinGet" / "Packages"
    if not root.exists():
        return None
    for ffmpeg_exe in root.glob("Gyan.FFmpeg_*/*/bin/ffmpeg.exe"):
        if ffmpeg_exe.is_file():
            return str(ffmpeg_exe.parent)
    return None


@lru_cache(maxsize=1)
def get_ffmpeg_bin() -> str:
    env = os.environ.get("FFMPEG_BIN")
    if _is_file(env):
        return str(Path(env))

    found = shutil.which("ffmpeg")
    if found:
        return found

    winget_dir = _winget_ffmpeg_bin_dir()
    if winget_dir:
        candidate = Path(winget_dir) / "ffmpeg.exe"
        if candidate.is_file():
            return str(candidate)

    return "ffmpeg"


@lru_cache(maxsize=1)
def get_ffprobe_bin() -> str:
    env = os.environ.get("FFPROBE_BIN")
    if _is_file(env):
        return str(Path(env))

    found = shutil.which("ffprobe")
    if found:
        return found

    winget_dir = _winget_ffmpeg_bin_dir()
    if winget_dir:
        candidate = Path(winget_dir) / "ffprobe.exe"
        if candidate.is_file():
            return str(candidate)

    return "ffprobe"


def ensure_ffmpeg_available() -> str:
    ffmpeg_bin = get_ffmpeg_bin()
    if ffmpeg_bin == "ffmpeg":
        raise RuntimeError(
            "ffmpeg is not installed or not detected. Install ffmpeg and restart backend "
            "(Windows: winget install -e --id Gyan.FFmpeg)."
        )
    return ffmpeg_bin


def _summarize_ffmpeg_stderr(stderr: str) -> str:
    lower = stderr.lower()
    if "no space left on device" in lower:
        return "Disk is full or temp/output drive has no free space."
    if "permission denied" in lower:
        return "Permission denied while reading input or writing output."
    if "invalid data found" in lower or "moov atom not found" in lower:
        return "Input video appears corrupt or unsupported."
    if "no such file or directory" in lower:
        return "Input or output path does not exist."
    if "could not write header" in lower:
        return "FFmpeg could not write the output file/header."
    if "encoder" in lower and ("not found" in lower or "unknown encoder" in lower):
        return "Requested encoder is unavailable."
    if "error while opening encoder" in lower:
        return "FFmpeg failed to open the encoder with the selected settings."
    return "FFmpeg failed. See stderr tail for details."
