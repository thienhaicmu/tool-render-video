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
# Idea-mode source cap — was a hardcoded 8000 that silently truncated the TAIL of a
# detailed outline (losing the ending/message). Env-tunable; generous default so a full
# multi-act brief survives, still bounded for prompt context.
MAX_IDEA_CHARS = int(_os.getenv("STORY_MAX_IDEA_CHARS", "20000"))
SUPER_PROMPT_VERSION = "s24"  # s24: added modern-drama procedural scenes (station/pachinko/hotel) → new scene_kind tokens auto-appear in the TOKEN VOCAB. s23: master-data sync — TOKEN VOCAB block also teaches genre_key + region (derived from domain GENRE_KEY/REGION, incl. new xianxia) so the AI library-picks a reachable asset scope. s22: multiline rule-5 now threads the per-beat length hint (beat_char_hint) + drops the "SHORT SCENE / 1-4 turns" cap, so a beat's lines total a SUBSTANTIAL mini-scene — fixes multiline beats coming out as 1-word stubs (10-min request → ~78s). s21: P3 idea — STORY IDEA treated as a SKELETON to DRAMATIZE (never compress at input granularity) + build_super_idea_prompt gains a length_factor override so the director can ESCALATE-AND-REGENERATE when the first plan lands short (STORY_IDEA_EXPAND_*). s20: P1 MULTI-LINE beats — STORY_MULTILINE_BEATS=1 makes a beat carry a lines[] dialogue array (each turn its own speaker/text/emotion/pose); one shot may hold 1-4 turns. Default off = pre-P1, bit-identical. s19: Phase-3 LEAN CONTRACT — SVG prompts (P1/P3) ask only for the CREATIVE per-beat fields (narration/speaker/visual/focus/bgm_mood/emotion/pose/hook); the 9 mechanical style labels are derived by StoryPlan.derive_beat_styling (cuts OpenAI strict-mode truncation). P2 keeps the full schema. Toggle STORY_LEAN_CONTRACT=0 to restore the 19-field ask. s18: Phase-1 hygiene — rule-5 self-contradiction fixed (RICH beats no longer told "no paragraph-long beats"); OUTPUT FRAME/aspect now injected in-prompt (was a dead param); STORY_IDEA_DEFAULT_SEC fallback when the FE omits a target length. s17: P3 length compensation (aim ~1.8× since gpt-4o delivers ~55% of a requested length from a thin idea in one call; STORY_IDEA_LENGTH_FACTOR). s16: five-act beat QUOTA (mandate beats per stage → model can't compress a 3-min story into too few beats). s15: P3 RICH-beat length lever — beats are full ~10s paragraphs (~cps*10 chars), count+length derived from target with explicit arithmetic (fixes the terse-beat cap that held a 3-min idea at ~70s). s14: THREE specialised super-prompts by use-case — P1 adapt→SVG, P2 adapt→over-video (new, overlay/source_audio focus), P3 idea→length-as-brief scene scaffold. Full schema kept. s13: per-beat narration budget (P-C); s12: reuse example + visual target (P-B); s11: SVG cleanup (P-A); s10: idea length; s9: drop negative_prompt (F-12); s8: emotion+vocab; s7: pose; s6: library-pick; s5: asset hints; s4: bgm_cue/char_*
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


def _beat_char_hint(language: str) -> str:
    """Language-aware per-beat narration budget (P-C). A beat is one TTS clip; ~3-8s
    of speech is a comfortable, evenly-paced chunk. Derived from the language CPS
    (VI 15 / EN 14 / JA 8 / KO 9 chars-per-second) so the range fits each language."""
    cps = _CPS.get((language or "").strip().lower()[:2], 14.0)
    lo, hi = int(cps * 3), int(cps * 8)
    return f" (~{lo}-{hi} characters, ~1-2 short sentences)"


def _fit(text: str, n: int = MAX_SOURCE_CHARS) -> str:
    try:
        s = (text or "").strip()
        return s[:n].rstrip() if (n > 0 and len(s) > n) else s
    except Exception:
        return (text or "")


_JSON_TAIL = ("Output ONLY one valid JSON object in the exact shape requested — no prose, "
              "no markdown, no code fences.")

# Three SPECIALISED director roles (one super-prompt per use-case, selected by the
# caller). Same StoryPlan schema + HARD RULES; only the ROLE + INPUT + emphasis differ,
# so the model gets a clear, single job instead of one generic prompt serving all cases.

# P1 — ADAPT an existing story → procedurally-illustrated (SVG) narrated video.
_SYS_ADAPT = (
    "You are an expert STORY-TO-VIDEO DIRECTOR adapting an EXISTING written story into a "
    "procedurally-illustrated (SVG) narrated video for a faceless channel (wuxia / xianxia / "
    "romance / horror / fantasy). Understand the WHOLE given story, then design ONE production "
    "plan that NARRATES IT FAITHFULLY: recurring CHARACTERS (canonical look), SETTINGS, a SMALL "
    "set of reused key IMAGES (drawn procedurally), and a BEAT TIMELINE that tells the story in "
    "order. Preserve the original names, facts and plot; never invent new events. Think like a "
    "cinematographer: few strong images, camera focus per beat, hold on emotion. " + _JSON_TAIL
)

# P2 — NARRATE + overlay characters over an EXISTING background VIDEO (no scene design).
_SYS_VIDEO = (
    "You are an expert VIDEO DIRECTOR creating a NARRATED CHARACTER-OVERLAY track over an EXISTING "
    "BACKGROUND VIDEO. The supplied video provides ALL imagery — you NEVER design scenes or key "
    "images. Understand the given story, then write a BEAT TIMELINE that narrates it over the "
    "video, deciding per beat: the narration, WHICH character is on screen and where (overlay), "
    "their emotion/pose, and how the video's own audio is treated. Preserve the original names, "
    "facts and plot; never invent. " + _JSON_TAIL
)

# P3 — WRITE a story of a TARGET LENGTH from an idea, then storyboard it (SVG).
_SYS_IDEA = (
    "You are an expert SCREENWRITER and story-to-video director. Given a short IDEA and a TARGET "
    "LENGTH, FIRST write a complete, engaging story OF THAT LENGTH (a real arc: hook → rising "
    "action → climax → resolution), THEN storyboard it as a procedurally-illustrated (SVG) "
    "narrated video: recurring CHARACTERS, SETTINGS, a SMALL set of reused key IMAGES, and a BEAT "
    "TIMELINE. The story must GENUINELY run the requested length — write it out in full, never "
    "summarise. " + _JSON_TAIL
)

# Back-compat alias (repair prompt + any external reference).
_SYSTEM = _SYS_ADAPT

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
      "canonical_desc": "<the character's canonical look: age, hair, attire, weapon, aura — kept consistent across the whole story / later chapters>",
      "archetype": "<lowercase English role token, e.g. swordsman|emperor|office_worker|princess|witch|child|ghost — or '' if unsure>",
      "asset": "<a CHARACTERS slug from the ASSET LIBRARY that best fits this character, or '' if none fits / no library given>",
      "age": "", "gender": "male|female|", "voice_gender": "male|female" }
  ],
  "settings": [
    { "id": "<slug>", "name": "<place>", "canonical_desc": "<canonical look of the place>",
      "scene_kind": "<lowercase English scene token, e.g. cafe|forest|throne_room|bedroom|garden|street — or '' if unsure>",
      "asset": "<a BACKGROUNDS slug from the ASSET LIBRARY that best fits this place, or '' if none fits / no library given>" }
  ],
  "visuals": [
    { "id": "v1", "setting_id": "<a settings id>",
      "character_ids": ["<characters ids present>"] }
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

# Phase 3 — LEAN CONTRACT beat: only the CREATIVE per-beat fields. The mechanical style
# labels (motion/transition_in/bgm_cue/bgm_intensity/source_audio/char_*/text_anchor) are
# derived deterministically by the pipeline (StoryPlan.derive_beat_styling), so asking the
# model for them only costs tokens + truncation. Used for the SVG prompts (P1/P3) when
# STORY_LEAN_CONTRACT is on; P2 (over-video) keeps the FULL schema (overlay is AI-decided).
_SCHEMA_LEAN = """═══ OUTPUT SCHEMA (return ONLY this one JSON object) ═══
{
  "topic": "<short topic in {LANG}>",
  "tone": "<detected/created tone>",
  "language": "<LANG code>",
  "art_style": "<overall art style, e.g. cinematic ink-wash wuxia>",
  "region": "cn|jp|ko|vi|eu|us|",
  "genre_key": "wuxia|ngontinh|horror|fantasy|codai|hiendai|",
  "characters": [
    { "id": "<short slug, e.g. han_phong>", "name": "<display name>",
      "canonical_desc": "<the character's canonical look: age, hair, attire, weapon, aura — kept consistent across the whole story / later chapters>",
      "archetype": "<lowercase English role token, e.g. swordsman|emperor|office_worker|princess|witch|child|ghost — or '' if unsure>",
      "asset": "<a CHARACTERS slug from the ASSET LIBRARY that best fits this character, or '' if none fits / no library given>",
      "age": "", "gender": "male|female|", "voice_gender": "male|female" }
  ],
  "settings": [
    { "id": "<slug>", "name": "<place>", "canonical_desc": "<canonical look of the place>",
      "scene_kind": "<lowercase English scene token, e.g. cafe|forest|throne_room|bedroom|garden|street — or '' if unsure>",
      "asset": "<a BACKGROUNDS slug from the ASSET LIBRARY that best fits this place, or '' if none fits / no library given>" }
  ],
  "visuals": [
    { "id": "v1", "setting_id": "<a settings id>",
      "character_ids": ["<characters ids present>"] }
  ],
  "timeline": [
    { "id": "b1", "narration": "<voice-over for this beat, in target language>",
      "speaker_id": "<a characters id, or '' for narrator>",
      "visual_id": "<a visuals id>",
      "focus": "wide|left|center|right|top|bottom|close",
      "bgm_mood": "<MOOD_VOCAB>",
      "emotion": "normal|happy|angry|sad|surprised",
      "pose": "stand|wave|cheer|point|hip",
      "hook": false, "hook_text": "" }
  ]
}"""


def _lean_contract() -> bool:
    """Phase 3 — SVG prompts ask only for the creative per-beat fields (default on).
    STORY_LEAN_CONTRACT=0 restores the full 19-field ask (pre-Phase-3, bit-identical)."""
    return _os.getenv("STORY_LEAN_CONTRACT", "1") != "0"


def _multiline() -> bool:
    """P1 — a beat carries a ``lines[]`` dialogue array (each turn its own speaker/
    emotion) instead of a single narration. Default off. STORY_MULTILINE_BEATS=1 to
    enable. Off = the pre-P1 contract, bit-identical."""
    return _os.getenv("STORY_MULTILINE_BEATS", "0") == "1"


# P1 — MULTI-LINE beat: one shot (khung hình) holding a `lines[]` dialogue array. The
# khung-hình fields (visual_id/focus/bgm_mood/hook) stay on the beat; who-says-what +
# emotion/pose move INTO each line. Used when STORY_MULTILINE_BEATS is on.
_SCHEMA_MULTILINE = """═══ OUTPUT SCHEMA (return ONLY this one JSON object) ═══
{
  "topic": "<short topic in {LANG}>",
  "tone": "<detected/created tone>",
  "language": "<LANG code>",
  "art_style": "<overall art style, e.g. cinematic ink-wash wuxia>",
  "region": "cn|jp|ko|vi|eu|us|",
  "genre_key": "wuxia|ngontinh|horror|fantasy|codai|hiendai|",
  "characters": [
    { "id": "<short slug, e.g. han_phong>", "name": "<display name>",
      "canonical_desc": "<the character's canonical look: age, hair, attire, weapon, aura — kept consistent across the whole story / later chapters>",
      "archetype": "<lowercase English role token, e.g. swordsman|emperor|office_worker|princess|witch|child|ghost — or '' if unsure>",
      "asset": "<a CHARACTERS slug from the ASSET LIBRARY that best fits this character, or '' if none fits / no library given>",
      "age": "", "gender": "male|female|", "voice_gender": "male|female" }
  ],
  "settings": [
    { "id": "<slug>", "name": "<place>", "canonical_desc": "<canonical look of the place>",
      "scene_kind": "<lowercase English scene token, e.g. cafe|forest|throne_room|bedroom|garden|street — or '' if unsure>",
      "asset": "<a BACKGROUNDS slug from the ASSET LIBRARY that best fits this place, or '' if none fits / no library given>" }
  ],
  "visuals": [
    { "id": "v1", "setting_id": "<a settings id>",
      "character_ids": ["<characters ids present>"] }
  ],
  "timeline": [
    { "id": "b1", "visual_id": "<a visuals id>",
      "focus": "wide|left|center|right|top|bottom|close",
      "bgm_mood": "<MOOD_VOCAB>",
      "hook": false, "hook_text": "",
      "lines": [
        { "speaker_id": "<a characters id, or '' for narrator>",
          "text": "<what this speaker says here, in target language>",
          "emotion": "normal|happy|angry|sad|surprised",
          "pose": "stand|wave|cheer|point|hip" }
      ] }
  ]
}"""


def _schema(lean: bool) -> str:
    if _multiline():
        return _SCHEMA_MULTILINE
    return _SCHEMA_LEAN if lean else _SCHEMA


def _rules(ceiling: int, aspect: str, lang_name: str, subtitle_mode: str, beat_char_hint: str = "",
           render_mode: str = "svg", rich_beats: bool = False, lean: bool = False,
           multiline: bool = False) -> str:
    if subtitle_mode == "off":
        hook_rule = "Every beat: hook=false, hook_text=\"\" (no on-screen text at all)."
    else:
        hook_rule = ("Mark ONLY 1-3 climactic beats as hook=true with a SHORT punchy "
                     "hook_text (a few words); all other beats hook=false, hook_text=\"\".")
    if render_mode == "video":
        _r4 = ("4. The BACKGROUND is the SUPPLIED VIDEO — do NOT design scenes or picture content. "
               "Create only a FEW \"visuals\" as grouping anchors (one per story moment); their look "
               "is IGNORED (the video shows through). Put your effort into the timeline + character overlay.\n")
    else:
        _r4 = ("4. ONE visual per SETTING/moment — group beats in the same place onto ONE visual. The "
               "render draws each picture procedurally from the visual's setting + present characters "
               "(there is NO image prompt — do not write scene descriptions).\n")
    # A1: OUTPUT FRAME — was a dead param (never in the prompt); now tells the model the
    # aspect so it composes focus / character placement / on-screen text for the frame.
    _frame = {"9:16": "vertical / portrait", "16:9": "widescreen / landscape",
              "1:1": "square"}.get((aspect or "").strip(), (aspect or "16:9"))
    _frame_line = (f"0. OUTPUT FRAME is {aspect or '16:9'} ({_frame}) — compose focus, character "
                   "placement and on-screen text for THIS frame.\n")
    # A3: rule 5 must not self-contradict. For RICH beats (idea/long-adapt paragraphs)
    # the "no paragraph-long beats" clause is dropped; terse beats keep it.
    if multiline:
        _r5 = (f"5. narration in {lang_name}; each beat = ONE SHOT (one image) holding a self-contained "
               f"MINI-SCENE{beat_char_hint} told as a "
               "\"lines\" array of spoken turns. Each line = {speaker_id, text, emotion, pose}; "
               "speaker_id \"\" = narrator. Make the turns SUBSTANTIAL — full sentences with dialogue + "
               "action + feeling so the beat REACHES that length; NEVER emit a single short line or a "
               "one-word beat. A pure-narration beat may hold one or more narrator lines; a dialogue beat "
               "interleaves narrator + characters. Keep ALL lines of a beat in the SAME place/visual — start "
               "a NEW beat when the scene/image changes. The lines in order narrate the whole story "
               "faithfully (preserve names/facts, never invent).\n")
    elif rich_beats:
        _r5 = (f"5. narration in {lang_name}; each beat = a self-contained MINI-SCENE{beat_char_hint} — "
               "keep beats EVENLY sized (no one-word beats, no half-empty beats); the beats in order "
               "narrate the whole story faithfully (preserve names/facts, never invent).\n")
    else:
        _r5 = (f"5. narration in {lang_name}; each beat = ONE contiguous idea{beat_char_hint} — keep beats "
               "EVENLY sized (no one-word beats, no paragraph-long beats); the beats in order narrate the "
               "whole story faithfully (preserve names/facts, never invent).\n")
    # Rules 7+ describe the per-beat STYLE labels. Under the lean contract (SVG) the model
    # emits only bgm_mood + emotion + pose; the rest are pipeline-derived, so we drop their
    # instructions. Multiline: emotion/pose live INSIDE each line. Full block keeps all.
    if multiline:
        _style = (
            f"7. Each beat's bgm_mood = ONE of [{_MOOD_VOCAB}] — the music mood for THAT shot "
            "(a creative label only, NOT an audio file/timestamp).\n"
            "8. INSIDE each line: emotion = that speaker's feeling — normal|happy|angry|sad|surprised "
            "(use normal when neutral); pose = that speaker's gesture — stand|wave|cheer|point|hip "
            "(use stand unless the action clearly calls for one).\n"
            "9. region/genre_key/archetype/scene_kind are OPTIONAL asset-library hints: lowercase English "
            "tokens only; leave \"\" when unsure (never invent). They do NOT change the story.\n"
            "10. \"asset\" (character/setting) = an exact SLUG copied from the ASSET LIBRARY section when one "
            "fits, else \"\". Never a path; never a slug that is not listed. Absent library → \"\".\n"
            "11. DO NOT output any render/path/timestamp field, an image prompt, NOR camera motion / "
            "transitions / music placement / character-overlay position — those are added AUTOMATICALLY. "
            "Emit ONLY the fields shown in the schema.\n"
        )
    elif lean:
        _style = (
            f"7. Each timeline beat's bgm_mood = ONE of [{_MOOD_VOCAB}] — the background-music mood "
            "matching THAT beat's emotional tone (a creative label only, NOT an audio file/timestamp).\n"
            "8. emotion = the SPEAKER's feeling THIS beat: normal|happy|angry|sad|surprised — match the "
            "beat's tone (use normal when neutral). pose = the speaker's gesture THIS beat: stand (neutral) | "
            "wave (greeting) | cheer (excited) | point (accusing/indicating) | hip (defiant) — use stand "
            "unless the action clearly calls for one.\n"
            "9. region/genre_key/archetype/scene_kind are OPTIONAL asset-library hints: lowercase English "
            "tokens only; leave \"\" when unsure (never invent). They do NOT change the story.\n"
            "10. \"asset\" (character/setting) = an exact SLUG copied from the ASSET LIBRARY section when one "
            "fits, else \"\". Never a path; never a slug that is not listed. Absent library → \"\".\n"
            "11. DO NOT output any render/path/timestamp/duration/seconds field, an image prompt, NOR camera "
            "motion / transitions / music placement / character-overlay position — those are added "
            "AUTOMATICALLY. Emit ONLY the fields shown in the schema.\n"
        )
    else:
        _style = (
            f"7. Each timeline beat's bgm_mood = ONE of [{_MOOD_VOCAB}] — the background-music mood "
            "matching THAT beat's emotional tone (a creative label only, NOT an audio file/timestamp).\n"
            "8. bgm_cue = WHERE the music sits in the beat: under (whole beat) | intro (start only) | "
            "outro (end only) | none (silence). Use intro on a scene's FIRST beat, outro on its LAST, "
            "none for a quiet beat; under otherwise. bgm_intensity = low|med|high. LABELS only, never seconds.\n"
            "9. char_anchor = where the SPEAKING character stands: none|left|center|right — set none when "
            "speaker_id is '' (narrator). char_scale = small|medium|large; char_motion = static|fade|slide|float. "
            "emotion = the SPEAKER's feeling THIS beat: normal|happy|angry|sad|surprised — match the beat's tone "
            "(use normal when neutral). pose = the speaker's gesture THIS beat: stand (neutral) | wave (greeting) | "
            "cheer (excited) | point (accusing/indicating) | hip (defiant) — use stand unless the action clearly "
            "calls for one. source_audio = mute|duck|keep (how a base video's own audio is treated).\n"
            "10. text_anchor = where on-screen text sits: auto|top|bottom|left|right. Use auto normally; pick a "
            "side OPPOSITE char_anchor so text never covers the character.\n"
            "11. region/genre_key/archetype/scene_kind are OPTIONAL asset-library hints: lowercase English "
            "tokens only; leave \"\" when unsure (never invent). They do NOT change the story.\n"
            "12. \"asset\" (character/setting) = an exact SLUG copied from the ASSET LIBRARY section when one "
            "fits, else \"\". Never a path; never a slug that is not listed. Absent library → \"\".\n"
            "13. DO NOT output any render/path/timestamp/duration/seconds field, nor an image prompt.\n"
        )
    return (
        "═══ HARD RULES ═══\n"
        + _frame_line
        + "1. ONE JSON object. No prose, no markdown, no code fences.\n"
        f"2. AT MOST {ceiling} entries in \"visuals\" — usually FAR FEWER than the number of "
        "beats. REUSE each visual across MANY beats (aim for ~3-6 beats per visual): beats in the "
        "same place/moment share ONE visual_id. NEVER make one image per beat — the TIMELINE can be "
        "long (many beats = a long video), but the IMAGE SET stays small.\n"
        "3. Every timeline.visual_id MUST be an id in \"visuals\"; focus MUST be one of the "
        "listed values; speaker_id and every visuals.character_ids MUST be ids in \"characters\".\n"
        + _r4
        + _r5
        + f"6. {hook_rule}\n"
        + _style
        + _reuse_example()
        + "═══ SELF-CHECK before answering ═══\n"
        "Verify every visual_id / speaker_id / character_ids exists in the arrays above; if not, fix it.\n"
        "═══ OUTPUT JSON ═══"
    )


def _reuse_example() -> str:
    """1-shot ILLUSTRATIVE example (P-B) — the JSON Schema enforces STRUCTURE, this
    enforces BEHAVIOUR the schema can't: reuse a FEW visuals across MANY beats, and
    place 1-2 hooks at turning points. Structure only (no copyable story content) so
    it teaches the pattern without anchoring the model to a specific tale."""
    return (
        "═══ REUSE EXAMPLE (pattern only — write YOUR OWN story) ═══\n"
        "A good plan reuses a SMALL image set across MANY beats and hooks the turning points:\n"
        "  visuals : [ v1, v2 ]                    ← only 2 images\n"
        "  timeline: b1→v1 (hook: opening), b2→v1, b3→v1, b4→v2, b5→v2 (hook: climax)\n"
        "  ⇒ 5 beats used just 2 images. Do the SAME at scale: a long timeline of many "
        "beats over a SMALL set of reused visuals — never one image per beat.\n"
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
        from app.domain.story_plan_v2 import GENRE_KEY as _GK, REGION as _RG
        archetypes = ", ".join(sorted(_ARCH))
        seen: dict = {}                                   # one representative alias per scene fn
        for alias, fn in _SCENES.items():
            seen.setdefault(fn, alias)
        scenes = ", ".join(sorted(seen.values()))
        genres = ", ".join(g for g in _GK if g)
        regions = ", ".join(r for r in _RG if r)
        return (
            "\n═══ TOKEN VOCAB (for the OPTIONAL hint fields — pick the CLOSEST, else \"\") ═══\n"
            f"archetype ∈ {{ {archetypes} }}\n"
            f"scene_kind ∈ {{ {scenes} }}\n"
            f"genre_key ∈ {{ {genres} }}  (story-level asset-library GENRE scope)\n"
            f"region ∈ {{ {regions} }}  (story-level asset-library MARKET scope)\n"
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
    """P1 — (system, user) to ADAPT an existing story into a StoryPlan v2, rendered as
    procedural SVG (no base video). Role: faithful adaptation. ``prior_context`` (G1)
    grounds a later chapter; ``library_catalog`` (library-pick) enables ``asset`` slugs."""
    lang_name = _lang_name(language)
    method = (
        "═══ METHOD (follow this order) ═══\n"
        "(a) CHARACTERS: identify the recurring cast in the source + a canonical look + voice.\n"
        "(b) SETTINGS: identify the recurring places.\n"
        f"(c) VISUALS (≤{ceiling}): a SMALL set of key images, each REUSED across many beats.\n"
        "(d) TIMELINE: narrate the WHOLE source story as ordered beats — cover it from start to "
        "end, preserving the original names, facts and order; do not skip or invent.\n"
    )
    style_line = f"ART STYLE HINT: {art_style.strip()}\n" if (art_style or "").strip() else ""
    user = (
        f"NARRATION LANGUAGE: {lang_name}\n{style_line}"
        + method
        + _series_memory_block(prior_context)
        + _library_block(library_catalog)
        + _vocab_block()
        + "\n═══ SOURCE STORY (adapt THIS faithfully) ═══\n" + _fit(chapter) + "\n\n"
        + _schema(_lean_contract()).replace("{LANG}", lang_name).replace("<LANG code>", language).replace("<MOOD_VOCAB>", _MOOD_VOCAB) + "\n\n"
        + _rules(ceiling, aspect_ratio, lang_name, subtitle_mode, _beat_char_hint(language), "svg",
                 lean=_lean_contract(), multiline=_multiline())
    )
    return _SYS_ADAPT, user


def build_super_video_prompt(chapter: str, language: str = "vi", art_style: str = "",
                             aspect_ratio: str = "16:9", subtitle_mode: str = "hook_only",
                             ceiling: int = 15, prior_context: str = "",
                             library_catalog: str = "", base_video_dur: float = 0.0) -> "tuple[str, str]":
    """P2 — (system, user) to ADAPT a story into a NARRATED CHARACTER-OVERLAY over an
    existing BACKGROUND VIDEO. The video is all the imagery: NO scene design; the model
    focuses on narration + which character is on screen + overlay placement + how the
    video's own audio is treated (``source_audio``). Same schema; visuals are just
    grouping anchors. ``base_video_dur`` (when >0) paces the narration to the clip."""
    lang_name = _lang_name(language)
    dur_line = (f"BACKGROUND VIDEO LENGTH: ~{int(base_video_dur)} seconds — pace the narration so it "
                f"fits roughly this long when read aloud.\n") if base_video_dur and base_video_dur > 0 else ""
    method = (
        "═══ METHOD (follow this order) ═══\n"
        "(a) CHARACTERS: the cast that appears/speaks in the story + a canonical look + voice.\n"
        "(b) SETTINGS + VISUALS: create only a FEW grouping anchors (the VIDEO is the real "
        "background — its look is ignored; do NOT describe scenes).\n"
        "(c) TIMELINE (the main work): narrate the story over the video as ordered beats. For EACH "
        "beat set: narration, speaker_id, emotion + pose, char_anchor/char_scale (WHERE/how big the "
        "speaking character overlays the video), and source_audio (mute | duck under the voice | "
        "keep) — how the video's OWN sound is treated for that beat.\n"
    )
    style_line = f"ART STYLE HINT: {art_style.strip()}\n" if (art_style or "").strip() else ""
    user = (
        f"NARRATION LANGUAGE: {lang_name}\n{style_line}{dur_line}"
        + method
        + _series_memory_block(prior_context)
        + _library_block(library_catalog)
        + _vocab_block()
        + "\n═══ SOURCE STORY (narrate THIS over the video, faithfully) ═══\n" + _fit(chapter) + "\n\n"
        + _schema(False).replace("{LANG}", lang_name).replace("<LANG code>", language).replace("<MOOD_VOCAB>", _MOOD_VOCAB) + "\n\n"
        + _rules(ceiling, aspect_ratio, lang_name, subtitle_mode, _beat_char_hint(language), "video",
                 multiline=_multiline())
    )
    return _SYS_VIDEO, user


def build_super_idea_prompt(idea: str, duration_sec: int = 0, genre: str = "",
                            language: str = "vi", art_style: str = "", aspect_ratio: str = "16:9",
                            subtitle_mode: str = "hook_only", ceiling: int = 15,
                            prior_context: str = "", library_catalog: str = "",
                            length_factor: float = 0.0) -> "tuple[str, str]":
    """P3 — (system, user) to WRITE a story OF A TARGET LENGTH from an idea, then
    storyboard it (SVG). The length is baked into the creative BRIEF (not a constraint
    tacked on after), broken into a scene scaffold the model fills. ``prior_context``
    (G1) grounds a later chapter; ``library_catalog`` enables ``asset`` slugs."""
    lang_name = _lang_name(language)
    # A2: when the FE omits a target length, fall back to STORY_IDEA_DEFAULT_SEC
    # (default 0 = keep the "model decides" behaviour — backward compatible).
    if not duration_sec or duration_sec <= 0:
        try:
            duration_sec = int(_os.getenv("STORY_IDEA_DEFAULT_SEC", "0") or 0)
        except (TypeError, ValueError):
            duration_sec = 0
    cps = _CPS.get((language or "").strip().lower()[:2], 14.0)
    # Compensation (measured): gpt-4o delivers only ~50-60% of a requested length from a
    # thin idea in one call, so aim the BRIEF higher than the user's target and it lands
    # near it. Tunable via STORY_IDEA_LENGTH_FACTOR (1.0 disables). Applied to the numbers
    # shown to the model; the FE still compares the real estimate to the user's target.
    try:
        _factor = max(1.0, float(_os.getenv("STORY_IDEA_LENGTH_FACTOR", "1.8") or 1.8))
    except (TypeError, ValueError):
        _factor = 1.8
    # Escalate-and-regenerate: the director passes a higher length_factor on a retry
    # when the first plan landed short. >0 overrides the env/default; 0 keeps it.
    if length_factor and length_factor > 0:
        _factor = max(1.0, float(length_factor))
    _eff_sec = int(round(duration_sec * _factor)) if (duration_sec and duration_sec > 0) else 0
    budget = int(_eff_sec * cps) if _eff_sec else 0
    _mins = round(duration_sec / 60.0, 1) if duration_sec else 0
    # RICH beats (the real length lever): the model writes TERSE narration in JSON mode,
    # so a "~45-120 char" per-beat hint capped a 3-min request at ~70s. Instead aim ~10s
    # of speech PER BEAT — a full 2-4 sentence PARAGRAPH — and derive the beat COUNT and
    # per-beat LENGTH from the (compensated) target so beats × per_beat ≈ budget.
    _sec_per_beat = 10.0
    _target_beats = max(6, int(round(_eff_sec / _sec_per_beat))) if _eff_sec else 0
    _per_beat = int(round(cps * _sec_per_beat)) if _target_beats else 0
    _scenes = max(2, min(int(ceiling), int(round(_target_beats / 4.0)))) if _target_beats else 0
    # Five-act beat quota (fixes the "model tells the whole story in too few beats" cap):
    # mandate a beat count PER STAGE so the model must develop each act, not summarise.
    _a1 = max(1, int(round(_target_beats * 0.18)))
    _a2 = max(1, int(round(_target_beats * 0.32)))
    _a3 = max(1, int(round(_target_beats * 0.18)))
    _a4 = max(1, int(round(_target_beats * 0.20)))
    _a5 = max(1, _target_beats - _a1 - _a2 - _a3 - _a4)
    brief = (
        "═══ BRIEF (this defines the whole task) ═══\n"
        f"Write a LONG, fully-narrated STORY in {lang_name} from the STORY IDEA below. The finished "
        f"narration must TOTAL about {budget} CHARACTERS of spoken text (roughly {_target_beats} full "
        "paragraphs) — that total is the DEFINITION of the task, not a limit. Aim for the FULL length; a "
        "little OVER is fine, SHORT is a FAILURE. Write the ENTIRE story out, scene by scene, in RICH "
        "detail (dialogue, action, inner feeling). The STORY IDEA below may ALREADY be a complete "
        "outline/summary — treat it as a SKELETON, never the script: DRAMATIZE every line into a full "
        "2-4 sentence scene. The idea's OWN length is NOT the output's length; reach the target REGARDLESS "
        "of how terse the idea is.\n"
    ) if budget else "TARGET LENGTH: model decides.\n"
    genre_line = f"GENRE: {genre.strip()}\n" if (genre or "").strip() else ""
    style_line = f"ART STYLE HINT: {art_style.strip()}\n" if (art_style or "").strip() else ""
    if _target_beats:
        act_block = (
            "(0) INVENT the story and WRITE IT OUT as an ordered TIMELINE that fully develops ALL FIVE "
            f"stages below in {lang_name} — you MUST hit roughly the beat count for EACH stage (do not "
            "compress the story into fewer beats):\n"
            f"    • HOOK / SETUP — introduce world + characters (~{_a1} beats)\n"
            f"    • RISING ACTION — complications build, deepen the conflict (~{_a2} beats)\n"
            f"    • MIDPOINT TWIST — a turn that raises the stakes (~{_a3} beats)\n"
            f"    • CLIMAX — the confrontation / revelation (~{_a4} beats)\n"
            f"    • RESOLUTION — aftermath + ending (~{_a5} beats)\n"
            f"  → ~{_target_beats} beats TOTAL, and EACH beat's narration is a FULL, vivid 2-4 sentence "
            f"PARAGRAPH of ~{_per_beat} characters (dialogue + action + feeling), NOT a one-line summary. "
            f"(~{_target_beats} beats × ~{_per_beat} chars ≈ {budget} characters total.)\n"
        )
        tail_e = (f"(e) CHECK before you output: count your beats and estimate their total characters. "
                  f"If you have far fewer than {_target_beats} beats OR under ~{budget} characters, you "
                  "compressed the story — go back, expand each act with more beats and fuller paragraphs, "
                  "THEN output.\n")
    else:
        act_block = ("(0) INVENT a full story with a real arc (hook → rising action → climax → resolution), "
                     f"in {lang_name}, written out beat by beat (never summarised).\n")
        tail_e = ""
    method = (
        "═══ METHOD (follow this order) ═══\n"
        + act_block
        + "(a) CHARACTERS: the recurring cast you invented + canonical look + voice.\n"
        "(b) SETTINGS: the places (one per scene).\n"
        + (f"(c) VISUALS: about {_scenes} images (≤{ceiling}), each reused across many beats.\n"
           if _scenes else f"(c) VISUALS (≤{ceiling}): a SMALL set, each reused across many beats.\n")
        + tail_e
    )
    _idea_beat_hint = (f" (a FULL 2-4 sentence paragraph, ~{_per_beat} characters)"
                       if _per_beat else _beat_char_hint(language))
    user = (
        f"NARRATION LANGUAGE: {lang_name}\n{genre_line}{style_line}"
        + brief
        + method
        + _series_memory_block(prior_context)
        + _library_block(library_catalog)
        + _vocab_block()
        + "\n═══ STORY IDEA (a SKELETON to DRAMATIZE & EXPAND — never compress) ═══\n" + _fit(idea, MAX_IDEA_CHARS) + "\n\n"
        + _schema(_lean_contract()).replace("{LANG}", lang_name).replace("<LANG code>", language).replace("<MOOD_VOCAB>", _MOOD_VOCAB) + "\n\n"
        + _rules(ceiling, aspect_ratio, lang_name, subtitle_mode, _idea_beat_hint, "svg",
                 rich_beats=bool(_per_beat), lean=_lean_contract(), multiline=_multiline())
    )
    return _SYS_IDEA, user


_SYSTEM_REPAIR = (
    "You are a strict JSON repair tool. The text given was meant to be ONE StoryPlan JSON object "
    "but is malformed / truncated / wrapped in prose. Return ONLY a corrected valid JSON object "
    "(same shape), no prose/markdown/fences. Preserve as much content as possible; the object MUST "
    "have non-empty \"visuals\" and \"timeline\" arrays; every timeline.visual_id must match a "
    "visuals id. Drop an incomplete trailing beat rather than inventing content."
)


def build_super_repair_prompt(broken: str) -> "tuple[str, str]":
    return _SYSTEM_REPAIR, "Fix this into ONE valid StoryPlan JSON object:\n\n" + _fit(broken)


__all__ = ["build_super_story_prompt", "build_super_video_prompt", "build_super_idea_prompt",
           "build_super_repair_prompt", "SUPER_PROMPT_VERSION"]
