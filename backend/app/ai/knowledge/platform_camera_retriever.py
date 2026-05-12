"""
platform_camera_retriever.py — Phase 55C Platform Camera Intelligence.

Retrieves camera-specific platform and creator-archetype knowledge from
knowledge/platforms/ and builds advisory platform_camera_context metadata.

Wraps the Phase 55A platform knowledge loader; filters to items that carry
camera domain guidance, then merges and ranks the result.

Public API:
    retrieve_platform_camera_knowledge(platform, creator_type, tags, base_path, max_results)
        -> dict  ({"available", "platform", "creator_type", "matches", "confidence", "reasoning"})
    build_platform_camera_context(platform, creator_type, base_path)
        -> dict  ({"platform_camera_context": {...}})

Safety contract:
  - Local knowledge only: no internet, no subprocess, no cloud API
  - Never mutates motion_crop, tracking config, camera behavior, or FFmpeg
  - Never raises — fallback-safe
  - Deterministic: exact dual-match first, then platform-only, then creator_type-only, alpha
  - Bounded: max_results clamped [1, 10]
  - Advisory only: guidance fields are informational metadata, never execution commands
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.ai.knowledge.platform_knowledge_loader import load_platform_knowledge
from app.ai.knowledge.platform_knowledge_schema import AIPlatformKnowledgeItem

logger = logging.getLogger("app.ai.knowledge.platform_camera_retriever")

_MAX_RESULTS_BOUND = 10
_MIN_RESULTS_BOUND = 1
_MAX_REASONING_LINES = 5

# Guard: camera guidance keys that are safe to surface in metadata
_SAFE_GUIDANCE_KEYS = frozenset({
    "motion_energy", "stability_priority", "jitter_sensitivity",
    "subject_continuity", "deadzone_bias", "crop_aggressiveness_guidance",
    "smoothness_priority", "overreactive_tracking_risk", "anti_jitter_mode",
    "subject_hold_duration",
})

# Execution-forbidden keys must not appear in any output dict
_FORBIDDEN_KEYS = frozenset({
    "ffmpeg_args", "render_command", "subtitle_timing", "motion_crop",
    "tracking_config", "clip_boundaries", "playback_speed", "subprocess",
    "executable", "python_code", "shell", "transcript", "hook_rewrite",
    "crop_coordinates",
})


def retrieve_platform_camera_knowledge(
    platform: str = "",
    creator_type: str = "",
    tags: Optional[List[str]] = None,
    base_path: Any = None,
    max_results: int = 3,
) -> dict:
    """Retrieve camera-domain platform knowledge by platform and/or creator_type.

    Args:
        platform:     Platform identifier ("tiktok", "youtube_shorts", etc.)
        creator_type: Creator archetype ("podcast", "educational", etc.)
        tags:         Optional camera-specific tag filter (any-match).
        base_path:    Override for knowledge/platforms/ directory.
        max_results:  Max items returned (clamped 1–10).

    Returns:
        dict with keys: available, platform, creator_type, matches, confidence,
        reasoning, warnings.
        Always non-None. Never raises.
    """
    try:
        return _retrieve(platform, creator_type, tags, base_path, max_results)
    except Exception as exc:
        logger.debug("platform_camera_retrieval_error: %s", exc)
        return _fallback_retrieval(platform, creator_type)


def build_platform_camera_context(
    platform: str = "",
    creator_type: str = "",
    base_path: Any = None,
) -> dict:
    """Build platform_camera_context metadata dict for the edit plan. Never raises.

    Returns {"platform_camera_context": {...}} always.
    Fallback returns available=False context when no matching knowledge exists.

    Advisory only — context is metadata, never alters camera execution.
    """
    try:
        return _build_context(platform, creator_type, base_path)
    except Exception as exc:
        logger.debug("platform_camera_context_build_error: %s", exc)
        return {"platform_camera_context": _fallback_ctx(platform, creator_type)}


# ---------------------------------------------------------------------------
# Internal retrieval
# ---------------------------------------------------------------------------

def _retrieve(
    platform: str,
    creator_type: str,
    tags: Optional[List[str]],
    base_path: Any,
    max_results: int,
) -> dict:
    plat = str(platform or "").strip().lower()
    ctype = str(creator_type or "").strip().lower()
    max_results = max(_MIN_RESULTS_BOUND, min(int(max_results), _MAX_RESULTS_BOUND))
    req_tags = [str(t).strip().lower() for t in (tags or []) if t]

    all_items = load_platform_knowledge(base_path)
    if not all_items:
        return _fallback_retrieval(plat, ctype)

    # Filter 1: camera domain
    camera_items = [i for i in all_items if "camera" in (i.domains or [])]
    if not camera_items:
        return _fallback_retrieval(plat, ctype)

    # Filter 2: platform and/or creator_type
    filtered = _filter_by_platform_and_type(camera_items, plat, ctype)
    if not filtered:
        return _fallback_retrieval(plat, ctype)

    # Filter 3: optional tag filter (any-match)
    if req_tags:
        tag_matched = [i for i in filtered if _tags_intersect(i.tags, req_tags)]
        if tag_matched:
            filtered = tag_matched

    # Deterministic sort: exact dual-match → platform-only → ctype-only → alpha
    filtered.sort(key=lambda x: _sort_key(x, plat, ctype))
    selected = filtered[:max_results]

    avg_conf = sum(i.confidence for i in selected) / len(selected)
    confidence = round(max(0.0, min(1.0, avg_conf)), 4)

    reasoning = _build_reasoning(selected, plat, ctype)
    matches_out = [_item_to_slim_dict(i) for i in selected]

    return {
        "available": True,
        "platform": plat,
        "creator_type": ctype,
        "matches": matches_out,
        "confidence": confidence,
        "reasoning": reasoning,
        "warnings": [],
    }


def _build_context(
    platform: str,
    creator_type: str,
    base_path: Any,
) -> dict:
    retrieval = _retrieve(platform, creator_type, None, base_path, max_results=3)

    if not retrieval.get("available"):
        return {"platform_camera_context": _fallback_ctx(platform, creator_type)}

    plat = retrieval["platform"]
    ctype = retrieval["creator_type"]
    matches = retrieval["matches"]
    confidence = retrieval["confidence"]
    reasoning = retrieval["reasoning"]

    # Merge camera guidance: later items set defaults, first item wins on conflicts
    merged: Dict[str, Any] = {}
    for m in reversed(matches):
        camera_g = (m.get("guidance") or {}).get("camera") or {}
        merged.update(camera_g)
    merged = _safe_guidance(merged)

    logger.debug(
        "platform_camera_context_built platform=%s creator_type=%s confidence=%.3f",
        plat, ctype, confidence,
    )

    return {
        "platform_camera_context": {
            "available": True,
            "platform": plat,
            "creator_type": ctype,
            "guidance": merged,
            "confidence": confidence,
            "reasoning": reasoning,
        }
    }


# ---------------------------------------------------------------------------
# Filtering helpers
# ---------------------------------------------------------------------------

def _filter_by_platform_and_type(
    items: List[AIPlatformKnowledgeItem],
    plat: str,
    ctype: str,
) -> List[AIPlatformKnowledgeItem]:
    if not plat and not ctype:
        return list(items)
    return [
        i for i in items
        if ((not plat) or i.platform == plat) and ((not ctype) or i.creator_type == ctype)
    ]


def _tags_intersect(item_tags: List[str], req_tags: List[str]) -> bool:
    item_set = {t.lower() for t in item_tags}
    return any(t in item_set for t in req_tags)


def _sort_key(item: AIPlatformKnowledgeItem, plat: str, ctype: str) -> tuple:
    exact_dual = (item.platform == plat and item.creator_type == ctype) if (plat and ctype) else False
    plat_match = (item.platform == plat) if plat else False
    ctype_match = (item.creator_type == ctype) if ctype else False

    if exact_dual:
        priority = 0
    elif plat_match:
        priority = 1
    elif ctype_match:
        priority = 2
    else:
        priority = 3
    return (priority, item.knowledge_id)


def _safe_guidance(guidance: dict) -> dict:
    """Return only safe camera guidance keys, strip any forbidden content."""
    return {k: v for k, v in guidance.items() if k in _SAFE_GUIDANCE_KEYS}


def _item_to_slim_dict(item: AIPlatformKnowledgeItem) -> dict:
    return {
        "knowledge_id": item.knowledge_id,
        "platform": item.platform,
        "creator_type": item.creator_type,
        "title": item.title,
        "guidance": dict(item.guidance),
        "confidence": item.confidence,
    }


# ---------------------------------------------------------------------------
# Reasoning builder
# ---------------------------------------------------------------------------

def _build_reasoning(
    items: List[AIPlatformKnowledgeItem],
    plat: str,
    ctype: str,
) -> List[str]:
    lines: List[str] = []
    for item in items:
        cam_guidance = (item.guidance or {}).get("camera", {})
        motion = cam_guidance.get("motion_energy", "")
        stability = cam_guidance.get("stability_priority", "")

        if item.platform and item.platform != "general" and item.creator_type:
            if motion and stability:
                lines.append(
                    f"{item.title} recommends {motion} motion energy with {stability} stability priority"
                )
            else:
                lines.append(f"{item.title} provides camera guidance for {item.platform} {item.creator_type}")
        elif item.platform and item.platform != "general":
            if motion:
                lines.append(f"{item.title} favors {motion} motion energy for {item.platform}")
            else:
                lines.append(f"{item.title} provides camera guidance for {item.platform}")
        elif item.creator_type:
            if stability:
                lines.append(f"{item.title} supports {stability} stability priority for {item.creator_type} creators")
            else:
                lines.append(f"{item.title} provides camera guidance for {item.creator_type} creators")
        else:
            lines.append(f"{item.title} provides platform camera guidance")
    return lines[:_MAX_REASONING_LINES]


# ---------------------------------------------------------------------------
# Fallback helpers
# ---------------------------------------------------------------------------

def _fallback_retrieval(platform: str, creator_type: str) -> dict:
    return {
        "available": False,
        "platform": str(platform or ""),
        "creator_type": str(creator_type or ""),
        "matches": [],
        "confidence": 0.0,
        "reasoning": [],
        "warnings": ["no_platform_camera_knowledge"],
    }


def _fallback_ctx(platform: str, creator_type: str) -> dict:
    return {
        "available": False,
        "platform": str(platform or ""),
        "creator_type": str(creator_type or ""),
        "guidance": {},
        "confidence": 0.0,
        "reasoning": [],
    }
