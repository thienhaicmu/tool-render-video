"""B2 (2026-06-27) — structured JSONL error sink.

Pins the contract that ERROR+ events are written as one machine-parseable
JSON object per line in data/logs/errors.jsonl, with exception detail and
product context (job_id/stage/...) when supplied via logging extra={...}.
This file is the foundation for product observability (B3); a regression
that drops the structure or the context would silently break it.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from app.core.error_sink import JsonlErrorFormatter, build_errors_jsonl_handler


def _read_lines(path: Path) -> list[dict]:
    return [json.loads(ln) for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]


@pytest.fixture()
def sink_logger(tmp_path):
    """An isolated logger wired to a fresh errors.jsonl in a temp dir."""
    logger = logging.getLogger(f"app.test_error_sink.{id(tmp_path)}")
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = build_errors_jsonl_handler(tmp_path)
    logger.addHandler(handler)
    try:
        yield logger, tmp_path / "errors.jsonl"
    finally:
        handler.close()
        logger.removeHandler(handler)


def test_error_event_writes_one_json_line(sink_logger):
    logger, jsonl = sink_logger
    logger.error("boom happened")

    rows = _read_lines(jsonl)
    assert len(rows) == 1
    row = rows[0]
    assert row["level"] == "ERROR"
    assert row["message"] == "boom happened"
    assert "ts" in row and "logger" in row and "line" in row


def test_below_error_is_not_written(sink_logger):
    logger, jsonl = sink_logger
    logger.info("just info")
    logger.warning("just a warning")
    # delay=True + nothing at ERROR → file never created.
    assert not jsonl.exists()


def test_exception_traceback_is_captured(sink_logger):
    logger, jsonl = sink_logger
    try:
        raise ValueError("bad value")
    except ValueError:
        logger.error("operation failed", exc_info=True)

    row = _read_lines(jsonl)[0]
    assert row["exc_type"] == "ValueError"
    assert row["exc_message"] == "bad value"
    assert "Traceback" in row["traceback"]


def test_product_context_from_extra_is_recorded(sink_logger):
    logger, jsonl = sink_logger
    logger.error(
        "render stage failed",
        extra={"job_id": "job-123", "stage": "RENDERING", "part_no": 4, "error_kind": "ffmpeg"},
    )

    row = _read_lines(jsonl)[0]
    assert row["job_id"] == "job-123"
    assert row["stage"] == "RENDERING"
    assert row["part_no"] == 4
    assert row["error_kind"] == "ffmpeg"


def test_formatter_never_raises_on_bad_record():
    """The formatter must be bulletproof — a formatting failure must not
    drop the error or crash the logging thread."""
    fmt = JsonlErrorFormatter()
    rec = logging.makeLogRecord({"msg": "ok", "levelname": "ERROR", "name": "app.x"})
    out = fmt.format(rec)
    parsed = json.loads(out)  # must be valid JSON
    assert parsed["message"] == "ok"
