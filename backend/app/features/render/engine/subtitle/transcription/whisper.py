import subprocess
import os
import time
import threading
import logging
from collections import OrderedDict
from pathlib import Path
import whisper
from app.services.bin_paths import get_ffmpeg_bin
from app.features.render.engine.subtitle.generator.srt import format_srt_timestamp, _run_with_retry

logger = logging.getLogger(__name__)

# Audit FINDING-BR15 closure (Batch 10E 2026-06-06): LRU eviction so we
# don't hold both `tiny` (preview) and `large-v3` (main) resident — that
# pair eats several GB of RAM with no upper bound on the cache. The cap
# is set via WHISPER_MODEL_CACHE_MAX (default 2) so a future deployment
# with more RAM can opt in to a deeper cache.
_MODEL_CACHE_MAX: int = max(1, int(os.getenv("WHISPER_MODEL_CACHE_MAX", "2")))
_MODEL_CACHE: "OrderedDict[str, object]" = OrderedDict()
_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_TRANSCRIBE_LOCKS: dict = {}
WORD_MIN_GAP_SEC = 0.02
WORD_MIN_DURATION_SEC = 0.12
WORD_MERGE_SHORTER_THAN_SEC = 0.11

# Redirect Whisper model cache to project dir so models stay on D: not C:
# File is at backend/app/services/subtitles/transcription.py → parents[4] = project root
_WHISPER_CACHE_DIR: Path = Path(__file__).resolve().parents[4] / "data" / "whisper_cache"
_WHISPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _release_whisper_model(model_name: str, model) -> None:
    """Drop a model reference + release CUDA memory if torch is loaded.

    Never raises — the eviction path runs inside the cache lock and a
    failure here must not deadlock subsequent loads.
    """
    try:
        del model
    except Exception:
        pass
    try:
        import torch  # noqa: PLC0415
        if hasattr(torch, "cuda") and torch.cuda.is_available():
            torch.cuda.empty_cache()
    except Exception:
        pass
    # Drop the transcribe-lock entry too so future re-loads start clean.
    _MODEL_TRANSCRIBE_LOCKS.pop(model_name, None)
    logger.info("whisper LRU: evicted model=%s", model_name)


def get_whisper_model(model_name: str = "base"):
    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(model_name)
        if model is not None:
            # Touch → move to MRU end. OrderedDict.move_to_end is O(1).
            _MODEL_CACHE.move_to_end(model_name)
            return model
        model = whisper.load_model(model_name, download_root=str(_WHISPER_CACHE_DIR))
        _MODEL_CACHE[model_name] = model
        # Evict oldest entries until cache size is within cap. We loop
        # rather than evict-one to be safe if the cap was lowered at runtime.
        while len(_MODEL_CACHE) > _MODEL_CACHE_MAX:
            evict_name, evict_model = _MODEL_CACHE.popitem(last=False)
            _release_whisper_model(evict_name, evict_model)
        return model


def unload_all_whisper_models() -> int:
    """Explicitly drop every cached Whisper model (e.g., from a shutdown hook
    or a /maintenance endpoint). Returns the count evicted. Never raises."""
    with _MODEL_CACHE_LOCK:
        evicted = 0
        while _MODEL_CACHE:
            name, model = _MODEL_CACHE.popitem(last=False)
            _release_whisper_model(name, model)
            evicted += 1
        return evicted


def _get_transcribe_lock(model_name: str):
    with _MODEL_CACHE_LOCK:
        lock = _MODEL_TRANSCRIBE_LOCKS.get(model_name)
        if lock is None:
            lock = threading.Lock()
            _MODEL_TRANSCRIBE_LOCKS[model_name] = lock
        return lock


def _transcribe_with_retry(model, audio_path: str, retries: int = 2, wait_sec: float = 0.8, transcribe_lock=None, **kwargs):
    attempt = 0
    while True:
        attempt += 1
        try:
            if transcribe_lock is None:
                return model.transcribe(audio_path, fp16=False, **kwargs)
            with transcribe_lock:
                return model.transcribe(audio_path, fp16=False, **kwargs)
        except Exception:
            if attempt > retries:
                raise
            time.sleep(wait_sec * attempt)


def _ensure_ffmpeg_in_path_for_whisper():
    ffmpeg_bin = get_ffmpeg_bin()
    ffmpeg_dir = str(Path(ffmpeg_bin).parent)
    current = os.environ.get("PATH", "")
    if ffmpeg_dir and ffmpeg_dir not in current:
        os.environ["PATH"] = f"{ffmpeg_dir};{current}" if current else ffmpeg_dir


def has_audio_stream(video_path: str) -> bool:
    """Return True when the file has at least one audio stream (uses cached probe).

    Imports directly from render.ffmpeg_helpers (Phase 4G.6 coupling fix — no longer
    routes through the render_engine shim).
    """
    from app.features.render.engine.encoder.ffmpeg_helpers import _has_audio_stream
    return _has_audio_stream(video_path)


def extract_audio_for_transcription(video_path: str, wav_path: str, retry_count: int = 2) -> None:
    """Extract 16 kHz mono WAV from *video_path* for speech transcription engines.

    Used by both the default Whisper path and the faster-whisper adapter so that
    audio extraction logic lives in one place.  The caller is responsible for
    deleting *wav_path* after transcription completes.
    """
    _ensure_ffmpeg_in_path_for_whisper()
    _run_with_retry(
        [
            get_ffmpeg_bin(), "-y", "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", wav_path,
        ],
        retries=retry_count,
    )


def transcribe_to_srt(
    video_path: str,
    srt_path: str,
    model_name: str = "base",
    retry_count: int = 2,
    highlight_per_word: bool = False,
):
    """Transcribe audio to SRT.

    When highlight_per_word=True, uses Whisper word_timestamps to produce
    one SRT entry per word — required for word-by-word pop animation.
    Falls back to segment-level if word timestamps are unavailable.

    Fallback chain: primary model → "tiny" model → raises TranscriptionError.
    Caller is responsible for catching and handling gracefully.
    """
    audio_path = str(Path(srt_path).with_suffix(".wav"))
    _ensure_ffmpeg_in_path_for_whisper()
    _run_with_retry([
        get_ffmpeg_bin(), "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path
    ], retries=retry_count)

    try:
        return _transcribe_with_model(
            audio_path, srt_path, model_name, retry_count, highlight_per_word,
        )
    except Exception as primary_exc:
        # Fallback: try "tiny" when primary model fails (OOM, corrupt model, etc.)
        fallback = "tiny"
        if model_name == fallback:
            logger.error(
                "transcription_failed_no_fallback model=%s audio=%s error=%s",
                model_name, Path(audio_path).name, primary_exc,
            )
            raise
        logger.warning(
            "transcription_primary_failed model=%s error=%s — retrying with %s",
            model_name, primary_exc, fallback,
        )
        try:
            return _transcribe_with_model(
                audio_path, srt_path, fallback, retry_count=1, highlight_per_word=False,
            )
        except Exception as fallback_exc:
            logger.error(
                "transcription_fallback_failed model=%s error=%s",
                fallback, fallback_exc,
            )
            raise RuntimeError(
                f"Transcription failed with both '{model_name}' and '{fallback}'. "
                f"Primary error: {primary_exc}. Fallback error: {fallback_exc}"
            ) from fallback_exc
    finally:
        Path(audio_path).unlink(missing_ok=True)


def _transcribe_with_model(
    audio_path: str,
    srt_path: str,
    model_name: str,
    retry_count: int,
    highlight_per_word: bool,
):
    """Run transcription with a specific model. Raises on failure."""
    model = get_whisper_model(model_name)
    transcribe_lock = _get_transcribe_lock(model_name)

    # Anti-hallucination defaults (2026-06-15) — passed to model.transcribe()
    # via _transcribe_with_retry. Mirrors faster-whisper adapter so behavior
    # is consistent across engines. See adapters.transcribe_with_adapter
    # docstring for the rationale. Callers can still override by passing
    # the same kwargs explicitly into _transcribe_with_retry.
    _antihalluc = {
        "condition_on_previous_text": False,
        "temperature": (0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
        # compression_ratio_threshold / logprob_threshold / no_speech_threshold
        # use openai-whisper defaults (2.4 / -1.0 / 0.6) — those values are
        # what the temperature fallback schedule checks against.
    }

    if highlight_per_word:
        try:
            result = _transcribe_with_retry(
                model, audio_path, retries=retry_count,
                transcribe_lock=transcribe_lock,
                word_timestamps=True,
                **_antihalluc,
            )
            _write_word_level_srt(result, srt_path)
            return result
        except Exception as exc:
            logger.warning(
                "word_level_transcription_failed model=%s audio=%s error=%s fallback=segment_level",
                model_name, Path(audio_path).name, exc,
            )

    result = _transcribe_with_retry(
        model, audio_path, retries=retry_count, transcribe_lock=transcribe_lock,
        **_antihalluc,
    )
    _write_segment_level_srt(result, srt_path)
    return result


def _write_word_level_srt(result: dict, srt_path: str):
    """Write one SRT entry per word using Whisper word timestamps."""

    def _normalize_words(words: list[dict], seg_start: float, seg_end: float) -> list[dict]:
        items = []
        prev_end = None
        for w in words:
            text = str(w.get("word", "")).strip()
            if not text:
                continue
            start = float(w.get("start", seg_start))
            end = float(w.get("end", seg_end))
            if prev_end is not None and start < (prev_end + WORD_MIN_GAP_SEC):
                start = prev_end + WORD_MIN_GAP_SEC
            if end < (start + WORD_MIN_DURATION_SEC):
                end = start + WORD_MIN_DURATION_SEC
            items.append({"text": text, "start": start, "end": end})
            prev_end = end

        # Merge ultra-short word events to avoid stacked flashes/overlap feeling.
        merged = []
        i = 0
        while i < len(items):
            cur = items[i]
            cur_dur = float(cur["end"] - cur["start"])
            if cur_dur < WORD_MERGE_SHORTER_THAN_SEC and i + 1 < len(items):
                nxt = items[i + 1]
                merged.append({
                    "text": f"{cur['text']} {nxt['text']}".strip(),
                    "start": cur["start"],
                    "end": max(cur["end"], nxt["end"]),
                })
                i += 2
                continue
            merged.append(cur)
            i += 1
        return merged

    idx = 1
    with open(srt_path, "w", encoding="utf-8") as f:
        for seg in result.get("segments", []):
            words = seg.get("words", [])
            if words:
                normalized = _normalize_words(words, float(seg["start"]), float(seg["end"]))
                for w in normalized:
                    f.write(
                        f"{idx}\n"
                        f"{format_srt_timestamp(float(w['start']))} --> {format_srt_timestamp(float(w['end']))}\n"
                        f"{w['text']}\n\n"
                    )
                    idx += 1
            else:
                # No word timestamps for this segment — fall back to full segment text
                text = seg.get("text", "").strip()
                if text:
                    f.write(
                        f"{idx}\n"
                        f"{format_srt_timestamp(seg['start'])} --> {format_srt_timestamp(seg['end'])}\n"
                        f"{text}\n\n"
                    )
                    idx += 1


def _write_segment_level_srt(result: dict, srt_path: str):
    with open(srt_path, "w", encoding="utf-8") as f:
        for idx, seg in enumerate(result.get("segments", []), start=1):
            start_ts = format_srt_timestamp(seg["start"])
            end_ts = format_srt_timestamp(seg["end"])
            text = seg["text"].strip()
            if text:
                f.write(f"{idx}\n{start_ts} --> {end_ts}\n{text}\n\n")

