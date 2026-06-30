"""
recap_prompts.py — Prompt template for the Recap/Review Film selection call.

The LLM reads the full film transcript (with timestamps) and emits a
RecapPlan: a chronological, act-structured set of scenes that retells the
whole film. Length is AI-decided, scaled to the film runtime — NOT a forced
cap (a 2-hour film gets a longer recap). See docs/RECAP_REVIEW_SPEC.md.

This call only SELECTS scenes + structures acts. The per-scene narration
script is authored later by the rewrite/reaction path (R3).
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
    "You are an expert film recap narrator + editor. You READ THE WHOLE film "
    "transcript and UNDERSTAND the story, then produce a recap that retells it "
    "faithfully but shorter — same plot, same chronological order, no invented "
    "events. For each chosen scene you WRITE THE ACTUAL NARRATION the voice-over "
    "will speak (in the target language), as ONE cohesive script that flows "
    "scene→scene like a real recap (not disconnected blurbs). You think like a "
    "storyteller: setup → rising action → climax → resolution, and decide the "
    "recap length yourself, scaled to the film. Output ONLY valid JSON in the "
    "exact shape requested — no prose, no markdown, no code fences."
)

_USER_TEMPLATE_RECAP = """Build a RECAP PLAN for this film.

═══ FILM ═══
NARRATION LANGUAGE: {lang_name}
FILM DURATION:      {video_duration:.0f} seconds
CREATOR TONE:       {tone_clause}

═══ HOW TO WORK ═══
1. Read the timestamped transcript below — the numbers are SECONDS into the film.
2. Select the KEY scenes that, in order, tell the whole story. Skip filler.
3. **SCENE LENGTH**: each scene must be a SUBSTANTIAL, coherent beat — typically
   **8–40 seconds** long. MERGE adjacent utterances/lines into one scene. Do NOT
   emit one scene per subtitle line (2–5s fragments make a choppy, useless recap).
4. **COVER THE WHOLE FILM**: scenes must span from the opening to the ENDING
   (0s → ~{video_duration:.0f}s), not cluster at the start. A feature film usually
   needs **15–40 scenes** total across all acts.
5. Group the selected scenes into ACTS (chapters) following the narrative arc:
   setup → rising → climax → resolution. Give each act a short title.
6. Keep scenes in CHRONOLOGICAL order. Scene start/end use the transcript seconds.
7. Decide the recap's total length yourself, scaled to the film (roughly 10–25%
   of the film runtime is typical — use judgement). The recap MUST NOT exceed the
   film duration ({video_duration:.0f}s). Set total_target_sec to your chosen total.
8. For each scene, WRITE THE ACTUAL NARRATION ("narration") the voice-over will
   speak over that scene — in {lang_name}. This is the real recap script, not a
   note: write it as ONE cohesive story that flows from the previous scene into
   this one (use connective phrasing). Keep each scene's narration roughly within
   its on-screen time at a natural speaking pace. Mark is_climax=true for the few
   peak/turning-point scenes.
9. Preserve every key fact, name, and number — your recap retells, it never
   fabricates. Keep the SAME chronological order and plot as the film.

═══ THINK FIRST (fill story_summary before anything else) ═══
Before selecting scenes, mentally reconstruct the WHOLE film: who the characters
are, what they want, the central conflict, the key turns, and the ending. Capture
it in `story_summary` (3-6 sentences). Then select scenes + write narration that
SERVE that through-line. This prevents a recap that just samples the opening.

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
  "story_summary": "<3-6 câu tóm tắt toàn phim ({lang_name}) — bạn hiểu gì về phim>",
  "total_target_sec": <float>,
  "acts": [
    {{
      "title": "<act/chapter title>",
      "beat": "setup|rising|climax|resolution",
      "scenes": [
        {{ "start": <float>, "end": <float>, "title": "<short scene label>",
           "narration": "<the ACTUAL recap voice-over for this scene, in {lang_name}>",
           "is_climax": <true|false> }}
      ]
    }}
  ]
}}

═══ HARD RULES ═══
1. ONE JSON object. No markdown, no prose, no code fences.
2. acts non-empty; each act.scenes non-empty; scenes sorted by start, no overlaps.
3. Every scene 0 <= start < end <= {video_duration:.0f}.
4. total_target_sec > 0 and <= {video_duration:.0f}.
5. Each scene must be at least 6 seconds long (end - start >= 6). Merge shorter
   beats into a neighbour — NO 2–5s fragments.

═══ TRANSCRIPT (seconds) ═══
{srt_content}

═══ OUTPUT JSON ═══
"""


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


def build_recap_prompt(
    srt_content: str,
    video_duration: float,
    target_language: str = "vi-VN",
    tone: str = "",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for the recap selection LLM call."""
    cleaned = _fit_transcript((srt_content or "").strip(), MAX_RECAP_SRT_CHARS)
    lang_name = _LANG_NAMES.get(target_language, target_language or "the target language")
    tone_clause = (tone or "").strip() or "engaging / cinematic"
    user = _USER_TEMPLATE_RECAP.format(
        lang_name=lang_name,
        video_duration=float(video_duration or 0.0),
        tone_clause=tone_clause,
        srt_content=cleaned,
    )
    return _SYSTEM_RECAP, user
