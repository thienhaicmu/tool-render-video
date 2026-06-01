"""
whisper.py — Whisper transcription wrapper cho v2.

Delegate sang v1 transcribe_with_adapter — không duplicate Whisper logic.
v1 đã handle: faster-whisper, whisperx, fallback chain, CUDA detection, model cache.

Public API:
    transcribe_to_srt(source_path, output_srt, model, language) -> TranscribeInfo
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from v2.core.config import WHISPER_MODEL
from v2.core.exceptions import TranscribeError

logger = logging.getLogger("v2.services.whisper")


@dataclass(frozen=True)
class TranscribeInfo:
    """Kết quả transcription — chỉ metadata, không chứa nội dung SRT."""
    srt_path:   Path
    engine:     str    # "faster_whisper" | "whisperx" | "default"
    language:   str    # ISO code phát hiện được, hoặc "auto" nếu không detect
    elapsed_ms: int


def transcribe_to_srt(
    source_path: Path,
    output_srt: Path,
    model: Optional[str] = None,
    language: str = "auto",
) -> TranscribeInfo:
    """
    Transcribe video → SRT file. Raise TranscribeError nếu thất bại.

    Delegate sang v1 transcribe_with_adapter. Engine tự chọn:
      faster-whisper (nếu cài) → whisperx → default whisper.
    """
    resolved_model = model or WHISPER_MODEL
    logger.info(
        "transcribe_to_srt source=%s model=%s language=%s",
        source_path.name, resolved_model, language,
    )

    output_srt.parent.mkdir(parents=True, exist_ok=True)

    try:
        from app.services.subtitle_transcription_adapters import transcribe_with_adapter
    except ImportError as exc:
        raise TranscribeError("Không import được transcribe_with_adapter từ v1") from exc

    try:
        result = transcribe_with_adapter(
            video_path=str(source_path),
            readable_srt_path=str(output_srt),
            engine="default",         # auto-select: faster_whisper > default
            model_name=resolved_model,
            retry_count=0,
            highlight_per_word=False, # full SRT, không cần word-level cho segment selection
        )
    except Exception as exc:
        raise TranscribeError(f"Transcription thất bại: {exc}") from exc

    if not output_srt.exists() or output_srt.stat().st_size == 0:
        raise TranscribeError(f"SRT output rỗng hoặc không tồn tại: {output_srt}")

    detected_language = _detect_language_from_srt(output_srt) or language

    return TranscribeInfo(
        srt_path=output_srt,
        engine=str(result.engine),
        language=detected_language,
        elapsed_ms=int(result.elapsed_ms),
    )


# ── Internal ──────────────────────────────────────────────────────────────────

def _detect_language_from_srt(srt_path: Path) -> Optional[str]:
    """Heuristic: đọc 500 chars đầu SRT để đoán ngôn ngữ. Trả về None nếu không xác định được."""
    try:
        content = srt_path.read_text(encoding="utf-8", errors="replace")[:500]
        # Chỉ check Vietnamese — phổ biến nhất trong context này
        viet_chars = len(re.findall(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", content, re.IGNORECASE))
        if viet_chars >= 5:
            return "vi"
    except Exception:
        pass
    return None
