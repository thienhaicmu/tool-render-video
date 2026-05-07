from __future__ import annotations

import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path


def _is_file(path: str | None) -> bool:
    return bool(path) and Path(path).is_file()


def _packaged_ffmpeg_candidates() -> list[Path]:
    """Return ordered candidate paths to check when running as a PyInstaller bundle.

    Layout produced by build-offline-exe.ps1 (onedir mode):
      <resources>/backend-bin/render-backend.exe   ← sys.executable
      <resources>/ffmpeg-bin/ffmpeg.exe             ← bundled ffmpeg

    Also checks the EXE directory itself for standalone portable layouts.
    """
    if not getattr(sys, "frozen", False):
        return []
    exe_dir = Path(sys.executable).parent
    return [
        exe_dir / "ffmpeg.exe",                        # beside EXE (flat layout)
        exe_dir / "ffmpeg-bin" / "ffmpeg.exe",         # sub-dir of EXE dir
        exe_dir.parent / "ffmpeg-bin" / "ffmpeg.exe",  # sibling of backend-bin/
    ]


def _packaged_ffprobe_candidates() -> list[Path]:
    if not getattr(sys, "frozen", False):
        return []
    exe_dir = Path(sys.executable).parent
    return [
        exe_dir / "ffprobe.exe",
        exe_dir / "ffmpeg-bin" / "ffprobe.exe",
        exe_dir.parent / "ffmpeg-bin" / "ffprobe.exe",
    ]


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
    # 1. Explicit env override
    env = os.environ.get("FFMPEG_BIN")
    if _is_file(env):
        return str(Path(env))

    # 2. Packaged-EXE layout (checked before PATH to prefer bundled binary)
    for candidate in _packaged_ffmpeg_candidates():
        if candidate.is_file():
            return str(candidate)

    # 3. System PATH
    found = shutil.which("ffmpeg")
    if found:
        return found

    # 4. WinGet install location
    winget_dir = _winget_ffmpeg_bin_dir()
    if winget_dir:
        candidate = Path(winget_dir) / "ffmpeg.exe"
        if candidate.is_file():
            return str(candidate)

    # 5. Bare fallback — subprocess will raise if truly missing
    return "ffmpeg"


@lru_cache(maxsize=1)
def get_ffprobe_bin() -> str:
    env = os.environ.get("FFPROBE_BIN")
    if _is_file(env):
        return str(Path(env))

    for candidate in _packaged_ffprobe_candidates():
        if candidate.is_file():
            return str(candidate)

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
