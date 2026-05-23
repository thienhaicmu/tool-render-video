"""
render_mapper.py — Maps retrieved local knowledge items to validated render execution hints.

No render_pipeline imports. No cloud AI. No external API calls.
Deterministic: same input always produces same output.

Public API:
    map_knowledge_to_execution_hints(retrieved_knowledge, existing_hints=None) -> AIValidationResult
"""
from __future__ import annotations

import logging
from typing import Optional

from app.ai.contracts import AIValidationResult, RenderExecutionHints
from app.ai.validators import validate_execution_hints

logger = logging.getLogger(__name__)

# ── Pacing mappings ────────────────────────────────────────────────────────────
# Maps render_usage.pacing → (cut_interval_min, cut_interval_max)
_PACING_MAP: dict[str, tuple[float, float]] = {
    "fast":        (2.0, 4.0),
    "medium_fast": (3.0, 5.0),
    "medium":      (4.0, 7.0),
    "slow":        (6.0, 10.0),
}

# ── Subtitle emphasis mappings ─────────────────────────────────────────────────
# Maps render_usage.subtitle_emphasis → subtitle_emphasis_style
_SUBTITLE_MAP: dict[str, str] = {
    "high_emphasis":              "strong",
    "strong":                     "strong",
    "highlight_problem_keyword":  "strong",
    "medium_emphasis":            "medium",
    "medium":                     "medium",
    "subtle":                     "subtle",
}


# ── Public API ─────────────────────────────────────────────────────────────────

def map_knowledge_to_execution_hints(
    retrieved_knowledge: list[dict],
    existing_hints: Optional[dict] = None,
) -> AIValidationResult:
    """Map retrieved knowledge items to validated render execution hints.

    Sort items by weight descending before mapping. The highest-weight item
    that has a given render_usage field wins.

    Always calls validate_execution_hints() before returning — result is always
    a safe, validated AIValidationResult.

    Args:
        retrieved_knowledge: list of knowledge item dicts (from KnowledgeIndex.query())
        existing_hints: optional dict of pre-existing hints (currently unused; reserved
                        for future hint merging)

    Returns:
        AIValidationResult with validated RenderExecutionHints and fixup/warning lists.
        Never raises — returns empty/safe result on any error.
    """
    try:
        return _do_map(retrieved_knowledge or [], existing_hints)
    except Exception as exc:
        logger.warning("render_mapper: unexpected error: %s", exc)
        return AIValidationResult(
            ok=True,
            hints=RenderExecutionHints(),
            warnings=[f"mapper_error:{type(exc).__name__}"],
        )


# ── Internal helpers ───────────────────────────────────────────────────────────

def _do_map(knowledge: list[dict], existing_hints: Optional[dict]) -> AIValidationResult:
    """Core mapping logic. May raise — wrapped by map_knowledge_to_execution_hints."""
    if not knowledge:
        return validate_execution_hints({})

    # Sort by weight descending (highest-confidence item first)
    try:
        sorted_knowledge = sorted(
            knowledge,
            key=lambda item: float(item.get("weight") or 0.0),
            reverse=True,
        )
    except Exception:
        sorted_knowledge = list(knowledge)

    raw: dict = {}
    source_ids: list[str] = []

    # Track which fields have been resolved (first match wins per field)
    _pacing_resolved = False
    _subtitle_resolved = False
    _hook_resolved = False

    for item in sorted_knowledge:
        if not isinstance(item, dict):
            continue

        render_usage = item.get("render_usage") or {}
        if not isinstance(render_usage, dict):
            render_usage = {}

        item_id = item.get("id") or ""
        contributed = False

        # ── Pacing mapping ────────────────────────────────────────────────────
        if not _pacing_resolved:
            pacing_val = render_usage.get("pacing")
            if pacing_val is not None:
                mapped = _PACING_MAP.get(str(pacing_val))
                if mapped is not None:
                    raw["cut_interval_min"] = mapped[0]
                    raw["cut_interval_max"] = mapped[1]
                    _pacing_resolved = True
                    contributed = True

        # ── Subtitle emphasis mapping ──────────────────────────────────────────
        if not _subtitle_resolved:
            sub_val = render_usage.get("subtitle_emphasis")
            if sub_val is not None:
                mapped_style = _SUBTITLE_MAP.get(str(sub_val))
                if mapped_style is not None:
                    raw["subtitle_emphasis_style"] = mapped_style
                    _subtitle_resolved = True
                    contributed = True

        # ── Hook overlay mapping ───────────────────────────────────────────────
        if not _hook_resolved:
            hook_val = render_usage.get("hook")
            if hook_val is True:
                raw["hook_overlay_enabled"] = True
                _hook_resolved = True
                contributed = True
            elif hook_val is False:
                raw["hook_overlay_enabled"] = False
                _hook_resolved = True
                contributed = True
            # hook_val not present → skip

        # Track which items contributed
        if contributed and item_id:
            source_ids.append(item_id)

    # Attach source_knowledge_ids before validation
    raw["source_knowledge_ids"] = source_ids

    return validate_execution_hints(raw)
