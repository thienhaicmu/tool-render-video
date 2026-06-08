"""T1.2 closure regression guard — Audit 2026-06-08 (Batch A V9-A1/V9-G1).

Sacred Contract #8 partial bypass on resume. Pre-T1.2 the resume-skip
predicate at part_renderer.py:172 used a single ``_resume_output_valid``
probe (ffprobe duration > 0 only). That missed 4 of the 5 hard QA
checks: size floor 10 KB, video-stream presence, duration tolerance vs
expected, audio-stream presence. A part that "completed" but was
truncated, video-streamless, or far off the expected duration could be
re-served as DONE on resume without ever passing the gate that fresh
renders go through.

T1.2 (commit 48a5173) replaced the single probe with the full
``_validate_render_output`` gate. This file guards that closure with
two complementary checks:

1. **Behavioural** — call ``_validate_render_output`` directly on a
   5 KB sentinel file and assert it rejects with the size-floor
   failure code. This pins the gate's actual contract.

2. **Structural** — AST/source verification that
   part_renderer.py's resume-skip block actually invokes
   ``_validate_render_output`` (not just ``_resume_output_valid``)
   AND has a fall-through log when the gate rejects. Without this
   wiring guard a future refactor could re-introduce the bypass.

(The AST pin for "the right call is present" is already in
test_resume_disk_vs_db_invariant.py::test_resume_skip_block_uses_all_three_disk_checks
after T1.2 — see that file's history for the 88→69 evolution. This
file's structural check adds the COMPLEMENTARY assertion that the
QA-fail FALL-THROUGH path exists too — the bypass would be just as
bad if QA were called but its ok=False result were ignored.)
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# 1. Behavioural — the gate actually rejects too-small files.
# ---------------------------------------------------------------------------


def test_validate_render_output_rejects_under_size_floor(tmp_path):
    """The 10 KB size floor (qa_pipeline.py:97) is the cheapest of the
    5 hard checks — a 5 KB sentinel file should fail there with
    code RN001.

    This is the gate T1.2 wired into the resume-skip path. If a future
    change lowers the floor (e.g., "to allow tiny test clips"), the
    Sacred Contract #8 surface erodes and resume-skip can serve broken
    outputs. This test makes that loud.
    """
    from app.features.render.engine.pipeline.qa_pipeline import (
        _validate_render_output,
    )

    # 5 KB of zeros — well under the 10_240 floor.
    too_small = tmp_path / "tiny.mp4"
    too_small.write_bytes(b"\x00" * 5_000)

    result = _validate_render_output(too_small, expected_duration=30.0)

    assert result["ok"] is False, (
        f"T1.2 / Sacred Contract #8 erosion — a 5 KB file should be "
        f"rejected by _validate_render_output but ok={result['ok']!r}."
    )
    assert result.get("code") == "RN001", (
        f"Expected error code RN001 (the catch-all 'render output bad' "
        f"code that the resume-skip block at part_renderer.py:172+ "
        f"logs to the operator), got code={result.get('code')!r}."
    )
    assert "too small" in (result.get("error") or "").lower(), (
        f"Error message should mention size, got: {result.get('error')!r}"
    )


def test_validate_render_output_accepts_resume_payload_shape(tmp_path):
    """When called with the SAME signature the part_renderer resume
    block uses (``expected_duration=`` + ``expect_audio=None``), the
    gate should produce a structured result dict with the keys the
    caller relies on: ``ok``, ``code``, ``error``, ``metadata``.

    Guards that a future refactor of _validate_render_output's return
    shape doesn't silently break the resume-skip path (which reads
    ``_resume_qa.get('ok')`` and ``_resume_qa.get('code')``).
    """
    from app.features.render.engine.pipeline.qa_pipeline import (
        _validate_render_output,
    )

    # 5 KB sentinel — will return ok=False, but the SHAPE of the dict
    # is what we assert on.
    tiny = tmp_path / "shape.mp4"
    tiny.write_bytes(b"\x00" * 5_000)

    result = _validate_render_output(
        tiny,
        expected_duration=30.0,
        expect_audio=None,  # T1.2 — same kwarg the resume path passes
    )

    # The caller at part_renderer.py:172+ uses these three keys.
    for key in ("ok", "code", "error", "metadata"):
        assert key in result, (
            f"T1.2 caller (part_renderer.py resume-skip block) relies on "
            f"key {key!r} in the _validate_render_output return dict; "
            f"got keys: {sorted(result.keys())}"
        )


# ---------------------------------------------------------------------------
# 2. Structural — wire-up survives in part_renderer.py
# ---------------------------------------------------------------------------


PART_RENDERER_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "features" / "render" / "engine" / "stages" / "part_renderer.py"
)


def test_resume_skip_block_branches_on_qa_ok_result():
    """T1.2 introduced a two-arm structure inside the resume-skip
    predicate: when ``_resume_qa.get('ok')`` is true, call
    ``mark_part_skipped_done`` (the legacy skip behaviour); otherwise
    log a warning and fall through to re-render. If a future change
    drops the fall-through branch (e.g. ``if _resume_qa.get('ok'):``
    becomes ``mark_part_skipped_done(...)`` unconditionally), the
    bypass returns — even though _validate_render_output is still
    called. This test pins the shape.
    """
    source = PART_RENDERER_PATH.read_text(encoding="utf-8-sig")

    # Necessary substrings that together prove the structure.
    must_have = [
        # T1.2 — the new full QA call lives in this file.
        "_validate_render_output(",
        # The skip arm gates on the qa result's ok key.
        "_resume_qa.get(\"ok\")",
        # The fall-through warning log mentions QA rejection — operators
        # rely on this to distinguish "resume did nothing" from a
        # re-render triggered by QA gate.
        "rejected by QA",
        # mark_part_skipped_done MUST stay reachable — only when
        # _resume_qa.get('ok') returns true.
        "mark_part_skipped_done",
    ]
    missing = [needle for needle in must_have if needle not in source]
    assert not missing, (
        "T1.2 closure breached — resume-skip block lost one of its "
        f"two-arm structure markers. Missing: {missing}. The resume "
        "path must (a) call _validate_render_output, (b) gate skip on "
        "ok, (c) log the QA rejection on the fall-through, (d) keep "
        "the legacy mark_part_skipped_done reachable on the OK arm."
    )


def test_resume_skip_uses_kwarg_expect_audio_none():
    """T1.2's call site passes ``expect_audio=None`` so the gate
    treats missing audio as a warning (not a hard failure). Resume
    can't reliably know if audio was originally required (voice_enabled
    may have changed between runs), so missing-audio surfaces as a
    warning, matching the fresh-render policy for legacy callers
    (qa_pipeline.py:165-178). A future change that flips this to
    ``expect_audio=True`` would cause silent-audio outputs to be
    re-rendered on every resume — a UX regression.
    """
    source = PART_RENDERER_PATH.read_text(encoding="utf-8-sig")

    # Cheapest source-level match: the kwarg literally appears.
    assert "expect_audio=None" in source, (
        "T1.2 invariant breached — resume-skip block no longer passes "
        "expect_audio=None to _validate_render_output. If the kwarg "
        "moved to True the gate would hard-fail any silent clip on "
        "resume; if it dropped entirely we can't reason about the "
        "expected behaviour. Inspect the resume-skip block at "
        f"{PART_RENDERER_PATH}."
    )


# ---------------------------------------------------------------------------
# 3. The QA helper is still imported (defense in depth).
# ---------------------------------------------------------------------------


def test_validate_render_output_imported_into_part_renderer():
    """Pin that ``_validate_render_output`` is imported alongside
    ``_resume_output_valid`` at the top of part_renderer.py. The
    existing test_resume_disk_vs_db_invariant.py pins that
    ``_resume_output_valid`` is imported; this test adds the
    complementary pin for T1.2's stronger gate."""
    source = PART_RENDERER_PATH.read_text(encoding="utf-8-sig")
    tree = ast.parse(source)
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)

    assert "_validate_render_output" in imported_names, (
        "T1.2 closure breached — _validate_render_output must be "
        "imported into part_renderer.py for the resume-skip block to "
        "use it. Verify the import line near the top of part_renderer.py."
    )
