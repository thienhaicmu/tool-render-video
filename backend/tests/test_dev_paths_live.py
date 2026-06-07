"""Batch 10M cleanup regression guard (2026-06-06).

The dev-tools lookup tables (registry / autofix / qa_runner) used to
reference modules that were deleted during the Phase 1-18 backend
feature-layer migration + the Phase 4F.5A upload subsystem retirement
+ the Batch 9 ``services/db.py`` retirement + the Batch 10H
``routes/channels.py`` deletion. The references were "static string
data" — they didn't crash anything at runtime, but every category
pointing at the retired subsystem returned an empty file list.

Batch 10M cleaned every lookup so it points at the live tree. This
file pins the contract: every file path appearing in the lookup tables
MUST exist in the current repo. A future deletion of an actually-live
module will fail this test and force either:

  - update the test (legitimate move/rename), OR
  - update the dev-tools lookup to point at the new path.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


_REPO_ROOT = Path(__file__).resolve().parents[2]


def _existing(rel: str) -> bool:
    return (_REPO_ROOT / rel).exists()


# ---------------------------------------------------------------------------
# dev/registry.py
# ---------------------------------------------------------------------------


def test_registry_only_references_live_files():
    from app.services.dev.registry import _fix_feature_registry

    bad: list[tuple[str, str, str]] = []
    for domain, dom_spec in _fix_feature_registry().items():
        for feature, fs in dom_spec.get("features", {}).items():
            for f in fs.get("files", []):
                if not _existing(f):
                    bad.append((domain, feature, f))
    assert not bad, (
        "dev/registry.py points at non-existent files. Update the lookup or "
        "the test. Offenders:\n"
        + "\n".join(f"  {d}/{ft}: {p}" for d, ft, p in bad)
    )


# ---------------------------------------------------------------------------
# dev/autofix.py — five lookup tables + a few else-branches
# ---------------------------------------------------------------------------


def test_autofix_module_map_paths_live():
    from app.services.dev.autofix import _module_map

    for module_name in ("render_engine", "downloader", "channel_service",
                        "render", "main"):
        for f in _module_map(module_name):
            assert _existing(f), f"_module_map[{module_name}]: {f} missing"


def test_autofix_workflow_step_map_paths_live():
    from app.services.dev.autofix import _workflow_step_map

    for step in ("video.download", "video.render", "app.start"):
        for f in _workflow_step_map(step):
            assert _existing(f), f"_workflow_step_map[{step}]: {f} missing"


def test_autofix_event_map_paths_live():
    from app.services.dev.autofix import _event_map

    for event in ("video.download.start", "render.ffmpeg.start"):
        for f in _event_map(event):
            assert _existing(f), f"_event_map[{event}]: {f} missing"


def test_autofix_error_code_map_paths_live():
    from app.services.dev.autofix import _error_code_map

    # Iterate the keys defined in the function body so a future addition
    # is implicitly tested too.
    for fam in ("DL", "RN", "FS", "RT"):
        for f in _error_code_map(f"{fam}0001"):
            assert _existing(f), f"_error_code_map[{fam}]: {f} missing"


def test_autofix_context_map_paths_live():
    from app.services.dev.autofix import _context_map

    samples = [
        {}, {}, {},
    ]
    messages = ["path permission denied", "fetching url for video_id", ""]
    for ctx, msg in zip(samples, messages):
        for f in _context_map(ctx, msg):
            assert _existing(f), f"_context_map for msg={msg!r}: {f} missing"


def test_autofix_target_files_paths_live():
    from app.services.dev.autofix import _target_files

    for cat in ("download", "render", "file system", "startup/runtime"):
        # _target_files already pre-filters non-existent files via
        # PROJECT_ROOT / rel + p.exists(); a returned list must still
        # contain only existing files.
        for f in _target_files(cat):
            assert Path(f).exists(), f"_target_files[{cat}]: {f} missing"


def test_autofix_apply_upload_selector_wait_helper_removed():
    """The deleted helper must NOT come back without a deliberate review —
    it patched ``backend/app/services/upload_engine.py`` which no longer
    exists. Re-adding it without restoring the target file would crash
    silently in production."""
    import app.services.dev.autofix as autofix_mod

    assert not hasattr(autofix_mod, "_apply_upload_selector_wait_autofix"), (
        "_apply_upload_selector_wait_autofix re-appeared. It patches a "
        "deleted file (services/upload_engine.py). Restore the file first."
    )


# ---------------------------------------------------------------------------
# qa_runner.py
# ---------------------------------------------------------------------------


def test_qa_runner_default_patch_targets_paths_live():
    from app.services.qa_runner import _default_patch_targets

    # Iterate the named categories + the fallback.
    for cat in ("app_lifecycle", "video_pipeline", "logging", "completely-unknown"):
        for f in _default_patch_targets(cat):
            assert _existing(f), (
                f"qa_runner._default_patch_targets[{cat}]: {f} missing. "
                "Either update the mapping or move the test."
            )


# ---------------------------------------------------------------------------
# Source-grep — stale paths in code (not in comments/docstrings)
# ---------------------------------------------------------------------------


_DEAD_PATHS = (
    "backend/app/services/upload_engine.py",
    "backend/app/services/render_engine.py",
    "backend/app/services/downloader.py",
    "backend/app/services/scene_detector.py",
    "backend/app/services/segment_builder.py",
    "backend/app/services/db.py",
    "backend/app/routes/channels.py",
    "backend/app/routes/upload.py",
    "backend/app/routes/render.py",
)


def _scan_for_dead_paths(text: str) -> list[tuple[int, str, str]]:
    """Return list of (line_no, dead_path, line) for hits in CODE
    (skips Python comment + docstring contexts via a coarse heuristic)."""
    offenders: list[tuple[int, str, str]] = []
    in_doc = False
    for i, line in enumerate(text.splitlines(), start=1):
        stripped = line.lstrip()
        # Crude docstring tracking — both """ and ''' toggles.
        if stripped.startswith('"""') or stripped.startswith("'''"):
            ticks = stripped[:3]
            # Single-line docstring "" "" "" doesn't toggle state.
            rest = stripped[3:]
            if ticks not in rest:
                in_doc = not in_doc
            continue
        if in_doc:
            continue
        if stripped.startswith("#"):
            continue
        for dead in _DEAD_PATHS:
            if dead in line:
                offenders.append((i, dead, line.strip()))
    return offenders


@pytest.mark.parametrize(
    "rel_path",
    [
        "backend/app/services/dev/_shared.py",
        "backend/app/services/dev/log.py",
        "backend/app/services/dev/bug.py",
        "backend/app/services/dev/registry.py",
        "backend/app/services/dev/autofix.py",
        "backend/app/services/dev/router.py",
        "backend/app/services/qa_runner.py",
    ],
)
def test_no_dead_paths_in_code(rel_path):
    """No deleted-module path strings outside comments / docstrings.

    The presence of a deleted path inside a lookup return value means
    the helper will return an empty list for that category — silently
    useless. Catching it here means the cleanup is enforced.
    """
    text = (_REPO_ROOT / rel_path).read_text(encoding="utf-8-sig")
    offenders = _scan_for_dead_paths(text)
    assert not offenders, (
        f"{rel_path} contains references to deleted modules in code:\n"
        + "\n".join(f"  line {ln}: {dead}  ({src})" for ln, dead, src in offenders)
    )
