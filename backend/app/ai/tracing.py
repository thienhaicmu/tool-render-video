"""
tracing.py — AITraceLogger: structured JSONL logging for AI render decisions.

Writes one JSON line per event to data/logs/{job_id}_ai_trace.jsonl.
All methods catch all exceptions — tracing must never crash a render.

Public API:
    AITraceLogger(job_id, log_dir=None)
        .log_input_filters(filters)
        .log_knowledge_retrieved(results)   — logs IDs and scores only (not full rule text)
        .log_rules_selected(rules)
        .log_fallback(reason, detail=None)
        .log_render_plan_summary(summary)
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

# Default: data/logs/ relative to backend root
# This file lives at: backend/app/ai/tracing.py
# Resolves to:        backend/../data/logs/ = data/logs/
_DEFAULT_LOG_DIR = Path(__file__).resolve().parents[3] / "data" / "logs"


class AITraceLogger:
    """Structured JSONL trace logger for AI render decisions.

    One instance per render job. Each log call appends one JSON line to
    data/logs/{job_id}_ai_trace.jsonl.

    Thread-safe: file writes are protected by an internal lock.
    Never raises from any public method.
    """

    def __init__(self, job_id: str, log_dir: Optional[Path] = None) -> None:
        self._job_id = str(job_id)
        self._log_dir = Path(log_dir) if log_dir else _DEFAULT_LOG_DIR
        self._log_path = self._log_dir / f"{self._job_id}_ai_trace.jsonl"
        self._lock = threading.Lock()

    # -----------------------------------------------------------------------
    # Core write
    # -----------------------------------------------------------------------

    def _write(self, event: str, payload: dict) -> None:
        """Write one JSONL line. Creates log_dir if missing. Never raises."""
        try:
            self._log_dir.mkdir(parents=True, exist_ok=True)
            record = {
                "job_id": self._job_id,
                "event": event,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            record.update(payload)
            line = json.dumps(record, ensure_ascii=False, default=str) + "\n"
            with self._lock:
                with open(self._log_path, "a", encoding="utf-8") as fh:
                    fh.write(line)
                    fh.flush()
        except Exception as exc:
            # Tracing must never crash the render — internal warning only
            logger.warning(
                "ai_trace_logger: failed to write event '%s' for job '%s': %s",
                event, self._job_id, exc,
            )

    # -----------------------------------------------------------------------
    # Event methods
    # -----------------------------------------------------------------------

    def log_input_filters(self, filters: dict) -> None:
        """Log the knowledge retrieval input filters."""
        self._write("ai.input_filters", {"filters": dict(filters)})

    def log_knowledge_retrieved(self, results: list) -> None:
        """Log retrieved knowledge IDs and scores (NOT full rule text)."""
        try:
            candidates = [
                {
                    "id": r.get("id"),
                    "type": r.get("type"),
                    "weight": r.get("weight"),
                    "match_score": r.get("match_score"),
                    "match_reason": r.get("match_reason", []),
                }
                for r in (results or [])
            ]
        except Exception:
            candidates = []

        self._write(
            "ai.knowledge_retrieved",
            {
                "candidates": candidates,
                "total_candidates": len(candidates),
                "top_k": len(candidates),
            },
        )

    def log_rules_selected(self, rules: list) -> None:
        """Log which rules were promoted from candidates."""
        try:
            selected = [
                {
                    "id": r.get("id"),
                    "type": r.get("type"),
                    "reason": r.get("reason", ""),
                }
                for r in (rules or [])
            ]
        except Exception:
            selected = []

        self._write("ai.rules_selected", {"selected": selected})

    def log_fallback(self, reason: str, detail: Optional[str] = None) -> None:
        """Log when AI augmentation falls back to defaults."""
        payload: dict[str, Any] = {
            "reason": str(reason),
            "fallback_used": "safe_defaults",
        }
        if detail is not None:
            payload["detail"] = str(detail)
        self._write("ai.fallback", payload)

    def log_render_plan_summary(self, summary: dict) -> None:
        """Log a summary of the finalised render plan."""
        self._write("ai.render_plan_summary", {"plan": dict(summary)})
