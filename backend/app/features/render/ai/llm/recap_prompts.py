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

_USER_TEMPLATE_RECAP = """Build a RECAP PLAN for this film.

═══ FILM ═══
NARRATION LANGUAGE: {lang_name}
FILM DURATION:      {video_duration:.0f} seconds (~{video_minutes:.0f} min)
CREATOR TONE:       {tone_clause}

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

═══ THINK FIRST (fill story_summary before anything else) ═══
Before selecting scenes, mentally reconstruct the WHOLE film: who the characters
are, what they want, the central conflict, the key turns, and the ending. Capture
it in `story_summary` (3-6 sentences). Then split episodes + select scenes + write
narration that SERVE that through-line. This prevents a recap that just samples
the opening.

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
    dur = float(video_duration or 0.0)
    ep_lo, ep_hi = _episode_range(dur)
    user = _USER_TEMPLATE_RECAP.format(
        lang_name=lang_name,
        video_duration=dur,
        video_minutes=dur / 60.0,
        tone_clause=tone_clause,
        episode_min=ep_lo,
        episode_max=ep_hi,
        episode_guidance=_episode_guidance(ep_lo, ep_hi),
        srt_content=cleaned,
    )
    return _SYSTEM_RECAP, user
