import subprocess
import os
import re
import logging
from pathlib import Path
import time
import threading
import whisper
from app.services.subtitles.output_timeline import (
    slice_srt_to_output_timeline,
)
from app.services.subtitles.styles import (
    _HL_OPEN, _HL_CLOSE,
    _compute_subtitle_scale, _compute_margin_v,
    BOUNCE_FX, _PRESET_MOTION_FX, _MOTION_FX_DEFAULT, _get_motion_fx,
    ASSPreset, _PRESETS, _STYLE_ALIASES, _DEFAULT_PRESET_ID,
    normalize_subtitle_style_id, get_subtitle_preset, build_ass_style_line,
)
from app.services.subtitles.srt_core import (
    format_srt_timestamp, parse_srt_timestamp,
    _parse_srt_blocks, parse_srt_blocks, write_srt_blocks,
    slice_srt_by_time, slice_srt_to_text, _run_with_retry,
)
from app.services.subtitles.readability import (
    _WIDE_CHARS, _NARROW_CHARS, _approx_visual_width, _break_by_visual_width,
    _HOOK_EMPHASIS_WORDS,
    _is_cjk, _emphasis_level,
    _EMPH_CONTRAST, _EMPH_EMOTIONAL, _EMPH_URGENCY, _NUMBER_RE,
    _should_emphasize, _uppercase_emphasis_words, _insert_emphasis_markers,
    _semantic_wrap_block, subtitle_emphasis_pass,
    _INTEL_MAX_WPS, _INTEL_MAX_WORDS, _INTEL_MIN_DISPLAY_SEC, _INTEL_GAP_FILL_SEC,
    _PUNCT_PAUSE_RE, _CLAUSE_STARTERS,
    _find_phrase_split, _split_block_semantic, resegment_srt_for_readability,
)
from app.services.subtitles.text_transforms import (
    resolve_hook_overlay_text, apply_market_line_break_to_srt,
    apply_market_hook_text_to_srt, format_hook_subtitle,
    apply_hook_subtitle_format, apply_subtitle_execution_hints,
)
from app.services.subtitles.ass_core import (
    _ass_time, _ass_escape_text, _ass_highlight_tags,
    srt_to_ass_bounce, _hex_to_ass, srt_to_ass_karaoke,
    _safe_filter_path, burn_subtitle_onto_video,
    _PREVIEW_ASPECT_RES, _PREVIEW_FONTS_DIR, render_subtitle_preview,
)

logger = logging.getLogger(__name__)
from app.services.bin_paths import get_ffmpeg_bin, get_ffprobe_bin

_MODEL_CACHE = {}
_MODEL_CACHE_LOCK = threading.Lock()
_MODEL_TRANSCRIBE_LOCKS = {}
WORD_MIN_GAP_SEC = 0.02
WORD_MIN_DURATION_SEC = 0.12
WORD_MERGE_SHORTER_THAN_SEC = 0.11

# Whisper model cache — redirect to project dir so models stay on D: not C:
_WHISPER_CACHE_DIR: Path = Path(__file__).resolve().parents[3] / "data" / "whisper_cache"
_WHISPER_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def get_whisper_model(model_name: str = "base"):
    with _MODEL_CACHE_LOCK:
        model = _MODEL_CACHE.get(model_name)
        if model is None:
            model = whisper.load_model(model_name, download_root=str(_WHISPER_CACHE_DIR))
            _MODEL_CACHE[model_name] = model
        return model


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

    Delegates to render_engine._has_audio_stream() which wraps the shared cached
    probe_video_metadata() call — zero subprocess cost on repeat calls to the same
    unmodified file.  Deferred import avoids pulling render_engine into the module
    namespace at import time.
    """
    from app.services.render_engine import _has_audio_stream
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
    """
    audio_path = str(Path(srt_path).with_suffix(".wav"))
    _ensure_ffmpeg_in_path_for_whisper()
    _run_with_retry([
        get_ffmpeg_bin(), "-y", "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", audio_path
    ], retries=retry_count)

    try:
        model = get_whisper_model(model_name)
        transcribe_lock = _get_transcribe_lock(model_name)

        if highlight_per_word:
            try:
                result = _transcribe_with_retry(model, audio_path, retries=retry_count, transcribe_lock=transcribe_lock, word_timestamps=True)
                _write_word_level_srt(result, srt_path)
                return result
            except Exception as exc:
                logger.warning(
                    "word_level_transcription_failed model=%s audio=%s error=%s fallback=segment_level",
                    model_name,
                    Path(audio_path).name,
                    exc,
                )

        result = _transcribe_with_retry(model, audio_path, retries=retry_count, transcribe_lock=transcribe_lock)
        _write_segment_level_srt(result, srt_path)
        return result
    finally:
        # Always remove extracted WAV — avoids orphan if Whisper fails mid-job
        Path(audio_path).unlink(missing_ok=True)


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


