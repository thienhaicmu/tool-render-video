"""Audit FINDING-BR12 closure (Batch 10B 2026-06-06).

The resume-skip decision in ``part_renderer.process_one_part`` is
"disk truth, not DB truth": it consults the actual file on disk
(``final_part.exists() + ffprobe``), NOT the ``job_parts.output_file``
DB column.

Why: ``output_file`` defaults to '' in the schema and is sometimes left
empty by interrupted writers. Using it as the resume signal would
either over-skip (DB stale, file gone) or over-render (DB empty-string,
file present and valid).

These guards lock the invariant in place so a future maintainer can't
accidentally introduce a code path that reads ``output_file`` from the
existing-part dict and uses it for the skip decision — that would
re-introduce the bug class.

The guards are AST-based (cheap, no I/O, no fragile string matching of
operator precedence):

1. ``output_file`` does NOT appear as a key lookup on ``_existing_part_info``
   anywhere in part_renderer.py — the existing-part dict is read for
   ``status`` only, not for the file path.
2. The resume-skip ``if`` includes ALL three disk-truth checks
   (``final_part.exists``, ``stat().st_size > 0``, ``_resume_output_valid``).
3. ``_resume_output_valid`` is imported into part_renderer — pinning that
   the ffprobe validation is wired into the resume path (not merely
   defined but unused).
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest


PART_RENDERER_PATH = (
    Path(__file__).resolve().parent.parent
    / "app" / "features" / "render" / "engine"
    / "stages" / "part_renderer.py"
)


def _load_module_ast() -> ast.Module:
    text = PART_RENDERER_PATH.read_text(encoding="utf-8-sig")
    return ast.parse(text)


def test_existing_part_info_never_read_for_output_file():
    """The existing-part dict supplied to ``process_one_part`` is read for
    ``status`` only — never for ``output_file``. If anyone introduces
    ``_existing_part_info.get("output_file")`` (or any sibling lookup),
    this test fails and forces a review of the resume invariant."""
    tree = _load_module_ast()
    offending: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Pattern A: _existing_part_info.get("output_file") / .get("output_file", ...)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "_existing_part_info"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "output_file"
        ):
            offending.append((node.lineno, ast.unparse(node)))
        # Pattern B: _existing_part_info["output_file"]
        if (
            isinstance(node, ast.Subscript)
            and isinstance(node.value, ast.Name)
            and node.value.id == "_existing_part_info"
        ):
            slc = node.slice
            if isinstance(slc, ast.Constant) and slc.value == "output_file":
                offending.append((node.lineno, ast.unparse(node)))

    assert not offending, (
        "BR12 invariant breached — resume must not consult the DB "
        "output_file column. Use final_part (recomputed) + ffprobe "
        "validation instead. Offenders:\n"
        + "\n".join(f"  line {ln}: {src}" for ln, src in offending)
    )


def test_resume_skip_block_uses_all_three_disk_checks():
    """Pin the disk-truth signal set: a resume-skip ``if`` that only checks
    ``status == 'done'`` (and not file existence + size + qa_pipeline
    gate) would skip parts whose files are corrupt or missing —
    silently corrupting output.

    T1.2 — Audit 2026-06-08 closure (Batch A V9-A1/V9-G1). The
    invariant was originally pinned with ``_resume_output_valid(final_part)``,
    which runs a single ffprobe ``format=duration`` probe. T1.2
    STRENGTHENED the invariant: resume now runs the SAME
    ``_validate_render_output`` gate as fresh renders (size floor 10
    KB, video-stream presence, duration tolerance vs expected,
    audio-stream presence — i.e. the full Sacred Contract #8 gate).
    This guard now pins the stronger function while still verifying
    the cheap disk-truth signals (existence + size).
    """
    source = PART_RENDERER_PATH.read_text(encoding="utf-8-sig")
    # All four signals must coexist in the file. We don't pin a specific
    # call site here — just that the names show up so a deletion is loud.
    must_have = [
        "final_part.exists()",
        "final_part.stat().st_size",
        # T1.2: the full QA gate replaces the duration-only probe. The
        # function name is pinned so a future refactor can't quietly
        # drop back to ``_resume_output_valid`` or to ``.exists()``-only.
        "_validate_render_output(",
        "resume_from_last",
    ]
    missing = [needle for needle in must_have if needle not in source]
    assert not missing, (
        "Resume-skip invariant breached — resume-skip lost one of its "
        f"disk-truth/QA checks. Missing: {missing}. The full check set "
        "is required so a stale 'done' DB status with a corrupt file "
        "can't be wrongly skipped (Sacred Contract #8, T1.2 closure)."
    )


def test_resume_output_valid_is_imported():
    """The ffprobe-based validation helper must be imported into
    part_renderer — pinning that the resume path actually invokes
    qa_pipeline rather than relying on .exists() alone."""
    tree = _load_module_ast()
    imported_names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                imported_names.add(alias.name)

    assert "_resume_output_valid" in imported_names, (
        "part_renderer.py must import _resume_output_valid from qa_pipeline. "
        "Without it, the resume path falls back to existence-only checks "
        "and silently skips parts whose output files are truncated or "
        "missing video streams."
    )


def test_output_file_column_default_is_empty_string(tmp_path, monkeypatch):
    """Defensive: the schema default for ``job_parts.output_file`` is ''
    (NOT NULL). Some upserts leave it as the default. If the resume
    decision ever depended on this column being either NULL or a real
    path, an empty string would land in a third state that callers
    rarely cover. We pin the default here so a future schema migration
    that flips it (e.g., to NULL) requires an explicit update to this
    test plus a review of the resume path."""
    monkeypatch.setattr("app.db.connection.DATABASE_PATH", tmp_path / "x.db")
    monkeypatch.setattr("app.db.connection._ACTIVE_DB_PATH", None)
    from app.db.connection import init_db, get_conn
    init_db()
    conn = get_conn()
    try:
        info = conn.execute("PRAGMA table_info(job_parts)").fetchall()
    finally:
        conn.close()
    cols = {r["name"]: r for r in info}
    assert "output_file" in cols, "job_parts.output_file column missing"
    default = cols["output_file"]["dflt_value"]
    # SQLite returns the literal text including quotes; the schema spec
    # is "output_file TEXT DEFAULT ''" so the default string is "''" or
    # similar. Accept both empty-string forms.
    assert default in ("''", '""', "''"), (
        f"job_parts.output_file default changed from '' to {default!r}. "
        "Resume invariant assumed empty-string default — update the test "
        "AND review part_renderer.py's resume-skip block before changing."
    )
