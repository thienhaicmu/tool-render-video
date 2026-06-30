"""
recap_prompts.py — Prompt template for the Recap/Review Film selection call.

The LLM reads the full film transcript (with timestamps) and emits a
RecapPlan: a chronological, act-structured set of scenes that retells the
whole film. Length is AI-decided, scaled to the film runtime — NOT a forced
cap (a 2-hour film gets a longer recap). See docs/RECAP_REVIEW_SPEC.md.

R6: the AI also SPLITS a long film into 1..N EPISODES (Tập) at natural story
breakpoints — each episode becomes its own deliverable video — and decides,
per scene, whether to NARRATE (recap voice-over) or let the SOURCE audio play
raw (``audio_mode``: "narrate" | "original") for the few peak dramatic beats.
The AI authors the actual narration text in this same call.
"""
from __future__ import annotations

import os as _os

# Cap on input transcript chars sent to the LLM. Per the content-strategy
# contract the AI must read the WHOLE film, so this is set generously — Gemini
# 2.5 Flash has a ~1M-token context and a 2-3h film transcript is only ~40-150k
# tokens. Default 600000 chars (~150k tokens) covers feature films in full;
# only a pathologically huge transcript is downsampled (last resort). Override
# via RECAP_MAX_SRT_CHARS.
MAX_RECAP_SRT_CHARS = int(_os.getenv("RECAP_MAX_SRT_CHARS", "600000"))

_LANG_NAMES: dict[str, str] = {
    "vi-VN": "Vietnamese (Tiếng Việt)",
    "en-US": "English (American)",
    "en-GB": "English (British)",
    "ja-JP": "Japanese (日本語)",
    "ko-KR": "Korean (한국어)",
}


_SYSTEM_RECAP = (
    "You are an expert film recap narrator + editor (a top recap/review "
    "channel). You READ THE WHOLE film transcript and UNDERSTAND the story, "
    "then produce a recap that retells it faithfully but shorter — same plot, "
    "same chronological order, no invented events. Like a real channel you "
    "SPLIT a long film into a few EPISODES (Tập) at natural story breaks, and "
    "you decide per scene whether to NARRATE over it or stay silent and let "
    "the ORIGINAL audio play for a peak dramatic beat. For narrated scenes you "
    "WRITE THE ACTUAL NARRATION the voice-over speaks (in the target language), "
    "as ONE cohesive script that flows scene→scene (not disconnected blurbs). "
    "You think like a storyteller: setup → rising action → climax → resolution. "
    "Output ONLY valid JSON in the exact shape requested — no prose, no "
    "markdown, no code fences."
)

_USER_TEMPLATE_RECAP = """═══ TRANSCRIPT (seconds into the film) ═══
{srt_content}

═══ BUILD A RECAP PLAN FOR THIS FILM ═══
NARRATION LANGUAGE: {lang_name}
FILM DURATION:      {video_duration:.0f} seconds (~{video_minutes:.0f} min)
CREATOR TONE:       {tone_clause}
{story_block}{editorial_block}
═══ HOW TO WORK ═══
1. Read the timestamped transcript below — the numbers are SECONDS into the film.
2. Select the KEY scenes that, in order, tell the whole story. Skip filler.
3. **SCENE LENGTH**: each scene must be a SUBSTANTIAL, coherent beat — typically
   **8–40 seconds** long. MERGE adjacent utterances/lines into one scene. Do NOT
   emit one scene per subtitle line (2–5s fragments make a choppy, useless recap).
4. **COVER THE WHOLE FILM**: scenes must span from the opening to the ENDING
   (0s → ~{video_duration:.0f}s), not cluster at the start. A feature film usually
   needs **15–40 scenes** total across all episodes.
5. **SPLIT INTO EPISODES (Tập)**: {episode_guidance} Each episode is its own
   deliverable video, so it must be a self-contained arc with its own mini
   setup→climax and end on a hook/turning-point. Cut episodes at NATURAL story
   breaks (a time jump, a major reveal, end of an act) — never mid-scene. Give
   each episode a short title like "Tập 1: <hook>".
6. Inside each episode, group scenes into ACTS (chapters) following the arc:
   setup → rising → climax → resolution. Give each act a short title.
7. Keep ALL scenes in CHRONOLOGICAL order across the whole film and across
   episodes (episode 1 is the earliest part of the film, etc.). Scene start/end
   use the transcript seconds.
8. Decide the recap's total length yourself, scaled to the film (roughly 10–25%
   of the film runtime is typical — use judgement). The recap MUST NOT exceed the
   film duration ({video_duration:.0f}s). Set total_target_sec to your chosen total.
9. **NARRATE vs ORIGINAL AUDIO** (set "audio_mode" per scene):
   - "narrate" (DEFAULT, the vast majority of scenes): you WRITE THE ACTUAL
     NARRATION ("narration") the voice-over speaks over that scene — in
     {lang_name}. Write it as ONE cohesive story that flows from the previous
     scene (use connective phrasing). Keep each scene's narration CONCISE — about
     1-3 sentences, speakable within its on-screen time at a natural pace (no
     paragraphs; brevity keeps the recap from being cut off).
   - "original" (a FEW peak beats only — a killer line, a shocking reveal, an
     emotional gut-punch): let the SOURCE audio play RAW. Leave "narration"
     EMPTY for these. Use this sparingly (roughly 1–3 per episode) and keep the
     scene short — it's the moment you stop talking and let the film land. Lead
     INTO it with the previous narrated scene so the silence has weight.
10. Mark is_climax=true for the few peak/turning-point scenes.
11. Preserve every key fact, name, and number — your recap retells, it never
   fabricates. Keep the SAME chronological order and plot as the film.
{think_first_block}
═══ NARRATION QUALITY BAR ═══
GOOD narration: "Nam tưởng mọi chuyện đã yên — cho đến khi viên cảnh sát lật hồ sơ
chiếc xe. Một cái tên hiện ra, và mọi lời nói dối bắt đầu sụp đổ."
BAD (avoid): "Cảnh này có một người đàn ông và cảnh sát nói chuyện về xe." (mô tả
khô khan, không kể chuyện) · liệt kê sự kiện rời rạc · lặp cấu trúc câu mỗi cảnh ·
spoiler-dump không cảm xúc.
Write like a great film-recap channel: cohesive, vivid, emotionally aware, each
scene's line flows from the previous one.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
{story_summary_line}  "total_target_sec": <float>,
  "episodes": [
    {{
      "title": "<episode title, e.g. 'Tập 1: ...'>",
      "acts": [
        {{
          "title": "<act/chapter title>",
          "beat": "setup|rising|climax|resolution",
          "scenes": [
            {{ "start": <float>, "end": <float>, "title": "<short scene label>",
               "audio_mode": "narrate|original",
               "narration": "<recap voice-over for this scene in {lang_name}; EMPTY if audio_mode=original>",
               "is_climax": <true|false> }}
          ]
        }}
      ]
    }}
  ]
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. episodes non-empty ({episode_min}–{episode_max} episodes); each episode.acts
   non-empty; each act.scenes non-empty.
3. Scenes sorted by start with NO overlaps, across the whole film AND across
   episodes (episode order = chronological).
4. Every scene 0 <= start < end <= {video_duration:.0f}.
5. total_target_sec > 0 and <= {video_duration:.0f}.
6. Each scene must be at least 6 seconds long (end - start >= 6). Merge shorter
   beats into a neighbour — NO 2–5s fragments.
7. audio_mode is "narrate" or "original". Most scenes are "narrate". "original"
   scenes have an EMPTY narration.

═══ OUTPUT JSON ═══
"""


# Single-pass "think first" block. Only injected when NO pass-1 Story Model is
# supplied — in two-pass mode the committed StoryModel is already injected via
# {story_block}, so asking the model to re-reconstruct + re-emit story_summary
# just wastes output tokens (the field is overwritten by plan.story downstream).
_THINK_FIRST_SECTION = (
    "═══ THINK FIRST (fill story_summary before anything else) ═══\n"
    "Before selecting scenes, mentally reconstruct the WHOLE film: who the characters\n"
    "are, what they want, the central conflict, the key turns, and the ending. Capture\n"
    "it in `story_summary` (3-6 sentences). Then split episodes + select scenes + write\n"
    "narration that SERVE that through-line. This prevents a recap that just samples\n"
    "the opening."
)


# ── R7 pass-1: Story Model (whole-film understanding) ────────────────────────
_SYSTEM_STORY = (
    "You are an expert film analyst. You READ THE WHOLE film transcript and "
    "reconstruct the story: who the characters are and what they want, the "
    "central conflict, the key plot turns in order, the climax, and the ending. "
    "You think like a storyteller (setup → rising action → climax → resolution). "
    "Output ONLY valid JSON in the exact shape requested — no prose, no markdown, "
    "no code fences. Base everything on the transcript; never invent events."
)

_USER_TEMPLATE_STORY = """═══ TRANSCRIPT (seconds into the film) ═══
{srt_content}

═══ TASK ═══
Reconstruct the WHOLE story of this {video_minutes:.0f}-min film ({video_duration:.0f}s)
BEFORE any editing. Write in {lang_name}. Base everything on the transcript above.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "summary": "<3-6 sentence whole-film synopsis in {lang_name}>",
  "theme": "<the central theme, one line in {lang_name}>",
  "genre": "<genre / tone, short>",
  "conflict": "<the central conflict driving the film, one line in {lang_name}>",
  "resolution": "<how that conflict resolves, one line in {lang_name}>",
  "characters": [
    {{ "name": "<character name>", "role": "<who they are / their function>",
       "want": "<what they want — the motor of their arc>" }}
  ],
  "beats": [
    {{ "text": "<key plot turn, short, in {lang_name}>",
       "t": <approx second into the film, or -1 if unsure>,
       "kind": "setup|turn|reveal|climax|resolution" }}
  ],
  "emotional_curve": ["<emotion per phase, ORDERED setup→ending, e.g. 'hope','dread','catharsis'>"],
  "climax": "<the single peak / turning point, one line in {lang_name}>",
  "ending": "<how the film resolves, one line in {lang_name}>"
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. Every field present. characters + beats are non-empty arrays of OBJECTS (not
   bare strings). emotional_curve is a non-empty ordered array of short strings.
3. beats in CHRONOLOGICAL order; set "t" to the approximate transcript second
   (use -1 only when genuinely unknown).
4. Retell, never fabricate — preserve names, facts, chronology.

═══ OUTPUT JSON ═══
"""


def _story_block(story_model) -> str:
    """Render a StoryModel into a plain-text block for injection into the pass-2
    recap prompt. Returns "" when no usable model. The text is passed to
    ``str.format`` as a VALUE (not re-parsed), so any braces it contains are
    safe — but we still strip them defensively. Never raises."""
    if story_model is None:
        return ""
    try:
        summary = (getattr(story_model, "summary", "") or "").strip()
        theme = (getattr(story_model, "theme", "") or "").strip()
        genre = (getattr(story_model, "genre", "") or "").strip()
        conflict = (getattr(story_model, "conflict", "") or "").strip()
        resolution = (getattr(story_model, "resolution", "") or "").strip()
        characters = [str(c).strip() for c in (getattr(story_model, "characters", []) or []) if str(c).strip()]
        beats = [str(b).strip() for b in (getattr(story_model, "beats", []) or []) if str(b).strip()]
        emo = [str(e).strip() for e in (getattr(story_model, "emotional_curve", []) or []) if str(e).strip()]
        climax = (getattr(story_model, "climax", "") or "").strip()
        ending = (getattr(story_model, "ending", "") or "").strip()
        if not (summary or characters or beats or climax or ending or theme or conflict or emo):
            return ""
        lines = ["", "═══ STORY MODEL (your pass-1 understanding — plan FROM this) ═══"]
        if summary:
            lines.append(f"SUMMARY: {summary}")
        if theme:
            lines.append(f"THEME: {theme}")
        if genre:
            lines.append(f"GENRE: {genre}")
        if conflict:
            lines.append(f"CONFLICT: {conflict}")
        if characters:
            lines.append("CHARACTERS: " + " · ".join(characters))
        if beats:
            lines.append("KEY BEATS (chronological):")
            lines.extend(f"  - {b}" for b in beats)
        if emo:
            lines.append("EMOTIONAL CURVE: " + " → ".join(emo))
        if climax:
            lines.append(f"CLIMAX: {climax}")
        if resolution:
            lines.append(f"RESOLUTION: {resolution}")
        if ending:
            lines.append(f"ENDING: {ending}")
        lines.append(
            "Select scenes + write narration that SERVE this through-line; keep the "
            "SAME chronology and characters. Do not contradict the Story Model."
        )
        block = "\n".join(lines) + "\n"
        # Defensive: neutralise stray braces so an accidental re-format can't break.
        return block.replace("{", "(").replace("}", ")")
    except Exception:
        return ""


def _editorial_block(editorial) -> str:
    """Render an EditorialBlueprint into a plain-text block for injection into the
    pass-3 recap prompt. Returns "" when no usable plan. Passed to ``str.format``
    as a VALUE (brace-neutralised) — format-safe. Never raises."""
    if editorial is None:
        return ""
    try:
        ep_count = int(getattr(editorial, "episode_count", 0) or 0)
        rationale = (getattr(editorial, "episode_rationale", "") or "").strip()
        pacing = (getattr(editorial, "pacing", "") or "").strip()
        raw_beats = getattr(editorial, "beats", []) or []
        if not (ep_count or rationale or pacing or raw_beats):
            return ""
        lines = ["", "═══ EDITORIAL PLAN (your pass-2 plan — EXECUTE it) ═══"]
        if ep_count:
            lines.append(f"EPISODES: {ep_count}" + (f" — {rationale}" if rationale else ""))
        elif rationale:
            lines.append(f"EPISODES: {rationale}")
        if pacing:
            lines.append(f"PACING: {pacing}")
        beat_lines: list[str] = []
        for b in raw_beats:
            summ = str(getattr(b, "summary", "") or "").strip()
            if not summ:
                continue
            role = str(getattr(b, "story_role", "") or "").strip()
            emo = str(getattr(b, "emotional_intent", "") or "").strip()
            treat = str(getattr(b, "treatment", "") or "").strip()
            meta = " · ".join(x for x in (role, emo, treat) if x)
            beat_lines.append(f"  - {summ}" + (f" ({meta})" if meta else ""))
        if beat_lines:
            lines.append("BEATS (role · emotional intent · treatment):")
            lines.extend(beat_lines)
        lines.append(
            "EXECUTE this plan: split into the stated episodes, match the pacing, "
            "and set audio_mode=original for the beats marked 'hold'."
        )
        block = "\n".join(lines) + "\n"
        return block.replace("{", "(").replace("}", ")")
    except Exception:
        return ""


def _fit_transcript(srt: str, max_chars: int) -> str:
    """Fit a long transcript into max_chars WITHOUT losing the film's ending.

    The old code hard-truncated to the first max_chars → on a feature film the
    AI only saw the opening and clustered the recap there (observed: span 6%).
    Instead, when over budget, DOWNSAMPLE: keep evenly-spaced transcript lines
    across the WHOLE runtime so the AI sees the full arc (start → end), coarser
    but complete. Never raises."""
    try:
        if not srt or len(srt) <= max_chars:
            return srt
        lines = [ln for ln in srt.splitlines() if ln.strip()]
        if not lines:
            return srt[:max_chars]
        # Estimate how many evenly-spaced lines fit the budget.
        avg = max(1, len(srt) // max(1, len(lines)))
        keep = max(50, int(max_chars / avg * 0.95))
        if keep >= len(lines):
            return "\n".join(lines)
        step = len(lines) / keep
        sampled = [lines[int(i * step)] for i in range(keep)]
        out = "\n".join(sampled)
        return (out[:max_chars] if len(out) > max_chars else out) + "\n[transcript downsampled to fit — full runtime represented]"
    except Exception:
        return srt[:max_chars]


# R6 episode-split soft guards. The AI decides the count, but we steer it with a
# duration-based range so it never splits a short film into vunks or leaves a
# 2-hour film as one unwatchable block. Override the hard cap via RECAP_MAX_EPISODES.
_RECAP_MAX_EPISODES = max(1, int(_os.getenv("RECAP_MAX_EPISODES", "4") or 4))


def _episode_range(video_duration: float) -> tuple[int, int]:
    """Suggested (min, max) episode count from film runtime. Short films stay a
    single episode; long films split at natural breaks. Capped by RECAP_MAX_EPISODES."""
    minutes = max(0.0, float(video_duration or 0.0)) / 60.0
    if minutes < 40:
        lo, hi = 1, 1
    elif minutes < 70:
        lo, hi = 1, 2
    elif minutes < 100:
        lo, hi = 2, 3
    else:
        lo, hi = 3, 4
    cap = _RECAP_MAX_EPISODES
    return min(lo, cap), min(hi, cap)


def _episode_guidance(lo: int, hi: int) -> str:
    if hi <= 1:
        return ("This film is short enough to be ONE episode — keep it as a single "
                "episode (still required in the `episodes` array, with one entry).")
    if lo == hi:
        return (f"This film is long — split it into EXACTLY {lo} episodes of roughly "
                "equal length.")
    return (f"This film is long — split it into {lo}–{hi} episodes (you choose, based "
            "on where the story naturally breaks) of roughly comparable length.")


def build_story_model_prompt(
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
) -> tuple[str, str]:
    """R7 pass-1 — return (system, user) for the Story Model (whole-film
    understanding) LLM call. ``tone`` is accepted for signature parity with
    build_recap_prompt but not used (the synopsis is tone-neutral)."""
    cleaned = _fit_transcript((srt_content or "").strip(), MAX_RECAP_SRT_CHARS)
    lang_name = _LANG_NAMES.get(target_language, target_language or "the target language")
    dur = float(video_duration or 0.0)
    user = _USER_TEMPLATE_STORY.format(
        lang_name=lang_name,
        video_duration=dur,
        video_minutes=dur / 60.0,
        srt_content=cleaned,
    )
    return _SYSTEM_STORY, user


def build_recap_prompt(
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
    story_model=None,
    editorial=None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the recap selection LLM call.

    R7: when ``story_model`` is provided (pass-1 output), its understanding is
    injected so pass-2 plans FROM a committed Story Model.
    R7.3: when ``editorial`` (pass-2 EditorialBlueprint) is provided, its plan is
    injected and its ``episode_count`` overrides the duration-based episode range
    (pass-3 EXECUTES the editorial plan). Both blocks are passed as ``str.format``
    values (not re-parsed) and brace-neutralised — format-safe."""
    cleaned = _fit_transcript((srt_content or "").strip(), MAX_RECAP_SRT_CHARS)
    lang_name = _LANG_NAMES.get(target_language, target_language or "the target language")
    tone_clause = (tone or "").strip() or "engaging / cinematic"
    dur = float(video_duration or 0.0)
    # Two-pass when a non-empty Story Model block is available: drop the
    # "think first" reasoning + the story_summary output field (the StoryModel is
    # already injected above and is authoritative). Single-pass keeps both.
    story_block = _story_block(story_model)
    has_story = bool(story_block)
    think_first_block = "" if has_story else f"\n{_THINK_FIRST_SECTION}\n"
    story_summary_line = (
        "" if has_story
        else f'  "story_summary": "<3-6 câu tóm tắt toàn phim ({lang_name}) — bạn hiểu gì về phim>",\n'
    )
    # Editorial blueprint (pass-2). When it pins an episode_count, that is the
    # authoritative split for pass-3; otherwise fall back to the duration heuristic.
    editorial_block = _editorial_block(editorial)
    ed_count = int(getattr(editorial, "episode_count", 0) or 0) if editorial is not None else 0
    if ed_count >= 1:
        ep_lo = ep_hi = min(ed_count, _RECAP_MAX_EPISODES)
    else:
        ep_lo, ep_hi = _episode_range(dur)
    user = _USER_TEMPLATE_RECAP.format(
        lang_name=lang_name,
        video_duration=dur,
        video_minutes=dur / 60.0,
        tone_clause=tone_clause,
        episode_min=ep_lo,
        episode_max=ep_hi,
        episode_guidance=_episode_guidance(ep_lo, ep_hi),
        story_block=story_block,
        editorial_block=editorial_block,
        think_first_block=think_first_block,
        story_summary_line=story_summary_line,
        srt_content=cleaned,
    )
    return _SYSTEM_RECAP, user


# ── R7.3 pass-2: Editorial Blueprint (HOW to tell it — from the StoryModel) ───
_SYSTEM_EDITORIAL = (
    "You are an expert film-recap EDITOR / show-runner. Given a whole-film STORY "
    "UNDERSTANDING (not the transcript), you plan HOW to TELL it as a recap: how "
    "many EPISODES (Tập) and WHY (where the story naturally breaks), the overall "
    "PACING (driven by the emotional curve), and per key beat its editorial ROLE, "
    "the EMOTIONAL INTENT to land, and whether to NARRATE or HOLD (let the source "
    "audio play for a peak beat). You do NOT pick timestamps or write narration — "
    "the next step does that. Output ONLY valid JSON in the exact shape requested "
    "— no prose, no markdown, no code fences. Plan only from the story given."
)

_USER_TEMPLATE_EDITORIAL = """═══ STORY UNDERSTANDING (plan FROM this) ═══
{story_block}
═══ TASK ═══
Plan HOW to tell this ~{video_minutes:.0f}-min film as a recap. Write in {lang_name}.
Decide:
- EPISODES (Tập): how many and WHY — cut at natural story breaks. Suggested {episode_min}–{episode_max}.
- PACING: overall rhythm, using the emotional curve (where to linger, where to move fast).
- per key BEAT: its editorial role, the emotional intent to land, and NARRATE vs HOLD
  (HOLD = let source audio play for a peak beat — use sparingly, 1–3 total).
Do NOT pick timestamps and do NOT write narration — that is the next step.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "episode_count": <int, >= 1>,
  "episode_rationale": "<why this many / where the breaks are, in {lang_name}>",
  "pacing": "<overall pacing guidance from the emotional curve, in {lang_name}>",
  "beats": [
    {{ "summary": "<which beat / moment, short>",
       "story_role": "setup|inciting|rising|climax|resolution",
       "emotional_intent": "<the feeling this beat should land, in {lang_name}>",
       "treatment": "narrate|hold" }}
  ]
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. episode_count >= 1. beats is a non-empty array of objects in chronological order.
3. Use "hold" sparingly (peak beats only); the rest are "narrate".
4. Plan FROM the story understanding above — do not invent events.

═══ OUTPUT JSON ═══
"""


def build_editorial_prompt(
    story_model,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
) -> tuple[str, str]:
    """R7.3 pass-2 — return (system, user) for the Editorial Blueprint call. Input
    is the StoryModel (rendered as text), NOT the transcript — so the call is cheap.
    ``tone`` is accepted for signature parity but not used (editorial is structural)."""
    block = _story_block(story_model) or "(no story model available)"
    lang_name = _LANG_NAMES.get(target_language, target_language or "the target language")
    dur = float(video_duration or 0.0)
    ep_lo, ep_hi = _episode_range(dur)
    user = _USER_TEMPLATE_EDITORIAL.format(
        story_block=block,
        lang_name=lang_name,
        video_minutes=dur / 60.0,
        episode_min=ep_lo,
        episode_max=ep_hi,
    )
    return _SYSTEM_EDITORIAL, user
