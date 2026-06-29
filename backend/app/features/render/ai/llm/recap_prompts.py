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

# Cap on input transcript chars sent to the LLM. Films are long; default
# generous. Override via RECAP_MAX_SRT_CHARS.
MAX_RECAP_SRT_CHARS = int(_os.getenv("RECAP_MAX_SRT_CHARS", "120000"))

_LANG_NAMES: dict[str, str] = {
    "vi-VN": "Vietnamese (Tiếng Việt)",
    "en-US": "English (American)",
    "en-GB": "English (British)",
    "ja-JP": "Japanese (日本語)",
    "ko-KR": "Korean (한국어)",
}


_SYSTEM_RECAP = (
    "You are an expert film recap/review editor. Given a film's full transcript "
    "with timestamps, you select the KEY scenes that retell the whole story in "
    "chronological order and group them into ACTS (chapters). You think like a "
    "storyteller: setup → rising action → climax → resolution. You decide the "
    "recap's total length yourself, scaled to the film — a longer film gets a "
    "longer recap. You NEVER invent scenes or events not present in the "
    "transcript. Output ONLY valid JSON in the exact shape requested — no prose, "
    "no markdown, no code fences."
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
8. For each scene write a short narration_intent: what the narrator should convey
   at that scene (1 sentence). Mark is_climax=true for the few peak/turning-point
   scenes (used for dramatic emphasis later).
9. Preserve every key fact, name, and number — your selection retells, it never
   fabricates.

═══ OUTPUT FORMAT (STRICT — return ONLY this JSON) ═══
{{
  "total_target_sec": <float>,
  "acts": [
    {{
      "title": "<act/chapter title>",
      "beat": "setup|rising|climax|resolution",
      "scenes": [
        {{ "start": <float>, "end": <float>, "title": "<short scene label>",
           "narration_intent": "<what the narrator conveys here>",
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
