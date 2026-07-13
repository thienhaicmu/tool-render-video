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
SUPER_PROMPT_VERSION = "s10"  # s10: idea-mode length enforcement (fill target duration, no "never pad") + quantified visual reuse; s9: drop dead negative_prompt (F-12); s8: +per-beat emotion + code-derived vocab; s7: +pose; s6: library-pick; s5: asset-library hints; s4: bgm_cue/char_*
# AI-facing music-mood vocab (drop the "default" fallback folder — not a creative choice).
_MOOD_VOCAB = "|".join(m for m in BGM_MOODS if m != "default")

_LANG_NAMES = {
    "vi": "Vietnamese (Tiếng Việt)", "vi-VN": "Vietnamese (Tiếng Việt)",
    "en": "English", "en-US": "English", "en-GB": "English",
    "ja": "Japanese (日本語)", "ja-JP": "Japanese (日本語)",
    "ko": "Korean (한국어)", "ko-KR": "Korean (한국어)",
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
  "region": "cn|jp|ko|vi|eu|us|",
  "genre_key": "wuxia|ngontinh|horror|fantasy|codai|hiendai|",
  "characters": [
    { "id": "<short slug, e.g. han_phong>", "name": "<display name>",
      "canonical_desc": "<CANONICAL look: age, hair, attire, weapon, aura — reused every image>",
      "archetype": "<lowercase English role token, e.g. swordsman|emperor|office_worker|princess|witch|child|ghost — or '' if unsure>",
      "asset": "<a CHARACTERS slug from the ASSET LIBRARY that best fits this character, or '' if none fits / no library given>",
      "age": "", "gender": "male|female|", "voice_gender": "male|female", "voice_style": "calm|fierce|young|…" }
  ],
  "settings": [
    { "id": "<slug>", "name": "<place>", "canonical_desc": "<canonical look of the place>",
      "scene_kind": "<lowercase English scene token, e.g. cafe|forest|throne_room|bedroom|garden|street — or '' if unsure>",
      "asset": "<a BACKGROUNDS slug from the ASSET LIBRARY that best fits this place, or '' if none fits / no library given>" }
  ],
  "visuals": [
    { "id": "v1", "setting_id": "<a settings id>",
      "prompt": "<FULL English image prompt: a WIDE 16:9 scene; place key elements in clear LEFT / CENTER / RIGHT zones so the camera can pan to them; reuse each present character's canonical look; cinematic, detailed>",
      "character_ids": ["<characters ids present>"], "tier": "low|medium|high" }
  ],
  "timeline": [
    { "id": "b1", "narration": "<voice-over for this beat, in target language>",
      "speaker_id": "<a characters id, or '' for narrator>",
      "visual_id": "<a visuals id>",
      "focus": "wide|left|center|right|top|bottom|close",
      "motion": "zoom_in|zoom_out|pan_left|pan_right|pan_up|pan_down|static",
      "transition_in": "cut|fade|slide|zoom|flash|to_black",
      "bgm_mood": "<MOOD_VOCAB>",
      "bgm_cue": "under|intro|outro|none",
      "bgm_intensity": "low|med|high",
      "source_audio": "mute|duck|keep",
      "char_anchor": "none|left|center|right",
      "char_scale": "small|medium|large",
      "char_motion": "static|fade|slide|float",
      "emotion": "normal|happy|angry|sad|surprised",
      "pose": "stand|wave|cheer|point|hip",
      "text_anchor": "auto|top|bottom|left|right",
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
        f"2. AT MOST {ceiling} entries in \"visuals\" — usually FAR FEWER than the number of "
        "beats. REUSE each visual across MANY beats (aim for ~3-6 beats per visual): beats in the "
        "same place/moment share ONE visual_id. NEVER make one image per beat — the TIMELINE can be "
        "long (many beats = a long video), but the IMAGE SET stays small.\n"
        "3. Every timeline.visual_id MUST be an id in \"visuals\"; focus MUST be one of the "
        "listed values; speaker_id and every visuals.character_ids MUST be ids in \"characters\".\n"
        f"4. visuals[].prompt in ENGLISH, a WIDE {aspect} scene composed with clear LEFT/CENTER/"
        "RIGHT zones (so the camera pans to focus regions). Reuse each character's canonical look.\n"
        "5. ONE image per SETTING/moment — group beats in the same place onto ONE visual.\n"
        f"6. narration in {lang_name}; each beat = ONE contiguous idea (~1-3 sentences); the beats "
        "in order narrate the whole story faithfully (preserve names/facts, never invent).\n"
        f"7. {hook_rule}\n"
        f"8. Each timeline beat's bgm_mood = ONE of [{_MOOD_VOCAB}] — the background-music mood "
        "matching THAT beat's emotional tone (a creative label only, NOT an audio file/timestamp).\n"
        "9. bgm_cue = WHERE the music sits in the beat: under (whole beat) | intro (start only) | "
        "outro (end only) | none (silence). Use intro on a scene's FIRST beat, outro on its LAST, "
        "none for a quiet beat; under otherwise. bgm_intensity = low|med|high. LABELS only, never seconds.\n"
        "10. char_anchor = where the SPEAKING character stands: none|left|center|right — set none when "
        "speaker_id is '' (narrator). char_scale = small|medium|large; char_motion = static|fade|slide|float. "
        "emotion = the SPEAKER's feeling THIS beat: normal|happy|angry|sad|surprised — match the beat's tone "
        "(use normal when neutral). pose = the speaker's gesture THIS beat: stand (neutral) | wave (greeting) | "
        "cheer (excited) | point (accusing/indicating) | hip (defiant) — use stand unless the action clearly "
        "calls for one. source_audio = mute|duck|keep (how a base video's own audio is treated).\n"
        "11. text_anchor = where on-screen text sits: auto|top|bottom|left|right. Use auto normally; pick a "
        "side OPPOSITE char_anchor so text never covers the character.\n"
        "12. region/genre_key/archetype/scene_kind are OPTIONAL asset-library hints: lowercase English "
        "tokens only; leave \"\" when unsure (never invent). They do NOT change the story.\n"
        "13. \"asset\" (character/setting) = an exact SLUG copied from the ASSET LIBRARY section when one "
        "fits, else \"\". Never a path; never a slug that is not listed. Absent library → \"\".\n"
        "14. DO NOT output any render/path/timestamp/duration/seconds field.\n"
        "═══ SELF-CHECK before answering ═══\n"
        "Verify every visual_id / speaker_id / character_ids exists in the arrays above; if not, fix it.\n"
        "═══ OUTPUT JSON ═══"
    )


def _library_block(library_catalog: str) -> str:
    """Optional ASSET LIBRARY catalog (library-pick): reproduced VERBATIM (concatenated,
    never str.format'd) so arbitrary characters are safe. "" when there is no catalog —
    the prompt is then byte-identical to the no-library version (Sacred #2 rollback)."""
    cat = (library_catalog or "").strip()
    if not cat:
        return ""
    return (
        "\n═══ ASSET LIBRARY (offline art you MAY reuse) ═══\n"
        + cat
        + "\nFor each character/setting, if a library asset above FITS it, set its "
        "\"asset\" to that exact slug (copy verbatim). If none fits, set \"asset\":\"\" "
        "(fresh art will be drawn). Only ever use a slug that appears above.\n"
    )


def _vocab_block() -> str:
    """Controlled token vocab for the OPTIONAL hint fields (archetype / scene_kind /
    emotion / pose), DERIVED FROM CODE (svg_presets._ARCH + svg_scene._SCENES) so it never
    drifts as new archetypes/scenes are added. Teaching the vocab aligns the AI's free
    tokens with the library + procedural presets → stronger matching even without the
    library catalog. Lazy-imported + defensive: "" on any failure (prompt stays valid)."""
    try:
        from app.features.render.engine.visual.svg_presets import _ARCH
        from app.features.render.engine.visual.svg_scene import _SCENES
        archetypes = ", ".join(sorted(_ARCH))
        seen: dict = {}                                   # one representative alias per scene fn
        for alias, fn in _SCENES.items():
            seen.setdefault(fn, alias)
        scenes = ", ".join(sorted(seen.values()))
        return (
            "\n═══ TOKEN VOCAB (for the OPTIONAL hint fields — pick the CLOSEST, else \"\") ═══\n"
            f"archetype ∈ {{ {archetypes} }}\n"
            f"scene_kind ∈ {{ {scenes} }}\n"
            "emotion ∈ { normal, happy, angry, sad, surprised }  (per beat — the speaker's feeling)\n"
            "pose ∈ { stand, wave, cheer, point, hip }           (per beat — the speaker's gesture)\n"
        )
    except Exception:
        return ""


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
                             ceiling: int = 15, prior_context: str = "",
                             library_catalog: str = "") -> "tuple[str, str]":
    """Mode A — (system, user) to ADAPT an existing story into a StoryPlan v2.
    ``prior_context`` (G1) grounds a later chapter on earlier ones when non-empty.
    ``library_catalog`` (library-pick) lets the AI choose ``asset`` slugs when non-empty."""
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
        + _library_block(library_catalog)
        + _vocab_block()
        + "\n═══ SOURCE STORY (adapt THIS) ═══\n" + _fit(chapter) + "\n\n"
        + _SCHEMA.replace("{LANG}", lang_name).replace("<LANG code>", language).replace("<MOOD_VOCAB>", _MOOD_VOCAB) + "\n\n"
        + _rules(ceiling, aspect_ratio, lang_name, subtitle_mode)
    )
    return _SYSTEM, user


def build_super_idea_prompt(idea: str, duration_sec: int = 0, genre: str = "",
                            language: str = "vi", art_style: str = "", aspect_ratio: str = "16:9",
                            subtitle_mode: str = "hook_only", ceiling: int = 15,
                            prior_context: str = "", library_catalog: str = "") -> "tuple[str, str]":
    """Mode B — (system, user) to CREATE a story from an idea then storyboard it (same schema).
    ``prior_context`` (G1) grounds a later chapter on earlier ones when non-empty.
    ``library_catalog`` (library-pick) lets the AI choose ``asset`` slugs when non-empty."""
    lang_name = _lang_name(language)
    cps = _CPS.get((language or "").strip().lower()[:2], 14.0)
    budget = int(max(0, duration_sec) * cps) if duration_sec and duration_sec > 0 else 0
    # Length is a REQUIREMENT, not a soft target: a thin idea + "never pad" used to
    # collapse a 3-minute request into a ~30s stub. Floor at ~85% of budget and give
    # a beat-count guide (~1 beat per ~6s) so the model develops a full arc.
    _min_chars = int(budget * 0.85) if budget else 0
    _min_beats = max(6, int(round(duration_sec / 6.0))) if (duration_sec and duration_sec > 0) else 0
    dur_line = (
        f"TARGET LENGTH: ~{int(duration_sec)} seconds. This REQUIRES ~{budget} characters of "
        f"narration IN TOTAL across all beats (at least ~{_min_chars}), spread over roughly "
        f"{_min_beats}+ beats. GENUINELY FILL {int(duration_sec)}s — develop the plot to reach it; "
        f"do NOT stop early or hand back a short stub.\n"
    ) if budget else "TARGET LENGTH: model decides.\n"
    genre_line = f"GENRE: {genre.strip()}\n" if (genre or "").strip() else ""
    style_line = f"ART STYLE HINT: {art_style.strip()}\n" if (art_style or "").strip() else ""
    method = (
        "═══ METHOD (follow this order) ═══\n"
        "(0) INVENT a COMPLETE story from the idea below with a full arc "
        "(hook→rising action→climax→resolution), "
        f"in {lang_name}, DEVELOPED richly enough to fill the whole TARGET LENGTH above — a longer "
        "target needs MORE scenes, MORE beats and fuller narration. Do NOT stop short. Keep it "
        "coherent with no filler repetition, but flesh out plot, characters and detail to reach the length.\n"
        "(a) CHARACTERS: the recurring cast you invented + canonical look + voice.\n"
        "(b) SETTINGS: the places.\n"
        f"(c) VISUALS (≤{ceiling}): a SMALL set of WIDE images, each reused across many beats.\n"
        "(d) TIMELINE: narrate your story as ordered beats (enough beats to fill the target length), "
        "each pointing to a visual + focus.\n"
    )
    user = (
        f"NARRATION LANGUAGE: {lang_name}\n{genre_line}{dur_line}{style_line}"
        + method
        + _series_memory_block(prior_context)
        + _library_block(library_catalog)
        + _vocab_block()
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
