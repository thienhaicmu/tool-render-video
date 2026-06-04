from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from app.ai.dependencies import has_faster_whisper, has_whisperx

# Languages with a supported wav2vec2 alignment model in WhisperX.
# Configurable via WHISPERX_ALIGN_LANGS env var (comma-separated ISO codes).
SUPPORTED_ALIGNMENT_LANGUAGES: frozenset[str] = frozenset(
    os.environ.get("WHISPERX_ALIGN_LANGS", "en,de,fr,es,it,ja,zh,nl,uk,pt").split(",")
)
from app.services.subtitle_engine import (
    extract_audio_for_transcription,
    format_srt_timestamp,
    transcribe_to_srt,
)

_WORD_MIN_DURATION_SEC = 0.10
_WORD_MIN_GAP_SEC = 0.01

# ---------------------------------------------------------------------------
# In-process faster-whisper model cache — one WhisperModel per
# (model_name, device, compute_type) key.  Guarded by a threading.Lock so
# that concurrent render jobs share one loaded model without re-initializing.
# ---------------------------------------------------------------------------
_FW_MODEL_CACHE: dict = {}
_FW_MODEL_LOCK = threading.Lock()


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
        language: str | None = None,
        beam_size: int | None = None,
        vad_filter: bool = False,
        condition_on_previous_text: bool = True,
    ) -> SubtitleTranscriptionResult:
        ...


# ---------------------------------------------------------------------------
# Shared CUDA detection helper
# ---------------------------------------------------------------------------

def _detect_fw_device_compute() -> tuple[str, str]:
    """Return (device, compute_type) for faster-whisper / WhisperX.

    Checks ctranslate2 CUDA device count — no PyTorch dependency required
    for the faster-whisper path.  Falls back to CPU int8 if CUDA is absent
    or ctranslate2 is not installed.
    """
    try:
        import ctranslate2  # noqa: PLC0415
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", "float16"
    except Exception:
        pass
    return "cpu", "int8"


def _get_fw_model(model_name: str, device: str, compute_type: str):
    """Return a cached WhisperModel, loading it on first call per (model, device, compute).

    On CUDA init failure, retries with CPU int8 and aliases the CUDA cache key
    to the CPU model so subsequent calls do not re-attempt CUDA.
    """
    cache_key = (model_name, device, compute_type)
    with _FW_MODEL_LOCK:
        if cache_key not in _FW_MODEL_CACHE:
            from faster_whisper import WhisperModel  # noqa: PLC0415
            try:
                model = WhisperModel(model_name, device=device, compute_type=compute_type)
            except Exception:
                if device == "cuda":
                    model = WhisperModel(model_name, device="cpu", compute_type="int8")
                    _FW_MODEL_CACHE[(model_name, "cpu", "int8")] = model
                else:
                    raise
            _FW_MODEL_CACHE[cache_key] = model
        return _FW_MODEL_CACHE[cache_key]


# ---------------------------------------------------------------------------
# Public warmup — called at server startup to pre-load model into RAM
# ---------------------------------------------------------------------------

def warmup_fw_model(model_name: str) -> bool:
    """Load the faster-whisper model into _FW_MODEL_CACHE before the first job.

    Returns True if the model was loaded (or was already cached), False on any
    failure. Never raises — startup must not crash due to a missing model.
    """
    if not has_faster_whisper():
        return False
    try:
        device, compute_type = _detect_fw_device_compute()
        _get_fw_model(model_name, device, compute_type)
        return True
    except Exception as exc:
        import logging
        logging.getLogger("app.startup").warning(
            "whisper_warmup: failed to pre-load %s — %s", model_name, exc
        )
        return False


# ---------------------------------------------------------------------------
# faster-whisper SRT writer
# ---------------------------------------------------------------------------

def _write_fw_srt(segments_iter, srt_path: str, *, word_level: bool) -> None:
    """Write an SRT file from a faster-whisper segment iterator.

    faster-whisper returns Segment namedtuples, not dicts.  This writer
    converts them into the same normalised word-block format used by the
    WhisperX adapter so the two paths are consistent.
    """
    segments = list(segments_iter)
    blocks: list[dict] = []

    if word_level:
        raw_words: list[dict] = []
        for seg in segments:
            for word in (seg.words or []):
                text = str(word.word).strip()
                if not text or not any(ch.isalnum() for ch in text):
                    continue
                start = float(word.start)
                end = float(word.end)
                if start < 0 or end <= start:
                    continue
                raw_words.append({"start": start, "end": end, "text": text})
        blocks = _normalize_whisperx_word_blocks(raw_words)

    if not blocks:
        # Segment-level fallback (also used when word_level=False)
        for seg in segments:
            text = str(seg.text).strip()
            if not text:
                continue
            start = float(seg.start)
            end = float(seg.end)
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


# ---------------------------------------------------------------------------
# Adapters
# ---------------------------------------------------------------------------

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
        language: str | None = None,
        beam_size: int | None = None,
        vad_filter: bool = False,
        condition_on_previous_text: bool = True,
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


class FasterWhisperAdapter:
    """Transcription adapter using faster-whisper (CTranslate2 backend).

    Automatically selects CUDA float16 when an NVIDIA GPU is available,
    falls back to CPU int8 otherwise.  Compatible with large-v3 and all
    other faster-whisper model sizes.

    Graceful fallback: on any runtime error, returns a result with a
    non-empty warnings list so the caller can fall back to DefaultWhisperAdapter.
    """
    engine_name = "faster_whisper"

    def is_available(self) -> bool:
        return has_faster_whisper()

    def transcribe(
        self,
        video_path: str,
        readable_srt_path: str,
        *,
        model_name: str,
        retry_count: int,
        highlight_per_word: bool,
        language: str | None = None,
        beam_size: int | None = None,
        vad_filter: bool = False,
        condition_on_previous_text: bool = True,
    ) -> SubtitleTranscriptionResult:
        start = time.perf_counter()

        if not self.is_available():
            return SubtitleTranscriptionResult(
                readable_srt_path=readable_srt_path,
                engine=self.engine_name,
                aligned=False,
                warnings=["faster_whisper_unavailable"],
                elapsed_ms=0,
            )

        wav_path = str(Path(readable_srt_path).with_suffix(".fw.wav"))
        try:
            extract_audio_for_transcription(video_path, wav_path, retry_count=retry_count)

            device, compute_type = _detect_fw_device_compute()
            _model_name = model_name or "large-v3"
            model = _get_fw_model(_model_name, device, compute_type)

            _fw_kwargs: dict = {
                "word_timestamps": highlight_per_word,
                "vad_filter": vad_filter,
                "condition_on_previous_text": condition_on_previous_text,
            }
            if language is not None:
                _fw_kwargs["language"] = language
            if beam_size is not None:
                _fw_kwargs["beam_size"] = beam_size
            segments_iter, _info = model.transcribe(wav_path, **_fw_kwargs)
            _write_fw_srt(segments_iter, readable_srt_path, word_level=highlight_per_word)

            return SubtitleTranscriptionResult(
                readable_srt_path=readable_srt_path,
                engine=self.engine_name,
                aligned=False,
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        except Exception as exc:
            return SubtitleTranscriptionResult(
                readable_srt_path=readable_srt_path,
                engine=self.engine_name,
                aligned=False,
                warnings=[f"faster_whisper_runtime_error:{type(exc).__name__}:{exc}"],
                elapsed_ms=int((time.perf_counter() - start) * 1000),
            )
        finally:
            Path(wav_path).unlink(missing_ok=True)


class WhisperXAdapter:
    """Transcription adapter using WhisperX (faster-whisper + forced wav2vec2 alignment).

    When CUDA is available, uses float16 for both transcription and alignment.
    Defaults to large-v3 for maximum accuracy.

    Language support for forced alignment: en, de, fr, es, it, ja, zh, nl, uk, pt.
    For languages without an alignment model (e.g. vi), alignment fails gracefully
    and the result falls back to the faster-whisper path.
    """
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
        language: str | None = None,
        beam_size: int | None = None,
        vad_filter: bool = False,
        condition_on_previous_text: bool = True,
    ) -> SubtitleTranscriptionResult:
        start = time.perf_counter()
        _forced_language = language  # caller hint; None = auto-detect
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
            import whisperx  # noqa: PLC0415

            device, compute_type = _detect_fw_device_compute()
            batch_size = 8 if device == "cuda" else 4
            _model_name = model_name or "large-v3"

            model = whisperx.load_model(
                _model_name,
                device,
                compute_type=compute_type,
            )
            audio = whisperx.load_audio(video_path)
            result = model.transcribe(
                audio,
                batch_size=batch_size,
                **({"language": _forced_language} if _forced_language else {}),
            )
            language = str(result.get("language") or "en")

            if language not in SUPPORTED_ALIGNMENT_LANGUAGES:
                # No wav2vec2 model for this language — write SRT from transcription
                # result directly and return without alignment (single pass, no retry).
                _write_whisperx_srt(result, str(tmp_path), word_level=highlight_per_word)
                if not tmp_path.exists() or tmp_path.stat().st_size <= 0:
                    raise RuntimeError("whisperx transcription produced empty SRT")
                tmp_path.replace(out_path)
                return SubtitleTranscriptionResult(
                    readable_srt_path=readable_srt_path,
                    engine=self.engine_name,
                    aligned=False,
                    warnings=[f"whisperx_language_not_supported:{language}"],
                    elapsed_ms=int((time.perf_counter() - start) * 1000),
                )

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


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

def transcribe_with_adapter(
    video_path: str,
    readable_srt_path: str,
    *,
    engine: str,
    model_name: str,
    retry_count: int,
    highlight_per_word: bool,
    language: str | None = None,
    beam_size: int | None = None,
    vad_filter: bool = False,
    condition_on_previous_text: bool = True,
    logger=None,
) -> SubtitleTranscriptionResult:
    """Route transcription to the appropriate adapter.

    engine="default"
        Transparent upgrade: uses FasterWhisperAdapter when faster-whisper is
        installed, otherwise falls back to DefaultWhisperAdapter.  No caller
        change required — existing payloads automatically benefit.

    engine="faster_whisper"
        Explicit faster-whisper request.  Falls back to DefaultWhisperAdapter
        on error, appending warning codes to the result.

    engine="whisperx"
        WhisperX with wav2vec2 forced alignment.  Falls back first to
        FasterWhisperAdapter (if available), then to DefaultWhisperAdapter.
    """
    requested = str(engine or "default").strip().lower()
    default_adapter = DefaultWhisperAdapter()
    _adapt_kw = {
        "language": language,
        "beam_size": beam_size,
        "vad_filter": vad_filter,
        "condition_on_previous_text": condition_on_previous_text,
    }

    # ------------------------------------------------------------------
    # engine="default" — transparent upgrade when faster-whisper present
    # ------------------------------------------------------------------
    if requested == "default":
        if has_faster_whisper():
            result = FasterWhisperAdapter().transcribe(
                video_path,
                readable_srt_path,
                model_name=model_name,
                retry_count=retry_count,
                highlight_per_word=highlight_per_word,
                **_adapt_kw,
            )
            if not result.warnings:
                if logger is not None:
                    logger.info(
                        "subtitle_transcription_adapter_used requested=default used=faster_whisper "
                        "device=%s elapsed_ms=%d",
                        "cuda" if "cuda" in result.engine else "cpu",
                        result.elapsed_ms,
                    )
                return result
            if logger is not None:
                logger.warning(
                    "subtitle_transcription_adapter_fallback requested=default "
                    "faster_whisper_warnings=%s fallback=default_whisper",
                    ",".join(result.warnings),
                )
        return default_adapter.transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
            **_adapt_kw,
        )

    # ------------------------------------------------------------------
    # engine="faster_whisper" — explicit request
    # ------------------------------------------------------------------
    if requested == "faster_whisper":
        fw_result = FasterWhisperAdapter().transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
            **_adapt_kw,
        )
        if not fw_result.warnings:
            if logger is not None:
                logger.info(
                    "subtitle_transcription_adapter_used requested=faster_whisper used=faster_whisper "
                    "aligned=%s elapsed_ms=%d",
                    fw_result.aligned,
                    fw_result.elapsed_ms,
                )
            return fw_result
        warning = fw_result.warnings[0] if fw_result.warnings else "faster_whisper_fallback"
        if logger is not None:
            logger.warning(
                "subtitle_transcription_adapter_fallback requested=faster_whisper "
                "warning=%s fallback=default elapsed_ms=%d",
                warning,
                fw_result.elapsed_ms,
            )
        result = default_adapter.transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
            **_adapt_kw,
        )
        result.warnings.extend(fw_result.warnings)
        return result

    # ------------------------------------------------------------------
    # engine="whisperx" — WhisperX alignment, two-level fallback
    # ------------------------------------------------------------------
    if requested == "whisperx":
        whisperx_result = WhisperXAdapter().transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
            **_adapt_kw,
        )
        # Accept aligned=True (full alignment) OR aligned=False with only
        # language_not_supported warnings (SRT was written; alignment skipped by gate).
        _lang_gate_only = (
            not whisperx_result.aligned
            and bool(whisperx_result.warnings)
            and all("language_not_supported" in w for w in whisperx_result.warnings)
        )
        if whisperx_result.aligned or _lang_gate_only:
            if logger is not None:
                logger.info(
                    "subtitle_transcription_adapter_used requested=whisperx used=whisperx "
                    "aligned=%s elapsed_ms=%d warnings=%s",
                    whisperx_result.aligned,
                    whisperx_result.elapsed_ms,
                    ",".join(whisperx_result.warnings) if whisperx_result.warnings else "none",
                )
            return whisperx_result

        # WhisperX runtime failure — try faster-whisper before falling all the way back
        warning = whisperx_result.warnings[0] if whisperx_result.warnings else "whisperx_fallback"
        if logger is not None:
            logger.warning(
                "subtitle_transcription_adapter_fallback requested=whisperx "
                "warning=%s fallback=faster_whisper elapsed_ms=%d",
                warning,
                whisperx_result.elapsed_ms,
            )

        if has_faster_whisper():
            fw_result = FasterWhisperAdapter().transcribe(
                video_path,
                readable_srt_path,
                model_name=model_name,
                retry_count=retry_count,
                highlight_per_word=highlight_per_word,
                **_adapt_kw,
            )
            if not fw_result.warnings:
                fw_result.warnings.extend(whisperx_result.warnings)
                return fw_result
            if logger is not None:
                logger.warning(
                    "subtitle_transcription_adapter_fallback requested=whisperx "
                    "faster_whisper_warning=%s fallback=default",
                    fw_result.warnings[0] if fw_result.warnings else "fw_fallback",
                )

        result = default_adapter.transcribe(
            video_path,
            readable_srt_path,
            model_name=model_name,
            retry_count=retry_count,
            highlight_per_word=highlight_per_word,
            **_adapt_kw,
        )
        result.warnings.extend(whisperx_result.warnings)
        return result

    # ------------------------------------------------------------------
    # Unknown engine — log and use default path
    # ------------------------------------------------------------------
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
        **_adapt_kw,
    )
    result.warnings.append("unknown_subtitle_transcription_engine")
    return result


# ---------------------------------------------------------------------------
# WhisperX SRT writer (unchanged from original — preserved for compatibility)
# ---------------------------------------------------------------------------

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
    """Apply timing normalisation to per-word blocks (shared by WhisperX and faster-whisper paths)."""
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
