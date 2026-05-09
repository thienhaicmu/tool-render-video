"""
knowledge_ingestion.py — Local JSON creator knowledge ingestion. Phase 39.

Reads structured creator knowledge from local JSON files only.
No network access, no subprocess, no remote requests, no auto-download.
Never raises. Malformed files skipped safely.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, List, Optional

from app.ai.knowledge.knowledge_schema import AICreatorKnowledge
from app.ai.knowledge.knowledge_safety import is_knowledge_safe, sanitize_knowledge

logger = logging.getLogger("app.ai.knowledge.ingestion")

_MAX_FILE_SIZE_BYTES = 1_000_000  # 1 MB hard cap per knowledge file


def ingest_knowledge_file(path: Any) -> Optional[AICreatorKnowledge]:
    """Parse a single local JSON file into an AICreatorKnowledge item.

    Returns None when:
    - file does not exist or cannot be read
    - JSON is malformed
    - safety check fails
    - required fields are missing

    Never raises. No network access.
    """
    try:
        p = Path(str(path))
        if not p.exists() or not p.is_file():
            logger.debug("knowledge_file_missing path=%s", path)
            return None

        file_size = p.stat().st_size
        if file_size > _MAX_FILE_SIZE_BYTES:
            logger.debug("knowledge_file_too_large path=%s size=%d", path, file_size)
            return None

        raw_text = p.read_text(encoding="utf-8", errors="replace")
        try:
            raw_data = json.loads(raw_text)
        except json.JSONDecodeError as exc:
            logger.debug("knowledge_file_malformed_json path=%s error=%s", path, exc)
            return None

        if not isinstance(raw_data, dict):
            logger.debug("knowledge_file_not_dict path=%s", path)
            return None

        sanitized = sanitize_knowledge(raw_data)
        if not sanitized:
            logger.debug("knowledge_file_sanitize_empty path=%s", path)
            return None

        if not is_knowledge_safe(sanitized):
            logger.debug("knowledge_file_safety_rejected path=%s", path)
            return None

        item = _build_creator_knowledge(sanitized)
        logger.debug(
            "ai_creator_knowledge_ingested knowledge_id=%s category=%s style=%s",
            item.knowledge_id, item.category, item.creator_style,
        )
        return item

    except Exception as exc:
        logger.debug("knowledge_ingestion_error path=%s: %s", path, exc)
        return None


def ingest_knowledge_directory(path: Any) -> List[AICreatorKnowledge]:
    """Ingest all *.json files in a local directory. Never raises.

    Returns list of successfully parsed AICreatorKnowledge items.
    Malformed or unsafe files are silently skipped.
    No network access, no subprocess.
    """
    items: List[AICreatorKnowledge] = []
    try:
        p = Path(str(path))
        if not p.exists() or not p.is_dir():
            logger.debug("knowledge_directory_missing path=%s", path)
            return items

        json_files = sorted(p.glob("*.json"))
        for json_file in json_files:
            item = ingest_knowledge_file(json_file)
            if item is not None:
                items.append(item)

        logger.debug(
            "knowledge_directory_scanned path=%s files=%d loaded=%d",
            path, len(json_files), len(items),
        )
    except Exception as exc:
        logger.debug("knowledge_directory_error path=%s: %s", path, exc)

    return items


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_creator_knowledge(data: dict) -> AICreatorKnowledge:
    """Convert a sanitised dict into an AICreatorKnowledge dataclass."""
    knowledge_id = str(data.get("knowledge_id", ""))
    category = str(data.get("category", ""))
    source_type = str(data.get("source_type", "local_json"))
    creator_style = str(data.get("creator_style", ""))
    title = str(data.get("title", ""))
    description = str(data.get("description", ""))

    tags = list(data.get("tags") or [])
    hook_patterns = list(data.get("hook_patterns") or [])

    subtitle_patterns = dict(data.get("subtitle_patterns") or {})
    pacing_patterns = dict(data.get("pacing_patterns") or {})
    camera_patterns = dict(data.get("camera_patterns") or {})
    retention_patterns = dict(data.get("retention_patterns") or {})
    creator_patterns = dict(data.get("creator_patterns") or {})

    return AICreatorKnowledge(
        knowledge_id=knowledge_id,
        category=category,
        source_type=source_type,
        creator_style=creator_style,
        title=title,
        description=description,
        tags=tags,
        hook_patterns=hook_patterns,
        subtitle_patterns=subtitle_patterns,
        pacing_patterns=pacing_patterns,
        camera_patterns=camera_patterns,
        retention_patterns=retention_patterns,
        creator_patterns=creator_patterns,
        safe=True,
        warnings=[],
    )
