"""
parser.py â€” Parse LLM segment-selection response into LLMSegment list.

All parsing is defensive: never raises, returns None on any failure.
Caller treats None as signal to hard-fail the pipeline.

Sprint 4.A â€” adds `parse_render_plan_response()` alongside the existing
`parse_segment_response()`. Both functions co-exist while the
orchestrator gates the new path behind a flag. Phase 4.D will wire the
new parser; phase 4.H will retire the segment-only path.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Optional

from app.domain.render_plan import (
    AudioPlan,
    CameraStrategy,
    ClipPlan,
    OutputConfig,
    RenderPlan,
    SubtitlePolicy,
)

logger = logging.getLogger("app.render.llm_parser")

_INVALID_FS_CHARS = re.compile(r'[/\\:*?"<>|\t\n\r]')


@dataclass
class LLMSegment:
    start: float      # seconds
    end: float        # seconds
    score: float      # 0.0â€“1.0
    clip_name: str    # natural name used as output filename stem
    title: str        # display title
    reason: str       # model's explanation
    # RenderPlan extended fields â€” populated when LLM returns the full schema
    hook_type: str = ""            # question|reveal|contrast|humor|emotion|statement
    content_type: str = ""         # interview|vlog|tutorial|commentary|montage|gaming
    subtitle_style: str = ""       # viral|clean|story|gaming
    viral_score: float = 0.0       # 0.0â€“1.0 shareability
    hook_score: float = 0.0        # 0.0â€“1.0 first-3s grab strength
    retention_score: float = 0.0   # 0.0â€“1.0 predicted watch-through rate
    speech_density: float = 0.0    # 1.0=dense dialogue, 0.0=silence/visuals
    duration_fit: float = 0.0      # 1.0=ideal length for target short-form
    cover_offset_ratio: float = 0.0  # thumbnail moment as fraction of clip (0=absent)


# Sprint 7.6 LITE (2026-06-05): GroqSegment = LLMSegment backward-compat
# alias deleted. Zero callers verified across backend/ + tests/ + frontend/
# at audit time. See docs/review/SPRINT_7_6_LITE_GROQSEGMENT_ALIAS_2026-06-05.md.


def sanitize_clip_name(raw: str) -> str:
    """Keep natural name (spaces, Vietnamese chars OK), strip only FS-invalid chars."""
    clean = _INVALID_FS_CHARS.sub("", raw).strip()
    clean = re.sub(r" {2,}", " ", clean)[:80]
    return clean or "clip"


def parse_segment_response(
    raw: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
) -> Optional[list[LLMSegment]]:
    """
    Parse LLM raw text response into validated LLMSegment list.

    Returns None only when no valid segments can be parsed at all.
    When the LLM returns fewer valid segments than requested, returns the
    valid subset (lenient â€” better some clips than render failure).
    """
    try:
        data = _extract_json_array(raw)
        if isinstance(data, dict):
            for _key in ("segments", "clips", "items", "results", "data"):
                if isinstance(data.get(_key), list):
                    data = data[_key]
                    break
        if not isinstance(data, list):
            logger.warning(
                "llm_parser: expected list (or object with 'segments' key), "
                "got %s â€” raw preview: %r",
                type(data).__name__, raw[:300],
            )
            return None

        segments: list[LLMSegment] = []
        rejected = 0
        for item in data:
            seg = _parse_item(item, min_sec, max_sec, video_duration)
            if seg is not None:
                segments.append(seg)
            else:
                rejected += 1

        # Second pass: LLM ignored duration constraints â€” accept any segment with
        # positive duration rather than failing the entire render.
        if not segments and rejected > 0:
            logger.warning(
                "llm_parser: 0 valid segments with strict bounds "
                "(min_sec=%.0f max_sec=%.0f) â€” retrying without duration filter",
                min_sec, max_sec,
            )
            for item in data:
                seg = _parse_item(item, min_sec=1.0, max_sec=86400, video_duration=video_duration)
                if seg is not None:
                    segments.append(seg)

        if not segments:
            logger.warning(
                "llm_parser: 0 valid segments out of %d returned "
                "(min_sec=%.0f max_sec=%.0f video_dur=%.0f) â€” raw preview: %r",
                len(data), min_sec, max_sec, video_duration, raw[:300],
            )
            return None

        segments.sort(key=lambda s: s.score, reverse=True)
        result = segments[:output_count]

        if len(result) < output_count:
            logger.info(
                "llm_parser: %d/%d valid segments (%d rejected) â€” proceeding with subset",
                len(result), output_count, rejected,
            )

        return result

    except Exception as exc:
        logger.warning("llm_parser: unexpected error â€” %s", exc, exc_info=True)
        return None


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


def _parse_item(
    item: object,
    min_sec: float,
    max_sec: float,
    video_duration: float,
) -> Optional[LLMSegment]:
    if not isinstance(item, dict):
        return None
    try:
        start = float(item["start"])
        end   = float(item["end"])
    except (KeyError, TypeError, ValueError):
        return None

    duration = end - start
    if not (min_sec <= duration <= max_sec):
        logger.debug("llm_parser: segment %.1f-%.1f rejected (dur=%.1fs)", start, end, duration)
        return None
    if start < 0 or (video_duration > 0 and end > video_duration + 1.0):
        logger.debug("llm_parser: segment %.1f-%.1f out of bounds (video=%.1fs)", start, end, video_duration)
        return None

    raw_name  = str(item.get("clip_name") or item.get("title") or "clip")
    raw_title = str(item.get("title")     or raw_name)
    score     = float(item.get("score", 0.5))
    score     = max(0.0, min(1.0, score))

    # Defensive parse of RenderPlan extended fields â€” any bad value falls back to safe defaults
    try:
        _hook_type    = str(item.get("hook_type")    or "").strip()[:30]
        _content_type = str(item.get("content_type") or "").strip()[:30]
        _sub_style    = str(item.get("subtitle_style") or "").strip()[:20]
        def _fs(key: str, fallback: float) -> float:
            v = item.get(key)
            return max(0.0, min(1.0, float(v))) if v is not None else fallback
        _viral_score    = _fs("viral_score",       score)
        _hook_score     = _fs("hook_score",        score)
        _ret_score      = _fs("retention_score",   score)
        _speech_density = _fs("speech_density",    0.0)
        _dur_fit        = _fs("duration_fit",       score)
        _cover_ratio    = _fs("cover_offset_ratio", 0.0)
    except Exception:
        _hook_type = _content_type = _sub_style = ""
        _viral_score = _hook_score = _ret_score = _dur_fit = score
        _speech_density = _cover_ratio = 0.0

    return LLMSegment(
        start=start,
        end=end,
        score=score,
        clip_name=sanitize_clip_name(raw_name),
        title=raw_title.strip()[:120],
        reason=str(item.get("reason", "")).strip()[:300],
        hook_type=_hook_type,
        content_type=_content_type,
        subtitle_style=_sub_style,
        viral_score=_viral_score,
        hook_score=_hook_score,
        retention_score=_ret_score,
        speech_density=_speech_density,
        duration_fit=_dur_fit,
        cover_offset_ratio=_cover_ratio,
    )


# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# Sprint 4.A â€” RenderPlan parser (dual-mode alongside parse_segment_response)
# â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def parse_render_plan_response(
    raw: str,
    output_count: int,
    min_sec: float,
    max_sec: float,
    video_duration: float,
) -> Optional[RenderPlan]:
    """Parse the LLM's raw text response into a validated RenderPlan.

    Sprint 4.A (foundation for AI Director full RenderPlan). The
    function is intentionally permissive about the wire shape â€” three
    forms are normalised:

      1. Native RenderPlan: ``{"clips": [...], "subtitle_policy": {...},
         "camera_strategy": {...}, "audio_plan": {...},
         "output_config": {...}, "overlays": [...], ...}``
      2. Wrapped: ``{"render_plan": {...native...}}`` so providers can
         emit a structured top-level key without colliding with
         conversational prose.
      3. Legacy segments-only: ``{"segments": [...]}`` â€” clips-only,
         every other sub-plan stays at its safe default. This is the
         exact same payload shape ``parse_segment_response`` accepts,
         so a Sprint 4.D dual-path provider can hand the same response
         to either parser without rewriting the prompt.

    Validation:
      - Each clip's ``(end - start)`` must land in [min_sec, max_sec].
      - Each clip must satisfy ``start >= 0`` and
        ``end <= video_duration + 1.0`` (legacy parser's bounds rule).
      - Clips that violate either rule are silently dropped.
      - When NO valid clips remain (or zero in the payload to begin
        with) the function returns ``None`` â€” Sprint 4.D treats that
        as the cue to fall back to the Sprint 2.2 builder shim.
      - Top-level sub-plans that are malformed (wrong type, garbage
        values) fall back to default sub-dataclasses via
        ``RenderPlan.from_json``'s defensive deserialiser â€” they do
        NOT cause the whole parse to return None.

    Sacred Contract #3: never raises. Any unexpected exception is
    logged and turned into ``None``.
    """
    try:
        data = _extract_json_array(raw)
        if not isinstance(data, dict):
            logger.warning(
                "llm_parser: parse_render_plan_response expected object, got %s â€” raw preview: %r",
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

        # Sort by score descending (mirrors parse_segment_response) and
        # truncate to the requested output count.
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
        # belt-and-braces â€” but we want a strict "empty plan === None"
        # contract from this entry point.
        if not plan.clips:
            return None
        return plan

    except Exception as exc:
        logger.warning("llm_parser: parse_render_plan_response unexpected error â€” %s", exc, exc_info=True)
        return None


# â”€â”€ Shape normaliser â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


def _normalise_render_plan_shape(data: dict) -> Optional[dict]:
    """Map any of the three accepted shapes onto a native RenderPlan
    dict. Returns None when no recognisable shape is found.
    """
    # Shape 2: wrapped â€” peel the top-level key.
    if isinstance(data.get("render_plan"), dict):
        inner = data["render_plan"]
        if isinstance(inner, dict):
            return _native_or_legacy(inner)

    return _native_or_legacy(data)


def _native_or_legacy(data: dict) -> Optional[dict]:
    """Decide whether `data` is the native shape (`clips` key) or the
    legacy shape (`segments` key), and synthesise the native shape."""
    if isinstance(data.get("clips"), list):
        # Already native â€” pass through, but also accept LLMSegment-
        # style keys inside each clip entry so providers can emit
        # either {"clips":[{start,end,score,...}]} (already ClipPlan-ish)
        # or {"clips":[{start,end,viral_score,hook_score,...}]} (still
        # LLMSegment shape but under a "clips" key).
        return data
    if isinstance(data.get("segments"), list):
        # Legacy â€” convert each segment to a ClipPlan-shaped dict and
        # leave every other sub-plan at its default.
        return {
            "clips": [_segment_to_clip_dict(s) for s in data["segments"] if isinstance(s, dict)],
        }
    return None


def _segment_to_clip_dict(seg: dict) -> dict:
    """Translate an LLMSegment-shaped dict into a ClipPlan-shaped dict.

    Field mapping mirrors what the Sprint 2.2 builder shim produces in
    `render_plan_builder._build_clips`. Score fields are passed through
    as-is â€” `_filter_and_score_clip_dicts` later coerces them to [0,1].
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


# â”€â”€ Per-clip validation â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€


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
        # Sanitise score â†’ [0,1] so RenderPlan.from_json doesn't have to
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
            # segment parser uses â€” keeps filesystem invariants for
            # downstream code (no slashes / nulls in output names).
            "clip_name": sanitize_clip_name(
                str(entry.get("clip_name") or entry.get("title") or "clip")
            ),
        })
    return out

