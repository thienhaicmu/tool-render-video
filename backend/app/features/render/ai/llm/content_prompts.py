"""
content_prompts.py — Prompt template for the AI Content Director call
(render_format="content": Script → AI narration → Video).

The LLM reads a raw script / article / news text the user pasted and acts as a
CONTENT DIRECTOR (not a TTS reader): it understands the whole text, then plans
the video — splitting the script into semantic SCENES, authoring the narration
per scene, and deciding emotion / reading speed / pauses / subtitle style. See
docs/CONTENT_MODE_SPEC.md.

v1 MVP scope: the director emits scene/narration/emotion/speed/pause/
subtitle-style/timeline. Visual/bgm/camera/transition/animation are captured as
descriptive HINTS only (stored on the plan, not yet consumed by the render).

Format-safety: the user script is injected via ``str.format`` as a VALUE — Python
does NOT re-parse braces inside substituted values, so a script containing ``{``
or ``}`` is safe. Only the TEMPLATE's own literal braces are doubled (``{{``/``}}``).
"""
from __future__ import annotations

import os as _os

# Cap on input script chars sent to the LLM. A content script is usually short
# (an article / news item / outline), so this is generous. Override via
# CONTENT_MAX_SCRIPT_CHARS.
MAX_CONTENT_SCRIPT_CHARS = int(_os.getenv("CONTENT_MAX_SCRIPT_CHARS", "40000"))

_LANG_NAMES: dict[str, str] = {
    "vi-VN": "Vietnamese (Tiếng Việt)",
    "en-US": "English (American)",
    "en-GB": "English (British)",
    "ja-JP": "Japanese (日本語)",
    "ko-KR": "Korean (한국어)",
}


def _fit_script(text: str, max_chars: int) -> str:
    """Trim an over-long script to ``max_chars`` (keep the head — the opening
    carries the hook + topic). Never raises."""
    try:
        s = (text or "").strip()
        if max_chars > 0 and len(s) > max_chars:
            return s[:max_chars].rstrip()
        return s
    except Exception:
        return (text or "")


_SYSTEM_CONTENT = (
    "You are an expert AI CONTENT DIRECTOR for a faceless short-form video "
    "channel (YouTube automation / AI storytelling / AI news / AI education). "
    "You are given a raw script, article, or news text. You do NOT merely read "
    "it aloud — you UNDERSTAND the whole content, then DIRECT the video: you "
    "detect the topic, tone and target audience; you SPLIT the script into "
    "coherent SCENES by MEANING (never by character count); for each scene you "
    "WRITE THE ACTUAL NARRATION the voice-over speaks (in the target language), "
    "as ONE cohesive script that flows scene→scene; and you decide the emotion, "
    "reading speed, and pauses that make the delivery feel human — not flat. "
    "You think like a storyteller: hook → intro → explain → example → "
    "conclusion → CTA. Output ONLY valid JSON in the exact shape requested — no "
    "prose, no markdown, no code fences."
)

_USER_TEMPLATE_CONTENT = """═══ SOURCE SCRIPT / CONTENT ═══
{script}

═══ BUILD A CONTENT PLAN FROM THIS SCRIPT ═══
NARRATION LANGUAGE: {lang_name}
TARGET DURATION:    ~{target_seconds:.0f} seconds (~{target_minutes:.1f} min) — a GUIDE, not a hard cap
CREATOR TONE:       {tone_clause}

═══ HOW TO WORK ═══
1. Read the WHOLE script above and understand it before planning.
2. Detect the metadata: topic, tone, target audience.
3. **SPLIT INTO SCENES BY MEANING** — each scene is one coherent idea/beat, NOT
   a fixed number of characters. Follow the arc where it fits the content:
   hook → intro → explain → example → conclusion → cta. Set each scene's "role".
4. **WRITE THE NARRATION** ("narration") for every scene, in {lang_name}. Rewrite
   the source into spoken voice-over that flows from the previous scene (use
   connective phrasing). Keep each scene CONCISE — about 1–4 sentences, speakable
   at a natural pace. Preserve every key fact, name and number — never fabricate.
5. **EMOTION** ("emotion"): pick the feeling this scene should land — one of
   normal|excited|calm|suspense|epic|sad|happy|curious|motivating|surprise.
6. **READING SPEED** ("reading_speed"): a multiplier 0.90–1.15 — slower for weighty
   / emotional beats, a touch faster for light or list-like beats. Do NOT make
   every scene the same speed.
7. **PAUSES** ("pause_before" / "pause_after", seconds): add a short pause (0.2–1.0s)
   where a beat should breathe — e.g. before a reveal, after the hook. 0 = none.
8. **EMPHASIS** ("emphasis"): a few words/phrases in the narration to stress.
9. **DURATION** ("est_duration_sec"): estimate each scene's spoken length. The
   engine refines this from the real TTS — your estimate only guides pacing.
10. **SUBTITLE STYLE** ("subtitle_style", plan-level): suggest one of
    default|capcut|word_by_word|karaoke|highlight|minimal|bold based on the tone.
11. **VISUAL / BGM / CAMERA / TRANSITION / ANIMATION HINTS**: describe what would
    suit each scene (e.g. visual_hint "footage of a battlefield"). These are
    DESCRIPTIVE SUGGESTIONS ONLY — the engine may or may not use them. Leave any
    hint you have no opinion on as an empty string.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "topic": "<detected topic, short, in {lang_name}>",
  "tone": "<detected tone, short>",
  "audience": "<target audience, short>",
  "language": "{target_language}",
  "total_target_sec": <float — your estimated total spoken length>,
  "subtitle_style": "default|capcut|word_by_word|karaoke|highlight|minimal|bold",
  "bgm_mood": "epic|calm|technology|news|sad|funny|dark|happy|corporate|",
  "scenes": [
    {{
      "index": <int, 0-based>,
      "role": "hook|intro|explain|example|conclusion|cta",
      "narration": "<voice-over for this scene in {lang_name}>",
      "emotion": "normal|excited|calm|suspense|epic|sad|happy|curious|motivating|surprise",
      "reading_speed": <float 0.90-1.15>,
      "pause_before": <float seconds>,
      "pause_after": <float seconds>,
      "emphasis": ["<word or phrase to stress>"],
      "est_duration_sec": <float>,
      "visual_hint": "<what footage/image would suit this scene, or ''>",
      "camera_hint": "zoom_in|zoom_out|pan|still|",
      "transition_hint": "fade|cut|slide|flash|zoom|",
      "animation_hint": "highlight|popup|title|lower_third|progress_bar|"
    }}
  ]
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. "scenes" is a non-empty array; every scene has a non-empty "narration".
3. Scenes are in narration order; "index" starts at 0 and increases by 1.
4. reading_speed within 0.50–2.00 (aim 0.90–1.15). pause_before/pause_after >= 0.
5. Preserve the source's facts, names and numbers — rewrite the wording, never
   invent content that is not supported by the script.

═══ OUTPUT JSON ═══
"""


def build_content_plan_prompt(
    script: str,
    target_duration_sec: float = 90.0,
    target_language: str = "vi-VN",
    tone: str = "",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the Content Director LLM call.

    ``script`` is the raw user text (article / news / outline). It is injected as
    a ``str.format`` VALUE — braces inside it are NOT re-parsed, so arbitrary
    user text is format-safe. Never raises."""
    cleaned = _fit_script(script, MAX_CONTENT_SCRIPT_CHARS)
    lang_name = _LANG_NAMES.get(target_language, target_language or "the target language")
    tone_clause = (tone or "").strip() or "engaging / natural"
    dur = float(target_duration_sec or 0.0)
    user = _USER_TEMPLATE_CONTENT.format(
        script=cleaned,
        lang_name=lang_name,
        target_language=target_language or "vi-VN",
        target_seconds=dur,
        target_minutes=dur / 60.0,
        tone_clause=tone_clause,
    )
    return _SYSTEM_CONTENT, user
