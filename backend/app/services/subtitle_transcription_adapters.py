from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.ai.dependencies import has_whisperx
from app.services.subtitle_engine import format_srt_timestamp, transcribe_to_srt

_WORD_MIN_DURATION_SEC = 0.10
_WORD_MIN_GAP_SEC = 0.01


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
        start = time.perf_counter()
        if not self.is_available():
            return SubtitleTranscriptionResult(
                readable_srt_path=readable_srt_path,
                engine=self.engine_name,
                aligned=False,
                warnings=["whisperx_unavailable"],
            )

        out_path = Path(readable_srt_path)
        tmp_path = out_path.with_name(out_path.stem + ".whisperx.tmp" + out_path.suffix)
        try:
            # Lazy import only. WhisperX, torch, and alignment models must never load at startup.
            import whisperx  # type: ignore

            device = "cpu"
            compute_type = "int8"
            batch_size = 4
            model = whisperx.load_model(
                model_name or "base",
                device,
                compute_type=compute_type,
            )
            audio = whisperx.load_audio(video_path)
            result = model.transcribe(audio, batch_size=batch_size)
            language = str(result.get("language") or "en")
            model_a, metadata = whisperx.load_align_model(language_code=language, device=device)
            aligned = whisperx.align(
                result.get("segments", []),
                model_a,
                metadata,
                audio,
                device,
                return_char_alignments=False,
            )

            _write_whisperx_srt(aligned, str(tmp_path), word_level=highlight_per_word)
            if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
                raise RuntimeError("whisperx produced empty SRT")
            tmp_path.replace(out_path)
            return SubtitleTranscriptionResult(
                readable_srt_path=readable_srt_path,
                engine=self.engine_name,
                aligned=True,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            tmp_path.unlink(missing_ok=True)
            return SubtitleTranscriptionResult(
                readable_srt_path=readable_srt_path,
                engine=self.engine_name,
                aligned=False,
                warnings=[f"whisperx_runtime_error:{type(exc).__name__}"],
                elapsed_ms=int((time.perf_counter() - start) * 1000),
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
        whisperx_result = WhisperXAdapter().transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
        )
        if whisperx_result.aligned:
            if logger is not None:
                logger.info(
                    "subtitle_transcription_adapter_used requested=%s used=%s aligned=%s elapsed_ms=%d",
                    requested,
                    whisperx_result.engine,
                    whisperx_result.aligned,
                    whisperx_result.elapsed_ms,
                )
            return whisperx_result

        warning = whisperx_result.warnings[0] if whisperx_result.warnings else "whisperx_fallback"
        if logger is not None:
            logger.warning(
                "subtitle_transcription_adapter_fallback requested=%s warning=%s fallback=default elapsed_ms=%d",
                requested,
                warning,
                whisperx_result.elapsed_ms,
            )
        result = default_adapter.transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
        )
        result.warnings.extend(whisperx_result.warnings)
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


def _write_whisperx_srt(result: dict, srt_path: str, *, word_level: bool) -> None:
    segments = list((result or {}).get("segments", []) or [])
    blocks: list[dict] = []

    if word_level:
        raw_words: list[dict] = []
        for seg in segments:
            for word in seg.get("words", []) or []:
                text = str(word.get("word", "")).strip()
                if not text or _is_punctuation_only(text):
                    continue
                if word.get("start") is None or word.get("end") is None:
                    continue
                try:
                    start = float(word.get("start"))
                    end = float(word.get("end"))
                except (TypeError, ValueError):
                    continue
                if start < 0 or end <= start:
                    continue
                raw_words.append({"start": start, "end": end, "text": text})
        blocks = _normalize_whisperx_word_blocks(raw_words)

    if not blocks:
        for seg in segments:
            text = str(seg.get("text", "")).strip()
            if not text or seg.get("start") is None or seg.get("end") is None:
                continue
            start = float(seg.get("start"))
            end = float(seg.get("end"))
            if end <= start:
                continue
            blocks.append({"start": start, "end": end, "text": text})

    with Path(srt_path).open("w", encoding="utf-8") as f:
        for idx, block in enumerate(blocks, start=1):
            f.write(
                f"{idx}\n"
                f"{format_srt_timestamp(block['start'])} --> "
                f"{format_srt_timestamp(block['end'])}\n"
                f"{block['text']}\n\n"
            )


def _is_punctuation_only(text: str) -> bool:
    return not any(ch.isalnum() for ch in str(text or ""))


def _normalize_whisperx_word_blocks(words: list[dict]) -> list[dict]:
    """Apply tiny visual-stability normalization to WhisperX word timings only."""
    normalized: list[dict] = []
    prev_end: float | None = None

    for word in sorted(words, key=lambda w: (float(w.get("start") or 0), float(w.get("end") or 0))):
        text = str(word.get("text", "")).strip()
        if not text or _is_punctuation_only(text):
            continue
        try:
            start = float(word.get("start"))
            end = float(word.get("end"))
        except (TypeError, ValueError):
            continue
        if start < 0 or end <= start:
            continue

        if prev_end is not None and start < prev_end + _WORD_MIN_GAP_SEC:
            start = prev_end + _WORD_MIN_GAP_SEC
        if end < start + _WORD_MIN_DURATION_SEC:
            end = start + _WORD_MIN_DURATION_SEC

        normalized.append({"start": start, "end": end, "text": text})
        prev_end = end

    return normalized
