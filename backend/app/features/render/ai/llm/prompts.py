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

# Audit 2026-06-08 T1.5 closure — module-level fallback cap for callers
# that invoke check_srt_truncation() / build_render_plan_prompt() WITHOUT
# an explicit max_srt_chars (notably render_pipeline.py's pre-flight
# warning emit). Providers ALWAYS pass their own _MAX_SRT_CHARS, so this
# constant only applies to provider-agnostic call sites. Default 60000
# matches Gemini's permissive cap so the warning fires only when even the
# most-permissive provider would truncate. Override via PROMPTS_MAX_SRT_CHARS.
MAX_SRT_CHARS = int(_os.getenv("PROMPTS_MAX_SRT_CHARS", "60000"))

# Phase B — per-platform editorial guidance injected into the prompt when
# target_platform is set.  Each entry is a concise paragraph appended as a
# PLATFORM GUIDANCE section.  Empty platform (or unknown value) suppresses
# the section entirely — backward-compat with all callers that never set it.
_PLATFORM_PROMPT_HINTS: dict[str, str] = {
    "tiktok": (
        "Target platform: TikTok. "
        "Prefer clips with energetic pacing and an immediately grabbing hook. "
        "subtitle_policy.style MUST be \"viral\" unless the content is clearly "
        "educational (then \"clean\") or storytelling-driven (then \"story\"). "
        "Set motion_aware_crop=true for mobile-first vertical framing. "
        "Aim for hook_intensity >= 0.7 on the top-ranked clip."
    ),
    "youtube_shorts": (
        "Target platform: YouTube Shorts. "
        "Prefer clear, informative clips that reward curiosity. "
        "subtitle_policy.style MUST be \"clean\" unless content is commentary/reaction "
        "(then \"viral\"). "
        "Clip duration MUST NOT exceed 60 seconds — truncate the end before the payoff "
        "drops if necessary. "
        "Avoid over-aggressive hooks; YouTube rewards retention over shock."
    ),
    "instagram_reels": (
        "Target platform: Instagram Reels. "
        "Prefer polished, aesthetically pleasing clips with a slightly slower pace than TikTok. "
        "subtitle_policy.style MUST be \"story\" or \"clean\". "
        "Avoid aggressive shock hooks — favor emotional peaks, beauty moments, or "
        "thoughtful insights. "
        "motion_aware_crop=true for clean subject framing."
    ),
}


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


_SYSTEM_RP = (
    "You are a viral video editor AI. Your job is to emit a complete RenderPlan "
    "as a single JSON object describing both WHICH clips to extract and HOW each "
    "one should be subtitled, framed, mixed, and overlaid. "
    "Return one JSON object only — no prose, no markdown fences, no explanation."
)

# The literal {{ and }} pairs in the JSON example resolve to single { and }
# after .format(). The pre-flight {end}/{start} bug class is the reason every
# literal brace in the prose body below is doubled — only the named
# placeholders ({language}, {min_sec}, {max_sec}, {output_count},
# {srt_content}, {example_end}, {editorial_section}) are substituted.
_USER_TEMPLATE_RP = """Build a RenderPlan from this transcript ({language}) — pick up to {output_count} clips
and decide the editorial sub-plans that fit the content. Every clip MUST be
{min_sec}–{max_sec} seconds long; clips outside that range are invalid.

─── STEP 1 — CLIP SELECTION ───

Read the ENTIRE transcript. Identify every moment that is:
  • A hook, reveal, or surprising statement that grabs attention immediately
  • An emotional peak, confrontational moment, or strong opinion
  • A contrarian or counterintuitive insight
  • A curiosity gap ("here's why X is wrong / here's what most people don't know")
  • A complete standalone thought that works without prior context

Rank ALL found hook moments by viral + retention potential.
Remove near-duplicates — only keep the strongest version if two hooks cover the same idea.

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

OVERLAP RULES

✔ Two clips MAY overlap or share transcript content if they are anchored on DIFFERENT hooks.
✔ Two clips MAY come from nearby timestamps if they represent distinct viral opportunities.
✗ Do NOT return two clips that convey the same idea or differ only in a few seconds.

COVERAGE IS NOT THE GOAL

Do NOT try to:
  - Cover different parts of the transcript
  - Distribute clips evenly across the video timeline
  - Avoid returning clips from the same section

DO prioritize:
  - The absolute strongest viral moments, wherever they appear
  - Hooks that work without requiring prior context
  - Clips a viewer can share and understand standalone

Avoid: intros, sponsor segments, outros, long silences, mid-sentence cuts.

─── STEP 2 — SUBTITLE POLICY ───

Pick ONE subtitle_style that fits the dominant content type:
  viral  - high-energy reactions, commentary, hook-heavy shorts
  clean  - tutorial, education, podcast clips
  story  - vlog, emotional, storytelling
  gaming - gaming, sports, montage

Set market when the transcript clearly targets a regional audience
("us", "eu", "jp", "vn", "global"). Leave empty otherwise.

Set emphasis_pass=true ONLY when at least one clip has a strong
single-line shouty hook that benefits from bigger subtitle styling on
that line. Otherwise leave false.

─── STEP 3 — CAMERA STRATEGY ───

motion_aware_crop=true when subjects move noticeably (interview head
movement, gameplay action). False for static talking-head content.

reframe_mode:
  track   - subject moves and the crop should follow them
  center  - subject roughly stays in frame center
  fixed   - keep the original framing (rare for vertical short-form)

─── STEP 4 — AUDIO PLAN ───

Default both flags to false. Only flip a flag when the content clearly
needs the feature:
  voice_enabled=true  - the clip needs AI narration over silent footage
                        (extremely rare for short-form viral clips)
  bgm_enabled=true    - the clip is montage-style and needs background music

─── STEP 5 — OVERLAYS ───

overlays is an array. Emit at most one entry per kind:
  kind=hook  - add when the strongest clip's hook deserves an on-screen
               teaser overlay. Include a short "text" (<=60 chars).
  kind=cta   - add when the content has a clear call-to-action moment
               (subscribe, comment, part 2). Set "type" to one of
               "comment" | "part_2" | "follow" | "auto".

When no overlay fits, return overlays=[] instead of inventing one.{clip_lock_section}{clip_exclude_section}{creator_preferences_section}

─── TRANSCRIPT ───

Each [start_sec - end_sec] line is followed by spoken text:
{srt_content}

─── HARD CONSTRAINTS ───

1. ({{end}} - {{start}}) MUST be in [{min_sec}, {max_sec}] for every clip.
2. start >= 0 and end <= video duration.
3. clip_name <= 60 chars; letters (incl. Vietnamese/CJK), digits, spaces,
   hyphens only.
4. All numeric scores in [0.0, 1.0].

─── OUTPUT JSON SHAPE ───

Return EXACTLY this JSON object. No extra top-level keys, no markdown fences:

{{
  "clips": [
    {{
      "start": 42.0,
      "end": {example_end},
      "score": 0.92,
      "clip_name": "Hook reveal moment",
      "title": "The hook everyone missed",
      "reason": "Hook at 44s grabs immediately; extended to payoff at {example_end}s — complete thought, {min_sec}–{max_sec}s",
      "hook_type": "reveal",
      "content_type": "interview",
      "subtitle_style": "viral",
      "viral_score": 0.88,
      "hook_score": 0.92,
      "retention_score": 0.78,
      "speech_density": 0.85,
      "duration_fit": 0.90,
      "cover_offset_ratio": 0.15,
      "pacing": "fast",
      "hook_intensity": 0.92,
      "rank": 1
    }}
  ],
  "subtitle_policy": {{
    "style": "viral",
    "market": "",
    "emphasis_pass": false,
    "subtitle_mode": "word_by_word"
  }},
  "camera_strategy": {{
    "motion_aware_crop": false,
    "reframe_mode": "center",
    "tracker": ""
  }},
  "audio_plan": {{
    "voice_enabled": false,
    "voice_provider": "",
    "bgm_enabled": false,
    "cta_audio": "",
    "bgm_mood": "energetic",
    "bgm_volume": 0.0
  }},
  "overlays": []
}}

FIELD RULES:
- clip_name, title, reason: write these FREE-TEXT fields in {language}. Enum values
  (subtitle_style, hook_type, content_type, pacing) and JSON keys stay in English,
  but human-readable labels follow the transcript language. Example for vi-VN:
  clip_name = "Khoảnh khắc bất ngờ", NOT "The shocking moment".
- hook_type: question | reveal | contrast | humor | emotion | statement
- content_type: interview | vlog | tutorial | commentary | montage | gaming
- subtitle_style (pick exactly one per clip):
    viral  = bold bounce, thick outline, Anton font  — commentary / reaction / hook-heavy shorts
    clean  = minimal, thin outline, Inter font        — tutorial / education / podcast clips
    story  = soft cinematic, Montserrat font          — vlog / emotional / storytelling
    gaming = box-backed caption, Anton font           — gaming / sports / montage
- viral_score: shareability — surprising, relatable, emotional peak
- hook_score: how hard the first 3 seconds grab attention
- retention_score: predicted fraction watching to the end
- speech_density: 1.0=dense dialogue, 0.0=pure visuals or long silence
- duration_fit: 1.0=ideal clip length, 0.0=stretched/cramped
- cover_offset_ratio: best thumbnail moment as fraction of clip
  (0.1=very early, 0.5=mid)
- pacing (per clip): fast | medium | slow | "" = unset
    fast  = rapid cuts, high speech density, energy-driven (gaming, reaction, hype)
    medium = balanced dialogue + reaction (interview, commentary, vlog)
    slow   = deliberate, emotional, minimal cuts (storytelling, emotional, cinematic)
- hook_intensity (per clip): 0.0–1.0 — how aggressively to punch the opening
    ≥ 0.75 triggers a zoom-burst visual effect on the first cut
- rank: quality rank among all returned clips; 1 = strongest, N = weakest.
  Every clip gets a unique integer in [1, N] where N = number of clips returned.
  Assign based on your viral + retention ordering from Step 1.
- subtitle_policy.subtitle_mode: word_by_word | sentence | phrase | "" = inherit
    word_by_word = karaoke-style one word at a time (fast/hype clips)
    sentence     = full sentence appears at once (slow/cinematic)
    phrase       = 3–5 word groups (default for most content)
- audio_plan.bgm_mood: energetic | calm | emotional | hype | "" = no BGM preference
- audio_plan.bgm_volume: dB gain relative to vocal track (0.0 = platform default, -6.0 = softer){editorial_section}{target_duration_section}{target_platform_section}

⚠️ FINAL VERIFICATION — before responding, check EVERY clip:
   • {min_sec} ≤ (end - start) ≤ {max_sec}  →  if any clip fails this, fix or remove it
   • start lands 5–15s before the hook moment  →  the hook fires within the first 3s of the clip
   • the clip ends after the payoff, not mid-thought

Quality over quantity. Fewer strong clips beat many weak ones.
Return up to {output_count} clips. Never invent moments not in the transcript.
"""
def check_srt_truncation(srt_content: str, max_srt_chars: int | None = None) -> dict:
    """Return truncation metadata without modifying input or building the prompt.

    Callers use this to emit a warning event before dispatching to the LLM
    so users know the AI only saw a fraction of a long transcript.

    Returns:
        {
            "truncated": bool,
            "original_chars": int,   # converted seconds-format length
            "shown_chars": int,
            "shown_pct": int,        # 0-100
        }
    """
    converted = _srt_to_seconds_format(srt_content)
    cap = max_srt_chars if max_srt_chars is not None else MAX_SRT_CHARS
    truncated = len(converted) > cap
    shown = min(len(converted), cap)
    return {
        "truncated": truncated,
        "original_chars": len(converted),
        "shown_chars": shown,
        "shown_pct": round(shown / max(len(converted), 1) * 100),
    }


def _build_creator_preferences_section(
    video_type: str = "auto",
    hook_strength: str = "balanced",
    ai_target_market: str = "",
    subtitle_emphasis: str | None = None,
    multi_variant: bool = False,
    structure_bias: str | None = None,
) -> str:
    """Render a labelled prompt section for the creator's editorial preferences.

    These are HINTS that bias clip selection + sub-plan choices without
    overriding the hard constraints (min/max duration, output count,
    transcript content). Suppressed when every field is at its default
    so the prompt is byte-for-byte identical to the pre-S5 baseline for
    all callers that don't pass the new kwargs.

    Hints surfaced (when not default):
    - content_type_hint    — `video_type` (auto / talking / cinematic / ...)
    - hook_intensity_target — `hook_strength` (light / balanced / aggressive)
    - target_market        — `ai_target_market` (us / eu / jp / vn / global)
    - subtitle_emphasis    — `subtitle_emphasis` (when explicit, biases the
                              emphasis_pass decision in subtitle_policy)
    - variant_emission     — `multi_variant=True` asks the model to emit
                              multiple stylistically distinct variants per
                              hook moment instead of one canonical pick
    - ranking_priority     — `structure_bias` (used to break ties when two
                              clips have similar viral+retention scores)
    """
    parts: list[str] = []
    vt = (video_type or "").strip().lower()
    if vt and vt != "auto":
        parts.append(f"content_type_hint: {vt}  (bias clip selection toward this content shape)")
    hs = (hook_strength or "").strip().lower()
    if hs and hs != "balanced":
        # 'light' → softer openings, 'aggressive' → punchier hook moments.
        parts.append(
            f"hook_intensity_target: {hs}  "
            f"({'softer openings, less front-loaded' if hs == 'light' else 'punchier hooks, front-load the surprise'})"
        )
    mk = (ai_target_market or "").strip().lower()
    if mk:
        parts.append(f"target_market: {mk}  (favor clips that resonate with this audience)")
    if subtitle_emphasis:
        parts.append(
            f"subtitle_emphasis_preference: {subtitle_emphasis}  "
            f"(set emphasis_pass=true on clips matching this style)"
        )
    if multi_variant:
        parts.append(
            "variant_emission: ON  "
            "(when a single hook anchors multiple viable cuts, emit each as a separate clip)"
        )
    sb = (structure_bias or "").strip().lower() if structure_bias else ""
    if sb:
        parts.append(
            f"ranking_priority: {sb}  "
            f"(use this as a tiebreaker between clips with similar viral+retention scores)"
        )
    if not parts:
        return ""
    body = "\n".join(f"  • {p}" for p in parts)
    return (
        "\n\n─── CREATOR PREFERENCES ───\n"
        f"{body}\n\n"
        "These are HINTS, not hard rules. Hard constraints "
        "(min/max duration, output count, transcript content) still win."
    )


def build_render_plan_prompt(
    srt_content: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    language: str = "auto",
    max_srt_chars: int | None = None,
    editorial_hint: str = "",
    target_duration: int = 0,
    clip_lock: list[dict] | None = None,
    clip_exclude: list[dict] | None = None,
    target_platform: str = "",
    # S5 — creator preference hints. Each defaults to a value that
    # suppresses its prompt line so the prompt is byte-for-byte identical
    # to the pre-S5 baseline for all callers that don't pass them. See
    # _build_creator_preferences_section docstring for semantics.
    video_type: str = "auto",
    hook_strength: str = "balanced",
    ai_target_market: str = "",
    subtitle_emphasis: str | None = None,
    multi_variant: bool = False,
    structure_bias: str | None = None,
) -> tuple[str, str]:
    """Return (system_prompt, user_prompt) for LLM RenderPlan emission.

    Asks the AI to emit a complete RenderPlan (clips + subtitle_policy
    + camera_strategy + audio_plan + overlays) in one pass. The
    resulting JSON is parseable by ``parse_render_plan_response`` under
    the "native" shape (see parser.py).

    Calling convention:
      - SRT timestamps are converted to seconds format before sending.
      - ``max_srt_chars`` overrides the module-level ``MAX_SRT_CHARS``
        fallback for high-context providers.
      - ``editorial_hint`` is appended to BOTH system prompt and user
        prompt body. The orchestrator already wires
        ``CreatorContext.to_prompt_hint`` into this string via
        ``llm_stage._build_editorial_hint``.
      - ``target_duration`` (T2.4 — Audit 2026-06-08 closure, Batch A
        V8-A1) is the creator's soft total-duration target in seconds.
        When > 0 the prompt grows a TARGET TOTAL DURATION section that
        invites the model to balance clip count × per-clip length to
        fit the budget. ``min_sec``/``max_sec`` and ``output_count``
        remain hard limits. ``target_duration=0`` (the default)
        suppresses the section — back-compat with all callers that
        don't pass the new kwarg.

    Format safety: every literal '{' / '}' inside _USER_TEMPLATE_RP is
    doubled. Only the named placeholders ({language}, {output_count},
    {min_sec}, {max_sec}, {srt_content}, {example_end},
    {editorial_section}, {target_duration_section}) are substituted by
    .format(). This pin matches the format-safety contract baked into
    test_creator_context_dataclass.py and is the regression guard for
    the pre-flight {end}/{start} bug class.
    """
    converted = _srt_to_seconds_format(srt_content)

    cap = max_srt_chars if max_srt_chars is not None else MAX_SRT_CHARS
    truncated = converted[:cap]
    if len(converted) > cap:
        truncated += "\n... [transcript truncated]"

    hint = editorial_hint.strip()
    system = _SYSTEM_RP + (f" {hint}" if hint else "")
    editorial_section = f"\n\nEDITORIAL GUIDANCE: {hint}" if hint else ""

    # T2.4 — soft target. When target_duration is set and positive, the
    # model gets one paragraph asking it to size the clip count × per-
    # clip length to land near that aggregate total. When 0 (default),
    # the slot resolves to empty string — same prompt as pre-T2.4.
    target_duration_section = (
        f"\n\nTARGET TOTAL DURATION: aim for approximately {int(target_duration)} seconds "
        f"of total output across all clips (sum of every clip's end - start). "
        f"This is a SOFT TARGET — the {int(min_sec)}-{int(max_sec)}s per-clip range "
        f"and the {output_count}-clip cap remain hard limits. Prefer fewer longer "
        f"clips or more shorter clips to land near the budget, whichever fits the content."
        if target_duration and int(target_duration) > 0
        else ""
    )

    # Strategic-1 — UP26 Pro Timeline Steering. When the operator
    # supplies clip_lock and/or clip_exclude ranges, render them as
    # explicit hard constraints in the prompt. Each range is a dict
    # {start_sec, end_sec} (floats, seconds). Empty list / None
    # suppresses the section — back-compat with all pre-Strategic-1
    # callers that don't pass the kwargs.
    # Phase B — platform guidance section.  Suppressed when target_platform
    # is empty (default) so the prompt is byte-for-byte identical to the
    # pre-Phase-B baseline for all callers that don't pass the kwarg.
    _plat_key = (target_platform or "").strip().lower()
    target_platform_section = (
        f"\n\n─── PLATFORM GUIDANCE ───\n{_PLATFORM_PROMPT_HINTS[_plat_key]}"
        if _plat_key in _PLATFORM_PROMPT_HINTS
        else ""
    )

    clip_lock_section = _format_range_section(
        clip_lock,
        header="HARD LOCKED RANGES",
        body=(
            "Each entry is a range the operator MARKED FOR INCLUSION. "
            "At LEAST one of your emitted clips MUST OVERLAP each "
            "locked range — drop other candidate clips before "
            "leaving a locked range uncovered."
        ),
    )
    clip_exclude_section = _format_range_section(
        clip_exclude,
        header="HARD EXCLUDED RANGES",
        body=(
            "Each entry is a range the operator MARKED FOR EXCLUSION. "
            "NONE of your emitted clips may overlap any excluded "
            "range — even partially. Drop candidate clips that touch "
            "an excluded range rather than truncating them at the "
            "boundary."
        ),
    )

    # Example end timestamp lands inside [min_sec, max_sec] so the JSON
    # example always demonstrates a compliant clip.
    example_end = round(45.2 + (min_sec + max_sec) / 2, 1)

    # S5 — creator preferences section. Builder suppresses to "" when
    # all hints are at default so existing prompt is byte-for-byte same.
    creator_preferences_section = _build_creator_preferences_section(
        video_type=video_type,
        hook_strength=hook_strength,
        ai_target_market=ai_target_market,
        subtitle_emphasis=subtitle_emphasis,
        multi_variant=multi_variant,
        structure_bias=structure_bias,
    )

    user = _USER_TEMPLATE_RP.format(
        language=language,
        srt_content=truncated,
        output_count=output_count,
        min_sec=int(min_sec),
        max_sec=int(max_sec),
        example_end=example_end,
        editorial_section=editorial_section,
        target_duration_section=target_duration_section,
        target_platform_section=target_platform_section,
        clip_lock_section=clip_lock_section,
        clip_exclude_section=clip_exclude_section,
        creator_preferences_section=creator_preferences_section,
    )
    return system, user


def _format_range_section(
    ranges: list[dict] | None,
    *,
    header: str,
    body: str,
) -> str:
    """Render a list of {start_sec, end_sec} dicts as a labelled
    prompt section. Returns "" when ranges is None / empty so the
    {clip_lock_section}/{clip_exclude_section} slots in the template
    suppress cleanly. Defensive: silently skips malformed entries
    rather than raising — Sacred Contract #3 spirit applies to
    AI-input assembly. Validity rule: start_sec >= 0 and
    end_sec > start_sec."""
    if not ranges:
        return ""
    try:
        lines: list[str] = []
        for r in ranges:
            if not isinstance(r, dict):
                continue
            try:
                start = float(r.get("start_sec"))
                end = float(r.get("end_sec"))
            except (TypeError, ValueError):
                continue
            if start < 0 or end <= start:
                continue
            lines.append(f"  - [{start:.1f}s, {end:.1f}s]")
        if not lines:
            return ""
        return f"\n\n{header}:\n{body}\n" + "\n".join(lines)
    except Exception:
        return ""

