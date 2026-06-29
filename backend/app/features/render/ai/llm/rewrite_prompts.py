"""
rewrite_prompts.py — Prompt template for AI subtitle rewrite for TTS.

v2 (2026-06-27): segmented + timestamp-aware output.
The LLM sees the source SRT WITH per-utterance timestamps and emits a
JSON array of segments {start, end, text}. The downstream pipeline
synthesizes TTS per segment, silence-pads the gaps, and concats them so
the narration lands at the same pacing as the original speech.

The v1 plain-text path (one rewritten paragraph for the whole clip)
remains as the implicit fallback inside the parser: when the LLM
response can't be parsed as JSON, the parser collapses it into a single
segment spanning the whole clip.
"""
from __future__ import annotations

import os as _os
from typing import Iterable, Optional

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

# Hard cap on input SRT chars sent to the LLM (rewrite call).
# Per-part SRTs are short (~15-90 sec → ~50-1500 chars including timestamps),
# cap at 8000 to cover the long tail and reject pathologically long inputs.
MAX_REWRITE_INPUT_CHARS = int(_os.getenv("REWRITE_MAX_INPUT_CHARS", "8000"))

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


# A2.1 (2026-06-28): translate clip-context hints into concrete wording guidance
# that the rewriter can apply. Empty value suppresses its line in the prompt,
# preserving back-compat for callers that don't pass the field.
_CONTENT_TYPE_GUIDANCE: dict[str, str] = {
    "vlog":       "first-person voice ('I', 'we'); informal, conversational tone",
    "commentary": "opinionated stance, direct second-person ('you'), confident analytical",
    "interview":  "neutral narrator framing the speaker's quote; third-person acceptable",
    "tutorial":   "instructive, step-driven, imperative voice (\"Here's how...\")",
    "montage":    "minimal — let visuals speak; short evocative phrases",
    "gaming":     "high-energy reactive, present-tense action verbs, exclamations OK",
}
_HOOK_TYPE_GUIDANCE: dict[str, str] = {
    "question":  "open with a rhetorical question mirroring the source hook moment",
    "reveal":    "build tension in segment 1; save the reveal verb for the next segment",
    "contrast":  "frame as 'X vs Y' with parallel sentence structure",
    "humor":     "set up the joke in segment 1; deliver the punch in the last segment",
    "emotion":   "soften pacing, lean on adjectives, use '—' for reflective beats",
    "statement": "lead with the bold claim, then unpack it across following segments",
}
# Compact 1-liners — different from prompts.py's PLATFORM_PROMPT_HINTS which target
# the segment selector. These target the narrator's wording cadence.
_PLATFORM_NARRATOR_HINTS: dict[str, str] = {
    "tiktok":          "punch the first 3 seconds, keep sentences short and rhythmic",
    "youtube_shorts":  "clear narrative arc within 60s; setup → twist → payoff",
    "instagram_reels": "polished, slightly slower cadence than tiktok; emotional resonance",
}


def _compute_word_budget(target_duration_sec: float, target_language: str) -> int:
    """Return target word count from duration + language WPM table.
    Floors at 3 words (TTS sanity); ceils at 800 (sanity)."""
    wpm = _WPM_BY_LANG.get(target_language, _DEFAULT_WPM)
    budget = int((max(1.0, target_duration_sec) / 60.0) * wpm)
    return max(3, min(800, budget))


def format_segments_for_prompt(blocks: Iterable[dict]) -> str:
    """Render parsed SRT blocks ({start, end, text}) as compact lines
    `[s.s - e.e] text` — same shape as prompts.py uses for select_render_plan.
    Drops invalid blocks (missing fields, end <= start)."""
    lines: list[str] = []
    for b in blocks:
        try:
            s = float(b["start"])
            e = float(b["end"])
            t = str(b.get("text", "")).strip()
        except (TypeError, ValueError, KeyError):
            continue
        if e <= s or not t:
            continue
        lines.append(f"[{s:.1f} - {e:.1f}] {t}")
    return "\n".join(lines)


_SYSTEM_REWRITE = (
    "You are a professional TTS narration script writer fluent in many languages. "
    "You write the way real narrators SPEAK to an audience — with rhythm, emphasis, "
    "rhetorical pauses, and natural emotion — never the way essays are written. "
    "Rewrite the input transcript (which has per-utterance timestamps) into a "
    "TIMED NARRATION that fits the same pacing — speaking when the source speaks, "
    "pausing when the source pauses. When the source language differs from the "
    "target language, TRANSLATE while rewriting — produce natural, native-sounding "
    "output in the target language (NOT a literal word-for-word translation). "
    "Preserve every key fact, name, and number. "
    "Output ONLY valid JSON in the exact shape requested — no prose, no markdown, "
    "no code fences, no explanation."
)

_USER_TEMPLATE_REWRITE = """Rewrite the SOURCE TRANSCRIPT below into a TIMED NARRATION script.

═══ TARGET OUTPUT ═══
LANGUAGE:        {target_lang_name} ({target_language}) — write in {target_lang_native}
CLIP DURATION:   {clip_duration_sec:.1f} seconds (TOTAL narration must fit within this)
WORD BUDGET:     about {word_budget} total words (at {wpm} words/minute for {target_lang_name})
TONE:            {tone_clause}
LANGUAGE STYLE:  {style_note}{clip_context_section}

═══ HOW TO WORK ═══

STEP 1 — Detect the source language of the SOURCE TRANSCRIPT below.

STEP 2 — Decide your task:
  IF source language == {target_lang_name}:
      → REWRITE ONLY (keep the same language, polish for TTS narration).
  IF source language != {target_lang_name}:
      → TRANSLATE + REWRITE into {target_lang_name}. Do NOT keep any source-language
        words except proper nouns (names of people, places, brands).
        The output MUST be entirely in {target_lang_name}.

STEP 3 — Read the timestamps `[start - end]` carefully. Each timestamp shows WHEN
the speaker speaks in the clip. Gaps between timestamps are SILENT pauses.

STEP 4 — Emit a JSON array of narration segments, one per spoken utterance:
  - Each segment covers ONE [start - end] window from the source (or a merged
    pair if two utterances are close together, e.g. < 0.5s apart).
  - If a single source utterance is LONGER than 12 seconds, SPLIT it into 2-3
    sub-segments at natural sentence boundaries (use timestamps that fall
    INSIDE the original source window). The TTS engine cannot safely speed
    up beyond 1.25x — a single 30-second utterance with 60+ words of
    narration would over-run and get truncated.
  - If two source utterances are separated by a GAP > 1.5 seconds of silence,
    KEEP them as separate segments — do NOT extend earlier segment.end into
    the silent gap. The silence is intentional pacing and the TTS pipeline
    will pad it back during concat.
  - Each segment.start / segment.end uses the SAME numbers as the source [start - end].
  - segment.text is your rewritten narration for that utterance.
  - Length of segment.text MUST fit (end - start) seconds at the {target_lang_name}
    narrator pace ({wpm} wpm). Compress or expand wording so it fits naturally.
  - Apply the TONE "{tone_clause}" to your wording throughout.

═══ HUMAN-LIKE DELIVERY ═══

Write like a narrator SPEAKING to a real audience — not like a paper being read aloud.

PUNCTUATION = BREATH CUES (the TTS engine literally honours these):
  "..."    → dramatic pause (1-1.5 beats). Use before a reveal or punchline.
  "—"      → mid-sentence reflective pause (half a beat). Use for emphasis.
  ", "     → natural micro-pause inside a sentence.
  "."      → full sentence stop. Use SHORT sentences for tension, LONG for flow.
  "?"      → question — TTS rises at the end. Use for rhetorical questions.
  "!"      → exclamation — TTS raises pitch / energy. Use SPARINGLY (1-2 per clip max).

SENTENCE VARIETY:
  - Mix short punchy sentences with longer flowing ones — never two long sentences in a row.
  - Open the first segment with a HOOK (a question, a bold claim, or a vivid image).
  - Save the strongest point or twist for the LAST segment if the source allows it.
  - Avoid filler words ("basically", "you know", "kind of"). Every word earns its slot.

TONE INTERPRETATION (multi-language preset table)

The creator may type the tone in ANY of the 5 supported languages: English (en),
Vietnamese (vi), Japanese (ja), or Korean (ko). Match the input to the closest
canonical row below and apply the WORDING + PUNCTUATION pattern in the right
column. The guidance is the SAME regardless of input language — only WORDING
LANGUAGE follows the target voice language ({target_language}).

  English (canonical)  | Vietnamese        | Japanese       | Korean         | Pattern
  ---------------------|-------------------|----------------|----------------|--------
  dramatic             | kịch tính / gây cấn | 劇的 / 緊張感   | 극적 / 긴장감    | short tense sentences, "..." before reveals, rhetorical questions, strong verbs
  humorous             | hài hước / vui nhộn | 面白い / コメディ| 유머러스 / 코믹  | playful word choices, surprise endings, 1 light "!" OK, conversational
  informative          | nghiêm túc / chuyên nghiệp | 真面目 / 情報的 | 정보적 / 진지한 | clear declarative sentences, zero filler, confident even pacing, no "!"
  emotional            | cảm xúc / truyền cảm | 感情的 / 感動的 | 감정적 / 감동적  | warmer adjectives, longer reflective sentences, "—" for reflection
  energetic            | năng động / hào hứng | 元気 / 活発     | 활기찬 / 에너지  | present tense, action verbs, faster rhythm, 1-2 "!", short questions
  calm                 | trầm tĩnh / nhẹ nhàng | 落ち着いた / 静か | 차분한 / 평온한 | measured pacing, soft verbs, longer breaths ("," "—" over "!"), no rushing
  sarcastic            | châm biếm / mỉa mai | 皮肉 / 嫌味     | 빈정대는 / 풍자적 | understated delivery, deliberate pauses, ironic word choices, low-key declarative
  anxious              | hốt hoảng / lo lắng | 不安 / 焦り     | 불안한 / 초조한  | fragmented short clauses, repetition for urgency, rising intonation, more "?"
  confessional         | tâm sự / tự sự    | 告白 / 打ち明け  | 고백 / 토로     | personal voice ("I", "me"), vulnerable tone, gentler verbs, slower rhythm
  mysterious           | bí mật / bí ẩn    | ミステリアス / 神秘的 | 신비로운 / 비밀스러운 | lowered voice register, hints not reveals, "..." for suspense, half-answers
  investigative        | trinh thám / điều tra | 探偵 / 調査  | 탐정 / 수사     | analytical, building evidence step-by-step, "?" then declarative, deliberate

The creator's tone is "{tone_clause}". If it matches ANY column (English, Vietnamese,
Japanese, Korean) of one row, apply that row's pattern. If it matches NO row, invent
a sensible pattern that captures the creator's intent. Apply the chosen pattern
CONSISTENTLY across EVERY segment.{reaction_section}

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON, nothing else) ═══

{{
  "segments": [
    {{ "start": <float>, "end": <float>, "text": "<rewritten narration for this slot>" }},
    {{ "start": <float>, "end": <float>, "text": "..." }}
  ]
}}

═══ HARD RULES ═══

1. Output is ONE JSON object. No bullets, no markdown, no prose wrapper, no code fences.
2. `segments` MUST be a non-empty array. Segments MUST NOT overlap and MUST be sorted by start.
3. Every segment.start >= 0 and segment.end <= {clip_duration_sec:.1f}.
4. Output MUST be 100% in {target_lang_name}. No mixed languages inside a segment.
5. Avoid TTS-unfriendly symbols inside segment.text: no &, no #, no %, no abbreviations
   like "Mr." / "U.S." — spell them out the way they should be SPOKEN.
6. Preserve every key fact, every name, every number from the source.

═══ SOURCE TRANSCRIPT (timestamps in seconds, relative to clip start) ═══
{srt_segmented}

═══ OUTPUT JSON ═══
"""


# ── Reaction / storyteller persona (narration_mode="reaction") ───────────────
# Faceless reaction mode: the narrator REACTS to and dramatises the clip rather
# than relaying the transcript. System prompt swaps in a commentator voice;
# _REACTION_SECTION is injected into the user prompt (otherwise empty string,
# so default rewrite output is byte-identical — Sacred Contract #2 spirit).
_SYSTEM_REWRITE_REACTION = (
    "You are a charismatic FACELESS REACTION narrator and storyteller. You do not "
    "merely relay the transcript — you REACT to it and lead the viewer through the "
    "moment like a commentator: building curiosity, voicing genuine surprise and "
    "opinion, teasing what's coming, and landing the payoff. You ADAPTIVELY blend "
    "two registers depending on the content: add reaction commentary, emotional "
    "beats, and rhetorical questions where they heighten engagement; stay close to "
    "the source where the content already speaks for itself. You write the way a "
    "real person SPEAKS while reacting — rhythm, emphasis, rhetorical pauses, "
    "natural emotion — never like an essay read aloud. Produce a TIMED narration "
    "that fits the same pacing as the source. When the source language differs "
    "from the target language, TRANSLATE while rewriting into natural, native "
    "output. Preserve every key fact, name, and number — your commentary adds "
    "reaction and framing, it NEVER invents events that did not happen. "
    "Output ONLY valid JSON in the exact shape requested — no prose, no markdown, "
    "no code fences."
)

_REACTION_SECTION = """

═══ REACTION MODE (narration_mode = reaction) — OVERRIDES THE RULES ABOVE ═══

This is a FACELESS REACTION edit. The viewer must still hear the ORIGINAL video.
You do NOT narrate over the whole clip. Instead you INTERLEAVE: the reactor SETS
UP a moment, then goes SILENT and lets the original audio deliver the payoff.

CORE RHYTHM (lead-in → freeze → original payoff):
  1. Find the clip's CLIMAX(es) — the most surprising / emotional / punchy moment.
  2. Just BEFORE a climax, add a short "voice" segment where the reactor LEADS IN
     and builds anticipation (e.g. "Watch what he says about the car…").
  3. Optionally hold a FREEZE-FRAME right after that lead-in (freeze_after) to
     create a 1–2 second suspense beat with a caption (freeze_text).
  4. At the climax itself, emit an "original" segment (NO text): the reactor is
     SILENT and the source audio/voice plays at full volume — this is the payoff.
  5. Between beats, simply leave GAPS (no segment) — the original audio plays.

BE SPARSE AND CONTENT-DRIVEN: only react where it adds value. A 60s clip might
have just 2–4 lead-in beats. Do NOT cover every utterance. Silence is a tool.

SEGMENT SCHEMA FOR REACTION (extend the output objects with these fields):
  • "kind": "voice"     → reactor speaks (TTS). Requires "text".
        - "freeze_after": <float seconds, 0–2> → hold a freeze-frame AFTER this
          line for suspense (omit or 0 = no freeze). Use on the lead-in before a
          big payoff.
        - "freeze_text": "<short caption shown during the freeze>" → keep it
          punchy (a few words), in {target_lang_name}. Defaults to the line.
  • "kind": "original"  → reactor SILENT, source audio plays. NO "text" field.
        Place this exactly over the climax window from the source timestamps.

RULES:
  • Lead-in commentary = reaction, opinion, anticipation, framing. NEVER fabricate
    events, quotes, names, or numbers not in the source.
  • Keep each "voice" line tight and inside the WORD BUDGET — reaction is energy,
    not length. Place voice lines in natural pauses where possible.
  • Use freeze_after sparingly (1–2 per clip) and only before the strongest payoff.
  • Keep the creator's TONE; reaction amplifies it.

REACTION OUTPUT EXAMPLE (shape only — your timestamps come from the source):
  { "segments": [
    { "kind": "voice", "start": 3.0, "end": 6.0,
      "text": "He looks calm… until the officer mentions the car.",
      "freeze_after": 1.5, "freeze_text": "Wait for it…" },
    { "kind": "original", "start": 7.5, "end": 12.0 }
  ] }"""


def _build_clip_context_section(
    *,
    content_type: str,
    hook_type: str,
    clip_title: str,
    target_platform: str,
    part_idx: int,
    total_parts: int,
    editorial_hint: str = "",
) -> str:
    """Render the optional CLIP CONTEXT block. Returns "" when every hint is
    empty / default so back-compat callers see the pre-A2.1 prompt verbatim.

    ``editorial_hint`` (R3) is a per-scene DIRECTOR'S INTENT — e.g. the recap
    plan's narration_intent + act context. When set it is the strongest steer:
    the narrator should convey exactly this beat. Empty = no line (back-compat).
    """
    lines: list[str] = []
    hint = (editorial_hint or "").strip()
    if hint:
        lines.append(f"DIRECTOR'S INTENT: {hint} (convey THIS beat — top priority)")
    ct = (content_type or "").strip().lower()
    guidance_ct = _CONTENT_TYPE_GUIDANCE.get(ct, "")
    if ct and guidance_ct:
        lines.append(f"CONTENT TYPE:    {ct} — {guidance_ct}")
    ht = (hook_type or "").strip().lower()
    guidance_ht = _HOOK_TYPE_GUIDANCE.get(ht, "")
    if ht and guidance_ht:
        lines.append(f"HOOK ARCHETYPE:  {ht} — {guidance_ht}")
    title = (clip_title or "").strip()
    if title:
        lines.append(f"CLIP TITLE:      {title} (AI-suggested — use as creative direction)")
    pf = (target_platform or "").strip().lower()
    guidance_pf = _PLATFORM_NARRATOR_HINTS.get(pf, "")
    if pf and guidance_pf:
        lines.append(f"TARGET PLATFORM: {pf} — {guidance_pf}")
    if part_idx and total_parts and total_parts > 0:
        if part_idx == 1:
            pos = "FIRST clip — strongest hook, grab in first 3 seconds"
        elif part_idx == total_parts:
            pos = "LAST clip — give a satisfying close / call-back"
        else:
            pos = f"middle clip ({part_idx}/{total_parts}) — maintain rhythm without repeating earlier hooks"
        lines.append(f"PART POSITION:   {pos}")
        # 2026-06-28: clips often come from the same source video, so the LLM
        # tends to produce near-identical narration across parts. Explicitly
        # ask for variation in word choice + sentence structure + opening
        # device so each clip feels like a fresh take rather than a clone.
        lines.append(
            f"VARIATION:       this is clip {part_idx} of {total_parts} from the SAME source video. "
            "Each part MUST sound DISTINCT — vary opening device (question vs claim vs "
            "image), sentence rhythm, and vocabulary. Do NOT repeat phrasing patterns "
            "the earlier clips may have used."
        )
    if not lines:
        return ""
    body = "\n".join(lines)
    return f"\n\n═══ CLIP CONTEXT (use to inform wording — these are HINTS) ═══\n{body}"


def build_rewrite_prompt(
    srt_segmented: str,
    clip_duration_sec: float,
    target_language: str,
    tone: str = "",
    *,
    content_type: str = "",
    hook_type: str = "",
    clip_title: str = "",
    target_platform: str = "",
    part_idx: int = 0,
    total_parts: int = 0,
    narration_mode: str = "",
    editorial_hint: str = "",
    # Back-compat alias for v1 callers passing `text` instead of `srt_segmented`.
    text: Optional[str] = None,
    target_duration_sec: Optional[float] = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the segmented rewrite LLM call.

    Inputs:
      srt_segmented: SRT formatted as one line per utterance:
        `[start_sec - end_sec] text`. Produced by format_segments_for_prompt().
      clip_duration_sec: total clip duration in seconds.
      target_language: ISO-locale ("vi-VN", "en-US", ...).
      tone: optional creator hint forwarded to the prompt's TONE line.

    Back-compat: v1 callers pass `text` + `target_duration_sec`. When that
    form is used the source is treated as a SINGLE utterance covering the
    full clip duration.
    """
    if text is not None and not srt_segmented:
        srt_segmented = f"[0.0 - {float(target_duration_sec or 0.0):.1f}] {text}"
        clip_duration_sec = float(target_duration_sec or clip_duration_sec)

    cleaned = (srt_segmented or "").strip()
    if len(cleaned) > MAX_REWRITE_INPUT_CHARS:
        cleaned = cleaned[:MAX_REWRITE_INPUT_CHARS] + " [truncated]"
    word_budget = _compute_word_budget(clip_duration_sec, target_language)
    wpm = _WPM_BY_LANG.get(target_language, _DEFAULT_WPM)
    tone_clause = (tone or "").strip() or "natural / informative"
    lang_info = _LANG_INFO.get(target_language, _DEFAULT_LANG_INFO)
    clip_context_section = _build_clip_context_section(
        content_type=content_type,
        hook_type=hook_type,
        clip_title=clip_title,
        target_platform=target_platform,
        part_idx=part_idx,
        total_parts=total_parts,
        editorial_hint=editorial_hint,
    )
    # Reaction persona: swap system prompt + inject the reaction directive.
    # Any other value (incl. "") keeps the default faithful-rewrite prompt
    # byte-identical — Sacred Contract #2 spirit.
    _is_reaction = (narration_mode or "").strip().lower() == "reaction"
    system_prompt = _SYSTEM_REWRITE_REACTION if _is_reaction else _SYSTEM_REWRITE
    reaction_section = _REACTION_SECTION if _is_reaction else ""
    user = _USER_TEMPLATE_REWRITE.format(
        clip_duration_sec=float(clip_duration_sec),
        target_language=target_language,
        target_lang_name=lang_info["name"],
        target_lang_native=lang_info["native"] or lang_info["name"],
        style_note=lang_info["style_note"],
        word_budget=word_budget,
        wpm=wpm,
        tone_clause=tone_clause,
        srt_segmented=cleaned,
        clip_context_section=clip_context_section,
        reaction_section=reaction_section,
    )
    return system_prompt, user
