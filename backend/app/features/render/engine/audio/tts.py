import asyncio
import html as _html
import logging
import os
import re
from pathlib import Path

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
# Sentence boundary regex — accepts both Latin (.!?) and CJK (。！？)
# punctuation, with optional whitespace. CJK text rarely has spaces
# between sentences so the trailing \s+ requirement (pre-2026-06-28)
# silently swallowed multi-sentence ja/ko/zh input into one chunk.
_SENTENCE_END_RE = re.compile(r"(?<=[.!?。！？])\s*")
# Question-mark terminator across Latin + CJK.
_QUESTION_END_RE = re.compile(r"[?？]\s*$")
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
# Spoken-text cleanup — strip caption disfluencies before TTS (P0b)
# ---------------------------------------------------------------------------
# The "subtitle" / "translated_subtitle" voice sources speak the RAW
# transcript verbatim. Auto-captions are full of disfluencies ("um", "uh",
# "ờ", "えーと"), stutter repeats ("the the"), and run-on fragments that a
# TTS engine reads literally — which is a major cause of robotic-sounding
# narration. This is a CONSERVATIVE, no-LLM cleanup: it only removes tokens
# that are unambiguously fillers (never meaningful content words like
# "like"/"so"/"well"), collapses immediate word repeats, and normalises
# punctuation/whitespace. Disable via SPOKEN_TEXT_CLEANUP=0.
_SPOKEN_CLEANUP_ENABLED: bool = os.environ.get("SPOKEN_TEXT_CLEANUP", "1") == "1"

# Standalone filler tokens by language primary tag. Matched only as WHOLE
# words (word boundaries) so substrings inside real words are never touched.
_FILLERS_BY_LANG: dict[str, tuple[str, ...]] = {
    "en": ("um", "uh", "erm", "uhh", "umm", "hmm", "mhm", "uh-huh"),
    "vi": ("ờ", "à", "ừm", "ừ", "ừa", "á", "ời", "hử", "hả"),
    "ja": ("えーと", "えっと", "あのー", "あの", "ええと", "まあ", "なんか"),
    "ko": ("음", "어", "에", "그게", "저기", "뭐랄까"),
}
# Multi-word English fillers removed as phrases (case-insensitive).
_EN_FILLER_PHRASES = ("you know", "i mean", "sort of", "kind of", "you know what i mean")


def _filler_pattern_for(language: str) -> "re.Pattern | None":
    prefix = (language or "").split("-")[0].lower()
    toks = _FILLERS_BY_LANG.get(prefix)
    if not toks:
        return None
    # CJK has no whitespace word boundaries → match the literal token; Latin
    # uses \b boundaries + optional trailing comma so "um," is removed cleanly.
    if prefix in ("ja", "ko"):
        return re.compile("|".join(re.escape(t) for t in toks))
    return re.compile(r"\b(?:%s)\b[,]?" % "|".join(re.escape(t) for t in toks), re.IGNORECASE)


def clean_spoken_text(text: str, language: str = "en-US") -> str:
    """Conservatively strip caption disfluencies before TTS. Never raises;
    returns the input unchanged on any failure or when disabled."""
    if not _SPOKEN_CLEANUP_ENABLED or not text or not text.strip():
        return text
    try:
        s = text
        prefix = (language or "").split("-")[0].lower()
        if prefix == "en":
            for ph in _EN_FILLER_PHRASES:
                s = re.sub(r"\b%s\b[,]?" % re.escape(ph), "", s, flags=re.IGNORECASE)
        pat = _filler_pattern_for(language)
        if pat is not None:
            s = pat.sub("", s)
        # Collapse immediate duplicate words ("the the" / "rồi rồi") — Latin only.
        if prefix not in ("ja", "ko"):
            s = re.sub(r"\b(\w+)(\s+\1\b)+", r"\1", s, flags=re.IGNORECASE)
        # Normalise leftover punctuation/space artefacts.
        s = re.sub(r"\s+([,.!?;:])", r"\1", s)     # space before punctuation
        s = re.sub(r"([,.!?;:])\1{2,}", r"\1", s)  # 3+ repeated punctuation
        s = re.sub(r"\s+([、。，．！？])", r"\1", s)  # space before CJK punctuation
        s = re.sub(r"\s{2,}", " ", s)
        # leading junk after stripping a lead filler (Latin + CJK punctuation)
        s = re.sub(r"^[\s,;:.\-—、。，．！？]+", "", s)
        s = s.strip()
        # Safety: if cleanup nuked almost everything (over-aggressive on a
        # filler-only fragment), keep the original so narration isn't lost.
        if len(s) < max(2, int(len(text.strip()) * 0.4)):
            return text.strip()
        return s
    except Exception as exc:
        logger.debug("clean_spoken_text fallback reason=%s", exc)
        return text


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
# 2026-06-28: previously English-only — now matched per-language so SSML
# emphasis + hook lead-in apply to vi-VN / ja-JP / ko-KR / en-GB narration
# (previously these languages had NO SSML emphasis — narration sounded
# flat and robotic per user feedback).
_HOOK_STARTERS_BY_LANG: dict[str, frozenset[str]] = {
    "en": frozenset((
        "but", "wait", "so", "now", "here", "then", "and",
        "remember", "think", "imagine", "look", "listen",
    )),
    "vi": frozenset((
        "nhưng", "đợi", "vậy", "rồi", "thế", "bây giờ", "hãy",
        "nhớ", "thử", "nhìn", "nghe", "tưởng", "hỏi", "này",
        "thật", "đúng", "thực sự", "đầu tiên", "cuối cùng",
    )),
    "ja": frozenset((
        "でも", "しかし", "ちょっと", "さて", "今", "ここで", "それでは",
        "思い出して", "想像して", "考えて", "見て", "聞いて",
        "まず", "次に", "最後に", "実は",
    )),
    "ko": frozenset((
        "그런데", "하지만", "잠깐", "자", "지금", "여기", "그럼",
        "기억하세요", "상상해보세요", "생각해보세요", "보세요", "들어보세요",
        "먼저", "다음으로", "마지막으로", "사실은",
    )),
}

# Quoted phrases get emphasis in any language. ALLCAPS only triggers for
# Latin-script languages because CJK doesn't have a "shouty" register.
_ALLCAPS_RE = re.compile(r"\b([A-Z]{2,})\b")
_QUOTED_RE = re.compile(r"[\"'“”‘’]([^\"'“”‘’]{2,30})[\"'“”‘’]")


def _hook_set_for(language: str) -> frozenset[str]:
    """Return hook-starter words for the language's primary tag (en/vi/ja/ko)."""
    prefix = (language or "").split("-")[0].lower()
    return _HOOK_STARTERS_BY_LANG.get(prefix, _HOOK_STARTERS_BY_LANG["en"])


def _build_ssml_content(text: str, pause_style: str, language: str) -> str:
    """Build SSML fragment for insertion inside edge-tts <voice><prosody> wrapper.

    Uses <break>, <emphasis>, and inline <prosody> tweaks only — no outer
    <speak>/<voice> tags. HTML-escapes text content before inserting SSML
    tags so user text containing & < > doesn't corrupt the SSML document.

    2026-06-28: dropped the English-only restriction on emphasis + hook
    lead-in. Multi-language hook starters (en/vi/ja/ko) + quoted-phrase
    emphasis apply to every language so non-English narration gets the
    same expressive cadence as English.
    """
    brk = _SSML_BREAK_MS.get(pause_style, _SSML_BREAK_MS["normal"])
    is_latin_script = (language or "").lower().startswith(("en-", "es-", "pt-", "fr-", "de-", "it-"))
    hook_set = _hook_set_for(language)

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

        # 3a. Quoted-phrase emphasis FIRST (before ALLCAPS) so the SSML
        #     tag's own single-quotes can't be mis-matched as a "quote".
        s = _QUOTED_RE.sub(
            lambda m: f"<emphasis level='moderate'>{m.group(0)}</emphasis>",
            s,
        )
        # 3b. ALLCAPS strong emphasis — latin-script languages only
        #     (CJK has no shouty register). Runs AFTER quoted regex so
        #     the `level='strong'` literal inside the new tag isn't
        #     itself picked up as a quoted phrase by a re-scan.
        if is_latin_script:
            s = _ALLCAPS_RE.sub(
                lambda m: f"<emphasis level='strong'>{m.group(1)}</emphasis>",
                s,
            )

        # 4. Hook lead-in pause for ANY language (was English-only).
        #    Looks up the first word against the language's hook-starter
        #    set; on match, inserts a small beat before the sentence.
        if brk["hook"] > 0 and i > 0:
            _first_token = sent.split(maxsplit=1)
            if _first_token:
                _first_word = _first_token[0].lower().rstrip(",:;。、")
                if _first_word in hook_set:
                    s = f"<break time='{brk['hook']}ms'/> {s}"

        # 5. Question sentences get a small pitch rise via <prosody>.
        #    Latin: wrap the LAST whitespace-delimited word. CJK: wrap
        #    the whole sentence (no whitespace to split on). Edge TTS
        #    honours the tag for all neural voices.
        if _QUESTION_END_RE.search(sent.rstrip()) and "<emphasis" not in s:
            _words = s.rsplit(maxsplit=1)
            if len(_words) == 2:
                head, last = _words
                s = f"{head} <prosody pitch='+1st'>{last}</prosody>"
            else:
                # CJK fallback — no whitespace boundaries.
                s = f"<prosody pitch='+1st'>{s}</prosody>"

        parts.append(s)

        # 6. Inter-sentence break before next sentence
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

    # Lazy import: edge-tts is an optional dependency. Importing it here
    # (not at module top) keeps the render pipeline importable when the
    # package is absent, and surfaces a clear error only on actual use.
    try:
        import edge_tts
    except ImportError as _imp_exc:
        raise RuntimeError(
            "edge-tts is not installed; cannot synthesize narration "
            "(pip install edge-tts, or switch tts_engine to an offline option)"
        ) from _imp_exc

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
    """Route narration synthesis to the requested TTS engine.

    Engines:
      "edge" (default) — Edge-TTS (online). On failure (no network / 403)
                         it falls back to an offline engine automatically:
                         Piper (CPU — vi/en) first, then XTTS (GPU — adds
                         ja/ko). Voice keeps working on offline/firewalled
                         machines with no config change; zero behaviour
                         change when Edge succeeds.
      "piper"          — Piper offline neural TTS (CPU, no network).
                         Falls back to Edge on any failure.
      "xtts"           — Coqui XTTS v2 (GPU, multilingual incl. ja/ko).
                         Falls back to Edge.
    """
    engine = (tts_engine or "edge").strip().lower()

    def _edge() -> str:
        return generate_narration_mp3(
            text=text, language=language, gender=gender, rate=rate,
            job_id=job_id, voice_id=voice_id, output_path=output_path,
            content_type=content_type,
        )

    def _piper() -> str:
        # Piper takes plain text — use the same humanizer as XTTS (no SSML,
        # which Piper would read literally).
        from app.features.render.engine.audio.tts_piper import synthesize_piper
        _ct = _CONTENT_TYPE_VOICE_PROFILES.get(content_type) or _CONTENT_TYPE_VOICE_PROFILES["vlog"]
        _h = humanize_narration_text(str(text or "").strip(), pause_style=_ct["pause_style"])
        return synthesize_piper(
            text=_h, language=language, gender=gender,
            job_id=job_id, content_type=content_type, output_path=output_path,
        )

    def _xtts() -> str:
        # XTTS v2 (GPU) — multilingual; the offline path for Japanese/Korean,
        # which Piper's catalog has no voices for.
        clean = str(text or "").strip()
        if not clean:
            raise RuntimeError("Narration text is empty")
        from app.features.render.engine.audio.tts_xtts import synthesize_xtts
        _ct = _CONTENT_TYPE_VOICE_PROFILES.get(content_type) or _CONTENT_TYPE_VOICE_PROFILES["vlog"]
        _h = humanize_narration_text(clean, pause_style=_ct["pause_style"])
        logger.info(
            "xtts_route job_id=%s content_type=%s pause_style=%s language=%s",
            job_id, content_type, _ct["pause_style"], language,
        )
        return synthesize_xtts(
            text=_h, language=language, gender=gender,
            job_id=job_id, content_type=content_type, output_path=output_path,
        )

    # ── Piper requested ──────────────────────────────────────────────────
    if engine == "piper":
        from app.features.render.ai.dependencies import has_piper
        if has_piper():
            try:
                return _piper()
            except Exception as piper_exc:
                logger.warning(
                    "piper_synthesis_failed_fallback job_id=%s: %s — falling back to edge",
                    job_id, piper_exc,
                )
        else:
            logger.warning("piper_unavailable_fallback job_id=%s — package absent, using edge", job_id)
        return _edge()

    # ── XTTS requested ───────────────────────────────────────────────────
    if engine == "xtts":
        from app.features.render.ai.dependencies import has_xtts as _has_xtts
        if not _has_xtts():
            logger.warning("xtts_unavailable_fallback job_id=%s — TTS package absent, using edge", job_id)
            return _edge()
        try:
            return _xtts()
        except Exception as xtts_exc:
            logger.warning(
                "xtts_synthesis_failed_fallback job_id=%s: %s — falling back to edge",
                job_id, xtts_exc,
            )
            return _edge()

    # ── Default: Edge-TTS, with automatic offline fallback ───────────────
    # Edge needs network. On failure, synthesize offline instead of losing
    # narration: Piper (CPU — vi/en) first, then XTTS (GPU — adds ja/ko).
    try:
        return _edge()
    except Exception as edge_exc:
        from app.features.render.ai.dependencies import has_piper, has_xtts
        # Tier 1 — Piper (CPU offline: Vietnamese, English).
        try:
            from app.features.render.engine.audio.tts_piper import piper_model_available
            if has_piper() and piper_model_available(language, gender):
                logger.warning(
                    "edge_failed_piper_fallback job_id=%s: %s — using offline Piper",
                    job_id, edge_exc,
                )
                return _piper()
        except Exception as piper_exc:
            logger.warning("piper_fallback_failed job_id=%s: %s", job_id, piper_exc)
        # Tier 2 — XTTS (GPU offline: Japanese, Korean, and the rest).
        try:
            if has_xtts():
                logger.warning(
                    "edge_failed_xtts_fallback job_id=%s: %s — using offline XTTS",
                    job_id, edge_exc,
                )
                return _xtts()
        except Exception as xtts_exc:
            logger.warning("xtts_fallback_failed job_id=%s: %s", job_id, xtts_exc)
        raise
