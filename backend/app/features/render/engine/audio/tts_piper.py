"""Piper TTS adapter — offline neural narration synthesis.

Piper runs fully offline on CPU (no GPU, no network), which makes it the
right narration engine for this offline-first desktop app — unlike
Edge-TTS, which calls Microsoft's online service and fails when the
machine is offline, behind a proxy, or hit by Edge's periodic 403s.

Design mirrors tts_xtts.py:
  - Voice model resolved per language from a models directory.
  - Thread-safe model cache (load once, reuse across renders).
  - Hash-based synthesis cache (TEMP_DIR/piper_cache/).
  - WAV → MP3 via FFmpeg so the output contract matches Edge/XTTS.
  - Raises RuntimeError on any failure — the caller falls back to Edge.

Models are NOT bundled (each is ~25–65 MB). Place them under the models
dir (PIPER_MODELS_DIR env, default <backend>/models/piper) as the pair
``<voice>.onnx`` + ``<voice>.onnx.json``. Fetch with:
    python -m piper.download_voices vi_VN-vais1000-medium --data-dir <dir>
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path

logger = logging.getLogger(__name__)

_PIPER_TIMEOUT_SEC = int(os.environ.get("PIPER_TIMEOUT_SEC", "120"))

# Thread-safe model cache — keyed by model file path. Loading parses a
# 25–65 MB ONNX graph, so we keep loaded voices alive across renders.
_PIPER_VOICE_CACHE: dict = {}
_PIPER_VOICE_LOCK = threading.Lock()

# Thread-safe synthesis cache — key → MP3 path.
_PIPER_SYNTHESIS_CACHE: dict[str, str] = {}
_PIPER_CACHE_LOCK = threading.Lock()

# Language → gender → Piper voice model basename (without extension).
# Piper voices are single-speaker, so distinct male/female models give the
# gender choice. "default" is used when the requested gender's model is
# absent. Only languages with at least one model present on disk
# synthesize; everything else raises and the caller falls back to Edge-TTS.
# Add an entry here (and download the model) to support a new language.
#
# NOTE: Piper's official catalog has NO Japanese (ja-JP) or Korean (ko-KR)
# voices — those languages have no offline Piper path and fall back to
# Edge-TTS (online) or XTTS (GPU).
_PIPER_VOICE_MAP: dict[str, dict[str, str]] = {
    "vi-VN": {"default": "vi_VN-vais1000-medium"},
    "vi":    {"default": "vi_VN-vais1000-medium"},
    "en-US": {
        "female":  "en_US-hfc_female-medium",
        "male":    "en_US-hfc_male-medium",
        "default": "en_US-hfc_female-medium",
    },
    "en-GB": {
        "female":  "en_GB-alba-medium",
        "male":    "en_GB-northern_english_male-medium",
        "default": "en_GB-alba-medium",
    },
    "en": {
        "female":  "en_US-hfc_female-medium",
        "male":    "en_US-hfc_male-medium",
        "default": "en_US-hfc_female-medium",
    },
}


def _models_dir() -> Path:
    """Return the Piper models directory.

    Resolution: PIPER_MODELS_DIR env override first, else ``models/piper``
    next to the backend package (parents[5] from this module).
    """
    env = (os.environ.get("PIPER_MODELS_DIR") or "").strip()
    if env:
        return Path(env)
    return Path(__file__).resolve().parents[5] / "models" / "piper"


def _resolve_model(language: str, gender: str = "") -> tuple[Path, Path]:
    """Return (onnx_path, config_path) for the language's Piper voice.

    Preference order: the requested gender's model, then the language
    "default". Raises RuntimeError when no model is mapped for the
    language or none of the candidate files exist — the caller then falls
    back to Edge-TTS.
    """
    lang = str(language or "").strip()
    table = _PIPER_VOICE_MAP.get(lang) or _PIPER_VOICE_MAP.get(lang.split("-")[0])
    if not table:
        raise RuntimeError(f"piper_no_model_for_language language={language!r}")

    g = str(gender or "").strip().lower()
    seen: set[str] = set()
    for basename in (table.get(g), table.get("default")):
        if not basename or basename in seen:
            continue
        seen.add(basename)
        base = _models_dir() / basename
        onnx = base.with_suffix(".onnx")
        config = base.with_name(base.name + ".onnx.json")
        if onnx.exists() and config.exists():
            return onnx, config

    raise RuntimeError(
        f"piper_model_missing language={language} gender={gender} "
        f"dir={_models_dir()} (download with: python -m piper.download_voices "
        f"{table.get('default')} --data-dir {_models_dir()})"
    )


def _get_piper_voice(onnx_path: Path, config_path: Path):
    """Load a PiperVoice once per model path and cache it (thread-safe)."""
    key = str(onnx_path)
    with _PIPER_VOICE_LOCK:
        if key not in _PIPER_VOICE_CACHE:
            from piper import PiperVoice  # lazy — optional dependency
            logger.info("piper_model_loading model=%s", onnx_path.name)
            _PIPER_VOICE_CACHE[key] = PiperVoice.load(str(onnx_path), str(config_path))
            logger.info("piper_model_ready model=%s", onnx_path.name)
        return _PIPER_VOICE_CACHE[key]


def _wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
    """Convert WAV to MP3 via FFmpeg (libmp3lame, VBR quality 2 ≈ 190 kbps)."""
    from app.services.bin_paths import get_ffmpeg_bin
    cmd = [
        get_ffmpeg_bin(), "-y",
        "-i", str(wav_path),
        "-codec:a", "libmp3lame", "-q:a", "2",
        str(mp3_path),
    ]
    result = subprocess.run(cmd, capture_output=True, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(
            f"WAV→MP3 conversion failed: {result.stderr.decode(errors='replace')[:300]}"
        )


def _synthesis_cache_key(text: str, language: str, gender: str, content_type: str) -> str:
    """16-char SHA256 prefix — deterministic key for synthesized audio."""
    payload = f"piper\x00{text}\x00{language}\x00{gender}\x00{content_type}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def synthesize_piper(
    *,
    text: str,
    language: str,
    gender: str,
    job_id: str,
    content_type: str = "vlog",
    output_path: str | None = None,
) -> str:
    """Synthesize speech with Piper (offline). Returns path to an MP3.

    Raises RuntimeError on any failure — the caller must catch and fall
    back to Edge-TTS. Uses a hash-based cache: identical (text, language,
    gender, content_type) returns instantly. ``gender`` is part of the
    cache key for forward-compat but Piper voices are single-speaker, so
    it does not change the synthesized audio today.
    """
    from app.core.config import TEMP_DIR

    clean_text = str(text or "").strip()
    if not clean_text:
        raise RuntimeError("Narration text is empty")

    onnx_path, config_path = _resolve_model(language, gender)

    # Cache check — skip inference if identical synthesis was done earlier.
    cache_key = _synthesis_cache_key(clean_text, language, gender, content_type)
    cache_dir = TEMP_DIR / "piper_cache"
    cached_mp3 = cache_dir / f"{cache_key}.mp3"
    with _PIPER_CACHE_LOCK:
        if cached_mp3.exists() and cached_mp3.stat().st_size > 0:
            dest = Path(output_path) if output_path else (TEMP_DIR / job_id / "voice" / "narration.mp3")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest != cached_mp3:
                shutil.copy2(str(cached_mp3), str(dest))
            logger.info("piper_synthesis_cache_hit job_id=%s key=%s", job_id, cache_key)
            return str(dest)

    work_dir = TEMP_DIR / job_id / "voice"
    work_dir.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "narration.piper.wav"
    mp3_path = Path(output_path) if output_path else work_dir / "narration.mp3"
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    logger.info(
        "piper_synthesis_start job_id=%s language=%s model=%s content_type=%s",
        job_id, language, onnx_path.name, content_type,
    )

    voice = _get_piper_voice(onnx_path, config_path)
    with wave.open(str(wav_path), "wb") as wf:
        voice.synthesize_wav(clean_text, wf)

    if not wav_path.exists() or wav_path.stat().st_size <= 0:
        raise RuntimeError("Piper produced empty WAV output")

    _wav_to_mp3(wav_path, mp3_path)
    wav_path.unlink(missing_ok=True)

    if not mp3_path.exists() or mp3_path.stat().st_size <= 0:
        raise RuntimeError("Piper WAV→MP3 conversion produced empty file")

    # Store in shared cache for future reuse.
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(mp3_path), str(cached_mp3))
        with _PIPER_CACHE_LOCK:
            _PIPER_SYNTHESIS_CACHE[cache_key] = str(cached_mp3)
    except Exception as _cache_exc:
        logger.debug("piper_cache_write_failed key=%s: %s", cache_key, _cache_exc)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "piper_synthesis_complete job_id=%s model=%s elapsed_ms=%d output=%s",
        job_id, onnx_path.name, elapsed_ms, mp3_path.name,
    )
    return str(mp3_path)


def piper_model_available(language: str, gender: str = "") -> bool:
    """True when a Piper voice model for ``language`` is present on disk.

    Never raises — used by the dispatcher to decide whether Piper is a
    viable fallback before attempting synthesis.
    """
    try:
        _resolve_model(language, gender)
        return True
    except Exception:
        return False
