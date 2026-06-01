"""
prompts.py — Prompt templates for Groq segment selection.

Versioned here so prompts evolve independently of the API client.
Groq is called in JSON mode, so the response is guaranteed to be a
single JSON object. We ask for {"segments": [...]} and the parser
unwraps the array.
"""
from __future__ import annotations

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

# Hard cap: prevent excessive token cost on very long transcripts.
MAX_SRT_CHARS = 12_000


def build_segment_prompt(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    language: str = "auto",
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for Groq segment selection."""
    truncated = srt_content[:MAX_SRT_CHARS]
    if len(srt_content) > MAX_SRT_CHARS:
        truncated += "\n... [transcript truncated]"

    user = _USER_TEMPLATE.format(
        language=language,
        srt_content=truncated,
        output_count=output_count,
        min_sec=int(min_sec),
        max_sec=int(max_sec),
    )
    return _SYSTEM, user
