import asyncio
import logging
import re
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)

from app.core.config import TEMP_DIR
from app.services.voice_profiles import resolve_voice_profile

TTS_TIMEOUT_SEC = 60

# Content-type voice profiles — rate and pause style defaults.
# Applied only when creator has not set a custom voice_rate.
_CONTENT_TYPE_VOICE_PROFILES: dict[str, dict] = {
    "commentary": {"rate_nudge": "+10%", "pause_style": "light"},
    "vlog":       {"rate_nudge": "+0%",  "pause_style": "normal"},
    "story":      {"rate_nudge": "-3%",  "pause_style": "normal"},
    "tutorial":   {"rate_nudge": "-8%",  "pause_style": "deliberate"},
    "interview":  {"rate_nudge": "-5%",  "pause_style": "deliberate"},
    "montage":    {"rate_nudge": "+12%", "pause_style": "light"},
    "gaming":     {"rate_nudge": "+12%", "pause_style": "light"},
}
_DEFAULT_VOICE_RATE = "+0%"
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s+")
_CONJUNCTIONS = frozenset(
    ("and", "but", "so", "because", "while", "when", "although", "however", "therefore")
)


def _effective_rate_for(creator_rate: str, content_type: str) -> str:
    """Use content-type rate nudge when creator has not customized the rate."""
    raw = str(creator_rate or _DEFAULT_VOICE_RATE).strip()
    if raw == _DEFAULT_VOICE_RATE or not raw:
        p = _CONTENT_TYPE_VOICE_PROFILES.get(content_type) or _CONTENT_TYPE_VOICE_PROFILES["vlog"]
        return p["rate_nudge"]
    return raw


def _break_sentence_if_long(sent: str, min_split_words: int) -> str:
    """Insert a comma before the first conjunction that appears after `min_split_words` words."""
    words = sent.split()
    for i in range(min_split_words, len(words) - 2):
        w = words[i].lower().rstrip(",:;")
        if w in _CONJUNCTIONS:
            before = " ".join(words[:i])
            if not before.endswith(","):
                return before + ", " + " ".join(words[i:])
            return sent
    return sent


def humanize_narration_text(text: str, pause_style: str = "normal") -> str:
    """
    Add natural cadence signals to TTS input text.

    pause_style:
      "light"      — minimal intervention (commentary, gaming, montage)
      "normal"     — sentence pauses + short declaration emphasis (vlog, story)
      "deliberate" — phrase breaks, colon pauses, more breathing (tutorial, interview)
    """
    if not text or not text.strip():
        return text

    text = re.sub(r" {2,}", " ", text).strip()
    sentences = _SENTENCE_END_RE.split(text)
    processed = []

    # Per-style thresholds for long-sentence breaking.
    # long_threshold: sentence must exceed this word count before a break is inserted.
    # min_before: conjunction must appear after this many words.
    long_threshold = {"light": 20, "normal": 15, "deliberate": 11}.get(pause_style, 15)
    min_before = {"light": 12, "normal": 9, "deliberate": 7}.get(pause_style, 9)

    for raw_sent in sentences:
        sent = raw_sent.strip()
        if not sent:
            continue

        word_count = len(sent.split())

        # Break long sentences at natural conjunction points
        if word_count > long_threshold:
            sent = _break_sentence_if_long(sent, min_before)

        # Convert "Label: explanation" → "Label... explanation" for cleaner pause
        if pause_style == "deliberate":
            m = re.match(r"^([A-Za-z][^:]{1,18}):\s+(.+)$", sent)
            if m:
                sent = m.group(1) + "... " + m.group(2)

        # Add dramatic pause ellipsis after short strong declarations
        if pause_style in ("normal", "deliberate") and sent.endswith("!") and word_count <= 7:
            sent = sent + "..."

        processed.append(sent)

    return " ".join(processed)


def generate_narration_mp3(
    *,
    text: str,
    language: str,
    gender: str,
    rate: str,
    job_id: str,
    voice_id: str | None = None,
    output_path: str | None = None,
    content_type: str = "vlog",
) -> str:
    clean_text = str(text or "").strip()
    if not clean_text:
        raise RuntimeError("Narration text is empty")

    _ct_profile = _CONTENT_TYPE_VOICE_PROFILES.get(content_type) or _CONTENT_TYPE_VOICE_PROFILES["vlog"]
    _humanized = humanize_narration_text(clean_text, pause_style=_ct_profile["pause_style"])
    _rate = _effective_rate_for(rate, content_type)
    logger.info(
        "tts_humanized job_id=%s content_type=%s rate=%s pause_style=%s",
        job_id, content_type, _rate, _ct_profile["pause_style"],
    )

    profile = resolve_voice_profile(language, gender, voice_id=voice_id)
    work_dir = TEMP_DIR / job_id / "voice"
    work_dir.mkdir(parents=True, exist_ok=True)
    mp3_path = Path(output_path) if output_path else work_dir / "narration.mp3"
    mp3_path.parent.mkdir(parents=True, exist_ok=True)

    async def _run():
        communicate = edge_tts.Communicate(_humanized, profile["voice_id"], rate=_rate)
        try:
            await asyncio.wait_for(communicate.save(str(mp3_path)), timeout=TTS_TIMEOUT_SEC)
        except asyncio.TimeoutError:
            raise RuntimeError(f"TTS timed out after {TTS_TIMEOUT_SEC}s")

    try:
        asyncio.run(_run())
    except Exception as exc:
        logger.error("tts_generation_failed job_id=%s voice_id=%s: %s", job_id, profile.get("voice_id"), exc)
        raise RuntimeError(f"AI voice generation failed: {exc}") from exc

    if not mp3_path.exists() or mp3_path.stat().st_size <= 0:
        raise RuntimeError("AI voice generation failed: output file was not created")
    return str(mp3_path)
