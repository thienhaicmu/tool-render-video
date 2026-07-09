"""
tts_elevenlabs.py — ElevenLabs TTS provider (Story Mode, online, opt-in).

Story routes English + Japanese narration to ElevenLabs (audiobook-grade
expressiveness) while Vietnamese stays on Gemini TTS (see resolve_story_tts_engine
in tts.py). This module is the thin ElevenLabs adapter: lazy SDK import, key from
ELEVENLABS_API_KEY, model from STORY_ELEVEN_MODEL (default eleven_multilingual_v2).

Opt-in + graceful: ``elevenlabs_available()`` gates use; ``synthesize_elevenlabs``
raises on failure so the tts.py dispatch falls through to the free edge chain — a
paid-provider outage never loses a render's narration. Never imported at startup
(optional dep).
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("app.render.tts.elevenlabs")


def elevenlabs_available() -> bool:
    """True when the ElevenLabs SDK is importable AND a key is configured. Never
    raises."""
    if not (os.getenv("ELEVENLABS_API_KEY") or "").strip():
        return False
    try:
        import elevenlabs  # noqa: F401 — lazy optional dep
        return True
    except Exception:
        return False


def _model() -> str:
    return (os.getenv("STORY_ELEVEN_MODEL", "eleven_multilingual_v2").strip()
            or "eleven_multilingual_v2")


def _default_voice(gender: str) -> str:
    """Fallback ElevenLabs VOICE ID when the caller passes no voice_id. Env-overridable
    (STORY_ELEVEN_VOICE_FEMALE / _MALE). Defaults are well-known ElevenLabs default
    voice IDs (Rachel / Josh) — the API needs an ID, not a name."""
    g = (gender or "").strip().lower()
    if g == "male":
        return (os.getenv("STORY_ELEVEN_VOICE_MALE", "TxGEqnHWrfWFTfGW9XjX").strip() or "TxGEqnHWrfWFTfGW9XjX")
    return (os.getenv("STORY_ELEVEN_VOICE_FEMALE", "21m00Tcm4TlvDq8ikWAM").strip() or "21m00Tcm4TlvDq8ikWAM")


def synthesize_elevenlabs(
    *,
    text: str,
    language: str = "en",
    gender: str = "female",
    job_id: str = "",
    voice_id: "str | None" = None,
    output_path: "str | None" = None,
) -> str:
    """Synthesize ``text`` with ElevenLabs → an mp3 path. RAISES on any failure so
    the tts dispatch falls through to the edge chain. ``voice_id`` is an ElevenLabs
    voice name or id (from Voice Casting); falls back to a gender default."""
    clean = str(text or "").strip()
    if not clean:
        raise RuntimeError("Narration text is empty")
    key = (os.getenv("ELEVENLABS_API_KEY") or "").strip()
    if not key:
        raise RuntimeError("ELEVENLABS_API_KEY not set")

    from elevenlabs.client import ElevenLabs  # lazy — optional dep
    client = ElevenLabs(api_key=key)
    voice = (voice_id or "").strip() or _default_voice(gender)

    out = Path(output_path) if output_path else Path(f"eleven_{job_id or 'x'}.mp3")
    out.parent.mkdir(parents=True, exist_ok=True)

    audio = client.text_to_speech.convert(
        voice_id=voice, model_id=_model(), text=clean,
        output_format="mp3_44100_128",
    )
    # The SDK returns an iterator of byte chunks (or bytes) — normalise to bytes.
    if isinstance(audio, (bytes, bytearray)):
        data = bytes(audio)
    else:
        data = b"".join(chunk for chunk in audio if chunk)
    if not data:
        raise RuntimeError("ElevenLabs returned no audio")
    out.write_bytes(data)
    if not (out.exists() and out.stat().st_size > 0):
        raise RuntimeError("ElevenLabs wrote no audio file")
    logger.info("elevenlabs_ok job_id=%s voice=%s lang=%s bytes=%d", job_id, voice, language, len(data))
    return str(out)


__all__ = ["elevenlabs_available", "synthesize_elevenlabs"]
