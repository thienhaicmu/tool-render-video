"""
rewrite_prompts.py — Prompt template for AI subtitle rewrite for TTS.

Mirrors prompts.py organization but for a different LLM call: rewrite
the per-part transcript text into TTS-friendly narration that fits a
target duration in seconds. Used by app.features.render.ai.llm.rewrite.
"""
from __future__ import annotations

import os as _os

# Word-per-minute rate per language (avg adult narrator pace).
# Used to compute word budget = (target_duration_sec / 60) * wpm.
# Conservative (10% under typical) so TTS doesn't over-run.
_WPM_BY_LANG: dict[str, int] = {
    "vi-VN": 140,   # Vietnamese — syllable-heavy, slower
    "en-US": 150,   # American English
    "en-GB": 145,   # British English
    "ja-JP": 200,   # Japanese mora count
    "ko-KR": 180,   # Korean
}
_DEFAULT_WPM = 150  # fallback for unrecognised language

# Full language names + native examples so the LLM doesn't have to guess
# what "vi-VN" means and writes in the right script/style. Critical when
# the source transcript is in a different language than the target voice
# (cross-language rewrite / translation in one pass).
_LANG_INFO: dict[str, dict[str, str]] = {
    "vi-VN": {
        "name": "Vietnamese",
        "native": "Tiếng Việt",
        "style_note": "Use natural spoken Vietnamese with diacritics. Prefer everyday spoken vocabulary over formal/literary words.",
    },
    "en-US": {
        "name": "English (American)",
        "native": "English",
        "style_note": "Use natural spoken American English. Contractions OK (it's, you're).",
    },
    "en-GB": {
        "name": "English (British)",
        "native": "English",
        "style_note": "Use natural spoken British English. Contractions OK.",
    },
    "ja-JP": {
        "name": "Japanese",
        "native": "日本語",
        "style_note": "Use natural spoken Japanese (です/ます polite form by default). Mix kanji + kana naturally.",
    },
    "ko-KR": {
        "name": "Korean",
        "native": "한국어",
        "style_note": "Use natural spoken Korean (해요 polite form by default).",
    },
}
_DEFAULT_LANG_INFO = {
    "name": "the target language",
    "native": "",
    "style_note": "Use natural spoken style appropriate to a narrator voice-over.",
}

# Hard cap on input transcript chars sent to the LLM (rewrite call).
# Per-part SRTs are short (~15-90 sec → ~50-500 chars), so cap at 4000
# to cover the long tail and reject pathologically long inputs.
MAX_REWRITE_INPUT_CHARS = int(_os.getenv("REWRITE_MAX_INPUT_CHARS", "4000"))


def _compute_word_budget(target_duration_sec: float, target_language: str) -> int:
    """Return target word count from duration + language WPM table.
    Floors at 3 words (TTS sanity); ceils at 800 (sanity)."""
    wpm = _WPM_BY_LANG.get(target_language, _DEFAULT_WPM)
    budget = int((max(1.0, target_duration_sec) / 60.0) * wpm)
    return max(3, min(800, budget))


_SYSTEM_REWRITE = (
    "You are a professional TTS narration script writer fluent in many languages. "
    "Rewrite the input transcript to be spoken aloud as a voice-over that fits a "
    "TARGET DURATION in a SPECIFIC TARGET LANGUAGE. When the source transcript is "
    "in a different language than the target, TRANSLATE while rewriting — produce "
    "natural, native-sounding output in the target language (NOT a literal word-for-word "
    "translation). Preserve every key fact, name, and number. "
    "Output ONLY the rewritten text — no prose wrappers, no markdown, no code fences, "
    "no explanation, no language tags, no quotation marks around the output."
)

_USER_TEMPLATE_REWRITE = """Rewrite the SOURCE TRANSCRIPT below into a TTS-ready voice-over script.

═══ TARGET OUTPUT ═══
LANGUAGE:        {target_lang_name} ({target_language}) — write in {target_lang_native}
DURATION:        {target_duration_sec:.1f} seconds when read aloud by a natural narrator
WORD COUNT:      about {word_budget} words (at {wpm} words/minute — DO NOT exceed {hard_cap_words} words)
TONE:            {tone_clause}
LANGUAGE STYLE:  {style_note}

═══ HOW TO WORK ═══

STEP 1 — Detect the source language of the SOURCE TRANSCRIPT below.

STEP 2 — Decide your task:
  IF source language == {target_lang_name}:
      → REWRITE ONLY (keep the same language, polish for TTS narration).
  IF source language != {target_lang_name}:
      → TRANSLATE + REWRITE into {target_lang_name}. Do NOT keep any source-language
        words except proper nouns (names of people, places, brands).
        The output MUST be entirely in {target_lang_name}.

STEP 3 — Apply the TONE "{tone_clause}" to your wording choices throughout.

STEP 4 — Compress or expand so the spoken duration matches {target_duration_sec:.1f}s
        (about {word_budget} words at the {target_lang_name} narrator pace).

═══ HARD RULES ═══

1. Output is ONE block of plain text. No bullets, no numbering, no headings.
2. No JSON, no markdown, no code fences, no <tags>, no quotation marks wrapping the whole output.
3. Preserve every key fact, every name, every number from the source.
4. Output MUST be 100% in {target_lang_name}. No mixed languages.
5. Speakable structure: complete sentences, natural pauses, punctuation a narrator can follow.
6. Avoid symbols a TTS engine mispronounces: no &, no #, no %, no abbreviations
   like "Mr." / "U.S." — spell them out the way they should be SPOKEN.
7. NEVER exceed {hard_cap_words} words. Cut filler first, then merge sentences.

═══ SOURCE TRANSCRIPT ═══
{text}

═══ OUTPUT ═══
(Write the rewritten narration in {target_lang_native}, nothing else):"""


def build_rewrite_prompt(
    text: str,
    target_duration_sec: float,
    target_language: str,
    tone: str = "",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the rewrite LLM call.

    Inputs are truncated to MAX_REWRITE_INPUT_CHARS so a pathological
    long input doesn't blow the prompt budget. ``tone`` is a free-form
    creator hint ("playful", "dramatic", "informative") rendered into
    the TONE line — empty string defaults to "natural / informative".

    Format safety: the template uses {} placeholders exclusively
    (no literal braces inside the body), so .format() substitution is
    direct — no brace-doubling needed. Tests pin that the format call
    accepts the exact placeholder set without KeyError.
    """
    cleaned = (text or "").strip()
    if len(cleaned) > MAX_REWRITE_INPUT_CHARS:
        cleaned = cleaned[:MAX_REWRITE_INPUT_CHARS] + " [truncated]"
    word_budget = _compute_word_budget(target_duration_sec, target_language)
    wpm = _WPM_BY_LANG.get(target_language, _DEFAULT_WPM)
    tone_clause = (tone or "").strip() or "natural / informative"
    lang_info = _LANG_INFO.get(target_language, _DEFAULT_LANG_INFO)
    user = _USER_TEMPLATE_REWRITE.format(
        target_duration_sec=float(target_duration_sec),
        target_language=target_language,
        target_lang_name=lang_info["name"],
        target_lang_native=lang_info["native"] or lang_info["name"],
        style_note=lang_info["style_note"],
        word_budget=word_budget,
        wpm=wpm,
        tone_clause=tone_clause,
        hard_cap_words=word_budget * 2,
        text=cleaned,
    )
    return _SYSTEM_REWRITE, user
