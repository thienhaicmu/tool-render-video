"""
knowledge_schema.py — KnowledgeItem dataclass and validation for local knowledge retrieval.

Uses plain dataclasses (matching the codebase style in memory_schema.py / edit_plan_schema.py).
No Pydantic, no heavy deps. Safe to import at any time.

Public API:
    KnowledgeItem                     — dataclass for one knowledge item
    validate_knowledge_item(raw_dict) — returns KnowledgeItem | None (never raises)
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Required fields — must all be present for a valid item
_REQUIRED_FIELDS = {"id", "type", "platform", "niche", "style", "duration_range", "rule", "render_usage", "weight", "tags"}


@dataclass
class KnowledgeItem:
    """One knowledge item loaded from knowledge/processed/*.jsonl."""

    # Required
    id: str
    type: str
    platform: list             # list[str] — normalised to lowercase
    niche: list                # list[str] — normalised to lowercase
    style: list                # list[str] — normalised to lowercase
    duration_range: list       # list[int] — exactly 2 elements [min, max]
    rule: str
    render_usage: dict
    weight: float              # clamped to [0.0, 1.0]
    tags: list                 # list[str] — normalised to lowercase

    # Optional — default to empty list or None
    aspect_ratio: list = field(default_factory=list)       # list[str]
    subtitle_style: list = field(default_factory=list)     # list[str]
    target_goal: list = field(default_factory=list)        # list[str]
    examples: list = field(default_factory=list)           # list[str]
    source: Optional[str] = None
    notes: Optional[str] = None


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def _normalise_str_list(value: Any, field_name: str) -> Optional[list]:
    """Convert a value to a lowercase string list. Returns None on failure."""
    if not isinstance(value, list):
        logger.warning("knowledge_schema: field '%s' must be a list, got %s", field_name, type(value).__name__)
        return None
    result = []
    for item in value:
        if not isinstance(item, str):
            logger.warning("knowledge_schema: field '%s' contains non-string item: %r", field_name, item)
            return None
        result.append(item.lower())
    return result


def validate_knowledge_item(raw_dict: Any) -> Optional[KnowledgeItem]:
    """Validate and construct a KnowledgeItem from a raw dict.

    Returns KnowledgeItem on success, None on any validation failure.
    Logs a warning for each problem found.
    Never raises.
    """
    if not isinstance(raw_dict, dict):
        logger.warning("knowledge_schema: expected dict, got %s", type(raw_dict).__name__)
        return None

    # Check required fields present
    missing = _REQUIRED_FIELDS - raw_dict.keys()
    if missing:
        logger.warning("knowledge_schema: missing required fields: %s (id=%r)", sorted(missing), raw_dict.get("id"))
        return None

    try:
        # id
        item_id = raw_dict.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            logger.warning("knowledge_schema: 'id' must be a non-empty string, got %r", item_id)
            return None

        # type
        item_type = raw_dict.get("type")
        if not isinstance(item_type, str) or not item_type.strip():
            logger.warning("knowledge_schema: 'type' must be a non-empty string (id=%s)", item_id)
            return None

        # platform (required, lowercase list)
        platform = _normalise_str_list(raw_dict.get("platform"), "platform")
        if platform is None:
            logger.warning("knowledge_schema: invalid 'platform' field (id=%s)", item_id)
            return None

        # niche (required, lowercase list)
        niche = _normalise_str_list(raw_dict.get("niche"), "niche")
        if niche is None:
            logger.warning("knowledge_schema: invalid 'niche' field (id=%s)", item_id)
            return None

        # style (required, lowercase list)
        style = _normalise_str_list(raw_dict.get("style"), "style")
        if style is None:
            logger.warning("knowledge_schema: invalid 'style' field (id=%s)", item_id)
            return None

        # duration_range — must be exactly 2 ints
        dr = raw_dict.get("duration_range")
        if not isinstance(dr, list) or len(dr) != 2:
            logger.warning(
                "knowledge_schema: 'duration_range' must be a 2-element list (id=%s), got %r",
                item_id, dr,
            )
            return None
        try:
            duration_range = [int(dr[0]), int(dr[1])]
        except (TypeError, ValueError):
            logger.warning(
                "knowledge_schema: 'duration_range' elements must be ints (id=%s), got %r",
                item_id, dr,
            )
            return None

        # rule
        rule = raw_dict.get("rule")
        if not isinstance(rule, str):
            logger.warning("knowledge_schema: 'rule' must be a string (id=%s)", item_id)
            return None

        # render_usage
        render_usage = raw_dict.get("render_usage")
        if not isinstance(render_usage, dict):
            logger.warning("knowledge_schema: 'render_usage' must be a dict (id=%s)", item_id)
            return None

        # weight — clamp to [0.0, 1.0]
        raw_weight = raw_dict.get("weight")
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            logger.warning("knowledge_schema: 'weight' must be numeric (id=%s), got %r", item_id, raw_weight)
            return None
        weight = max(0.0, min(1.0, weight))

        # tags (required, lowercase list)
        tags = _normalise_str_list(raw_dict.get("tags"), "tags")
        if tags is None:
            logger.warning("knowledge_schema: invalid 'tags' field (id=%s)", item_id)
            return None

        # --- optional fields ---

        # aspect_ratio
        raw_ar = raw_dict.get("aspect_ratio", [])
        if isinstance(raw_ar, list):
            aspect_ratio = [str(x).lower() for x in raw_ar if isinstance(x, str)]
        else:
            aspect_ratio = []

        # subtitle_style
        raw_ss = raw_dict.get("subtitle_style", [])
        if isinstance(raw_ss, list):
            subtitle_style = [str(x).lower() for x in raw_ss if isinstance(x, str)]
        else:
            subtitle_style = []

        # target_goal
        raw_tg = raw_dict.get("target_goal", [])
        if isinstance(raw_tg, list):
            target_goal = [str(x).lower() for x in raw_tg if isinstance(x, str)]
        else:
            target_goal = []

        # examples
        raw_ex = raw_dict.get("examples", [])
        if isinstance(raw_ex, list):
            examples = [str(x) for x in raw_ex if isinstance(x, str)]
        else:
            examples = []

        # source / notes
        source = str(raw_dict["source"]) if "source" in raw_dict and raw_dict["source"] is not None else None
        notes = str(raw_dict["notes"]) if "notes" in raw_dict and raw_dict["notes"] is not None else None

        return KnowledgeItem(
            id=item_id,
            type=item_type,
            platform=platform,
            niche=niche,
            style=style,
            duration_range=duration_range,
            rule=rule,
            render_usage=render_usage,
            weight=weight,
            tags=tags,
            aspect_ratio=aspect_ratio,
            subtitle_style=subtitle_style,
            target_goal=target_goal,
            examples=examples,
            source=source,
            notes=notes,
        )

    except Exception as exc:
        logger.warning("knowledge_schema: unexpected error validating item %r: %s", raw_dict.get("id"), exc)
        return None
