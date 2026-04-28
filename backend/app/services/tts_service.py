import asyncio
from pathlib import Path

import edge_tts

from app.core.config import TEMP_DIR
from app.services.voice_profiles import resolve_voice_profile

TTS_TIMEOUT_SEC = 60


def generate_narration_mp3(
    *,
    text: str,
    language: str,
    gender: str,
    rate: str,
    job_id: str,
    voice_id: str | None = None,
    output_path: str | None = None,
) -> str:
    clean_text = str(text or "").strip()
    if not clean_text:
        raise RuntimeError("Narration text is empty")

    profile = resolve_voice_profile(language, gender, voice_id=voice_id)
    work_dir = TEMP_DIR / job_id / "voice"
    work_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = Path(output_path) if output_path else work_dir / "narration.mp3"
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run():
        communicate = edge_tts.Communicate(clean_text, profile["voice_id"], rate=str(rate or "+0%"))
        try:
            await asyncio.wait_for(communicate.save(str(mp3_path)), timeout=TTS_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            raise RuntimeError(f"TTS timed out after {TTS_TIMEOUT_SEC}s")

    try:
        asyncio.run(_run())
    except Exception as exc:
        raise RuntimeError(f"AI voice generation failed: {exc}") from exc

    if not mp3_path.exists() or mp3_path.stat().st_size <= 0:
        raise RuntimeError("AI voice generation failed: output file was not created")
    return str(mp3_path)
