"""
knowledge_pack_loader.py — Local knowledge pack JSON loader. Phase 53A.

Loads knowledge packs from the knowledge/packs/ directory.
Validates, skips malformed packs, returns deterministically sorted list.

Public API:
    load_knowledge_packs(packs_dir=None) -> list[KnowledgePack]

Safety contract:
    ✅ Local only — no internet, no cloud API, no vector DB
    ✅ Never raises — returns empty list on any failure
    ✅ Deterministic sort — (domain, id, version) ascending
    ✅ Skips malformed packs silently (logged at DEBUG level)
    ✅ Advisory only — no executable code triggered by pack content
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List, Optional

from app.ai.knowledge.knowledge_pack_schema import KnowledgePack, parse_pack

logger = logging.getLogger("app.ai.knowledge.pack_loader")

# Default packs directory: backend/knowledge/packs/ (4 parents up from this file)
_DEFAULT_PACKS_DIR: Path = (
    Path(__file__).parent.parent.parent.parent / "knowledge" / "packs"
)


def load_knowledge_packs(packs_dir: Optional[Path] = None) -> List[KnowledgePack]:
    """Load all valid knowledge packs from the packs directory. Never raises.

    Args:
        packs_dir: Path to the packs directory. Defaults to backend/knowledge/packs/.

    Returns:
        List of KnowledgePack objects sorted by (domain, id, version).
        Empty list if directory is missing or all packs are malformed.
    """
    try:
        return _load(packs_dir or _DEFAULT_PACKS_DIR)
    except Exception as exc:
        logger.debug("knowledge_pack_loader_failed: %s", exc)
        return []


def _load(packs_dir: Path) -> List[KnowledgePack]:
    if not packs_dir.exists() or not packs_dir.is_dir():
        logger.debug("knowledge_packs_dir_missing: %s", packs_dir)
        return []

    packs: List[KnowledgePack] = []
    json_files = sorted(packs_dir.glob("*.json"))  # stable glob order

    for path in json_files:
        pack = _load_one(path)
        if pack is not None:
            packs.append(pack)

    # Deterministic sort: domain → id → version
    packs.sort(key=lambda p: (p.domain, p.id, p.version))

    logger.debug("knowledge_packs_loaded count=%d dir=%s", len(packs), packs_dir)
    return packs


def _load_one(path: Path) -> Optional[KnowledgePack]:
    """Load and parse a single pack file. Returns None if invalid. Never raises."""
    try:
        with path.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        pack = parse_pack(raw)
        if pack is None:
            logger.debug("knowledge_pack_skipped_malformed: %s", path.name)
        return pack
    except Exception as exc:
        logger.debug("knowledge_pack_load_error file=%s: %s", path.name, exc)
        return None
