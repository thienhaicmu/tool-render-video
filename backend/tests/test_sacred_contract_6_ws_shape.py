"""Sacred Contract #6 tests — WebSocket event shape is frozen.

The contract: every progress event emitted by the WS handler at
GET /api/jobs/{id}/ws must conform to the top-level shape
    {"job": {...}, "parts": [...], "summary": {...}}

This shape is consumed by:
- frontend/src/websocket/RenderSocketClient.ts (RenderSocketClient.onmessage)
- frontend/src/hooks/useRenderSocket.ts (state mutations)
- per-Phase 2 audit, the FE state model assumes exactly these three keys.

Breaking the shape silently corrupts every connected UI client. These tests
guard the contract at two levels: the static source of the WS handler, and
the runtime shape of `_compute_progress_summary` which feeds the summary
slot of every emitted frame.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.routes.jobs import _compute_progress_summary


# ---------------------------------------------------------------------------
# Static check on the WS handler source — every send_json that emits a
# progress frame must use the exact key set {job, parts, summary}.
# ---------------------------------------------------------------------------

_PROGRESS_KEY_SET = {"job", "parts", "summary"}
_ALLOWED_NON_PROGRESS_KEY_SETS = (
    {"type"},          # ping keepalive
    {"error"},         # not_found short-circuit
    {"type", "event"}, # T3.1 — event message bridged from EVENT_BROADCASTER
)
# T3.1 — Audit 2026-06-08 closure (Batch A V8-C1). The snapshot
# message added a ``type="snapshot"`` discriminator alongside the
# canonical {job, parts, summary} keys, so the wire shape is
# {job, parts, summary, type}. Sacred Contract #6 freezes the
# REQUIRED keys ({job, parts, summary}) and EXPLICITLY allows
# additions ("Additions are allowed; removals never are" — see
# CLAUDE.md Frozen API Contracts §"Backward Compatibility Protocol").
# The keys the contract guards are PRESENT; ``type`` is additive.
_PROGRESS_OPTIONAL_KEYS = {"type"}


def _routes_jobs_path() -> Path:
    return Path(__file__).resolve().parent.parent / "app" / "routes" / "jobs.py"


def _send_json_call_keysets() -> list[set[str]]:
    """Parse routes/jobs.py and collect every literal dict passed to send_json."""
    src = _routes_jobs_path().read_text(encoding="utf-8")
    tree = ast.parse(src)
    keysets: list[set[str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match `<anything>.send_json(<dict literal>)`
        if not isinstance(func, ast.Attribute) or func.attr != "send_json":
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if not isinstance(arg, ast.Dict):
            continue
        keys: set[str] = set()
        for k in arg.keys:
            if isinstance(k, ast.Constant) and isinstance(k.value, str):
                keys.add(k.value)
        if keys:
            keysets.append(keys)
    return keysets


def test_ws_handler_uses_only_known_keysets():
    keysets = _send_json_call_keysets()
    assert keysets, "no send_json calls found in routes/jobs.py — test traversal broken"

    for keys in keysets:
        # T3.1: a progress frame is any send_json whose key set is a
        # SUPERSET of the Sacred Contract #6 required keys
        # {job, parts, summary}, with only the documented optional
        # extras (currently just ``type``).
        is_progress = (
            _PROGRESS_KEY_SET.issubset(keys)
            and (keys - _PROGRESS_KEY_SET).issubset(_PROGRESS_OPTIONAL_KEYS)
        )
        is_known_other = any(keys == allowed for allowed in _ALLOWED_NON_PROGRESS_KEY_SETS)
        assert is_progress or is_known_other, (
            f"unknown send_json shape: {sorted(keys)}. "
            f"Sacred Contract #6 requires progress frames carry "
            f"{{job, parts, summary}} (additions allowed — currently "
            f"only 'type' is documented). "
            f"Allowed non-progress shapes: ping / error / "
            f"T3.1 event {{type, event}}."
        )


def test_ws_handler_emits_at_least_one_progress_frame_shape():
    """Among all send_json calls, at least one must carry the
    canonical {job, parts, summary} keys (subset check — additional
    keys like ``type`` are allowed)."""
    keysets = _send_json_call_keysets()
    has_progress = any(_PROGRESS_KEY_SET.issubset(k) for k in keysets)
    assert has_progress, (
        "no send_json call carrying {job, parts, summary} found in "
        "routes/jobs.py — Sacred Contract #6 cannot be honoured."
    )


# ---------------------------------------------------------------------------
# Runtime check on _compute_progress_summary — guarantees the summary slot
# always carries the keys the FE reads.
# ---------------------------------------------------------------------------

_REQUIRED_SUMMARY_KEYS = {
    "total_parts",
    "completed_parts",
    "failed_parts",
    "pending_parts",
    "processing_parts",
    "active_parts",
    "stuck_parts",
    "overall_progress_percent",
    "parts_percent",  # backward-compat alias kept by contract
}


def test_summary_empty_parts_has_required_keys():
    summary = _compute_progress_summary([])
    missing = _REQUIRED_SUMMARY_KEYS - set(summary.keys())
    assert not missing, f"summary missing keys when parts=[]: {sorted(missing)}"


def test_summary_normal_parts_has_required_keys():
    parts = [
        {"part_no": 1, "status": "done",       "progress_percent": 100, "updated_at": ""},
        {"part_no": 2, "status": "rendering",  "progress_percent": 50,  "updated_at": ""},
        {"part_no": 3, "status": "failed",     "progress_percent": 99,  "updated_at": ""},
        {"part_no": 4, "status": "waiting",    "progress_percent": 0,   "updated_at": ""},
    ]
    summary = _compute_progress_summary(parts)
    missing = _REQUIRED_SUMMARY_KEYS - set(summary.keys())
    assert not missing, f"summary missing keys: {sorted(missing)}"


def test_summary_counts_consistent():
    # Per routes/jobs.py:24 _ACTIVE_STATUSES contains
    # {waiting, cutting, transcribing, rendering, downloading}. Use an unknown
    # status to land in the "pending" bucket cleanly.
    parts = [
        {"part_no": 1, "status": "done",       "progress_percent": 100, "updated_at": ""},
        {"part_no": 2, "status": "rendering",  "progress_percent": 50,  "updated_at": ""},
        {"part_no": 3, "status": "failed",     "progress_percent": 99,  "updated_at": ""},
        {"part_no": 4, "status": "queued",     "progress_percent": 0,   "updated_at": ""},
    ]
    summary = _compute_progress_summary(parts)
    assert summary["total_parts"] == 4
    assert summary["completed_parts"] == 1
    assert summary["failed_parts"] == 1
    assert summary["processing_parts"] == 1  # only "rendering" is in _ACTIVE_STATUSES
    assert summary["pending_parts"] == 1     # "queued" is neither active nor terminal
    assert summary["overall_progress_percent"] == pytest.approx((100 + 50 + 99 + 0) / 4, rel=0.01)
    # parts_percent is the backward-compat alias and must equal overall_progress_percent
    assert summary["parts_percent"] == summary["overall_progress_percent"]


def test_summary_active_parts_shape():
    """active_parts entries must carry the FE-required fields."""
    parts = [
        {"part_no": 1, "status": "rendering", "progress_percent": 42, "updated_at": ""},
    ]
    summary = _compute_progress_summary(parts)
    assert len(summary["active_parts"]) == 1
    entry = summary["active_parts"][0]
    assert entry == {"part_no": 1, "status": "rendering", "progress_percent": 42}
