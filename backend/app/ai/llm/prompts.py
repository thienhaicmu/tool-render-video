"""
prompts.py — Shared prompt template for LLM segment selection.

All providers (Gemini, OpenAI, Claude) use this same template.
The LLM is called in JSON mode (or equivalent), so the response must be a
single JSON object with a "segments" array.
"""
from __future__ import annotations

import os as _os
import re as _re

# SRT timestamp pattern: 00:01:23,456 --> 00:02:03,100
_SRT_TS_RE = _re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)
_SRT_BLOCK_NUM_RE = _re.compile(r"^\d+\s*$")


def _srt_to_seconds_format(srt_content: str) -> str:
    """Convert SRT timestamps to [start_sec - end_sec] format.

    00:01:23,456 --> 00:02:03,100  →  [83.5 - 123.1]

    Drops block numbers and blank separator lines (saves ~50% tokens).
    Text lines are preserved verbatim.
    Non-SRT input passes through unchanged.
    """
    out: list[str] = []
    for line in srt_content.splitlines():
        stripped = line.strip()
        m = _SRT_TS_RE.match(stripped)
        if m:
            h1, m1, s1, ms1, h2, m2, s2, ms2 = (int(x) for x in m.groups())
            start = h1 * 3600 + m1 * 60 + s1 + ms1 / 1000
            end   = h2 * 3600 + m2 * 60 + s2 + ms2 / 1000
            out.append(f"[{start:.1f} - {end:.1f}]")
        elif _SRT_BLOCK_NUM_RE.match(stripped):
            pass  # drop block sequence numbers
        elif stripped:
            out.append(line)
        # blank separator lines dropped — saves tokens, AI doesn't need them
    return "\n".join(out)


_SYSTEM = (
    "You are a viral video editor AI. Your job is to find the strongest viral hook moments "
    "in a transcript and build complete, standalone short-form clips around each one. "
    'Return a RenderPlan as a single JSON object with a "segments" array. '
    "No prose, no markdown fences, no explanation."
)

_USER_TEMPLATE = """\
Find the strongest viral hooks in this transcript ({language}) and build up to {output_count} complete clips.
Every returned clip MUST be {min_sec}–{max_sec} seconds long. Any clip outside this range is invalid.

━━━ STEP 1 — SCAN FOR VIRAL HOOKS ━━━

Read the ENTIRE transcript. Identify every moment that is:
  • A hook, reveal, or surprising statement that grabs attention immediately
  • An emotional peak, confrontational moment, or strong opinion
  • A contrarian or counterintuitive insight
  • A curiosity gap ("here's why X is wrong / here's what most people don't know")
  • A complete standalone thought that works without prior context

Rank ALL found hook moments by viral + retention potential.
Remove near-duplicates — only keep the strongest version if two hooks cover the same idea.

━━━ STEP 2 — BUILD CLIPS AROUND HOOKS ━━━

For each top-ranked hook:

  1. The hook moment itself is typically just 2–10 seconds. It is your anchor — NOT the clip.
  2. BACK UP the start timestamp: add enough lead-in so the hook lands in the first 3 seconds
     of the clip. Add at least 5–15 seconds before the hook moment.
  3. EXTEND the end timestamp: keep going until the thought is complete, the payoff lands,
     and the viewer feels satisfied. Usually 30–80 seconds AFTER the hook.
  4. Target clip duration: {min_sec}–{max_sec} seconds. This spans MANY transcript lines.
     A valid clip typically covers 15–60 [x - y] timestamp markers.
  5. Check: if ({{end}} - {{start}}) < {min_sec} → you must extend further. Do not return it.
  6. Check: if ({{end}} - {{start}}) > {max_sec} → trim to keep the core complete thought.

⛔ NEVER return a raw hook moment as a clip. A 2–10 second clip is ALWAYS invalid.
⛔ NEVER copy [x - y] transcript boundaries directly as start/end. Use arbitrary timestamps.

━━━ OVERLAP RULES ━━━

✓ Two clips MAY overlap or share transcript content if they are anchored on DIFFERENT hooks.
✓ Two clips MAY come from nearby timestamps if they represent distinct viral opportunities.
✗ Do NOT return two clips that convey the same idea or differ only in a few seconds.

━━━ COVERAGE IS NOT THE GOAL ━━━

Do NOT try to:
  - Cover different parts of the transcript
  - Distribute clips evenly across the video timeline
  - Avoid returning clips from the same section

DO prioritize:
  - The absolute strongest viral moments, wherever they appear
  - Hooks that work without requiring prior context
  - Clips a viewer can share and understand standalone

Transcript format — each [start_sec - end_sec] line is followed by the spoken text:
{srt_content}

━━━ HARD CONSTRAINTS ━━━

1. (end - start) MUST be between {min_sec} and {max_sec} seconds. Any other value = INVALID.
2. start ≥ 0 and end ≤ video duration.
3. clip_name: max 60 chars. Allowed: letters (incl. Vietnamese/CJK), digits, spaces, hyphens.
4. All float scores: 0.0–1.0.

Avoid: greetings, intros, sponsor segments, outros, long silences, mid-sentence cuts.

Return EXACTLY this JSON — no extra keys, no markdown:
{{
  "segments": [
    {{
      "start": 42.0,
      "end": {example_end},
      "score": 0.92,
      "clip_name": "Hook reveal moment",
      "title": "The hook everyone missed",
      "reason": "Hook at 44s grabs immediately; extended to payoff at {example_end}s — complete thought, {min_sec}–{max_sec}s",
      "hook_type": "question",
      "content_type": "interview",
      "subtitle_style": "viral",
      "viral_score": 0.88,
      "hook_score": 0.92,
      "retention_score": 0.78,
      "speech_density": 0.85,
      "duration_fit": 0.90,
      "cover_offset_ratio": 0.15
    }}
  ]
}}

FIELD RULES:
- hook_type: question | reveal | contrast | humor | emotion | statement
- content_type: interview | vlog | tutorial | commentary | montage | gaming
- subtitle_style (pick exactly one):
    viral  = bold bounce, thick outline, Anton font  — commentary / reaction / hook-heavy shorts
    clean  = minimal, thin outline, Inter font        — tutorial / education / podcast clips
    story  = soft cinematic, Montserrat font          — vlog / emotional / storytelling
    gaming = box-backed caption, Anton font           — gaming / sports / montage
- viral_score: shareability — surprising, relatable, emotional peak
- hook_score: how hard the first 3 seconds grab attention
- retention_score: predicted fraction of viewers who watch to the end
- speech_density: 1.0=dense dialogue, 0.0=pure visuals or long silence
- duration_fit: how well this clip length fits short-form (1.0=ideal {min_sec}–{max_sec}s)
- cover_offset_ratio: best thumbnail moment as fraction of clip duration (0.1=very early, 0.5=mid){editorial_section}

⚠️ FINAL VERIFICATION — before responding, check EVERY segment:
   • {min_sec} ≤ (end - start) ≤ {max_sec}  →  if any segment fails this, fix or remove it
   • start lands 5–15s before the hook moment  →  the hook fires within the first 3s of the clip
   • the clip ends after the payoff, not mid-thought

Quality over quantity. Fewer strong clips beat many weak ones.
Return up to {output_count} segments. Never invent moments not in the transcript.
"""

# Default cap for providers with tight token limits. High-context providers
# (Gemini 1M, Claude 200K) can override via max_srt_chars parameter.
MAX_SRT_CHARS = int(_os.getenv("LLM_MAX_SRT_CHARS", "6000"))


def build_segment_prompt(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    language: str = "auto",
    max_srt_chars: int | None = None,
    editorial_hint: str = "",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for LLM segment selection.

    Converts SRT timestamps to seconds format before sending to the LLM.
    max_srt_chars overrides MAX_SRT_CHARS — use for high-context providers.
    editorial_hint is appended to both system prompt and user prompt.
    """
    converted = _srt_to_seconds_format(srt_content)

    cap = max_srt_chars if max_srt_chars is not None else MAX_SRT_CHARS
    truncated = converted[:cap]
    if len(converted) > cap:
        truncated += "\n... [transcript truncated]"

    hint = editorial_hint.strip()
    system = _SYSTEM + (f" {hint}" if hint else "")
    editorial_section = f"\n\nEDITORIAL GUIDANCE: {hint}" if hint else ""

    # Example end timestamp: 45.2 + midpoint of requested range, so the
    # JSON example always shows a segment that complies with min/max duration.
    example_end = round(45.2 + (min_sec + max_sec) / 2, 1)

    user = _USER_TEMPLATE.format(
        language=language,
        srt_content=truncated,
        output_count=output_count,
        min_sec=int(min_sec),
        max_sec=int(max_sec),
        example_end=example_end,
        editorial_section=editorial_section,
    )
    return system, user
