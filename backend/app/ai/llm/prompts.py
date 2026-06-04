"""
prompts.py — Shared prompt template for LLM segment selection.

All providers (Gemini, OpenAI, Claude) use this same template.
The LLM is called in JSON mode (or equivalent), so the response must be a
single JSON object with a "segments" array.
"""
from __future__ import annotations

import os as _os

_SYSTEM = (
    "You are a video editor AI that selects the best short-form clips "
    "from a transcript. Return ONLY a single JSON object with a "
    '"segments" array. No prose, no markdown fences, no explanation.'
)

_USER_TEMPLATE = """\
Pick the best {output_count} segments from this transcript ({language}) for short-form video clips.

Transcript (timestamps in seconds):
{srt_content}

HARD CONSTRAINTS (violations are silently dropped — pick safer segments):
1. Each segment duration (end - start) must be between {min_sec} and {max_sec} seconds.
2. Segments must NOT overlap. Sort by start time ascending.
3. start >= 0 and end <= total video duration. Use the transcript timestamps as the source of truth.
4. clip_name: human-readable filename stem, max 60 chars. Allowed: letters (incl. Vietnamese / CJK), digits, spaces, hyphens. NOT allowed: / \\ : * ? " < > | newlines.
5. score: float 0.0–1.0 where 1.0 = best.

Prefer: strong hook in the first 3 seconds, valuable info, emotional/funny peaks, complete thoughts.
Avoid: intros, outros, ads, long silences, repetitive content, mid-sentence cuts.

Return EXACTLY this JSON shape (no other keys, no markdown, no comments):
{{
  "segments": [
    {{
      "start": 45.2,
      "end": 102.8,
      "score": 0.92,
      "clip_name": "Hook reveal moment",
      "title": "The hook everyone missed",
      "reason": "Strong opening question, payoff at 95s"
    }}
  ]
}}

Return up to {output_count} segments. Returning fewer is fine if the transcript is short or low-quality — never invent moments that are not in the transcript.
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

    max_srt_chars overrides MAX_SRT_CHARS — use for high-context providers.
    editorial_hint is appended to the system prompt only. Empty = no change.
    """
    cap = max_srt_chars if max_srt_chars is not None else MAX_SRT_CHARS
    truncated = srt_content[:cap]
    if len(srt_content) > cap:
        truncated += "\n... [transcript truncated]"

    hint = editorial_hint.strip()
    system = _SYSTEM + (f" {hint}" if hint else "")

    user = _USER_TEMPLATE.format(
        language=language,
        srt_content=truncated,
        output_count=output_count,
        min_sec=int(min_sec),
        max_sec=int(max_sec),
    )
    return system, user
