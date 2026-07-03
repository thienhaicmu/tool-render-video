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
{bible_block}
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
11. **SCENE TITLE** ("scene_title"): a short label for this scene (for the review
    timeline), in {lang_name}.
12. **VISUAL PROMPT** ("visual_prompt"): a FULL, descriptive prompt an image/video
    generator (or a stock search) could use for this scene — subject, setting,
    style, lighting, mood. English is fine here (generators prefer it). Example:
    "A cinematic battlefield at sunrise, Napoleon leading troops, dramatic
    lighting, realistic, 4k". Also give a short "negative_prompt" (things to
    avoid) when useful, else "". "visual_hint" stays a short human label.
13. **ASSET SUGGESTION** ("asset_suggestion"): your best guess at the visual
    source for this scene — one of ai_image|ai_video|stock|upload|local|"".
14. **CAMERA / TRANSITION / ANIMATION / BGM**: suggest what would suit each scene.
    DESCRIPTIVE SUGGESTIONS ONLY — the engine may or may not use them. Leave any
    field you have no opinion on as an empty string.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "topic": "<detected topic, short, in {lang_name}>",
  "tone": "<detected tone, short>",
  "audience": "<target audience, short>",
  "language": "{target_language}",
  "video_style": "documentary|storytelling|educational|news|explainer|",
  "total_target_sec": <float — your estimated total spoken length>,
  "subtitle_style": "default|capcut|word_by_word|karaoke|highlight|minimal|bold",
  "bgm_mood": "epic|calm|technology|news|sad|funny|dark|happy|corporate|",
  "scenes": [
    {{
      "index": <int, 0-based>,
      "scene_title": "<short scene label in {lang_name}>",
      "role": "hook|intro|explain|example|conclusion|cta",
      "narration": "<voice-over for this scene in {lang_name}>",
      "emotion": "normal|excited|calm|suspense|epic|sad|happy|curious|motivating|surprise",
      "reading_speed": <float 0.90-1.15>,
      "pause_before": <float seconds>,
      "pause_after": <float seconds>,
      "emphasis": ["<word or phrase to stress>"],
      "characters": ["<Story Bible character id/name appearing in this scene>"],
      "continuity": "<what carries over from the previous scene, or ''>",
      "est_duration_sec": <float>,
      "subtitle_style": "<per-scene override, or '' to use the plan style>",
      "visual_hint": "<short label of what footage/image suits this scene, or ''>",
      "visual_prompt": "<full image/video generator prompt for this scene, or ''>",
      "negative_prompt": "<things to avoid in the visual, or ''>",
      "asset_suggestion": "ai_image|ai_video|stock|upload|local|",
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


# ── CU-4 Pass A: Story Bible (whole-script understanding, BEFORE the plan) ────
_SYSTEM_BIBLE = (
    "You are an expert STORY EDITOR. You READ THE WHOLE script/article and "
    "reconstruct a compact 'story bible' BEFORE any scripting: the topic, tone "
    "and audience; the overall SETTING; the opening HOOK and the closing CTA; and "
    "the recurring CHARACTERS/subjects with a CANONICAL description of each (their "
    "look + role) so every later scene depicts them consistently. Output ONLY "
    "valid JSON in the exact shape requested — no prose, no markdown, no code fences."
)

_USER_TEMPLATE_BIBLE = """═══ SOURCE SCRIPT / CONTENT ═══
{script}

═══ TASK ═══
Reconstruct the story bible of this content BEFORE writing it. Language: {lang_name}.
CREATOR TONE: {tone_clause}. Base everything on the script; never invent facts.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "topic": "<detected topic, short, in {lang_name}>",
  "tone": "<detected tone, short>",
  "audience": "<target audience, short>",
  "video_style": "documentary|storytelling|educational|news|explainer|",
  "setting": "<the overall setting / world, one line>",
  "hook": "<the opening hook, one line in {lang_name}>",
  "cta": "<the closing call-to-action, one line in {lang_name}>",
  "characters": [
    {{ "id": "<short stable id, e.g. 'napoleon'>",
       "name": "<display name>",
       "description": "<CANONICAL look + role, reused for visual consistency>" }}
  ]
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. characters may be an empty array for abstract topics (no recurring subject).
3. Each character description is CANONICAL (age, appearance, attire, role) so an
   image generator draws the SAME character every scene.

═══ OUTPUT JSON ═══
"""


def build_story_bible_prompt(
    script: str,
    target_language: str = "vi-VN",
    tone: str = "",
) -> tuple[str, str]:
    """CU-4 Pass A — return (system, user) for the Story Bible call. Never raises."""
    cleaned = _fit_script(script, MAX_CONTENT_SCRIPT_CHARS)
    lang_name = _LANG_NAMES.get(target_language, target_language or "the target language")
    tone_clause = (tone or "").strip() or "engaging / natural"
    user = _USER_TEMPLATE_BIBLE.format(script=cleaned, lang_name=lang_name, tone_clause=tone_clause)
    return _SYSTEM_BIBLE, user


def _bible_block(bible) -> str:
    """Render a StoryBible into a plain-text context block for the plan prompt
    (Pass B). Passed as a str.format VALUE (brace-neutralised) → format-safe.
    Returns "" for an empty/None bible. Never raises."""
    if bible is None:
        return ""
    try:
        setting = (getattr(bible, "setting", "") or "").strip()
        hook = (getattr(bible, "hook", "") or "").strip()
        cta = (getattr(bible, "cta", "") or "").strip()
        chars = getattr(bible, "characters", []) or []
        if not (setting or hook or cta or chars):
            return ""
        lines = ["", "═══ STORY BIBLE (plan FROM this — keep it consistent) ═══"]
        if setting:
            lines.append(f"SETTING: {setting}")
        if hook:
            lines.append(f"HOOK: {hook}")
        if cta:
            lines.append(f"CTA: {cta}")
        if chars:
            lines.append("CHARACTERS (use the SAME description every scene they appear in):")
            for c in chars:
                cid = (getattr(c, "id", "") or getattr(c, "name", "") or "").strip()
                name = (getattr(c, "name", "") or "").strip()
                desc = (getattr(c, "description", "") or "").strip()
                if cid or name or desc:
                    lines.append(f"  - [{cid}] {name}: {desc}")
            lines.append("For each scene, set \"characters\" to the ids present.")
        block = "\n".join(lines) + "\n"
        return block.replace("{", "(").replace("}", ")")
    except Exception:
        return ""



# ── CU-14: Publish intelligence (SEO metadata from the finished plan) ─────────
_SYSTEM_PUBLISH = (
    "You are a YouTube/TikTok SEO expert. Given a video's topic + a sample of its "
    "narration, you write a click-worthy TITLE, a compelling DESCRIPTION, relevant "
    "TAGS, and pick which scene makes the best THUMBNAIL. Output ONLY valid JSON in "
    "the exact shape requested — no prose, no markdown, no code fences."
)

_USER_TEMPLATE_PUBLISH = """═══ VIDEO ═══
TOPIC: {topic}
TONE: {tone}
AUDIENCE: {audience}
LANGUAGE: {lang_name}
NARRATION SAMPLE:
{narration_sample}

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "title": "<catchy title in {lang_name}, < 90 chars>",
  "description": "<2-4 sentence description in {lang_name}>",
  "tags": ["<tag>", "..."],
  "thumbnail_scene_index": <int, the 0-based scene index that best represents the video>
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. title is < 90 chars; tags is 5-15 short strings.

═══ OUTPUT JSON ═══
"""


def build_publish_meta_prompt(
    topic: str, tone: str = "", audience: str = "",
    target_language: str = "vi-VN", narration_sample: str = "",
) -> tuple[str, str]:
    """CU-14 — return (system, user) for the publish-metadata call. Never raises."""
    lang_name = _LANG_NAMES.get(target_language, target_language or "the target language")
    user = _USER_TEMPLATE_PUBLISH.format(
        topic=(topic or "").strip() or "(unknown)",
        tone=(tone or "").strip() or "neutral",
        audience=(audience or "").strip() or "general",
        lang_name=lang_name,
        narration_sample=_fit_script(narration_sample or "", 4000),
    )
    return _SYSTEM_PUBLISH, user


def build_content_plan_prompt(
    script: str,
    target_duration_sec: float = 90.0,
    target_language: str = "vi-VN",
    tone: str = "",
    bible=None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the Content Director LLM call.

    ``script`` is the raw user text; ``bible`` (CU-4 Pass A StoryBible) is injected
    as context so narration + visuals are grounded/consistent. Both are ``str.format``
    VALUES — braces inside are NOT re-parsed, so arbitrary text is format-safe.
    Never raises."""
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
        bible_block=_bible_block(bible),
    )
    return _SYSTEM_CONTENT, user
