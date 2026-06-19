"""XTTS v2 adapter — premium narration synthesis with voice personas.

OQ-2.2A hardening:
  - Voice personas: content_type × gender → dedicated speaker per content character
  - Hash-based synthesis cache (TEMP_DIR/xtts_cache/)
  - CPU safety: no CUDA → RuntimeError → caller falls back to Edge-TTS
  - Prosody labels per content type for logging

Requires: pip install TTS  (Coqui TTS — xtts_v2)
GPU: ~3.2 GB VRAM peak on RTX 3060 12GB.
Fallback: caller catches RuntimeError and re-routes to Edge-TTS.
"""
from __future__ import annotations

import hashlib
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_XTTS_MODEL_ID = "tts_models/multilingual/multi-dataset/xtts_v2"
_XTTS_TIMEOUT_SEC = int(os.environ.get("XTTS_TIMEOUT_SEC", "120"))

# Max 1 concurrent XTTS session — prevents VRAM contention on RTX 3060.
_XTTS_SEMAPHORE = threading.Semaphore(int(os.environ.get("XTTS_MAX_SESSIONS", "1")))

# Thread-safe model cache — loaded once, reused across renders.
_XTTS_MODEL_CACHE: dict = {}
_XTTS_MODEL_LOCK = threading.Lock()

# Thread-safe synthesis cache — key → MP3 path.
_XTTS_SYNTHESIS_CACHE: dict[str, str] = {}
_XTTS_CACHE_LOCK = threading.Lock()

# XTTS v2 uses 2-char language codes.
_XTTS_LANGUAGE_MAP: dict[str, str] = {
    "vi-VN": "vi",
    "en-US": "en",
    "en-GB": "en",
    "ja-JP": "ja",
    "ko-KR": "ko",
}

# Voice personas: content_type × gender → XTTS v2 built-in speaker.
# All speakers verified for tts_models/multilingual/multi-dataset/xtts_v2.
# Character rationale — energetic: Claribel/Craig (punchy); authoritative: Daisy/Abrahan
# (clear, deliberate); conversational: Ana/Viktor (warm, natural); calm: Gracie/Baldur (soft).
_PERSONA_SPEAKER_MAP: dict[str, dict[str, str]] = {
    "viral":      {"female": "Claribel Dervla",  "male": "Craig Gutsy"},
    "gaming":     {"female": "Tammy Grit",        "male": "Damien Black"},
    "montage":    {"female": "Tammy Grit",        "male": "Craig Gutsy"},
    "commentary": {"female": "Claribel Dervla",  "male": "Craig Gutsy"},
    "tutorial":   {"female": "Daisy Studious",    "male": "Abrahan Mack"},
    "interview":  {"female": "Alison Dietlinde",  "male": "Ilkin Urbano"},
    "podcast":    {"female": "Ana Florence",      "male": "Viktor Eka"},
    "vlog":       {"female": "Ana Florence",      "male": "Viktor Eka"},
    "story":      {"female": "Gracie Wise",       "male": "Baldur Semen"},
}
_PERSONA_DEFAULT_FEMALE = "Ana Florence"
_PERSONA_DEFAULT_MALE   = "Viktor Eka"

# Prosody label per content type — used for logging and future text-preprocessing hooks.
_CONTENT_TYPE_PROSODY: dict[str, str] = {
    "viral":      "energetic",
    "gaming":     "energetic",
    "montage":    "energetic",
    "commentary": "energetic",
    "tutorial":   "authoritative",
    "interview":  "authoritative",
    "podcast":    "conversational",
    "vlog":       "conversational",
    "story":      "calm",
}
_PROSODY_DEFAULT = "conversational"


def _resolve_speaker(content_type: str, gender: str) -> str:
    """Return XTTS v2 speaker name for content_type × gender combination."""
    persona = _PERSONA_SPEAKER_MAP.get(str(content_type or "").lower(), {})
    g = str(gender or "").strip().lower()
    if g in persona:
        return persona[g]
    return _PERSONA_DEFAULT_FEMALE if g == "female" else _PERSONA_DEFAULT_MALE


def _synthesis_cache_key(text: str, language: str, gender: str, content_type: str) -> str:
    """16-char SHA256 prefix — deterministic key for synthesized audio."""
    payload = f"{text}\x00{language}\x00{gender}\x00{content_type}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _require_cuda() -> str:
    """Assert CUDA is available. Raises RuntimeError if not — caller falls back to Edge-TTS.

    CPU XTTS is 30-60s per synthesis — unacceptable for production. Fail fast instead.
    """
    try:
        import torch  # type: ignore[import]
    except ImportError:
        raise RuntimeError("xtts_torch_missing — torch not installed; XTTS requires CUDA")
    if not torch.cuda.is_available():
        raise RuntimeError("xtts_cuda_unavailable — no CUDA device found; XTTS requires GPU")
    return "cuda"


def _get_xtts_model():
    """Load XTTS v2 model once on CUDA and cache. Raises RuntimeError if no CUDA."""
    with _XTTS_MODEL_LOCK:
        if "model" not in _XTTS_MODEL_CACHE:
            device = _require_cuda()
            from TTS.api import TTS as _CoquiTTS  # type: ignore[import]
            logger.info("xtts_model_loading model=%s device=%s", _XTTS_MODEL_ID, device)
            model = _CoquiTTS(_XTTS_MODEL_ID).to(device)
            _XTTS_MODEL_CACHE["model"] = model
            _XTTS_MODEL_CACHE["device"] = device
            logger.info("xtts_model_ready device=%s", device)
        return _XTTS_MODEL_CACHE["model"]


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
        raise RuntimeError(f"WAV→MP3 conversion failed: {result.stderr.decode(errors='replace')[:300]}")


def synthesize_xtts(
    *,
    text: str,
    language: str,
    gender: str,
    job_id: str,
    content_type: str = "vlog",
    output_path: str | None = None,
) -> str:
    """Synthesize speech with XTTS v2 using content-type persona. Returns path to MP3.

    Raises RuntimeError on any failure — caller must catch and fall back to Edge-TTS.
    Uses hash-based cache: identical (text, language, gender, content_type) → instant return.
    Requires CUDA — raises RuntimeError if unavailable (no CPU stall).
    """
    from app.core.config import TEMP_DIR

    lang_code = _XTTS_LANGUAGE_MAP.get(str(language or ""), "en")
    speaker = _resolve_speaker(content_type, gender)
    prosody = _CONTENT_TYPE_PROSODY.get(str(content_type or "").lower(), _PROSODY_DEFAULT)

    # Cache check — skip inference if identical synthesis was done earlier.
    cache_key = _synthesis_cache_key(text, language, gender, content_type)
    cache_dir = TEMP_DIR / "xtts_cache"
    cached_mp3 = cache_dir / f"{cache_key}.mp3"

    with _XTTS_CACHE_LOCK:
        if cached_mp3.exists() and cached_mp3.stat().st_size > 0:
            dest = Path(output_path) if output_path else (TEMP_DIR / job_id / "voice" / "narration.mp3")
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest != cached_mp3:
                shutil.copy2(str(cached_mp3), str(dest))
            logger.info(
                "xtts_synthesis_cache_hit job_id=%s lang=%s speaker=%s prosody=%s key=%s",
                job_id, lang_code, speaker, prosody, cache_key,
            )
            return str(dest)

    # Full synthesis path.
    work_dir = TEMP_DIR / job_id / "voice"
    work_dir.mkdir(parents=True, exist_ok=True)
    wav_path = work_dir / "narration.xtts.wav"
    mp3_path = Path(output_path) if output_path else work_dir / "narration.mp3"
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    logger.info(
        "xtts_synthesis_start job_id=%s language=%s lang_code=%s gender=%s "
        "speaker=%s prosody=%s content_type=%s",
        job_id, language, lang_code, gender, speaker, prosody, content_type,
    )

    with _XTTS_SEMAPHORE:
        model = _get_xtts_model()
        model.tts_to_file(
            text=text,
            language=lang_code,
            speaker=speaker,
            file_path=str(wav_path),
        )

    if not wav_path.exists() or wav_path.stat().st_size <= 0:
        raise RuntimeError("XTTS produced empty WAV output")

    _wav_to_mp3(wav_path, mp3_path)
    wav_path.unlink(missing_ok=True)

    if not mp3_path.exists() or mp3_path.stat().st_size <= 0:
        raise RuntimeError("XTTS WAV→MP3 conversion produced empty file")

    # Store in shared cache for future reuse.
    try:
        cache_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(mp3_path), str(cached_mp3))
        with _XTTS_CACHE_LOCK:
            _XTTS_SYNTHESIS_CACHE[cache_key] = str(cached_mp3)
    except Exception as _cache_exc:
        logger.debug("xtts_cache_write_failed key=%s: %s", cache_key, _cache_exc)

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "xtts_synthesis_complete job_id=%s lang_code=%s speaker=%s prosody=%s "
        "elapsed_ms=%d output=%s",
        job_id, lang_code, speaker, prosody, elapsed_ms, mp3_path.name,
    )
    return str(mp3_path)
