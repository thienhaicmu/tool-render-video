"""
knowledge_loader.py — Load KnowledgeItem objects from knowledge/processed/*.jsonl files.

Public API:
    load_knowledge_items(processed_dir=None) -> list[KnowledgeItem]
        - default processed_dir: backend/knowledge/processed/
        - reads all *.jsonl files, parses each line as JSON
        - validates each item with validate_knowledge_item()
        - skips invalid items / invalid JSON lines with a warning
        - handles missing or empty directory gracefully (returns [])
        - never raises
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from app.ai.rag.knowledge_schema import KnowledgeItem, validate_knowledge_item

logger = logging.getLogger(__name__)

# Default: knowledge/processed/ relative to this file's location
# This file lives at: backend/app/ai/rag/knowledge_loader.py
# Resolves to:        backend/knowledge/processed/
_DEFAULT_PROCESSED_DIR = Path(__file__).resolve().parents[3] / "knowledge" / "processed"


def load_knowledge_items(
    processed_dir: Optional[Path] = None,
) -> list:
    """Load all KnowledgeItem objects from *.jsonl files in processed_dir.

    Returns a list of valid KnowledgeItem objects.
    Returns [] on missing directory, empty directory, or total failure.
    Never raises.
    """
    if processed_dir is None:
        processed_dir = _DEFAULT_PROCESSED_DIR

    processed_dir = Path(processed_dir)

    if not processed_dir.exists():
        logger.warning(
            "knowledge_loader: processed_dir does not exist: %s — returning empty list",
            processed_dir,
        )
        return []

    if not processed_dir.is_dir():
        logger.warning(
            "knowledge_loader: processed_dir is not a directory: %s — returning empty list",
            processed_dir,
        )
        return []

    jsonl_files = sorted(processed_dir.glob("*.jsonl"))
    if not jsonl_files:
        logger.warning(
            "knowledge_loader: no *.jsonl files found in %s — returning empty list",
            processed_dir,
        )
        return []

    items: list[KnowledgeItem] = []
    total_lines = 0
    skipped_invalid_json = 0
    skipped_invalid_schema = 0

    for jsonl_path in jsonl_files:
        try:
            with open(jsonl_path, "r", encoding="utf-8") as fh:
                for line_no, line in enumerate(fh, start=1):
                    line = line.strip()
                    if not line:
                        continue

                    total_lines += 1

                    # Parse JSON
                    try:
                        raw = json.loads(line)
                    except json.JSONDecodeError as exc:
                        logger.warning(
                            "knowledge_loader: invalid JSON in %s line %d: %s",
                            jsonl_path.name, line_no, exc,
                        )
                        skipped_invalid_json += 1
                        continue

                    # Validate schema
                    item = validate_knowledge_item(raw)
                    if item is None:
                        logger.warning(
                            "knowledge_loader: invalid knowledge item in %s line %d (id=%r)",
                            jsonl_path.name, line_no, raw.get("id"),
                        )
                        skipped_invalid_schema += 1
                        continue

                    items.append(item)

        except Exception as exc:
            logger.warning(
                "knowledge_loader: failed to read file %s: %s",
                jsonl_path, exc,
            )

    logger.info(
        "knowledge_loader: loaded %d items from %d files "
        "(total_lines=%d skipped_json=%d skipped_schema=%d)",
        len(items), len(jsonl_files), total_lines, skipped_invalid_json, skipped_invalid_schema,
    )
    return items
