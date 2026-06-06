import asyncio
import html as _html
import logging
import os
import re
from pathlib import Path

import edge_tts

logger = logging.getLogger(__name__)

from app.core.config import TEMP_DIR
from app.features.render.engine.audio.profiles import resolve_voice_profile

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


# ---------------------------------------------------------------------------
# SSML humanizer — Edge-TTS semantic pacing (OQ-4.1)
# ---------------------------------------------------------------------------

_SSML_HUMANIZER_ENABLED: bool = os.environ.get("SSML_HUMANIZER_ENABLED", "1") == "1"

# Break durations in milliseconds, indexed by pause_style.
_SSML_BREAK_MS: dict[str, dict[str, int]] = {
    "light": {
        "colon": 100, "ellipsis": 200, "sentence": 0,
        "question": 100, "exclaim": 0, "hook": 0,
    },
    "normal": {
        "colon": 250, "ellipsis": 350, "sentence": 150,
        "question": 200, "exclaim": 150, "hook": 100,
    },
    "deliberate": {
        "colon": 400, "ellipsis": 500, "sentence": 200,
        "question": 300, "exclaim": 200, "hook": 150,
    },
}

# Lead-in pause: these words at sentence start signal a hook or pivot point.
_HOOK_STARTERS = frozenset(
    ("but", "wait", "so", "now", "here", "then", "and", "remember", "think", "imagine")
)

_ALLCAPS_RE = re.compile(r"\b([A-Z]{2,})\b")


def _build_ssml_content(text: str, pause_style: str, language: str) -> str:
    """Build SSML fragment for insertion inside edge-tts <voice><prosody> wrapper.

    Uses <break> and <emphasis> only — no outer <speak>/<voice> tags.
    HTML-escapes text content before inserting SSML tags so user text
    containing & < > doesn't corrupt the SSML document.
    """
    brk = _SSML_BREAK_MS.get(pause_style, _SSML_BREAK_MS["normal"])
    is_english = language.startswith("en-")

    raw_sentences = _SENTENCE_END_RE.split(text.strip())
    parts: list[str] = []

    for i, raw in enumerate(raw_sentences):
        sent = raw.strip()
        if not sent:
            continue

        # Escape user-supplied text so &, <, > don't break SSML
        s = _html.escape(sent, quote=False)

        # 1. Ellipsis → dramatic break (before colon rule to avoid over-splitting)
        if brk["ellipsis"] > 0:
            s = s.replace("...", f"<break time='{brk['ellipsis']}ms'/>")

        # 2. Colon pause (introduces explanation, list, or reveal)
        if brk["colon"] > 0:
            s = re.sub(r":\s*", f":<break time='{brk['colon']}ms'/> ", s)

        # 3. English-only: ALL CAPS words get strong emphasis
        if is_english:
            s = _ALLCAPS_RE.sub(
                lambda m: f"<emphasis level='strong'>{m.group(1)}</emphasis>",
                s,
            )

        # 4. Hook lead-in: small beat before pivot/hook starters (not first sentence)
        if is_english and brk["hook"] > 0 and i > 0:
            first_word = sent.split()[0].lower().rstrip(",")
            if first_word in _HOOK_STARTERS:
                s = f"<break time='{brk['hook']}ms'/> {s}"

        parts.append(s)

        # 5. Inter-sentence break before next sentence
        if i < len(raw_sentences) - 1:
            end = sent.rstrip()
            if end.endswith("?") and brk["question"] > 0:
                parts.append(f"<break time='{brk['question']}ms'/>")
            elif end.endswith("!") and brk["exclaim"] > 0:
                parts.append(f"<break time='{brk['exclaim']}ms'/>")
            elif brk["sentence"] > 0:
                parts.append(f"<break time='{brk['sentence']}ms'/>")

    return " ".join(parts)


def ssml_humanize_for_edge(
    text: str,
    pause_style: str = "normal",
    language: str = "en-US",
) -> str:
    """SSML content for edge-tts: semantic pauses + emphasis.

    Returns SSML fragment (no <speak>/<voice> wrappers — edge-tts adds those).
    Falls back to humanize_narration_text() on any failure.
    SSML_HUMANIZER_ENABLED=0 disables SSML and uses plain-text humanization.
    """
    if not _SSML_HUMANIZER_ENABLED or not text or not text.strip():
        return humanize_narration_text(text, pause_style)
    try:
        result = _build_ssml_content(text, pause_style, language)
        if not result or len(result) < 3:
            return humanize_narration_text(text, pause_style)
        return result
    except Exception as exc:
        logger.debug("ssml_humanize_fallback reason=%s", exc)
        return humanize_narration_text(text, pause_style)


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
    _humanized = ssml_humanize_for_edge(
        clean_text,
        pause_style=_ct_profile["pause_style"],
        language=language,
    )
    _ssml_active = _SSML_HUMANIZER_ENABLED and "<break" in _humanized
    _rate = _effective_rate_for(rate, content_type)
    logger.info(
        "tts_humanized job_id=%s content_type=%s rate=%s pause_style=%s ssml=%s",
        job_id, content_type, _rate, _ct_profile["pause_style"], _ssml_active,
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


def generate_narration_audio(
    *,
    text: str,
    language: str,
    gender: str,
    rate: str,
    job_id: str,
    voice_id: str | None = None,
    output_path: str | None = None,
    content_type: str = "vlog",
    tts_engine: str = "edge",
) -> str:
    """Route narration synthesis to Edge-TTS (default) or XTTS v2 (premium).

    tts_engine="edge" → generate_narration_mp3() — zero behavior change.
    tts_engine="xtts" → XTTS v2 with automatic edge fallback on any failure.
    """
    if tts_engine != "xtts":
        return generate_narration_mp3(
            text=text, language=language, gender=gender, rate=rate,
            job_id=job_id, voice_id=voice_id, output_path=output_path,
            content_type=content_type,
        )

    # XTTS path: availability check before import
    from app.ai.dependencies import has_xtts as _has_xtts
    if not _has_xtts():
        logger.warning("xtts_unavailable_fallback job_id=%s — TTS package absent, using edge", job_id)
        return generate_narration_mp3(
            text=text, language=language, gender=gender, rate=rate,
            job_id=job_id, voice_id=voice_id, output_path=output_path,
            content_type=content_type,
        )

    # Humanize text through the same pipeline as edge (rate is not applied in XTTS — natural prosody)
    clean_text = str(text or "").strip()
    if not clean_text:
        raise RuntimeError("Narration text is empty")
    _ct_profile = _CONTENT_TYPE_VOICE_PROFILES.get(content_type) or _CONTENT_TYPE_VOICE_PROFILES["vlog"]
    _humanized = humanize_narration_text(clean_text, pause_style=_ct_profile["pause_style"])
    logger.info(
        "xtts_route job_id=%s content_type=%s pause_style=%s language=%s",
        job_id, content_type, _ct_profile["pause_style"], language,
    )

    try:
        from app.services.audio.tts_xtts import synthesize_xtts
        return synthesize_xtts(
            text=_humanized,
            language=language,
            gender=gender,
            job_id=job_id,
            content_type=content_type,
            output_path=output_path,
        )
    except Exception as xtts_exc:
        logger.warning(
            "xtts_synthesis_failed_fallback job_id=%s: %s — falling back to edge",
            job_id, xtts_exc,
        )
        return generate_narration_mp3(
            text=text, language=language, gender=gender, rate=rate,
            job_id=job_id, voice_id=voice_id, output_path=output_path,
            content_type=content_type,
        )
