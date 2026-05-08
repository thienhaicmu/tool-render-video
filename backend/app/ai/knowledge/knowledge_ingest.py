"""
knowledge_ingest.py — Local JSON knowledge ingestion. Phase 15.

Supports local curated JSON files only. No network access, no API calls.

Public API:
    parse_knowledge_json(data) -> list[ExternalKnowledgeItem]
    ingest_knowledge_file(path: str) -> dict
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List, Optional

from app.ai.knowledge.knowledge_schema import ExternalKnowledgeItem, VALID_SOURCE_TYPES

logger = logging.getLogger("app.ai.knowledge.ingest")


def parse_knowledge_json(data: Any) -> List[ExternalKnowledgeItem]:
    """Parse raw dict into ExternalKnowledgeItem list. Never raises.

    Expects: {"items": [...]}
    Skips any item that is malformed, missing required fields, or has
    an invalid source_type.
    """
    items: List[ExternalKnowledgeItem] = []

    if not isinstance(data, dict):
        return items

    raw_items = data.get("items", [])
    if not isinstance(raw_items, list):
        return items

    skipped = 0
    for idx, raw in enumerate(raw_items):
        try:
            item = _parse_item(raw)
            if item is not None:
                items.append(item)
            else:
                skipped += 1
        except Exception as exc:
            skipped += 1
            logger.debug("knowledge_ingest_item_skipped index=%d error=%s", idx, exc)

    logger.info(
        "ai_external_knowledge_loaded count=%d skipped=%d",
        len(items),
        skipped,
    )
    return items


def ingest_knowledge_file(path: str) -> dict:
    """Load and parse a local JSON knowledge file. Never raises.

    Returns:
        {
            "loaded": int,
            "skipped": int,
            "items": list[ExternalKnowledgeItem],
            "warnings": list[str],
        }
    """
    try:
        p = Path(str(path or ""))
        if not p.exists():
            return {
                "loaded": 0,
                "skipped": 0,
                "items": [],
                "warnings": [f"file_not_found:{path}"],
            }

        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)

        items = parse_knowledge_json(data)

        raw_count = 0
        if isinstance(data, dict):
            raw_items = data.get("items", [])
            raw_count = len(raw_items) if isinstance(raw_items, list) else 0

        skipped = max(0, raw_count - len(items))
        return {
            "loaded": len(items),
            "skipped": skipped,
            "items": items,
            "warnings": [],
        }
    except Exception as exc:
        logger.debug("knowledge_ingest_file_failed path=%s error=%s", path, exc)
        return {
            "loaded": 0,
            "skipped": 0,
            "items": [],
            "warnings": [f"ingest_error:{type(exc).__name__}"],
        }


# ---------------------------------------------------------------------------
# Internal parser
# ---------------------------------------------------------------------------

def _parse_item(raw: Any) -> Optional[ExternalKnowledgeItem]:
    """Parse a single raw dict into ExternalKnowledgeItem. Returns None if invalid."""
    if not isinstance(raw, dict):
        return None

    item_id = str(raw.get("id", "") or "").strip()
    if not item_id:
        return None

    source_type = str(raw.get("source_type", "") or "").strip()
    if source_type not in VALID_SOURCE_TYPES:
        return None

    text = str(raw.get("text", "") or "").strip()
    if not text:
        return None

    # Tags — normalize to list[str]
    raw_tags = raw.get("tags", [])
    if isinstance(raw_tags, list):
        tags = [str(t) for t in raw_tags if t is not None]
    else:
        tags = []

    # Confidence — clamp to [0, 1]
    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(1.0, confidence))

    # Metadata — must be dict
    metadata = raw.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    return ExternalKnowledgeItem(
        id=item_id,
        source_type=source_type,
        text=text,
        market=str(raw.get("market") or "").strip() or None,
        platform=str(raw.get("platform") or "").strip() or None,
        style=str(raw.get("style") or "").strip() or None,
        topic=str(raw.get("topic") or "").strip() or None,
        tags=tags,
        confidence=confidence,
        metadata=dict(metadata),
    )
