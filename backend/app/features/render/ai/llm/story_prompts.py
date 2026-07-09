"""
story_prompts.py — prompt templates for Story Intelligence (P1).

Two passes over a chunked chapter (see story_chunker):
  1. DIGEST (map)   — per chunk: rolling summary + characters/environments seen +
                      key beats, grounded in the running summary of prior chunks.
  2. REDUCE         — consolidate all chunk digests (+ any cross-chapter context)
                      into ONE Story Bible: setting/hook/cta + canonical characters
                      + canonical environments + topic/tone/audience/video_style
                      + a whole-chapter rolling summary.

Format-safety: every runtime value (chunk text, summaries) is injected via
``str.format`` as a VALUE — Python does NOT re-parse braces inside substituted
values, so arbitrary text (incl. ``{``/``}``) is safe. Only the TEMPLATE's own
literal braces are doubled (``{{``/``}}``). Mirrors content_prompts.py.
"""
from __future__ import annotations

import os as _os

MAX_CHUNK_CHARS = int(_os.getenv("STORY_MAX_CHUNK_CHARS", "16000"))

# Prompt version tag — logged with every run so a quality regression traces to a
# revision. Bump on any material change below.
STORY_PROMPT_VERSION = "v1"

_LANG_NAMES: dict[str, str] = {
    "vi": "Vietnamese (Tiếng Việt)", "vi-VN": "Vietnamese (Tiếng Việt)",
    "en": "English", "en-US": "English (American)", "en-GB": "English (British)",
    "ja": "Japanese (日本語)", "ja-JP": "Japanese (日本語)",
}


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get((code or "").strip(), code or "the target language")


def _fit(text: str, max_chars: int) -> str:
    try:
        s = (text or "").strip()
        return s[:max_chars].rstrip() if (max_chars > 0 and len(s) > max_chars) else s
    except Exception:
        return (text or "")


# ── Pass 1: DIGEST (per chunk) ────────────────────────────────────────────────

_SYSTEM_DIGEST = (
    "You are an expert STORY EDITOR reading ONE part of a longer novel/webnovel "
    "chapter (wuxia / xianxia / romance / horror / fantasy). You do NOT rewrite or "
    "shorten for narration here — you ANALYSE: track what happens, who appears, and "
    "where, so a later pass can build a consistent storyboard. Ground your analysis "
    "in the running summary of earlier parts when given. Output ONLY valid JSON in "
    "the exact shape requested — no prose, no markdown, no code fences."
)

_USER_DIGEST = """═══ RUNNING SUMMARY SO FAR (earlier parts) ═══
{prior_summary}

═══ CURRENT PART {chunk_index}/{total_chunks} ═══
{chunk}

═══ TASK ═══
Analyse THIS part in context. Language for summary/labels: {lang_name}.
Base everything on the text; never invent facts.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "summary": "<concise summary of THIS part, continuing the running summary, in {lang_name}>",
  "beats": ["<key plot beat in order>", "..."],
  "characters": [
    {{ "id": "<short stable id, e.g. 'han_phong'>",
       "name": "<display name>",
       "description": "<appearance + role as revealed HERE, for visual consistency>" }}
  ],
  "environments": [
    {{ "id": "<short stable id, e.g. 'van_kiem_tong'>",
       "name": "<place name>",
       "description": "<what the place looks like>" }}
  ]
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. characters/environments may be empty arrays if none appear in THIS part.
3. Reuse the SAME id for a character/place already introduced earlier.

═══ OUTPUT JSON ═══
"""


def build_story_digest_prompt(
    chunk: str,
    prior_summary: str = "",
    language: str = "vi",
    chunk_index: int = 1,
    total_chunks: int = 1,
) -> tuple[str, str]:
    """Pass-1 (map) — (system, user) for one chunk's digest. Never raises."""
    user = _USER_DIGEST.format(
        prior_summary=_fit(prior_summary, 4000) or "(this is the first part)",
        chunk=_fit(chunk, MAX_CHUNK_CHARS),
        chunk_index=int(chunk_index or 1),
        total_chunks=int(total_chunks or 1),
        lang_name=_lang_name(language),
    )
    return _SYSTEM_DIGEST, user


# ── Pass 2: REDUCE (consolidate into a Story Bible) ───────────────────────────

_SYSTEM_REDUCE = (
    "You are an expert STORY EDITOR building the 'story bible' of a whole chapter "
    "from the per-part digests. You reconstruct: the overall setting, the opening "
    "HOOK and closing CTA, the recurring CHARACTERS with a CANONICAL description of "
    "each (their look + role, reused for visual consistency), the recurring "
    "ENVIRONMENTS, and a single whole-chapter rolling summary. Output ONLY valid "
    "JSON in the exact shape requested — no prose, no markdown, no code fences."
)

_USER_REDUCE = """═══ CROSS-CHAPTER CONTEXT (prior chapters, optional) ═══
{prior_context}

═══ PER-PART DIGESTS OF THIS CHAPTER (in order) ═══
{digests}

═══ TASK ═══
Consolidate into ONE story bible for this chapter. Language: {lang_name}.
CREATOR TONE: {tone_clause}. Base everything on the digests; never invent facts.
Merge duplicate characters/places (same id/name) into one canonical entry.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "topic": "<short topic/genre in {lang_name}>",
  "tone": "<detected tone, short>",
  "audience": "<target audience, short>",
  "video_style": "cinematic|anime|documentary|storytelling|",
  "setting": "<overall setting / world, one line>",
  "hook": "<the opening hook, one line in {lang_name}>",
  "cta": "<the closing call-to-action, one line in {lang_name}>",
  "rolling_summary": "<whole-chapter summary in {lang_name}, a few sentences>",
  "characters": [
    {{ "id": "<short stable id>", "name": "<display name>",
       "age": "<if known, else ''>", "gender": "<male|female|'' >",
       "description": "<CANONICAL look + role, reused for visual consistency>" }}
  ],
  "environments": [
    {{ "id": "<short stable id>", "name": "<place name>",
       "description": "<CANONICAL look of the place>" }}
  ]
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. characters/environments may be empty for an abstract chapter.
3. Each description is CANONICAL (age, appearance, attire, role) so an image
   generator draws the SAME character/place every scene.

═══ OUTPUT JSON ═══
"""


def build_story_reduce_prompt(
    digests_text: str,
    prior_context: str = "",
    language: str = "vi",
    tone: str = "",
) -> tuple[str, str]:
    """Pass-2 (reduce) — (system, user) to build the Story Bible from the digests.
    ``digests_text`` and ``prior_context`` are inserted as VALUES → format-safe.
    Never raises."""
    user = _USER_REDUCE.format(
        prior_context=_fit(prior_context, 4000) or "(no prior chapters)",
        digests=_fit(digests_text, MAX_CHUNK_CHARS),
        lang_name=_lang_name(language),
        tone_clause=(tone or "").strip() or "engaging / natural",
    )
    return _SYSTEM_REDUCE, user


# ── Pass 3: STORYBOARD (chunk → scenes → shots, grounded in the Bible) ────────

_SYSTEM_STORYBOARD = (
    "You are an expert STORYBOARD DIRECTOR for a faceless story-video channel. You "
    "adapt ONE part of a novel chapter into a cinematic storyboard: you SPLIT it into "
    "narrative SCENES, and each scene into ordered SHOTS. For every shot you WRITE the "
    "voice-over/dialogue narration (in the target language), choose the shot type "
    "(establishing/medium/close_up/insert/action), camera move, composition and "
    "lighting, name which characters + environment appear, and author a FULL English "
    "image-generation prompt. You keep characters + places CONSISTENT with the given "
    "Story Bible (reuse each character's canonical look every shot). Think like a "
    "film director: vary shot sizes, cut on action, hold on emotion. Output ONLY "
    "valid JSON in the exact shape requested — no prose, no markdown, no code fences."
)

_USER_STORYBOARD = """═══ STORY BIBLE (keep characters + places CONSISTENT with this) ═══
{bible_block}
═══ ART STYLE (apply to every image prompt) ═══
{art_style}

═══ SOURCE PART {chunk_index}/{total_chunks} (adapt THIS into the storyboard) ═══
{chunk}

═══ HOW TO WORK ═══
1. Split THIS part into SCENES by meaning (a scene = one place/beat). Set each
   scene's "role" (hook|intro|rising|climax|falling|resolution|cta) + "emotion".
2. Split each scene into 2-6 SHOTS. Vary shot_type. First shot of a new place is
   usually "establishing"; dialogue alternates "medium"/"close_up"; big moments
   use "action"; details use "insert".
3. For each shot WRITE "narration" in {lang_name} — the voice-over/dialogue for
   that shot, 1-3 sentences, speakable. Set "speaker" to the Bible character id
   who speaks (or "" for the narrator). Preserve facts/names; never invent.
4. Set "camera" (zoom_in|zoom_out|pan_left|pan_right|still), "composition",
   "lighting", "emotion", and "est_duration_sec" (spoken estimate).
5. List "characters" (Bible ids present) + "environment_ref" (Bible env id).
6. Write "visual_prompt" — a FULL standalone English image prompt: SUBJECT ·
   SETTING · SHOT/COMPOSITION · STYLE (reuse the ART STYLE) · LIGHTING · MOOD.
   Reuse each present character's CANONICAL look from the Bible so they look the
   SAME every shot. Add a short "negative_prompt" (things to avoid) or "".

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "scenes": [
    {{
      "scene_title": "<short label in {lang_name}>",
      "role": "hook|intro|rising|climax|falling|resolution|cta",
      "setting_ref": "<Bible environment id or ''>",
      "emotion": "<scene mood>",
      "characters": ["<Bible character id present in the scene>"],
      "shots": [
        {{
          "shot_type": "establishing|medium|close_up|insert|action",
          "narration": "<voice-over/dialogue in {lang_name}>",
          "speaker": "<Bible character id, or '' for narrator>",
          "emotion": "<shot mood>",
          "reading_speed": <float 0.9-1.15>,
          "est_duration_sec": <float>,
          "camera": "zoom_in|zoom_out|pan_left|pan_right|still",
          "composition": "<short>",
          "lighting": "<short>",
          "characters": ["<Bible character id present in the shot>"],
          "environment_ref": "<Bible environment id or ''>",
          "visual_prompt": "<FULL English image prompt for this shot>",
          "negative_prompt": "<things to avoid, or ''>"
        }}
      ]
    }}
  ]
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. "scenes" is non-empty; every scene has >=1 shot; every shot has non-empty
   "narration" and non-empty "visual_prompt".
3. Reuse Bible character/environment ids consistently.

═══ OUTPUT JSON ═══
"""


def _story_bible_block(bible) -> str:
    """Render a StoryBible into a plain-text context block for the storyboard
    prompt. Inserted as a str.format VALUE (brace-neutralised) → format-safe.
    Returns a short placeholder for an empty/None bible. Never raises."""
    if bible is None:
        return "(no bible — infer from the source)"
    try:
        lines: list[str] = []
        if getattr(bible, "setting", ""):
            lines.append(f"SETTING: {bible.setting}")
        if getattr(bible, "hook", ""):
            lines.append(f"HOOK: {bible.hook}")
        if getattr(bible, "cta", ""):
            lines.append(f"CTA: {bible.cta}")
        chars = getattr(bible, "characters", []) or []
        if chars:
            lines.append("CHARACTERS (use the SAME look every shot they appear in):")
            for c in chars:
                cid = (getattr(c, "id", "") or getattr(c, "name", "") or "").strip()
                name = (getattr(c, "name", "") or "").strip()
                desc = (getattr(c, "description", "") or "").strip()
                if cid or name or desc:
                    lines.append(f"  - [{cid}] {name}: {desc}")
        envs = getattr(bible, "environments", []) or []
        if envs:
            lines.append("ENVIRONMENTS (keep each place visually consistent):")
            for e in envs:
                eid = (getattr(e, "id", "") or getattr(e, "name", "") or "").strip()
                name = (getattr(e, "name", "") or "").strip()
                desc = (getattr(e, "description", "") or "").strip()
                if eid or name or desc:
                    lines.append(f"  - [{eid}] {name}: {desc}")
        block = "\n".join(lines) if lines else "(bible is sparse — infer sensibly)"
        return block.replace("{", "(").replace("}", ")")
    except Exception:
        return "(no bible)"


def build_storyboard_prompt(
    chunk: str,
    bible=None,
    language: str = "vi",
    tone: str = "",
    art_style: str = "",
    chunk_index: int = 1,
    total_chunks: int = 1,
) -> tuple[str, str]:
    """Pass-3 — (system, user) to adapt ONE chunk into scenes→shots grounded in the
    Bible. ``chunk``/``art_style`` are inserted as VALUES → format-safe. Never raises."""
    user = _USER_STORYBOARD.format(
        bible_block=_story_bible_block(bible),
        art_style=(art_style or "").strip() or "cinematic, consistent style",
        chunk=_fit(chunk, MAX_CHUNK_CHARS),
        chunk_index=int(chunk_index or 1),
        total_chunks=int(total_chunks or 1),
        lang_name=_lang_name(language),
    )
    return _SYSTEM_STORYBOARD, user


__all__ = [
    "build_story_digest_prompt", "build_story_reduce_prompt", "build_storyboard_prompt",
    "STORY_PROMPT_VERSION", "MAX_CHUNK_CHARS",
]
