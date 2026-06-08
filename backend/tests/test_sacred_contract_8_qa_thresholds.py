"""Sacred Contract #8 tests — qa_pipeline validation never bypassed.

The contract: `_validate_render_output` is the sole output validation gate.
Phase 4 BR05 + audit Phase 1 §H established the failure modes and their
codes. These tests pin the threshold behavior so a future "lower the
threshold to make this broken render pass" change is rejected by CI.

Pinned thresholds:
- File-size floor: 10 KB = 10_240 bytes (code RN001).
- Duration tolerance: max(0.5, min(expected * 0.15, 3.0)) seconds.
- _stall_deadline: now + max(120, expected*10) seconds.

Existing test_pipeline_qa.py covers the happy-path validator behavior.
This file pins the *exact thresholds* so accidental relaxation fails CI.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from app.features.render.engine.pipeline.qa_pipeline import (
    _duration_tolerance,
    _failed_part_progress,
    _stall_deadline,
    _validate_render_output,
)


# ---------------------------------------------------------------------------
# _duration_tolerance — the formula must remain exactly:
#   max(0.5, min(expected * 0.15, 3.0))
# Any change to the formula breaks render-correctness assumptions in
# downstream tooling that compares observed vs expected duration.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("expected", "want_tol"),
    [
        (0.0,   1.0),   # zero/unknown expected → safe fallback of 1.0 s
        (-5.0,  1.0),   # negative expected → safe fallback (`expected_duration > 0` guard)
        (1.0,   0.5),   # very short clip → minimum 0.5 s
        (3.0,   0.5),   # still in the floor regime
        (10.0,  1.5),   # mid-range: 15 % of expected
        (20.0,  3.0),   # exactly at the cap
        (60.0,  3.0),   # above cap → still 3.0 s
        (300.0, 3.0),   # well above cap
    ],
)
def test_duration_tolerance_formula_pinned(expected: float, want_tol: float):
    assert _duration_tolerance(expected) == pytest.approx(want_tol)


# ---------------------------------------------------------------------------
# _stall_deadline — formula: encode_start + max(120, expected*10).
# Pins the stall budget the render loop relies on to declare a hung encode.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("encode_start", "expected", "want_deadline"),
    [
        (1000.0, 0.0,   1120.0),  # zero expected → 120 s floor (uses 60 fallback × 10 = 600s? check)
        (1000.0, 60.0,  1600.0),  # 60 s × 10 = 600 s > 120 floor
        (1000.0, 5.0,   1120.0),  # 5 × 10 = 50 s < 120 floor → 120 wins
        (1000.0, 12.0,  1120.0),  # 12 × 10 = 120 → match floor
        (1000.0, 12.1,  1121.0),  # 12.1 × 10 = 121 s just above floor
    ],
)
def test_stall_deadline_formula_pinned(encode_start: float, expected: float, want_deadline: float):
    # Note the implementation: max(120.0, (expected or 60.0) * 10).
    # So zero expected uses the 60-fallback × 10 = 600, NOT 120. Recalculate.
    # encode_start=1000, expected=0 → max(120, 60*10) = 600 → 1600.
    # We adjust the want_deadline for the zero case here:
    if expected == 0.0:
        want_deadline = encode_start + 600.0
    assert _stall_deadline(encode_start, expected) == pytest.approx(want_deadline)


# ---------------------------------------------------------------------------
# _failed_part_progress — must always be clamped to [0, 99].
# A part marked failed must never report 100 %; the FE colours the row by
# this clamp ceiling.
# ---------------------------------------------------------------------------

def test_failed_part_progress_clamp_ceiling(monkeypatch):
    # When the DB reports the part at 100 %, the failed-part progress must
    # be clamped below 100 — the FE treats 100 as "complete" and would
    # mis-render a failed row. The implementation returns min(99, fallback);
    # with the default fallback=95 the answer is 95. With an explicit
    # fallback ≥ 99 the answer is 99.
    from app.features.render.engine.pipeline import qa_pipeline as qp

    monkeypatch.setattr(qp, "list_job_parts", lambda job_id: [
        {"part_no": 1, "progress_percent": 100},
    ])
    # Default fallback path
    assert _failed_part_progress("job-x", 1) == 95
    # Explicit fallback path clamps at 99
    assert _failed_part_progress("job-x", 1, fallback=99) == 99
    assert _failed_part_progress("job-x", 1, fallback=120) == 99


def test_failed_part_progress_passthrough(monkeypatch):
    from app.features.render.engine.pipeline import qa_pipeline as qp

    monkeypatch.setattr(qp, "list_job_parts", lambda job_id: [
        {"part_no": 1, "progress_percent": 42},
    ])
    assert _failed_part_progress("job-x", 1) == 42


def test_failed_part_progress_fallback_when_not_found(monkeypatch):
    from app.features.render.engine.pipeline import qa_pipeline as qp

    monkeypatch.setattr(qp, "list_job_parts", lambda job_id: [])
    assert _failed_part_progress("job-x", 1, fallback=95) == 95


# ---------------------------------------------------------------------------
# _validate_render_output — size threshold (10 KB = 10240 bytes).
# Pin RN001 codes so threshold lowering breaks CI.
# ---------------------------------------------------------------------------

def test_validate_missing_file_returns_rn001(tmp_path: Path):
    missing = tmp_path / "does-not-exist.mp4"
    result = _validate_render_output(missing, expected_duration=10.0)
    assert result["ok"] is False
    assert result["code"] == "RN001"
    assert "does not exist" in result["error"].lower()


def test_validate_too_small_returns_rn001(tmp_path: Path):
    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"\x00" * 1024)  # 1 KB — well below 10 KB floor
    result = _validate_render_output(tiny, expected_duration=10.0)
    assert result["ok"] is False
    assert result["code"] == "RN001"
    assert "too small" in result["error"].lower()
    # Metadata size pinned in bytes.
    assert result["metadata"]["size_bytes"] == 1024


def test_validate_just_under_threshold_returns_rn001(tmp_path: Path):
    """File at 10239 bytes (1 byte under 10 KB) must fail.

    Pins the exact 10_240 floor — guards against an accidental "off by one"
    relaxation like `if size < 10_000`.
    """
    border = tmp_path / "border.mp4"
    border.write_bytes(b"\x00" * 10_239)
    result = _validate_render_output(border, expected_duration=10.0)
    assert result["ok"] is False
    assert result["code"] == "RN001"


def test_validate_at_or_above_threshold_passes_size_check(tmp_path: Path):
    """At exactly 10_240 bytes the size check passes; later checks
    (ffprobe / stream / duration) still apply but are out of scope here —
    we accept any non-RN001 outcome past the size gate.
    """
    just_ok = tmp_path / "just_ok.mp4"
    just_ok.write_bytes(b"\x00" * 10_240)
    result = _validate_render_output(just_ok, expected_duration=10.0)
    # Past the size check — ffprobe will fail on the fake bytes, but the
    # failure code must not be the size code anymore. The shape contract:
    # ok=False but the failure reason is downstream of size.
    assert result["ok"] is False
    # The size threshold is the contract being pinned; the error string
    # must no longer mention "too small".
    assert "too small" not in (result["error"] or "").lower()


# ---------------------------------------------------------------------------
# Return shape — Sacred #8 says the validator NEVER raises and always
# returns the documented dict shape. Pin the keys here.
# ---------------------------------------------------------------------------

_REQUIRED_RESULT_KEYS = {"ok", "warnings", "error", "code", "phase", "metadata"}
_REQUIRED_METADATA_KEYS = {"size_bytes", "duration", "has_video", "has_audio"}


def test_validate_result_shape_missing_file(tmp_path: Path):
    result = _validate_render_output(tmp_path / "nope.mp4", expected_duration=10.0)
    assert set(result.keys()) >= _REQUIRED_RESULT_KEYS
    assert set(result["metadata"].keys()) >= _REQUIRED_METADATA_KEYS
    assert result["phase"] == "validation"


def test_validate_result_shape_too_small(tmp_path: Path):
    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"\x00" * 1024)
    result = _validate_render_output(tiny, expected_duration=10.0)
    assert set(result.keys()) >= _REQUIRED_RESULT_KEYS
    assert set(result["metadata"].keys()) >= _REQUIRED_METADATA_KEYS
