"""Client-side error intake — B2 follow-up (2026-06-27).

The Electron renderer (uncaught JS errors / promise rejections) and the
Electron main process (hard renderer/child-process crashes) POST here. The
handler re-emits each report through the standard ``app`` logger at ERROR
level, so the structured JSONL sink (``core/error_sink.py``) records it in
``data/logs/errors.jsonl`` alongside backend errors, with the same schema.

Offline-first: reports never leave the machine. Sizes are capped so a
runaway client cannot bloat the log line. Fire-and-forget by contract — the
endpoint always returns 200 so a failing report can never cascade into more
client errors.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter
from pydantic import BaseModel, Field

logger = logging.getLogger("app.client")

router = APIRouter(prefix="/api/client", tags=["client-errors"])

# Cap per-field size so one report stays a bounded single JSONL line.
_MAX_TEXT = 16_000


class ClientErrorReport(BaseModel):
    source: str = Field(default="renderer", max_length=64)   # renderer | electron-main
    kind: str = Field(default="error", max_length=64)        # error | unhandledrejection | render-process-gone | child-process-gone
    message: str = Field(default="", max_length=_MAX_TEXT)
    stack: str = Field(default="", max_length=_MAX_TEXT)
    url: str = Field(default="", max_length=2048)


@router.post("/error")
def report_client_error(report: ClientErrorReport) -> dict:
    """Record a client error into the structured sink. Always 200."""
    try:
        logger.error(
            "client_error [%s]: %s",
            report.source,
            report.message or report.kind,
            extra={
                # error_kind is a first-class sink field; namespace it so
                # client reports are filterable from backend errors.
                "error_kind": f"client.{report.kind}",
                "client_source": report.source,
                "client_url": report.url,
                "client_stack": report.stack,
            },
        )
    except Exception:  # pragma: no cover - the intake must never throw
        pass
    return {"ok": True}
