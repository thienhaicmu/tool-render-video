"""
feedback_memory.py — Local creator feedback persistence. Phase 43.

Rules:
- Deterministic only
- Never raises
- Local JSON persistence only (data/feedback/render_feedback/)
- Safe fallback if missing or corrupt
- No DB migration
- No internet access
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Optional

from app.ai.feedback.feedback_schema import AICreatorFeedbackSignal
from app.ai.feedback.feedback_safety import sanitize_feedback

logger = logging.getLogger("app.ai.feedback.memory")

_FEEDBACK_DIR = Path("data/feedback/render_feedback")
_MEMORY_FILE = "feedback_memory.json"
_MAX_SIGNALS = 200  # cap stored signals to prevent unbounded growth


def _memory_path() -> Path:
    return _FEEDBACK_DIR / _MEMORY_FILE


def build_default_feedback_memory() -> dict:
    """Return a blank feedback memory structure. Never raises."""
    return {
        "version": 1,
        "signals": [],
        "pattern_counts": {
            "creator_style": {},
            "subtitle_style": {},
            "pacing_style": {},
            "camera_style": {},
            "duration_bucket": {},
            "exported_ranks": [],
            "ignored_ranks": [],
        },
        "total_signals": 0,
        "total_exports": 0,
        "total_ignores": 0,
    }


def load_feedback_memory() -> dict:
    """Load feedback memory from local JSON. Falls back to default if missing or corrupt.

    Never raises. Logs structured events.
    """
    path = _memory_path()
    try:
        if not path.exists():
            logger.info("ai_feedback_loaded status=not_found_using_default")
            return build_default_feedback_memory()

        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)

        if not isinstance(data, dict):
            logger.info("ai_feedback_loaded status=corrupt_using_default")
            return build_default_feedback_memory()

        data = sanitize_feedback(data)
        logger.info(
            "ai_feedback_loaded signals=%d exports=%d ignores=%d",
            data.get("total_signals", 0),
            data.get("total_exports", 0),
            data.get("total_ignores", 0),
        )
        return data

    except Exception as exc:
        logger.info("ai_feedback_loaded status=error_using_default error=%s", type(exc).__name__)
        return build_default_feedback_memory()


def save_feedback_memory(memory: dict) -> bool:
    """Persist feedback memory to local JSON. Returns True on success. Never raises."""
    try:
        _FEEDBACK_DIR.mkdir(parents=True, exist_ok=True)
        safe = sanitize_feedback(memory) if isinstance(memory, dict) else build_default_feedback_memory()
        _memory_path().write_text(
            json.dumps(safe, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return True
    except Exception as exc:
        logger.debug("feedback_memory_save_error: %s", exc)
        return False


def record_feedback_signal(signal: AICreatorFeedbackSignal) -> dict:
    """Record a feedback signal into local memory and return updated memory. Never raises."""
    try:
        memory = load_feedback_memory()
        pattern_counts = memory.get("pattern_counts", {})
        if not isinstance(pattern_counts, dict):
            pattern_counts = {}

        safe_signal = sanitize_feedback(signal.to_dict())

        # Append to signal list (capped)
        signals = list(memory.get("signals", []))
        signals.append(safe_signal)
        if len(signals) > _MAX_SIGNALS:
            signals = signals[-_MAX_SIGNALS:]
        memory["signals"] = signals
        memory["total_signals"] = memory.get("total_signals", 0) + 1

        # Update pattern counters
        _increment_pattern(pattern_counts, "creator_style", signal.creator_style)
        _increment_pattern(pattern_counts, "subtitle_style", signal.subtitle_style)
        _increment_pattern(pattern_counts, "pacing_style", signal.pacing_style)
        _increment_pattern(pattern_counts, "camera_style", signal.camera_style)
        _increment_pattern(pattern_counts, "duration_bucket", signal.duration_bucket)

        if signal.exported:
            memory["total_exports"] = memory.get("total_exports", 0) + 1
            ranks = list(pattern_counts.get("exported_ranks", []))
            ranks.append(int(signal.selected_output_rank))
            pattern_counts["exported_ranks"] = ranks[-50:]  # keep last 50

        if signal.ignored:
            memory["total_ignores"] = memory.get("total_ignores", 0) + 1
            ranks = list(pattern_counts.get("ignored_ranks", []))
            ranks.append(int(signal.selected_output_rank))
            pattern_counts["ignored_ranks"] = ranks[-50:]

        memory["pattern_counts"] = pattern_counts

        save_feedback_memory(memory)
        logger.info(
            "ai_feedback_signal_recorded feedback_id=%s exported=%s ignored=%s rank=%d",
            signal.feedback_id, signal.exported, signal.ignored, signal.selected_output_rank,
        )
        return memory

    except Exception as exc:
        logger.debug("feedback_memory_record_error: %s", exc)
        return build_default_feedback_memory()


def _increment_pattern(pattern_counts: dict, category: str, value: str) -> None:
    """Increment pattern frequency counter. Never raises."""
    try:
        if not value:
            return
        cat = pattern_counts.setdefault(category, {})
        if isinstance(cat, dict):
            cat[value] = cat.get(value, 0) + 1
    except Exception:
        pass
