"""
story_prompts_v2.py — Super-Prompt templates for Story Mode v2.

ONE call emits the whole StoryPlan v2 (characters + settings + visuals ≤ ceiling +
timeline). Two entry points, SAME output schema:
  • build_super_story_prompt  — mode A: ADAPT an existing story text.
  • build_super_idea_prompt   — mode B: CREATE a story from an idea (+duration/genre),
                                then storyboard it — still one call, same schema.
+ build_super_repair_prompt   — CM-8: fix a malformed/truncated JSON once.

Scientific structure (in-call, dependency order): ROLE → INPUT → METHOD
(characters→settings→visuals→timeline) → SCHEMA → HARD RULES (= domain INVARIANTS)
→ SELF-CHECK. Grounding: later sections reference earlier ids.

Format-safety: the user text (chapter/idea) is CONCATENATED (not str.format'd), and
the JSON schema block is a raw constant — so arbitrary braces in the input are safe.
Only small controlled params (lang name, ceiling, aspect, budget) use str.format.
Never raises.
"""
from __future__ import annotations

import os as _os

from app.domain.story_plan_v2 import BGM_MOODS

MAX_SOURCE_CHARS = int(_os.getenv("STORY_MAX_SOURCE_CHARS", "60000"))
SUPER_PROMPT_VERSION = "s2"   # s2: per-scene bgm_mood on visuals
# AI-facing music-mood vocab (drop the "default" fallback folder — not a creative choice).
_MOOD_VOCAB = "|".join(m for m in BGM_MOODS if m != "default")

_LANG_NAMES = {
    "vi": "Vietnamese (Tiếng Việt)", "vi-VN": "Vietnamese (Tiếng Việt)",
    "en": "English", "en-US": "English", "en-GB": "English",
    "ja": "Japanese (日本語)", "ja-JP": "Japanese (日本語)",
}
_CPS = {"vi": 15.0, "en": 14.0, "ja": 8.0, "ko": 9.0}


def _lang_name(code: str) -> str:
    return _LANG_NAMES.get((code or "").strip(), code or "the target language")


def _fit(text: str, n: int = MAX_SOURCE_CHARS) -> str:
    try:
        s = (text or "").strip()
        return s[:n].rstrip() if (n > 0 and len(s) > n) else s
    except Exception:
        return (text or "")


_SYSTEM = (
    "You are an expert STORY-TO-VIDEO DIRECTOR for a faceless narrated video channel "
    "(wuxia / xianxia / romance / horror / fantasy). You understand the WHOLE story, "
    "then design ONE production plan: recurring CHARACTERS (with a canonical look), "
    "SETTINGS, a SMALL set of WIDE key IMAGES (reused across many narration beats via "
    "camera focus), and a BEAT TIMELINE that narrates the story. You think like a "
    "cinematographer: few strong images, camera pans/zooms to focus regions, hold on "
    "emotion. Output ONLY one valid JSON object in the exact shape requested — no prose, "
    "no markdown, no code fences."
)

# Raw JSON schema (single braces; NOT str.format'd) — mirrors StoryPlan v2 contract.
_SCHEMA = """═══ OUTPUT SCHEMA (return ONLY this one JSON object) ═══
{
  "topic": "<short topic in {LANG}>",
  "tone": "<detected/created tone>",
  "language": "<LANG code>",
  "art_style": "<overall art style, e.g. cinematic ink-wash wuxia>",
  "characters": [
    { "id": "<short slug, e.g. han_phong>", "name": "<display name>",
      "canonical_desc": "<CANONICAL look: age, hair, attire, weapon, aura — reused every image>",
      "age": "", "gender": "male|female|", "voice_gender": "male|female", "voice_style": "calm|fierce|young|…" }
  ],
  "settings": [
    { "id": "<slug>", "name": "<place>", "canonical_desc": "<canonical look of the place>" }
  ],
  "visuals": [
    { "id": "v1", "setting_id": "<a settings id>",
      "prompt": "<FULL English image prompt: a WIDE 16:9 scene; place key elements in clear LEFT / CENTER / RIGHT zones so the camera can pan to them; reuse each present character's canonical look; cinematic, detailed>",
      "negative_prompt": "text, watermark, distorted faces",
      "character_ids": ["<characters ids present>"], "tier": "low|medium|high",
      "bgm_mood": "<MOOD_VOCAB>" }
  ],
  "timeline": [
    { "id": "b1", "narration": "<voice-over for this beat, in target language>",
      "speaker_id": "<a characters id, or '' for narrator>",
      "visual_id": "<a visuals id>",
      "focus": "wide|left|center|right|top|bottom|close",
      "motion": "zoom_in|zoom_out|pan_left|pan_right|pan_up|pan_down|static",
      "transition_in": "cut|fade|slide|zoom|flash|to_black",
      "hook": false, "hook_text": "" }
  ]
}"""


def _rules(ceiling: int, aspect: str, lang_name: str, subtitle_mode: str) -> str:
    if subtitle_mode == "off":
        hook_rule = "Every beat: hook=false, hook_text=\"\" (no on-screen text at all)."
    else:
        hook_rule = ("Mark ONLY 1-3 climactic beats as hook=true with a SHORT punchy "
                     "hook_text (a few words); all other beats hook=false, hook_text=\"\".")
    return (
        "═══ HARD RULES ═══\n"
        "1. ONE JSON object. No prose, no markdown, no code fences.\n"
        f"2. AT MOST {ceiling} entries in \"visuals\". REUSE a visual across many beats "
        "(a beat sharing a place keeps the same visual_id); do NOT make one image per beat.\n"
        "3. Every timeline.visual_id MUST be an id in \"visuals\"; focus MUST be one of the "
        "listed values; speaker_id and every visuals.character_ids MUST be ids in \"characters\".\n"
        f"4. visuals[].prompt in ENGLISH, a WIDE {aspect} scene composed with clear LEFT/CENTER/"
        "RIGHT zones (so the camera pans to focus regions). Reuse each character's canonical look.\n"
        "5. ONE image per SETTING/moment — group beats in the same place onto ONE visual.\n"
        f"6. narration in {lang_name}; each beat = ONE contiguous idea (~1-3 sentences); the beats "
        "in order narrate the whole story faithfully (preserve names/facts, never invent).\n"
        f"7. {hook_rule}\n"
        f"8. Each visuals[].bgm_mood = ONE of [{_MOOD_VOCAB}] — the background-music mood matching "
        "that scene's emotional tone (a creative label only, NOT an audio file/timestamp).\n"
        "9. DO NOT output any render/asset/path/timestamp/duration/seconds field.\n"
        "═══ SELF-CHECK before answering ═══\n"
        "Verify every visual_id / speaker_id / character_ids exists in the arrays above; if not, fix it.\n"
        "═══ OUTPUT JSON ═══"
    )


def _series_memory_block(prior_context: str) -> str:
    """Optional cross-chapter grounding (G1): reproduced VERBATIM from the caller
    (concatenated, never str.format'd) so arbitrary characters in it are safe. "" when
    there is no prior context — one-off chapters stay byte-identical."""
    pc = (prior_context or "").strip()
    if not pc:
        return ""
    return (
        "\n═══ SERIES MEMORY (earlier chapters — STAY CONSISTENT) ═══\n"
        + pc
        + "\nReuse the SAME character ids + canonical look above; do NOT rename or "
        "redesign a returning character. Continue the story faithfully from here.\n"
    )


def build_super_story_prompt(chapter: str, language: str = "vi", art_style: str = "",
                             aspect_ratio: str = "16:9", subtitle_mode: str = "hook_only",
                             ceiling: int = 15, prior_context: str = "") -> "tuple[str, str]":
    """Mode A — (system, user) to ADAPT an existing story into a StoryPlan v2.
    ``prior_context`` (G1) grounds a later chapter on earlier ones when non-empty."""
    lang_name = _lang_name(language)
    method = (
        "═══ METHOD (follow this order) ═══\n"
        "(a) CHARACTERS: define recurring characters + canonical look + voice.\n"
        "(b) SETTINGS: define recurring places.\n"
        f"(c) VISUALS (≤{ceiling}): one WIDE image per key setting/moment, grounded in (a)(b).\n"
        "(d) TIMELINE: narrate the whole story as ordered beats, each pointing to a visual + focus.\n"
    )
    style_line = f"ART STYLE HINT: {art_style.strip()}\n" if (art_style or "").strip() else ""
    user = (
        f"NARRATION LANGUAGE: {lang_name}\n{style_line}"
        + method
        + _series_memory_block(prior_context)
        + "\n═══ SOURCE STORY (adapt THIS) ═══\n" + _fit(chapter) + "\n\n"
        + _SCHEMA.replace("{LANG}", lang_name).replace("<LANG code>", language).replace("<MOOD_VOCAB>", _MOOD_VOCAB) + "\n\n"
        + _rules(ceiling, aspect_ratio, lang_name, subtitle_mode)
    )
    return _SYSTEM, user


def build_super_idea_prompt(idea: str, duration_sec: int = 0, genre: str = "",
                            language: str = "vi", art_style: str = "", aspect_ratio: str = "16:9",
                            subtitle_mode: str = "hook_only", ceiling: int = 15,
                            prior_context: str = "") -> "tuple[str, str]":
    """Mode B — (system, user) to CREATE a story from an idea then storyboard it (same schema).
    ``prior_context`` (G1) grounds a later chapter on earlier ones when non-empty."""
    lang_name = _lang_name(language)
    cps = _CPS.get((language or "").strip().lower()[:2], 14.0)
    budget = int(max(0, duration_sec) * cps) if duration_sec and duration_sec > 0 else 0
    dur_line = (f"TARGET LENGTH: ~{int(duration_sec)} seconds → total narration ~{budget} characters "
                f"(size the timeline to fit).\n") if budget else "TARGET LENGTH: model decides.\n"
    genre_line = f"GENRE: {genre.strip()}\n" if (genre or "").strip() else ""
    style_line = f"ART STYLE HINT: {art_style.strip()}\n" if (art_style or "").strip() else ""
    method = (
        "═══ METHOD (follow this order) ═══\n"
        "(0) INVENT a complete short story from the idea below (arc: hook→rising→climax→resolution), "
        f"in {lang_name}, sized to the target length. Never pad; keep it coherent.\n"
        "(a) CHARACTERS: the recurring cast you invented + canonical look + voice.\n"
        "(b) SETTINGS: the places.\n"
        f"(c) VISUALS (≤{ceiling}): one WIDE image per key setting/moment.\n"
        "(d) TIMELINE: narrate your story as ordered beats, each pointing to a visual + focus.\n"
    )
    user = (
        f"NARRATION LANGUAGE: {lang_name}\n{genre_line}{dur_line}{style_line}"
        + method
        + _series_memory_block(prior_context)
        + "\n═══ STORY IDEA (create FROM this) ═══\n" + _fit(idea, 8000) + "\n\n"
        + _SCHEMA.replace("{LANG}", lang_name).replace("<LANG code>", language).replace("<MOOD_VOCAB>", _MOOD_VOCAB) + "\n\n"
        + _rules(ceiling, aspect_ratio, lang_name, subtitle_mode)
    )
    return _SYSTEM, user


_SYSTEM_REPAIR = (
    "You are a strict JSON repair tool. The text given was meant to be ONE StoryPlan JSON object "
    "but is malformed / truncated / wrapped in prose. Return ONLY a corrected valid JSON object "
    "(same shape), no prose/markdown/fences. Preserve as much content as possible; the object MUST "
    "have non-empty \"visuals\" and \"timeline\" arrays; every timeline.visual_id must match a "
    "visuals id. Drop an incomplete trailing beat rather than inventing content."
)


def build_super_repair_prompt(broken: str) -> "tuple[str, str]":
    return _SYSTEM_REPAIR, "Fix this into ONE valid StoryPlan JSON object:\n\n" + _fit(broken)


__all__ = ["build_super_story_prompt", "build_super_idea_prompt", "build_super_repair_prompt",
           "SUPER_PROMPT_VERSION"]
