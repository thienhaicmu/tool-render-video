"""
hook_knowledge_retriever.py — Phase 53D hook / retention knowledge retrieval.

Retrieves curated hook, retention, curiosity, opening-sequence, and
market-specific hook expertise from the local knowledge registry.

Provides hook AI systems with expertise to improve reasoning, scoring,
and quality evaluation.

Supports:
  - hook quality intelligence (Phase 52C)
  - strategy reasoning (Phase 51)
  - unified quality score (Phase 52D)
  - market-aware hook optimization

Public API:
    retrieve_knowledge(domain, tags, creator_style, base_path, max_results)
        -> AIHookKnowledgePack
    build_hook_reasoning(pack, creator_style, hook_style)
        -> List[str]

Safety contract:
  - Local knowledge only: no internet, no subprocess, no network
  - Never mutates hook text, transcript, clip boundaries, or render pipeline
  - Never raises — fallback-safe
  - Deterministic: sort by creator_style priority then knowledge_id
  - Bounded: max_results clamped [1, 10]
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from app.ai.knowledge.knowledge_registry import load_category_knowledge
from app.ai.knowledge.hook_knowledge_schema import (
    AIHookKnowledgeItem,
    AIHookKnowledgePack,
)

logger = logging.getLogger("app.ai.knowledge.hook_retriever")

_MAX_RESULTS_BOUND = 10
_MIN_RESULTS_BOUND = 1
_MAX_HINTS = 8


def retrieve_knowledge(
    domain: str = "hook",
    tags: Optional[List[str]] = None,
    creator_style: Optional[str] = None,
    base_path: Any = None,
    max_results: int = 5,
) -> AIHookKnowledgePack:
    """Retrieve hook knowledge items by domain and tags.

    Args:
        domain:        Knowledge category to retrieve. Default "hook".
        tags:          Tag strings to filter by (any-match). None = no tag filter.
        creator_style: Optional creator style for prioritization.
        base_path:     Optional override for knowledge directory root.
        max_results:   Maximum items to return (clamped 1–10).

    Returns:
        AIHookKnowledgePack — always non-None, never raises.
        pack.available is False when no matching knowledge exists.
    """
    try:
        return _retrieve(domain, tags, creator_style, base_path, max_results)
    except Exception as exc:
        logger.debug("hook_knowledge_retrieval_error: %s", exc)
        return AIHookKnowledgePack(
            available=False,
            domain=str(domain or "hook"),
            warnings=[f"retrieval_error:{type(exc).__name__}"],
        )


def build_hook_reasoning(
    pack: AIHookKnowledgePack,
    creator_style: Optional[str] = None,
    hook_style: Optional[str] = None,
) -> List[str]:
    """Build reasoning hint strings from a hook knowledge pack.

    Combines pack reasoning_hints with optional creator/hook style context.
    Returns human-readable notes for hook quality reasoning.

    Never raises. Metadata-only — does not mutate any hook or render execution.
    """
    try:
        if not pack or not pack.available or not pack.items:
            return []

        hints: List[str] = list(pack.reasoning_hints)

        if creator_style and hook_style:
            for item in pack.items:
                if item.creator_style and item.creator_style == creator_style:
                    hints.append(
                        f"{hook_style} style aligned with {item.title.lower()} guidance."
                    )
                    break

        return hints[:_MAX_HINTS]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _retrieve(
    domain: str,
    tags: Optional[List[str]],
    creator_style: Optional[str],
    base_path: Any,
    max_results: int,
) -> AIHookKnowledgePack:
    domain = str(domain or "hook").strip() or "hook"
    max_results = max(_MIN_RESULTS_BOUND, min(int(max_results), _MAX_RESULTS_BOUND))
    requested_tags = [str(t).strip().lower() for t in (tags or []) if t]

    all_items = load_category_knowledge(domain, base_path)
    if not all_items:
        logger.debug("hook_knowledge_empty domain=%s", domain)
        return AIHookKnowledgePack(
            available=False,
            domain=domain,
            warnings=["no_hook_knowledge_available"],
        )

    # Tag-filter: any-match on lowercased item tags
    if requested_tags:
        matched = [
            item for item in all_items
            if _tags_intersect(item.tags, requested_tags)
        ]
    else:
        matched = list(all_items)

    if not matched:
        logger.debug(
            "hook_knowledge_no_match domain=%s tags=%s", domain, requested_tags
        )
        return AIHookKnowledgePack(
            available=False,
            domain=domain,
            matched_tags=requested_tags,
            warnings=["no_matching_hook_knowledge"],
        )

    # Deterministic ordering: creator_style matches first, then alphabetical by knowledge_id
    style = str(creator_style or "").strip()
    matched.sort(
        key=lambda x: (0 if (style and x.creator_style == style) else 1, x.knowledge_id)
    )

    selected = matched[:max_results]

    knowledge_items = [
        AIHookKnowledgeItem(
            knowledge_id=item.knowledge_id,
            title=item.title,
            description=item.description,
            tags=list(item.tags),
            hook_patterns=list(item.hook_patterns),
            retention_patterns=dict(item.retention_patterns),
            creator_style=item.creator_style,
        )
        for item in selected
    ]

    matched_tag_set: List[str] = sorted({
        t for item in selected
        for t in item.tags
        if not requested_tags or str(t).lower() in requested_tags
    })

    reasoning_hints = _build_hints(knowledge_items)

    logger.debug(
        "hook_knowledge_retrieved domain=%s tags=%s items=%d",
        domain, requested_tags, len(knowledge_items),
    )

    return AIHookKnowledgePack(
        available=True,
        domain=domain,
        items=knowledge_items,
        matched_tags=matched_tag_set,
        reasoning_hints=reasoning_hints,
        warnings=[],
    )


def _tags_intersect(item_tags: list, requested: list) -> bool:
    """Return True if any item tag (lowercased) appears in the requested set."""
    item_lower = {str(t).lower() for t in item_tags}
    return bool(item_lower.intersection(requested))


def _build_hints(items: List[AIHookKnowledgeItem]) -> List[str]:
    """Build concise reasoning hint strings from matched knowledge items."""
    hints: List[str] = []
    for item in items:
        if not item.title or not item.description:
            continue
        hint = f"{item.title}: {item.description}"
        if len(hint) > 200:
            hint = hint[:197] + "..."
        hints.append(hint)
    return hints
