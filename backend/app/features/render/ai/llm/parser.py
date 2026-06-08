"""
parser.py — Parse LLM RenderPlan response into a validated RenderPlan.

All parsing is defensive: never raises, returns None on any failure.
Caller treats None as signal to hard-fail the pipeline.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from app.domain.render_plan import (
    AudioPlan,
    CameraStrategy,
    ClipPlan,
    RenderPlan,
    SubtitlePolicy,
)

logger = logging.getLogger("app.render.llm_parser")

_INVALID_FS_CHARS = re.compile(r'[/\\:*?"<>|\t\n\r]')


def sanitize_clip_name(raw: str) -> str:
    """Keep natural name (spaces, Vietnamese chars OK), strip only FS-invalid chars."""
    clean = _INVALID_FS_CHARS.sub("", raw).strip()
    clean = re.sub(r" {2,}", " ", clean)[:80]
    return clean or "clip"


def _extract_json_array(raw: str) -> object:
    raw = raw.strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*([\[{].*?[\]}])\s*```", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError:
            pass
    return None


def parse_render_plan_response(
    raw: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
) -> Optional[RenderPlan]:
    """Parse the LLM's raw text response into a validated RenderPlan.

    Sprint 4.A (foundation for AI Director full RenderPlan). The
    function is intentionally permissive about the wire shape — three
    forms are normalised:

      1. Native RenderPlan: ``{"clips": [...], "subtitle_policy": {...},
         "camera_strategy": {...}, "audio_plan": {...},
         "overlays": [...], ...}``
      2. Wrapped: ``{"render_plan": {...native...}}`` so providers can
         emit a structured top-level key without colliding with
         conversational prose.
      3. Legacy segments-only: ``{"segments": [...]}`` — clips-only,
         every other sub-plan stays at its safe default. This shape is
         retained for backward compatibility with stored historical
         payloads (Sacred Contract #2); no live caller emits it post
         Sprint 4.H.

    Validation:
      - Each clip's ``(end - start)`` must land in [min_sec, max_sec].
      - Each clip must satisfy ``start >= 0`` and
        ``end <= video_duration + 1.0`` (legacy parser's bounds rule).
      - Clips that violate either rule are silently dropped.
      - When NO valid clips remain (or zero in the payload to begin
        with) the function returns ``None`` — Sprint 4.D treats that
        as the cue to fall back to the Sprint 2.2 builder shim.
      - Top-level sub-plans that are malformed (wrong type, garbage
        values) fall back to default sub-dataclasses via
        ``RenderPlan.from_json``'s defensive deserialiser — they do
        NOT cause the whole parse to return None.

    Sacred Contract #3: never raises. Any unexpected exception is
    logged and turned into ``None``.
    """
    try:
        data = _extract_json_array(raw)
        if not isinstance(data, dict):
            logger.warning(
                "llm_parser: parse_render_plan_response expected object, got %s — raw preview: %r",
                type(data).__name__, raw[:300],
            )
            return None

        normalised = _normalise_render_plan_shape(data)
        if normalised is None:
            return None

        # Run clip-level validation BEFORE handing to RenderPlan.from_json
        # so that out-of-bounds entries don't poison the resulting plan.
        clips_data = normalised.get("clips") if isinstance(normalised.get("clips"), list) else []
        valid_clip_dicts = _filter_and_score_clip_dicts(
            clips_data,
            min_sec=min_sec,
            max_sec=max_sec,
            video_duration=video_duration,
        )

        if not valid_clip_dicts:
            logger.warning(
                "llm_parser: parse_render_plan_response: 0 valid clips out of %d "
                "(min_sec=%.0f max_sec=%.0f video_dur=%.0f)",
                len(clips_data), min_sec, max_sec, video_duration,
            )
            return None

        # Sort by score descending and truncate to the requested output
        # count (this is the rank source consumed by pipeline_ranking.py
        # via _resolve_rank_from_plan).
        valid_clip_dicts.sort(key=lambda c: c.get("score", 0.0), reverse=True)
        valid_clip_dicts = valid_clip_dicts[: max(1, int(output_count))]

        # Re-tag ranks AFTER sort/truncate so they are 1..N and stable.
        for rank, clip in enumerate(valid_clip_dicts, start=1):
            clip["rank"] = rank

        normalised["clips"] = valid_clip_dicts

        try:
            plan = RenderPlan.from_json(json.dumps(normalised))
        except Exception as exc:
            logger.warning("llm_parser: RenderPlan.from_json failed: %s", exc)
            return None
        if plan is None:
            return None

        # RenderPlan.from_json is itself defensive enough that this is
        # belt-and-braces — but we want a strict "empty plan === None"
        # contract from this entry point.
        if not plan.clips:
            return None
        return plan

    except Exception as exc:
        logger.warning("llm_parser: parse_render_plan_response unexpected error — %s", exc, exc_info=True)
        return None


# â"€â"€ Shape normaliser â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def _normalise_render_plan_shape(data: dict) -> Optional[dict]:
    """Map any of the three accepted shapes onto a native RenderPlan
    dict. Returns None when no recognisable shape is found.
    """
    # Shape 2: wrapped — peel the top-level key.
    if isinstance(data.get("render_plan"), dict):
        inner = data["render_plan"]
        if isinstance(inner, dict):
            return _native_or_legacy(inner)

    return _native_or_legacy(data)


def _native_or_legacy(data: dict) -> Optional[dict]:
    """Decide whether `data` is the native shape (`clips` key) or the
    legacy shape (`segments` key), and synthesise the native shape."""
    if isinstance(data.get("clips"), list):
        # Already native — pass through, but also accept LLMSegment-
        # style keys inside each clip entry so providers can emit
        # either {"clips":[{start,end,score,...}]} (already ClipPlan-ish)
        # or {"clips":[{start,end,viral_score,hook_score,...}]} (still
        # LLMSegment shape but under a "clips" key).
        return data
    if isinstance(data.get("segments"), list):
        # Legacy — convert each segment to a ClipPlan-shaped dict and
        # leave every other sub-plan at its default.
        return {
            "clips": [_segment_to_clip_dict(s) for s in data["segments"] if isinstance(s, dict)],
        }
    return None


def _segment_to_clip_dict(seg: dict) -> dict:
    """Translate an LLMSegment-shaped dict into a ClipPlan-shaped dict.

    Field mapping mirrors what the Sprint 2.2 builder shim produces in
    `render_plan_builder._build_clips`. Score fields are passed through
    as-is — `_filter_and_score_clip_dicts` later coerces them to [0,1].
    """
    return {
        "start": seg.get("start"),
        "end": seg.get("end"),
        "score": seg.get("score", seg.get("viral_score", 0.0)),
        "clip_name": seg.get("clip_name", ""),
        "title": seg.get("title", ""),
        "reason": seg.get("reason", ""),
        "hook_type": seg.get("hook_type", ""),
        "content_type": seg.get("content_type", ""),
        "subtitle_style": seg.get("subtitle_style", ""),
        "viral_score": seg.get("viral_score", 0.0),
        "hook_score": seg.get("hook_score", 0.0),
        "retention_score": seg.get("retention_score", 0.0),
        "speech_density": seg.get("speech_density", 0.0),
        "duration_fit": seg.get("duration_fit", 0.0),
        "cover_offset_ratio": seg.get("cover_offset_ratio", 0.0),
    }


# â"€â"€ Per-clip validation â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€â"€


def _filter_and_score_clip_dicts(
    clips: list,
    *,
    min_sec: float,
    max_sec: float,
    video_duration: float,
) -> list[dict]:
    """Keep only clips whose duration sits in [min_sec, max_sec] and
    whose start/end land inside the video. Returns a fresh list of
    sanitised dicts ready for ``RenderPlan.from_json``."""
    out: list[dict] = []
    for entry in clips:
        if not isinstance(entry, dict):
            continue
        try:
            start = float(entry.get("start", 0.0))
            end = float(entry.get("end", 0.0))
        except (TypeError, ValueError):
            continue
        duration = end - start
        if not (min_sec <= duration <= max_sec):
            logger.debug(
                "llm_parser: clip %.1f-%.1f rejected (dur=%.1fs out of [%.0f,%.0f])",
                start, end, duration, min_sec, max_sec,
            )
            continue
        if start < 0 or (video_duration > 0 and end > video_duration + 1.0):
            logger.debug(
                "llm_parser: clip %.1f-%.1f out of bounds (video=%.1fs)",
                start, end, video_duration,
            )
            continue
        # Sanitise score → [0,1] so RenderPlan.from_json doesn't have to
        # coerce. Defaults to 0.5 when missing (same as parse_item).
        try:
            score = float(entry.get("score", 0.5))
        except (TypeError, ValueError):
            score = 0.5
        score = max(0.0, min(1.0, score))

        out.append({
            **entry,
            "start": start,
            "end": end,
            "score": score,
            # Normalise the clip_name through the same sanitiser the
            # segment parser uses — keeps filesystem invariants for
            # downstream code (no slashes / nulls in output names).
            "clip_name": sanitize_clip_name(
                str(entry.get("clip_name") or entry.get("title") or "clip")
            ),
        })
    return out

