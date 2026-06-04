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
    "You are a video editor AI. Select the best short-form clips from a transcript "
    'and return a RenderPlan as a single JSON object with a "segments" array. '
    "No prose, no markdown fences, no explanation."
)

_USER_TEMPLATE = """\
Pick the best {output_count} segments from this transcript ({language}) for short-form vertical video.

Transcript format — each [start_sec - end_sec] line is followed by the spoken text:
{srt_content}

HARD CONSTRAINTS (violated segments are silently dropped — pick safer ones):
1. duration (end - start): between {min_sec} and {max_sec} seconds.
2. No overlapping segments. Sort by start ascending.
3. start >= 0.0 and end > start. Copy start/end values exactly from the [x - y] markers above.
4. clip_name: max 60 chars, human-readable. Allowed: letters (incl. Vietnamese/CJK), digits, spaces, hyphens.
5. All float scores: 0.0–1.0 (0.0=worst, 1.0=best).

Prefer: strong hook in first 3s, emotional/funny peaks, complete thoughts, dense value.
Avoid: intros, outros, ads, long silences, mid-sentence cuts, repetitive content.

Return EXACTLY this JSON — no extra keys, no markdown:
{{
  "segments": [
    {{
      "start": 45.2,
      "end": 102.8,
      "score": 0.92,
      "clip_name": "Hook reveal moment",
      "title": "The hook everyone missed",
      "reason": "Strong opening question with payoff at 95s — complete thought",
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

Return up to {output_count} segments. Fewer is fine for short or low-quality transcripts — never invent moments not in the transcript.
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

    user = _USER_TEMPLATE.format(
        language=language,
        srt_content=truncated,
        output_count=output_count,
        min_sec=int(min_sec),
        max_sec=int(max_sec),
        editorial_section=editorial_section,
    )
    return system, user
