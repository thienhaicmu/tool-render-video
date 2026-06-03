"""P1 Contract #6 — `_emit_render_event` signature + emit-shape conformance.

Per CLAUDE.md Sacred Contract #6, the signature of `_emit_render_event`
and the structure of every entry it writes to log files are FROZEN.
The WebSocket handler in `routes/jobs.py` and 28+ call sites across
`stages/part_*.py` + `pipeline_*.py` + `render_pipeline.py` all rely
on the exact kwarg names AND the exact log-line schema.

A kwarg rename (`event` → `event_name`) or a renamed log key (`step` →
`stage_step`) does NOT raise an exception. The WebSocket handler would
silently ignore malformed events, freezing the UI progress display
mid-render with no error.

These tests fix the gap identified in the Track D D2 audit
(docs/review/AUDIT_2026-06-02_followup_7.md Finding 4 row #6).

Two layers of guard:
  1. inspect.signature() asserts kwarg names + keyword-only flag.
  2. End-to-end call asserts the resulting log dict has the
     expected keys with type-correct values.

See docs/review/AUDIT_2026-06-02_followup_9.md for the closure record.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import patch

import pytest


# Frozen kwarg names per CLAUDE.md Sacred Contract #6.
# Tuple order is documentary only — the params are keyword-only.
FROZEN_KWARGS = (
    "channel_code",
    "job_id",
    "event",
    "level",
    "message",
    "step",
    "context",
    "exception",
    "traceback_text",
    "duration_ms",
    "error_code",
)

# Frozen log-entry top-level keys per the function body (lines 120-133).
# These are what the WS handler + log consumers parse.
FROZEN_LOG_KEYS = {
    "timestamp",
    "level",
    "event",
    "module",
    "message",
    "job_id",
    "step",
    "error_code",
    "context",
    "exception",
    "traceback",
    "duration_ms",
}


class TestEmitRenderEventSignature:
    """Contract #6: signature shape is frozen.

    inspect.signature() catches kwarg renames or removals at test-collection
    time — no runtime call needed. If a future refactor renames `event` to
    `event_name`, this test fails before any other test runs.
    """

    def test_all_frozen_kwargs_present(self):
        from app.orchestration.render_events import _emit_render_event

        sig = inspect.signature(_emit_render_event)
        param_names = set(sig.parameters.keys())

        for name in FROZEN_KWARGS:
            assert name in param_names, (
                f"Contract #6 violation: kwarg '{name}' missing from "
                f"_emit_render_event signature. Current params: {sorted(param_names)}. "
                f"WebSocket handler at routes/jobs.py + 28+ call sites "
                f"depend on this exact name."
            )

    def test_all_params_are_keyword_only(self):
        """Every param is keyword-only (`*` separator) so callers cannot
        rely on positional ordering. This is what makes additive changes
        safe — new params can be inserted without breaking call sites."""
        from app.orchestration.render_events import _emit_render_event

        sig = inspect.signature(_emit_render_event)
        for name, param in sig.parameters.items():
            assert param.kind == inspect.Parameter.KEYWORD_ONLY, (
                f"Contract #6: param '{name}' must be keyword-only, "
                f"got kind={param.kind}. Positional acceptance would "
                f"allow call sites to bind by index, freezing the param "
                f"ORDER too — making future additive changes unsafe."
            )

    def test_required_kwargs_have_no_defaults(self):
        """The 6 load-bearing kwargs (channel_code, job_id, event, level,
        message, step) must have no default — callers MUST supply them.
        Missing values would produce empty fields in the WS event."""
        from app.orchestration.render_events import _emit_render_event

        sig = inspect.signature(_emit_render_event)
        required = ("channel_code", "job_id", "event", "level", "message", "step")
        for name in required:
            param = sig.parameters[name]
            assert param.default is inspect.Parameter.empty, (
                f"Contract #6: '{name}' is load-bearing — must NOT have a default. "
                f"Current default: {param.default!r}. Callers passing the "
                f"emit without this kwarg would emit a malformed event."
            )


class TestEmitRenderEventLogShape:
    """Contract #6: emitted log entry shape is frozen.

    End-to-end call with patched log dirs. Reads the resulting JSON
    lines and asserts every required top-level key is present and
    type-correct.
    """

    def test_log_entry_contains_all_frozen_top_level_keys(self, tmp_path, monkeypatch):
        """Every log line written by _emit_render_event must contain
        the full set of FROZEN_LOG_KEYS — even when optional kwargs
        (context, exception, etc.) are omitted."""
        from app.orchestration import render_events

        # Redirect log writes to tmp_path so we can read them back.
        monkeypatch.setattr(render_events, "CHANNELS_DIR", tmp_path / "channels")
        monkeypatch.setattr(render_events, "LOGS_DIR", tmp_path / "logs")

        render_events._emit_render_event(
            channel_code="manual",
            job_id="test_job_shape",
            event="test_event",
            level="INFO",
            message="conformance probe",
            step="test.step",
        )

        # Find the per-job log file (CHANNELS_DIR/<channel>/logs/<job_id>.log).
        log_file = tmp_path / "channels" / "manual" / "logs" / "test_job_shape.log"
        assert log_file.exists(), (
            f"Contract #6: per-job log not written at {log_file}. "
            f"The job log path is what feeds the WS stream."
        )

        # Read the first (only) JSON line.
        line = log_file.read_text(encoding="utf-8").strip().splitlines()[0]
        entry = json.loads(line)

        missing = FROZEN_LOG_KEYS - set(entry.keys())
        assert not missing, (
            f"Contract #6 violation: log entry missing keys {missing}. "
            f"WebSocket consumer expects every key in FROZEN_LOG_KEYS. "
            f"Actual keys: {sorted(entry.keys())}."
        )

        # Type sanity per the function body.
        assert isinstance(entry["timestamp"], str)
        assert entry["level"] == "INFO"
        assert entry["event"] == "test_event"
        assert entry["module"] == "render"
        assert entry["message"] == "conformance probe"
        assert entry["job_id"] == "test_job_shape"
        assert entry["step"] == "test.step"
        assert isinstance(entry["context"], dict)
        assert isinstance(entry["error_code"], str)
        assert isinstance(entry["duration_ms"], int)

    def test_log_entry_context_kwarg_lands_as_dict(self, tmp_path, monkeypatch):
        """When context kwarg is supplied, it appears in entry['context']
        as a dict. None becomes {}, not None."""
        from app.orchestration import render_events

        monkeypatch.setattr(render_events, "CHANNELS_DIR", tmp_path / "channels")
        monkeypatch.setattr(render_events, "LOGS_DIR", tmp_path / "logs")

        render_events._emit_render_event(
            channel_code="manual",
            job_id="test_job_ctx",
            event="test_event",
            level="INFO",
            message="context probe",
            step="test.step",
            context={"part_no": 1, "score": 73.5, "extra": "value"},
        )

        log_file = tmp_path / "channels" / "manual" / "logs" / "test_job_ctx.log"
        entry = json.loads(log_file.read_text(encoding="utf-8").strip())

        assert entry["context"] == {"part_no": 1, "score": 73.5, "extra": "value"}, (
            f"Contract #6: context kwarg must appear in entry['context'] verbatim. "
            f"Got {entry['context']!r}."
        )

    def test_log_entry_with_error_level_sets_error_code(self, tmp_path, monkeypatch):
        """When level is ERROR/CRITICAL/FATAL or event ends with '.error',
        the entry's error_code field auto-populates. This is the contract
        the WS handler uses to drive the failure UI."""
        from app.orchestration import render_events

        monkeypatch.setattr(render_events, "CHANNELS_DIR", tmp_path / "channels")
        monkeypatch.setattr(render_events, "LOGS_DIR", tmp_path / "logs")

        render_events._emit_render_event(
            channel_code="manual",
            job_id="test_job_err",
            event="render.failure",
            level="ERROR",
            message="something broke",
            step="render.encode",
            exception=RuntimeError("boom"),
        )

        log_file = tmp_path / "channels" / "manual" / "logs" / "test_job_err.log"
        entry = json.loads(log_file.read_text(encoding="utf-8").strip())

        # error_code is auto-computed by _render_error_code(step, message, exc).
        # Must be non-empty when level is ERROR.
        assert entry["error_code"] != "", (
            "Contract #6: ERROR-level events must auto-populate error_code. "
            "The WS failure UI keys off this field."
        )
        assert entry["exception"] == "boom"
        assert entry["level"] == "ERROR"
