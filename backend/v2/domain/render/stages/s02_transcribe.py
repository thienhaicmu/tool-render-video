"""
s02_transcribe.py — Transcribe full video → full_srt.srt (Whisper).

Input:  ValidateResult (source.path, source.duration)
Output: TranscribeResult(srt_path, duration_sec, language, from_cache)

Cache key = md5(first 512KB of file) + file size
  → cùng file, chạy nhiều lần → chỉ transcribe 1 lần.
  → file khác nhau nhưng cùng size sẽ vẫn transcribe lại (an toàn).

SRT output → work_dir/full_srt.srt
Cache SRT  → cache_dir/transcribe/{cache_key}.srt
"""
from __future__ import annotations

import hashlib
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from v2.core.config import CACHE_DIR, WHISPER_MODEL
from v2.core.exceptions import TranscribeError
from v2.core.types import PipelineContext
from v2.domain.render.stages.s01_validate import ValidateResult
from v2.services.whisper import TranscribeInfo, transcribe_to_srt

logger = logging.getLogger("v2.render.s02_transcribe")

_CACHE_SUBDIR = "transcribe"
_CACHE_READ_BYTES = 512 * 1024   # 512 KB để tính hash
SRT_FILENAME = "full_srt.srt"


@dataclass(frozen=True)
class TranscribeResult:
    srt_path:     Path
    duration_sec: float
    language:     str
    from_cache:   bool
    engine:       str


def run(ctx: PipelineContext, prev: ValidateResult) -> TranscribeResult:
    """
    Transcribe toàn bộ video. Raise TranscribeError nếu Whisper thất bại.

    Cache hit → copy SRT về work_dir, không chạy Whisper lại.
    Cache miss → chạy Whisper, lưu cache.
    """
    ctx.check_cancel()
    source = prev.source
    logger.info("s02_transcribe job_id=%s source=%s", ctx.job_id, source.path.name)

    output_srt = ctx.work_dir / SRT_FILENAME
    cache_key = _compute_cache_key(source.path)
    cached_srt = _cache_path(cache_key)

    # Cache hit
    if cached_srt.exists() and cached_srt.stat().st_size > 0:
        logger.info("s02_transcribe cache_hit key=%s", cache_key)
        shutil.copy2(cached_srt, output_srt)
        ctx.emit("transcribe.cache_hit", {"cache_key": cache_key})
        return TranscribeResult(
            srt_path=output_srt,
            duration_sec=source.duration,
            language=_read_language_hint(cached_srt),
            from_cache=True,
            engine="cached",
        )

    # Cache miss — chạy Whisper
    ctx.emit("transcribe.start", {"model": WHISPER_MODEL, "duration_sec": source.duration})
    logger.info("s02_transcribe cache_miss — running Whisper model=%s", WHISPER_MODEL)

    info: TranscribeInfo = transcribe_to_srt(
        source_path=source.path,
        output_srt=output_srt,
        model=WHISPER_MODEL,
        language="auto",
    )

    # Lưu vào cache
    _write_cache(output_srt, cached_srt, info.language)

    logger.info(
        "s02_transcribe done job_id=%s engine=%s language=%s elapsed_ms=%d",
        ctx.job_id, info.engine, info.language, info.elapsed_ms,
    )
    ctx.emit("transcribe.done", {
        "engine": info.engine,
        "language": info.language,
        "elapsed_ms": info.elapsed_ms,
    })

    return TranscribeResult(
        srt_path=output_srt,
        duration_sec=source.duration,
        language=info.language,
        from_cache=False,
        engine=info.engine,
    )


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _compute_cache_key(path: Path) -> str:
    """md5(đầu file) + '_' + file_size. Nhanh và đủ để phân biệt các file khác nhau."""
    h = hashlib.md5()
    file_size = path.stat().st_size
    with path.open("rb") as f:
        chunk = f.read(_CACHE_READ_BYTES)
        h.update(chunk)
    return f"{h.hexdigest()}_{file_size}"


def _cache_path(cache_key: str) -> Path:
    cache_dir = CACHE_DIR / _CACHE_SUBDIR
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{cache_key}.srt"


def _write_cache(srt_path: Path, cache_srt: Path, language: str) -> None:
    """Copy SRT vào cache. Lỗi cache không được crash pipeline."""
    try:
        shutil.copy2(srt_path, cache_srt)
        # Ghi language hint vào file nhỏ bên cạnh
        cache_srt.with_suffix(".lang").write_text(language, encoding="utf-8")
    except Exception as exc:
        logger.warning("s02_transcribe cache_write_failed: %s", exc)


def _read_language_hint(cached_srt: Path) -> str:
    """Đọc language từ .lang file bên cạnh SRT cache. Trả về 'auto' nếu không có."""
    try:
        lang_file = cached_srt.with_suffix(".lang")
        if lang_file.exists():
            return lang_file.read_text(encoding="utf-8").strip() or "auto"
    except Exception:
        pass
    return "auto"
