"""
platform_knowledge_retriever.py — Phase 55A platform knowledge retrieval.

Retrieves curated platform and creator-archetype knowledge from the local
knowledge/platforms/ directory.

Provides platform-aware AI systems with structured guidance to improve
reasoning, recommendation, and quality evaluation — without touching any
render execution path.

Public API:
    retrieve_platform_knowledge(platform, creator_type, base_path, max_results)
        -> AIPlatformKnowledgePack
    build_platform_context(platform, creator_type, base_path)
        -> dict   ({"platform_context": {...}})

Safety contract:
  - Local knowledge only: no internet, no subprocess, no network
  - Never mutates rendering, subtitle timing, motion_crop, or FFmpeg
  - Never raises — fallback-safe
  - Deterministic: exact-match first, then by knowledge_id alphabetically
  - Bounded: max_results clamped [1, 10]
  - Advisory only: metadata informs, never executes
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.ai.knowledge.platform_knowledge_loader import load_platform_knowledge
from app.ai.knowledge.platform_knowledge_schema import (
    AIPlatformKnowledgeItem,
    AIPlatformKnowledgePack,
    AIPlatformContext,
)

logger = logging.getLogger("app.ai.knowledge.platform_retriever")

_MAX_RESULTS_BOUND = 10
_MIN_RESULTS_BOUND = 1
_MAX_REASONING_LINES = 5
_CONTEXT_CONFIDENCE_FLOOR = 0.0
_CONTEXT_CONFIDENCE_CAP = 1.0


def retrieve_platform_knowledge(
    platform: str = "",
    creator_type: str = "",
    base_path: Any = None,
    max_results: int = 5,
) -> AIPlatformKnowledgePack:
    """Retrieve platform knowledge items by platform and/or creator_type.

    Args:
        platform:     Platform identifier (e.g. "tiktok", "youtube_shorts").
                      Empty string = no platform filter (all platforms).
        creator_type: Creator archetype (e.g. "podcast", "educational").
                      Empty string = no creator_type filter.
        base_path:    Optional override for knowledge/platforms/ directory.
        max_results:  Maximum items returned (clamped 1–10).

    Returns:
        AIPlatformKnowledgePack — always non-None, never raises.
        pack.available is False when no matching knowledge exists.

    Matching rules:
        1. If both platform and creator_type given: prefer exact dual-match,
           then platform-only match, then creator_type-only match.
        2. If only platform given: any item with that platform.
        3. If only creator_type given: any item with that creator_type.
        4. If neither given: all items (up to max_results).

    Sort order (deterministic):
        - Exact dual-match (platform AND creator_type) first
        - Platform-only match second
        - Creator_type-only match third
        - Tiebreaker: alphabetical by knowledge_id
    """
    try:
        return _retrieve(platform, creator_type, base_path, max_results)
    except Exception as exc:
        logger.debug("platform_knowledge_retrieval_error: %s", exc)
        return AIPlatformKnowledgePack(
            available=False,
            platform=str(platform or ""),
            creator_type=str(creator_type or ""),
            warnings=[f"retrieval_error:{type(exc).__name__}"],
        )


def build_platform_context(
    platform: str = "",
    creator_type: str = "",
    base_path: Any = None,
) -> dict:
    """Build platform context metadata dict for the edit plan. Never raises.

    Returns {"platform_context": {...}} always.
    Fallback returns available=False context when no knowledge is found.
    Advisory only — no render mutation.
    """
    try:
        return _build_context(platform, creator_type, base_path)
    except Exception as exc:
        logger.debug("platform_context_build_error: %s", exc)
        return {"platform_context": _fallback_context(platform, creator_type)}


# ---------------------------------------------------------------------------
# Internal retrieval engine
# ---------------------------------------------------------------------------

def _retrieve(
    platform: str,
    creator_type: str,
    base_path: Any,
    max_results: int,
) -> AIPlatformKnowledgePack:
    plat = str(platform or "").strip().lower()
    ctype = str(creator_type or "").strip().lower()
    max_results = max(_MIN_RESULTS_BOUND, min(int(max_results), _MAX_RESULTS_BOUND))

    all_items = load_platform_knowledge(base_path)
    if not all_items:
        logger.debug("platform_knowledge_empty")
        return AIPlatformKnowledgePack(
            available=False,
            platform=plat,
            creator_type=ctype,
            warnings=["no_platform_knowledge_available"],
        )

    # Filter: apply platform and/or creator_type constraints
    filtered = _filter_items(all_items, plat, ctype)

    if not filtered:
        logger.debug(
            "platform_knowledge_no_match platform=%s creator_type=%s", plat, ctype
        )
        return AIPlatformKnowledgePack(
            available=False,
            platform=plat,
            creator_type=ctype,
            warnings=["no_matching_platform_knowledge"],
        )

    # Deterministic sort: exact dual-match → platform-only → creator_type-only → alpha
    filtered.sort(key=lambda x: _sort_key(x, plat, ctype))

    selected = filtered[:max_results]

    # Aggregate confidence: mean of selected items, clamped
    avg_conf = sum(i.confidence for i in selected) / len(selected)
    confidence = round(
        max(_CONTEXT_CONFIDENCE_FLOOR, min(_CONTEXT_CONFIDENCE_CAP, avg_conf)), 4
    )

    reasoning = _build_reasoning(selected, plat, ctype)

    logger.debug(
        "platform_knowledge_retrieved platform=%s creator_type=%s matches=%d confidence=%.3f",
        plat, ctype, len(selected), confidence,
    )

    return AIPlatformKnowledgePack(
        available=True,
        platform=plat,
        creator_type=ctype,
        matches=selected,
        confidence=confidence,
        reasoning=reasoning,
    )


def _filter_items(
    items: List[AIPlatformKnowledgeItem],
    plat: str,
    ctype: str,
) -> List[AIPlatformKnowledgeItem]:
    """Filter items by platform and/or creator_type."""
    if not plat and not ctype:
        return list(items)

    result = []
    for item in items:
        plat_match = (not plat) or item.platform == plat
        ctype_match = (not ctype) or item.creator_type == ctype
        if plat_match and ctype_match:
            result.append(item)
    return result


def _sort_key(
    item: AIPlatformKnowledgeItem,
    plat: str,
    ctype: str,
) -> tuple:
    """Deterministic sort key: exact dual-match first, then alpha knowledge_id."""
    exact_dual = (item.platform == plat and item.creator_type == ctype) if (plat and ctype) else False
    plat_match = (item.platform == plat) if plat else False
    ctype_match = (item.creator_type == ctype) if ctype else False

    # Priority: 0=exact dual, 1=plat-only, 2=ctype-only, 3=other
    if exact_dual:
        priority = 0
    elif plat_match:
        priority = 1
    elif ctype_match:
        priority = 2
    else:
        priority = 3

    return (priority, item.knowledge_id)


def _build_reasoning(
    items: List[AIPlatformKnowledgeItem],
    plat: str,
    ctype: str,
) -> List[str]:
    """Build creator-facing reasoning strings for the pack."""
    lines: List[str] = []
    for item in items:
        if item.platform and item.creator_type:
            lines.append(
                f"Matched {item.title} guidance for {item.platform} {item.creator_type} content"
            )
        elif item.platform:
            lines.append(f"Matched {item.title} platform guidance for {item.platform}")
        elif item.creator_type:
            lines.append(f"Matched {item.title} creator archetype guidance for {item.creator_type}")
        else:
            lines.append(f"Matched {item.title} platform knowledge")
    return lines[:_MAX_REASONING_LINES]


# ---------------------------------------------------------------------------
# Context builder (for AIEditPlan.platform_context)
# ---------------------------------------------------------------------------

def _build_context(
    platform: str,
    creator_type: str,
    base_path: Any,
) -> dict:
    """Build platform_context dict from retrieved knowledge."""
    pack = _retrieve(platform, creator_type, base_path, max_results=3)

    ctx = AIPlatformContext(
        available=pack.available,
        platform=pack.platform,
        creator_type=pack.creator_type,
        matches=[m.to_dict() for m in pack.matches],
        confidence=pack.confidence,
        reasoning=list(pack.reasoning),
    )
    return {"platform_context": ctx.to_dict()}


def _fallback_context(platform: str, creator_type: str) -> dict:
    return AIPlatformContext(
        available=False,
        platform=str(platform or ""),
        creator_type=str(creator_type or ""),
    ).to_dict()
