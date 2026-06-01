"""
config.py — Tất cả environment variables, typed.

Quy tắc:
- Đọc từ os.getenv() tại import time
- Giá trị mặc định luôn là disabled/empty (không tự enable feature)
- Không có business logic ở đây
- Các module khác import trực tiếp: from v2.core.config import GROQ_API_KEY
"""
from __future__ import annotations

import os
from pathlib import Path

from v2.core.constants import (
    WHISPER_DEFAULT_MODEL,
    GROQ_DEFAULT_MODEL,
    MAX_CONCURRENT_PARTS,
)


# ── Groq ──────────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")
GROQ_MODEL:   str = os.getenv("GROQ_MODEL", GROQ_DEFAULT_MODEL)

# ── Whisper ───────────────────────────────────────────────────────────────────
WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", WHISPER_DEFAULT_MODEL)

# ── Paths ─────────────────────────────────────────────────────────────────────
APP_DATA_DIR: Path = Path(os.getenv("APP_DATA_DIR", "data"))
TEMP_DIR:     Path = Path(os.getenv("TEMP_DIR", str(APP_DATA_DIR / "temp")))
CACHE_DIR:    Path = Path(os.getenv("CACHE_DIR", str(APP_DATA_DIR / "cache")))
DB_PATH:      Path = Path(os.getenv("DB_PATH", str(APP_DATA_DIR / "app.db")))

# ── Render ────────────────────────────────────────────────────────────────────
RENDER_MAX_CONCURRENT_PARTS: int = int(
    os.getenv("MAX_CONCURRENT_PARTS", str(MAX_CONCURRENT_PARTS))
)

# ── FFmpeg ────────────────────────────────────────────────────────────────────
FFMPEG_BIN:  str = os.getenv("FFMPEG_BIN", "ffmpeg")
FFPROBE_BIN: str = os.getenv("FFPROBE_BIN", "ffprobe")
