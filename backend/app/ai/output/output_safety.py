"""
output_safety.py — Safety gates for AI output ranking.

Phase 30: metadata-only. No file reads, no file writes, no file deletion.
Never raises. Never mutates files.
"""
from __future__ import annotations

from typing import Any

_REQUIRED_OUTPUT_KEYS = frozenset({"output_id"})
_BLOCKED_OPS = frozenset({
    "delete", "upload", "publish", "overwrite", "move", "rename",
})

_SAFE_METADATA_KEYS = frozenset({
    "output_id",
    "path",
    "variant_id",
    "part_no",
    "output_score",
    "output_rank",
    "output_rank_score",
    "final_score",
    "raw_score",
    "quality_penalty",
    "ranking_reason",
    "ranking_components",
    "render_status",
    "duration",
    "size_bytes",
    "is_best_clip",
    "validation_passed",
    "failed",
    "warnings",
    "ai_mode",
    "variant_label",
    "safe_to_enqueue",
    "execution_id",
    "plan_id",
    "payload_overrides",
})


def sanitize_output_metadata(output: Any) -> dict:
    """Return a safe copy of output metadata. Never raises. Never mutates."""
    if not isinstance(output, dict):
        return {}
    result = {}
    for k, v in output.items():
        if k in _SAFE_METADATA_KEYS:
            result[k] = v
    return result


def is_output_rankable(output: Any) -> bool:
    """Return True if the output dict has the minimum required fields. Never raises."""
    if not isinstance(output, dict):
        return False
    if not output.get("output_id"):
        return False
    return True
