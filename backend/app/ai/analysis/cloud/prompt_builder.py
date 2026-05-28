"""
prompt_builder.py — Builds the transcript analysis prompt for cloud providers.

Prompt and system message are versioned here so they can evolve independently
of provider implementations.
"""
from __future__ import annotations

_SYSTEM = (
    "You are a short-form video editing AI. "
    "Analyze the transcript and return ONLY valid JSON. No text outside JSON."
)

_USER_TEMPLATE = """\
Transcript ({duration:.0f}s video, goal: {goal}):
{transcript}

Return JSON with exactly these keys:
{{
  "clip_signals": [
    {{"start": 10.5, "end": 75.0, "hook_score": 85, "hook_type": "curiosity",
      "relevance_score": 90, "reason": "strong hook with clear payoff",
      "clip_type": "hook", "thumbnail_sec": 12.0, "drop": false}}
  ],
  "emotion": {{"dominant": "urgency", "score": 78}},
  "subtitle_hints": {{
    "style_preset": "viral_bold",
    "highlight_keywords": ["never", "mistake", "warning"],
    "density": "compact"
  }},
  "camera_hints": {{
    "behavior": "dramatic_push",
    "zoom_strength": 1.12,
    "follow_strength": 0.65
  }}
}}

Rules:
- clip_signals: 1-5 best clips, start/end in seconds, all scores 0-100
- hook_type: curiosity|surprise|warning|authority|problem|story|contrarian|result_first|none
- clip_type: hook|payoff|educational|emotional|transition
- thumbnail_sec: best frame time in seconds for a thumbnail (must be within start..end range)
- drop: true if this clip is low quality and should be excluded; false otherwise
- subtitle_hints.style_preset: viral_bold|clean_pro|boxed_caption|null
- subtitle_hints.density: compact|normal|relaxed
- camera_hints.behavior: dramatic_push|fast_follow|slow_reveal|subject_lock|none
- zoom_strength: 1.0-1.18, follow_strength: 0.0-0.85
"""

# Hard cap on transcript chars sent to cloud to control token cost.
# ~6000 chars ≈ 1500-2000 tokens at GPT tokenization rates.
_MAX_TRANSCRIPT_CHARS = 6000


def build_prompt(chunks: list[dict], context: dict) -> str:
    goal = str(context.get("goal", "viral"))
    duration = float(context.get("duration") or 0.0)
    transcript = _format_chunks(chunks, _MAX_TRANSCRIPT_CHARS)
    return _USER_TEMPLATE.format(duration=duration, goal=goal, transcript=transcript)


def get_system_prompt() -> str:
    return _SYSTEM


# ── Internal ──────────────────────────────────────────────────────────────────

def _format_chunks(chunks: list[dict], max_chars: int) -> str:
    lines: list[str] = []
    total = 0
    for chunk in chunks:
        start = float(chunk.get("start") or 0.0)
        text = str(chunk.get("text") or "").strip()
        if not text:
            continue
        m, s = divmod(int(start), 60)
        line = f"{m}:{s:02d} - {text}"
        total += len(line) + 1
        if total > max_chars:
            lines.append("... [truncated]")
            break
        lines.append(line)
    return "\n".join(lines)
