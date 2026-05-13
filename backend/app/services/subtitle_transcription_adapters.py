from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Protocol

from app.ai.dependencies import has_whisperx
from app.services.subtitle_engine import transcribe_to_srt


@dataclass
class SubtitleTranscriptionResult:
    readable_srt_path: str
    word_srt_path: str | None = None
    engine: str = "default"
    aligned: bool = False
    warnings: list[str] = field(default_factory=list)
    elapsed_ms: int = 0


class SubtitleTranscriptionAdapter(Protocol):
    engine_name: str

    def is_available(self) -> bool:
        ...

    def transcribe(
        self,
        video_path: str,
        readable_srt_path: str,
        *,
        model_name: str,
        retry_count: int,
        highlight_per_word: bool,
    ) -> SubtitleTranscriptionResult:
        ...


class DefaultWhisperAdapter:
    engine_name = "default"

    def is_available(self) -> bool:
        return True

    def transcribe(
        self,
        video_path: str,
        readable_srt_path: str,
        *,
        model_name: str,
        retry_count: int,
        highlight_per_word: bool,
    ) -> SubtitleTranscriptionResult:
        start = time.perf_counter()
        transcribe_to_srt(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
        )
        return SubtitleTranscriptionResult(
            readable_srt_path=readable_srt_path,
            engine=self.engine_name,
            aligned=False,
            elapsed_ms=int((time.perf_counter() - start) * 1000),
        )


class WhisperXAdapter:
    engine_name = "whisperx"

    def is_available(self) -> bool:
        return has_whisperx()

    def transcribe(
        self,
        video_path: str,
        readable_srt_path: str,
        *,
        model_name: str,
        retry_count: int,
        highlight_per_word: bool,
    ) -> SubtitleTranscriptionResult:
        warning = (
            "whisperx_adapter_not_implemented"
            if self.is_available()
            else "whisperx_unavailable"
        )
        return SubtitleTranscriptionResult(
            readable_srt_path=readable_srt_path,
            engine=self.engine_name,
            aligned=False,
            warnings=[warning],
        )


def transcribe_with_adapter(
    video_path: str,
    readable_srt_path: str,
    *,
    engine: str,
    model_name: str,
    retry_count: int,
    highlight_per_word: bool,
    logger=None,
) -> SubtitleTranscriptionResult:
    requested = str(engine or "default").strip().lower()
    default_adapter = DefaultWhisperAdapter()

    if requested == "default":
        return default_adapter.transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
        )

    if requested == "whisperx":
        placeholder = WhisperXAdapter().transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
        )
        warning = placeholder.warnings[0] if placeholder.warnings else "whisperx_fallback"
        if logger is not None:
            logger.warning(
                "subtitle_transcription_adapter_fallback requested=%s warning=%s fallback=default",
                requested,
                warning,
            )
        result = default_adapter.transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
        )
        result.warnings.extend(placeholder.warnings)
        return result

    if logger is not None:
        logger.warning(
            "subtitle_transcription_adapter_unknown requested=%s fallback=default",
            requested,
        )
    result = default_adapter.transcribe(
        video_path,
        readable_srt_path,
        model_name=model_name,
        retry_count=retry_count,
        highlight_per_word=highlight_per_word,
    )
    result.warnings.append("unknown_subtitle_transcription_engine")
    return result
