"""Structured (JSONL) error sink — B2 (2026-06-27).

The human-readable ``error.log`` (see ``logging_setup.py``) is great for a
developer eyeballing a stack trace, but it is not machine-parseable, so it
cannot feed product observability (B3) or any aggregation/triage tooling.

This module adds a SECOND, parallel sink: one JSON object per line in
``data/logs/errors.jsonl``. It is wired as a normal ``logging.Handler`` on
the root ``app`` logger at ERROR level, so it captures every ERROR+ event
from the entire app uniformly — both the HTTP layer and the render worker
threads (which log via ``app.render.*``) — with zero changes to request
handling and zero behaviour change (logging is a pure side effect).

Offline-first: records are written locally only. Nothing leaves the
machine. The file rotates so it can never grow unbounded.

Each line carries, when available:
  ts, level, logger, message, module/func/line, exception type +
  traceback, and product context (job_id, stage, part_no, error_kind,
  request_method, request_path) — pulled from ``logging`` ``extra={...}``
  fields. Call sites opt in to the product context simply by passing
  ``logger.error("...", extra={"job_id": jid, "stage": st})``; absent
  fields are omitted.
"""
from __future__ import annotations

import json
import logging
import logging.handlers
import traceback as _traceback
from pathlib import Path

# Product-context fields lifted from a record's ``extra={...}`` when present.
# Adding a new field here makes it flow into the JSONL automatically once a
# call site passes it via ``extra``.
_CONTEXT_FIELDS = (
    "job_id",
    "stage",
    "part_no",
    "error_kind",
    "request_method",
    "request_path",
    "channel_code",
)

# Standard LogRecord attributes — used to detect *any* additional extras the
# caller attached, so the sink is forward-compatible without a code change.
_RESERVED = frozenset(vars(logging.makeLogRecord({})).keys()) | {
    "message", "asctime", "taskName",
}


class JsonlErrorFormatter(logging.Formatter):
    """Render a ``LogRecord`` as a single compact JSON line.

    Never raises — a formatter exception would otherwise be swallowed by
    ``logging`` and silently drop the record. On any failure we fall back
    to a minimal record so an error is never lost entirely.
    """

    def format(self, record: logging.LogRecord) -> str:  # noqa: A003
        try:
            payload: dict[str, object] = {
                "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
                "module": record.module,
                "func": record.funcName,
                "line": record.lineno,
            }

            if record.exc_info:
                exc_type, exc_val, exc_tb = record.exc_info
                payload["exc_type"] = getattr(exc_type, "__name__", str(exc_type))
                payload["exc_message"] = str(exc_val)
                payload["traceback"] = "".join(
                    _traceback.format_exception(exc_type, exc_val, exc_tb)
                )

            # Known product-context fields (explicit list → stable schema).
            for field in _CONTEXT_FIELDS:
                val = getattr(record, field, None)
                if val is not None:
                    payload[field] = val

            # Forward-compat: any other non-reserved attribute the caller
            # attached via extra={...} that is JSON-serialisable.
            for key, val in record.__dict__.items():
                if key in _RESERVED or key in payload or key.startswith("_"):
                    continue
                if isinstance(val, (str, int, float, bool)) or val is None:
                    payload.setdefault(key, val)

            return json.dumps(payload, ensure_ascii=False, default=str)
        except Exception:  # pragma: no cover - defensive last resort
            try:
                return json.dumps({
                    "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
                    "level": getattr(record, "levelname", "ERROR"),
                    "logger": getattr(record, "name", "?"),
                    "message": "error_sink: failed to format record",
                })
            except Exception:
                return '{"level":"ERROR","message":"error_sink: total format failure"}'


def build_errors_jsonl_handler(
    logs_dir: Path,
    *,
    max_mb: int = 20,
    backups: int = 5,
) -> logging.handlers.RotatingFileHandler:
    """Return a rotating ERROR-level handler that writes JSONL records.

    ``delay=True`` — the file is not created until the first error, so a
    clean run leaves no empty ``errors.jsonl`` behind.
    """
    logs_dir.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        str(logs_dir / "errors.jsonl"),
        maxBytes=max_mb * 1024 * 1024,
        backupCount=backups,
        encoding="utf-8",
        delay=True,
    )
    handler.setLevel(logging.ERROR)
    handler.setFormatter(JsonlErrorFormatter())
    return handler
