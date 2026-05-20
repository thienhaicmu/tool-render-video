"""XTTS v2 adapter for premium narration synthesis.

Requires: pip install TTS  (Coqui TTS — provides tts_models/multilingual/multi-dataset/xtts_v2)
GPU: ~3.2 GB VRAM peak on RTX 3060 12GB — safe.
Fallback: caller catches RuntimeError and re-routes to Edge-TTS.
"""
from __future__ import annotations

import logging
import os
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

# XTTS v2 uses 2-char language codes.
_XTTS_LANGUAGE_MAP: dict[str, str] = {
    "vi-VN": "vi",
    "en-US": "en",
    "en-GB": "en",
    "ja-JP": "ja",
}

# XTTS v2 built-in speakers (tts_models/multilingual/multi-dataset/xtts_v2).
_XTTS_SPEAKER_MAP: dict[str, str] = {
    "female": "Ana Florence",
    "male":   "Viktor Eka",
}
_XTTS_DEFAULT_SPEAKER = "Ana Florence"


def _get_xtts_model():
    """Load XTTS v2 model once and cache. Thread-safe via _XTTS_MODEL_LOCK."""
    with _XTTS_MODEL_LOCK:
        if "model" not in _XTTS_MODEL_CACHE:
            from TTS.api import TTS as _CoquiTTS  # type: ignore[import]
            try:
                import torch  # type: ignore[import]
                device = "cuda" if torch.cuda.is_available() else "cpu"
            except ImportError:
                device = "cpu"
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
    output_path: str | None = None,
) -> str:
    """Synthesize speech with XTTS v2. Returns path to MP3 file.

    Raises RuntimeError on any failure — caller must catch and fall back to Edge-TTS.
    """
    from app.core.config import TEMP_DIR

    lang_code = _XTTS_LANGUAGE_MAP.get(str(language or ""), "en")
    speaker = _XTTS_SPEAKER_MAP.get(str(gender or "").strip().lower(), _XTTS_DEFAULT_SPEAKER)

    work_dir = TEMP_DIR / job_id / "voice"
    work_dir.mkdir(parents=True, exist_ok=True)

    wav_path = work_dir / "narration.xtts.wav"
    mp3_path = Path(output_path) if output_path else work_dir / "narration.mp3"
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    start = time.perf_counter()
    logger.info(
        "xtts_synthesis_start job_id=%s language=%s lang_code=%s gender=%s speaker=%s",
        job_id, language, lang_code, gender, speaker,
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

    elapsed_ms = int((time.perf_counter() - start) * 1000)
    logger.info(
        "xtts_synthesis_complete job_id=%s lang_code=%s speaker=%s elapsed_ms=%d output=%s",
        job_id, lang_code, speaker, elapsed_ms, mp3_path.name,
    )
    return str(mp3_path)
